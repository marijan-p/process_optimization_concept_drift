"""Modell-Adaption an Concept Drift fuer zeitdiskrete Datenstroeme.

Universell importierbares Modul, analog zu ``drift_detection.py``. Buendelt die
in der Masterarbeit (Muehlen-Anwendungsfall, Module ``adaptation.py`` /
``updater.py`` / ``improved_adaptation_training.py``) entwickelten
Adaptionsstrategien in einer von externen Abhaengigkeiten (gpai/protocols)
befreiten Form. Kern ist das inkrementelle Nachtraining (:func:`incremental_fit`)
eines Keras-Modells sowie eine chunk-weise Online-Adaptionsschleife
(:func:`run_adaptation`) mit vier Strategien:

  * ``baseline`` – statisches Modell ohne Adaption (Referenz)
  * ``blind``    – fehlerschwellen-getriggertes Nachtraining auf gleitendem Fenster
  * ``informed`` – detektor-getriggertes Nachtraining um die Detektion herum
  * ``combined`` – Kombination aus blind und informed

Das Modul ist bewusst datensatz-agnostisch: ``run_adaptation`` arbeitet auf
beliebigen Feature-/Label-Arrays ``(X, y)`` und einem beliebigen kompilierten
Keras-Modell und laesst sich damit auch auf weitere Szenarien (z. B. den
Tennessee-Eastman-Process) anwenden.

Die Drift-Detektion fuer die informierte Adaption wird ueber :class:`StreamingDetector`
an ``drift_detection.py`` angebunden. Mit :func:`tune_adaptation` lassen sich die
Adaptions-Hyperparameter analog zu ``drift_detection.tune_detector`` mit Optuna
optimieren.

Beispiel
--------
>>> from drift_adaptation import run_adaptation, StreamingDetector
>>> det = StreamingDetector("EDDM", err_threshold=3.0)
>>> res = run_adaptation(base_model, X, y, mode="informed", detector=det,
...                      norm_mean=mu, norm_std=sigma)
>>> res["errors"]            # Praediktionsfehler waehrend der Adaption

Voraussetzung: ``tensorflow``/``keras`` (lazy importiert) sowie ``frouros``
(ueber ``drift_detection``); fuer das Tuning zusaetzlich ``optuna``.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np

import drift_detection as dd

__all__ = [
    "ADAPTATION_MODES",
    "FREEZE_CHOICES",
    "clone_compiled",
    "reset_optimizer",
    "reinit_layer",
    "incremental_fit",
    "StreamingDetector",
    "run_adaptation",
    "score_adaptation",
    "tune_adaptation",
    "decode_adapt_params",
]

# Unterstuetzte Adaptionsstrategien (Reihenfolge wie in der Auswertung).
ADAPTATION_MODES = ("baseline", "blind", "informed", "combined")


# ===========================================================================
# Inkrementelles Nachtraining (verdichtet aus adaptation.py /
# model_adaptation.utils.incremental_training der Masterarbeit)
# ===========================================================================
def clone_compiled(model, lr=1e-3, freeze=None):
    """Tiefe Kopie des Basismodells (gleiche Architektur + Gewichte, frischer Adam).

    lr/freeze werden – falls gesetzt – direkt beim einmaligen compile angewandt.
    Da Lernrate und Freeze-Muster innerhalb eines Adaptionslaufs konstant sind,
    entfaellt damit das wiederholte Neukompilieren je Nachtraining.
    """
    import tensorflow as tf
    m = tf.keras.models.clone_model(model)
    m.set_weights(model.get_weights())
    if freeze is not None:
        for layer, f in zip(m.layers, freeze):
            layer.trainable = not f
    m.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr), loss="mse")
    return m


def reset_optimizer(optimizer):
    """Setzt Slot-Variablen (Adam-Momente, iterations) auf Null zurueck, OHNE die
    Lernrate anzutasten.

    Repliziert die bisherige Semantik eines frischen Optimierers je Nachtraining,
    ohne das Modell neu zu kompilieren (kein Graph-Retracing). Vor dem ersten
    fit existieren noch keine Slot-Variablen -> No-op.

    WICHTIG: In Keras 3 ist die Lernrate selbst eine getrackte Optimizer-Variable
    und Teil von ``optimizer.variables``. Sie darf NICHT genullt werden, sonst
    faellt die effektive Lernrate auf 0 und jedes Nachtraining bleibt wirkungslos.
    """
    import tensorflow as tf
    lr_var = getattr(optimizer, "_learning_rate", None)
    variables = getattr(optimizer, "variables", [])
    variables = variables() if callable(variables) else variables
    for v in variables:
        if v is lr_var or "learning_rate" in getattr(v, "name", ""):
            continue
        v.assign(tf.zeros_like(v))


def reinit_layer(layer, seed=None):
    """Setzt Kernel (GlorotUniform) und Bias (Zeros) einer Dense-Schicht zurueck."""
    import tensorflow as tf
    w = layer.get_weights()
    if len(w) < 2:
        return
    k = tf.keras.initializers.GlorotUniform(seed=seed)(shape=w[0].shape).numpy()
    b = tf.keras.initializers.Zeros()(shape=w[1].shape).numpy()
    layer.set_weights([k, b])


def incremental_fit(model, X, y, epochs, freeze=None, reset=False, seed=None,
                    reset_opt=True):
    """Inkrementelles Nachtraining auf (X, y).

    Setzt voraus, dass ``model`` bereits mit der gewuenschten Lernrate und dem
    gewuenschten Freeze-Muster kompiliert ist (vgl. :func:`clone_compiled`).
    Dadurch entfaellt das wiederholte Neukompilieren (Graph-Retracing) je Aufruf.

    freeze     : nur fuer ``reset`` benoetigt (welche Schichten reinitialisiert
                 werden); ``None`` -> keine Reinitialisierung.
    reset      : nicht eingefrorene Schichten vor dem Training reinitialisieren.
    seed       : Seed fuer die Reinitialisierung (nur bei reset wirksam).
    reset_opt  : Optimierer-Zustand (Adam-Momente) vor dem Training nullen, um
                 die Semantik eines frischen Optimierers je Fenster zu erhalten.
    """
    from keras.callbacks import EarlyStopping
    if len(X) == 0:
        return model
    if reset and freeze is not None:
        for layer, f in zip(model.layers, freeze):
            if not f:
                reinit_layer(layer, seed=seed)
    if reset_opt:
        reset_optimizer(model.optimizer)
    es = EarlyStopping(monitor="loss", patience=max(1, epochs // 5),
                       min_delta=1e-6, restore_best_weights=True, verbose=0)
    model.fit(X, y, epochs=epochs, batch_size=32, verbose=0, callbacks=[es])
    return model


# ===========================================================================
# Drift-Detektor-Huelle fuer die informierte Adaption (Anbindung an
# drift_detection.py)
# ===========================================================================
class StreamingDetector:
    """Duenne Huelle um die frouros-Detektoren fuer punktweises Einspeisen.

    KSWIN/ADWIN erhalten den Betrag |e|, DDM/EDDM ein binarisiertes Signal
    |e| > err_threshold (vgl. drift_detection.run_detector / Masterarbeit
    Abschn. 4.4.1). Liefert pro update() True, falls ein Drift erkannt wurde.
    """

    def __init__(self, name, err_threshold=3.0, **overrides):
        self.name = name.upper()
        self.err_threshold = err_threshold
        self.is_rate = self.name in dd.ERROR_RATE_DETECTORS
        self._overrides = overrides
        self.detector = dd.build_detector(self.name, **overrides)

    def reset(self):
        self.detector = dd.build_detector(self.name, **self._overrides)

    def update(self, e):
        value = float(abs(e) > self.err_threshold) if self.is_rate else abs(float(e))
        self.detector.update(value=value)
        if self.detector.status["drift"]:
            self.detector.reset()
            return True
        return False


# ===========================================================================
# Chunk-weise Online-Adaptionsschleife (approximiert das punktweise Schema
# aus updater.ContinousUpdater bei praktikabler Laufzeit)
# ===========================================================================
def run_adaptation(base, X, y, *, mode, detector=None,
                   lr=3e-3, epochs=9, freeze=(True, False, False), reset=False,
                   error_window=44, error_threshold=1.5, cooldown=0,
                   window_prev=300, window_post=300,
                   chunk=144, norm_mean=0.0, norm_std=1.0, seed=None, verbose=False):
    """Chunk-weises Online-Adaptionsschema auf dem drift-behafteten Strom.

    mode : {"baseline", "blind", "informed", "combined"}.

    Ablauf je Chunk [i, j):
      1. Batch-Praediktion mit dem aktuellen Modell -> Praediktionen/Fehler.
      2. (informed/combined) normierten Fehler punktweise dem Detektor zufuehren;
         bei Detektion auf dem Fenster [t-window_prev, t+window_post] nachtrainieren.
      3. (blind/combined) ueberschreitet die rollende RMSE der letzten
         error_window Punkte die Schwelle, auf diesem Fenster nachtrainieren.
         Mit cooldown>0 wird zwischen zwei blinden Nachtrainings ein Mindest-
         abstand (Refraktaerzeit, analog drift_detection.run_detector) erzwungen;
         detektor-getriggerte (informierte) Nachtrainings bleiben unberuehrt.

    Die Normierung (norm_mean/std, Baseline drift-frei) dient sowohl der
    Detektor-Eingabe als auch spaeter der Darstellung, konsistent zu den
    Modell-/Detektions-Notebooks.

    Returns dict: preds, errors (roh), errors_norm, train_steps, detect_steps.
    """
    n = len(X)
    # Einmaliges Kompilieren mit Lernrate + Freeze-Muster (konstant je Lauf) ->
    # die Nachtrainings unten loesen kein Graph-Retracing mehr aus.
    model = clone_compiled(base, lr=lr, freeze=freeze)
    preds = np.empty(n, np.float32)
    train_steps, detect_steps = [], []
    last_blind = -(10 ** 18)   # Refraktaerzeit-Tracker: letzte blinde Adaption
    if detector is not None:
        detector.reset()

    i = 0
    while i < n:
        j = min(i + chunk, n)
        # 1) Guenstige Batch-Praediktion des Chunks (direkter Modellaufruf statt
        #    model.predict() -> deutlich weniger Overhead bei vielen Aufrufen)
        p = np.asarray(model(X[i:j], training=False)).ravel()
        preds[i:j] = p
        err = y[i:j] - p
        err_norm = (err - norm_mean) / norm_std

        train_windows = []

        # 2) Informed: Detektion auf dem normierten Fehler
        if mode in ("informed", "combined") and detector is not None:
            for t in range(len(err_norm)):
                if detector.update(err_norm[t]):
                    g = i + t
                    detect_steps.append(int(g))
                    a = max(0, g - window_prev)
                    b = min(n, g + window_post)
                    train_windows.append((a, b))
                    last_blind = j

        # 3) Blind: rollende RMSE des Chunk-Endes (cooldown = Mindestabstand
        #    zwischen zwei blinden Adaptionen; 0 = aus -> Verhalten wie getunt)
        if mode in ("blind", "combined"):
            tail = err_norm[-error_window:]
            if (len(tail) and np.sqrt(np.mean(tail ** 2)) >= error_threshold
                    and (j - last_blind) > cooldown
                    and not train_windows):
                a = max(0, j - error_window)
                train_windows.append((a, j))
                last_blind = j

        # 4) Inkrementelles Nachtraining auf den gesammelten Fenstern
        for (a, b) in train_windows:
            model = incremental_fit(model, X[a:b], y[a:b], epochs=epochs,
                                    freeze=list(freeze), reset=reset, seed=seed)
            train_steps.append(int(b))

        if verbose and (i // chunk) % 50 == 0:
            print(f"  {mode}: {j}/{n} Punkte, {len(train_steps)} Nachtrainings")
        i = j

    errors = y - preds
    errors_norm = (errors - norm_mean) / norm_std
    return dict(preds=preds, errors=errors, errors_norm=errors_norm,
                train_steps=train_steps, detect_steps=detect_steps)


# ===========================================================================
# Hyperparameter-Tuning der Adaption (analog zu drift_detection.tune_detector)
# ===========================================================================
# Im Gegensatz zur Detektion ist hier jeder Trial teuer, da run_adaptation das
# Modell wiederholt nachtrainiert. Daher wird typischerweise auf einem groeber
# downgesampelten Strom (kuerzere Laufzeit) mit wenigen Trials getunt und die
# beste Konfiguration anschliessend auf voller Aufloesung gegengeprueft. Anders
# als bei der Detektion wird keine Drift-Ground-Truth benoetigt: Da die gemessene
# Systemantwort als Label vorliegt, ist der RMSE direkt verfuegbar.

# Freeze-Muster werden als String kodiert (Optuna-Categoricals erlauben nur
# einfache Typen), Mapping auf die Bool-Tupel fuer run_adaptation:
FREEZE_CHOICES = {
    "TTF": (True, True, False),
    "TFF": (True, False, False),
    "FFF": (False, False, False),
}


def decode_adapt_params(params: dict) -> dict:
    """Dekodiert Optuna-best_params fuer run_adaptation (Freeze-String -> Tupel)."""
    p = dict(params)
    if isinstance(p.get("freeze"), str):
        p["freeze"] = FREEZE_CHOICES[p["freeze"]]
    return p


def score_adaptation(res: dict, rmse_baseline: float, n_units: int,
                     weights: Tuple[float, float] = (1.0, 0.1)) -> Dict[str, float]:
    """Bewertet einen Adaptionslauf: RMSE plus Strafterm fuer Eingriffe.

    score = w_rmse * (RMSE / RMSE_baseline) + w_train * (n_train / n_units),
    wobei n_units die Zahl der Chunks (max. moegliche blinde Nachtrainings) ist.
    Kleiner = besser. Spiegelt die gewichtete Zielfunktion der Detektion wider.
    """
    w_rmse, w_train = weights
    e = np.asarray(res["errors"], float)
    rmse = float(np.sqrt(np.mean(e ** 2)))
    rmse_norm = rmse / rmse_baseline if rmse_baseline else rmse
    n_train = len(res["train_steps"])
    train_norm = n_train / max(1, n_units)
    score = w_rmse * rmse_norm + w_train * train_norm
    return dict(rmse=rmse, rmse_norm=rmse_norm, n_train=int(n_train),
                n_detect=int(len(res["detect_steps"])), train_norm=train_norm,
                score=float(score))


def _suggest_adapt_params(strategy: str, trial) -> dict:
    """Optuna-Suchraum je Strategie. Nur strategie-relevante Parameter werden
    vorgeschlagen (Fenster-/Schwellenparameter nur dort, wo sie wirken)."""
    strategy = strategy.lower()
    params = dict(
        lr=trial.suggest_float("lr", 1e-4, 1.5e-2, log=True),
        epochs=trial.suggest_int("epochs", 1, 20),
        freeze=FREEZE_CHOICES[trial.suggest_categorical("freeze", list(FREEZE_CHOICES))],
        reset=trial.suggest_categorical("reset", [False, True]),
    )
    if strategy in ("blind", "combined"):
        params["error_window"] = trial.suggest_int("error_window", 15, 100)
        params["error_threshold"] = trial.suggest_float("error_threshold", 0.0, 3.0)
    if strategy in ("informed", "combined"):
        params["window_prev"] = trial.suggest_int("window_prev", 5, 100)
        params["window_post"] = trial.suggest_int("window_post", 5, 100)
    return params


def tune_adaptation(strategy: str, base, X, y, *, fixed: dict,
                    detector_factory=None, rmse_baseline: float = None,
                    n_trials: int = 20, weights: Tuple[float, float] = (1.0, 0.1),
                    seed: int = 42, show_progress_bar: bool = False, enqueue=None):
    """Optimiert die Adaptions-Hyperparameter einer Strategie mit Optuna (TPE).

    Parameters
    ----------
    strategy : {"blind", "informed", "combined"} (``baseline`` hat nichts zu tunen).
    base : kompiliertes Keras-Basismodell (wird je Trial geklont).
    X, y : Feature-/Label-Arrays des (ggf. downgesampelten) Tuning-Stroms.
    fixed : nicht getunte Argumente fuer run_adaptation
        (z. B. ``chunk``, ``norm_mean``, ``norm_std``, ``seed``).
    detector_factory : Callable -> StreamingDetector (fuer informed/combined),
        liefert pro Trial einen frischen Detektor.
    rmse_baseline : RMSE ohne Adaption; falls None, wird er einmal bestimmt.
    weights : (w_rmse, w_train) der Zielfunktion :func:`score_adaptation`.

    Returns
    -------
    (study, rmse_baseline) : Optuna-Study (beste Parameter in ``study.best_params``,
    via :func:`decode_adapt_params` dekodierbar) und der verwendete Baseline-RMSE.
    """
    import optuna   # lazy: Modul bleibt ohne Optuna importierbar

    strategy = strategy.lower()
    n = len(X)
    chunk = int(fixed.get("chunk", 144))
    n_units = int(np.ceil(n / chunk))

    if rmse_baseline is None:
        base_res = run_adaptation(base, X, y, mode="baseline", **fixed)
        rmse_baseline = float(np.sqrt(np.mean(np.asarray(base_res["errors"], float) ** 2)))

    def objective(trial):
        params = _suggest_adapt_params(strategy, trial)
        detector = (detector_factory()
                    if (strategy in ("informed", "combined") and detector_factory is not None)
                    else None)
        res = run_adaptation(base, X, y, mode=strategy, detector=detector,
                             **{**fixed, **params})
        s = score_adaptation(res, rmse_baseline, n_units, weights=weights)
        for k, v in s.items():
            trial.set_user_attr(k, v)
        return s["score"]

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    for _p in (enqueue or []):
        study.enqueue_trial(_p)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=show_progress_bar)
    return study, rmse_baseline
