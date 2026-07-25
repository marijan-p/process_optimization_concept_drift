"""Modell-Adaption an Concept Drift fuer zeitdiskrete Datenstroeme.

Universell importierbares Modul, analog zu ``drift_detection.py``. Buendelt die
in der Masterarbeit (Muehlen-Anwendungsfall, Module ``adaptation.py`` /
``updater.py`` / ``improved_adaptation_training.py``) entwickelten
Adaptionsstrategien in einer von externen Abhaengigkeiten (gpai/protocols)
befreiten Form. Kern ist das inkrementelle Nachtraining (:func:`incremental_fit`)
eines Keras-Modells sowie eine chunk-weise, prequentielle Online-Adaptions-
schleife (:func:`run_adaptation`) mit vier Strategien:

  * ``baseline`` – statisches Modell ohne Adaption (Referenz)
  * ``blind``    – passive Adaption i. S. v. Gama et al. (2014, Abschn. 3.3.2):
                   rein periodisches Nachtraining auf einem gleitenden Fenster
                   der letzten ``blind_window`` Punkte, ohne jede Auswertung des
                   Fehlers und ohne Detektor
  * ``informed`` – detektor-getriggertes Nachtraining: Sofort-Training auf dem
                   Vergangenheitsfenster, danach fortlaufende Follow-ups waehrend
                   einer Nachfuehrphase (kausal, analog dem punktweisen Schema
                   des Muehlen-Anwendungsfalls). Der Trigger kann ein
                   statistischer Detektor (KSWIN/ADWIN/DDM/EDDM) oder der
                   Schwellwert-Detektor ``RMSE`` sein.
  * ``combined`` – informed plus die passive Komponente als Backstop fuer
                   verpasste Detektionen

Das Modul ist bewusst datensatz-agnostisch: ``run_adaptation`` arbeitet auf
beliebigen Feature-/Label-Arrays ``(X, y)`` und einem beliebigen kompilierten
Keras-Modell und laesst sich damit auch auf weitere Szenarien (z. B. den
Tennessee-Eastman-Process) anwenden.

Die Drift-Detektion fuer die informierte Adaption wird ueber :class:`StreamingDetector`
an ``drift_detection.py`` angebunden. Mit :func:`tune_adaptation` lassen sich die
Adaptions-Hyperparameter analog zu ``drift_detection.tune_detector`` mit Optuna
optimieren (inkl. Warmstart via ``enqueue``); :func:`crosscheck_candidates`
prueft die besten Konfigurationen anschliessend auf dem voll aufgeloesten Strom.

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
    "SCALE_KEYS",
    "clone_compiled",
    "reset_optimizer",
    "reinit_layer",
    "incremental_fit",
    "StreamingDetector",
    "run_adaptation",
    "score_adaptation",
    "tune_adaptation",
    "decode_adapt_params",
    "encode_adapt_params",
    "scale_adapt_params",
    "apply_det_params",
    "estimate_cooldown",
    "crosscheck_candidates",
    "resolve_cooldown",
]

# Unterstuetzte Adaptionsstrategien (Reihenfolge wie in der Auswertung).
ADAPTATION_MODES = ("baseline", "blind", "informed", "combined")

# Zaehlparameter, die bei einem Wechsel der Abtastrate mitskaliert werden muessen.
SCALE_KEYS = ("window_prev", "window_post", "blind_window", "blind_period",
              "det_window", "det_min_num_instances", "det_num_test_instances",
              "det_min_window_size", "det_min_num_misclassified_instances")


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
# Chunk-weise, prequentielle Online-Adaptionsschleife (kausale Umsetzung des
# punktweisen Schemas aus updater.ContinousUpdater / adaptation_base bei
# praktikabler Laufzeit)
# ===========================================================================
def run_adaptation(base, X, y, *, mode, detector=None,
                   lr=3e-3, epochs=9, freeze=(True, False, False), reset=False,
                   cooldown=0, blind_window=44, blind_period=None,
                   window_prev=300, window_post=300, reject=False,
                   chunk=144, norm_mean=0.0, norm_std=1.0, seed=None, verbose=False):
    """Chunk-weises, prequentielles Online-Adaptionsschema (test-then-train).

    mode : {"baseline", "blind", "informed", "combined"}.

    Jeder Punkt wird praediziert, BEVOR er in ein Nachtraining einfliesst;
    Trainingsfenster reichen nie ueber das Chunk-Ende hinaus (kausal, keine
    Zukunftsdaten). Damit ist das Schema konsistent zum punktweisen Ablauf des
    Muehlen-Anwendungsfalls (``updater.ContinousUpdater`` bzw.
    ``adaptation_base.run_adaptation`` mit ``data_selector_sequence``).

    Ablauf je Chunk [i, j):
      1. Batch-Praediktion mit dem aktuellen Modell -> Praediktionen/Fehler.
      2. (informed/combined) normierten Fehler punktweise dem Detektor zufuehren.
         Bei Detektion zum globalen Schritt g: Sofort-Training auf dem
         Vergangenheitsfenster [g - window_prev, g] und Start einer
         Nachfuehrphase bis g + window_post. Innerhalb der Nachfuehrphase wird
         am Ende jedes Chunks ohne neue Detektion auf den soeben praedizierten
         Punkten des Chunks nachtrainiert (chunk-granulare Follow-ups, analog
         ``data_selector_sequence.train_scheduler`` alle batch_size Punkte).
         Detektionen innerhalb einer laufenden Phase verlaengern diese nur.
         ``cooldown`` erzwingt zusaetzlich einen Mindestabstand zwischen zwei
         Sofort-Trainings (Refraktaerzeit, aus der mittleren Dauer stationaerer
         Phasen abgeleitet; 0 = aus). ``window_post`` wirkt bereits als weiche
         Refraktaerzeit, ``cooldown`` legt eine davon unabhaengige, physikalisch
         begruendete Untergrenze darunter.
      3. (blind/combined) rein periodisches Nachtraining: alle ``blind_period``
         Punkte wird auf den letzten ``blind_window`` Punkten nachtrainiert. Der
         Fehler geht dabei NICHT ein - das ist die blinde Adaption nach Gama
         et al. (2014), proaktiv statt reaktiv. Die Termine werden auf
         Chunk-Enden quantisiert, sinnvoll ist daher blind_period >= chunk;
         ``blind_period=None`` -> jeder Chunk. In der kombinierten Strategie
         wirkt die Komponente als Backstop: der Zeitplan laeuft unabhaengig
         weiter, ein Termin faellt aber aus, wenn im selben Chunk bereits
         detektor-getriggert trainiert wurde.

    reject : Update-Validierung analog zur ``reject_mse``-Pruefung des
        Muehlen-Anwendungsfalls (updater.SimpleUpdater): Sinkt der MSE auf dem
        Trainingsfenster durch das Nachtraining nicht, wird das Update
        verworfen und der vorherige Gewichtsstand wiederhergestellt. Begrenzt
        Fehler-Ausreisser durch schaedliche Updates auf lokalen Fenstern.

    Die Normierung (norm_mean/std, Baseline drift-frei) dient sowohl der
    Detektor-Eingabe als auch spaeter der Darstellung, konsistent zu den
    Modell-/Detektions-Notebooks.

    Returns dict: preds, errors (roh), errors_norm, train_steps, detect_steps,
    reject_steps (verworfene Nachtrainings; Teilmenge von train_steps).
    """
    n = len(X)
    # Einmaliges Kompilieren mit Lernrate + Freeze-Muster (konstant je Lauf) ->
    # die Nachtrainings unten loesen kein Graph-Retracing mehr aus.
    model = clone_compiled(base, lr=lr, freeze=freeze)
    preds = np.empty(n, np.float32)
    train_steps, detect_steps, reject_steps = [], [], []
    last_train = -(10 ** 18)   # Refraktaerzeit-Tracker (Sofort-Trainings)
    active_until = -1          # Ende der laufenden Nachfuehrphase (informed)
    period = int(blind_period) if blind_period else int(chunk)
    next_blind = period        # naechster planmaessiger Termin (blind)
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

        # 2) Informed: Detektion -> Sofort-Training auf Vergangenheitsfenster
        #    und Start der Nachfuehrphase. Detektionen innerhalb einer bereits
        #    laufenden Phase VERLAENGERN diese nur (kein weiteres Sofort-
        #    Training) -> die Detektionsdichte des Verfahrens ist vom
        #    Eingriffsaufwand entkoppelt (max. ein Follow-up je Chunk), dichte
        #    Re-Detektoren wie KSWIN/ADWIN wirken damit als Ereignis-Trigger.
        if mode in ("informed", "combined") and detector is not None:
            for t in range(len(err_norm)):
                if detector.update(err_norm[t]):
                    g = i + t
                    detect_steps.append(int(g))
                    if g >= active_until and (g - last_train) > cooldown:
                        train_windows.append((max(0, g - window_prev), g + 1))
                        last_train = g
                        active_until = g + window_post
            # Follow-up am Chunk-Ende innerhalb einer laufenden Nachfuehrphase
            if not train_windows and i < active_until:
                train_windows.append((i, j))

        # 3) Passiv/blind (Gama et al. 2014, Abschn. 3.3.2): rein periodisches
        #    Nachtraining auf dem gleitenden Fenster der letzten blind_window
        #    Punkte, ohne jede Fehlerauswertung -> proaktiv, kein Trigger.
        if mode in ("blind", "combined") and j >= next_blind:
            next_blind = j + period          # Zeitplan laeuft unabhaengig weiter
            if not train_windows:            # in combined: kein Doppel-Training
                train_windows.append((max(0, j - blind_window), j))

        # 4) Inkrementelles Nachtraining auf den gesammelten Fenstern;
        #    mit reject wird ein Update verworfen, das den Fehler auf dem
        #    eigenen Trainingsfenster nicht senkt (vgl. reject_mse, origin)
        for (a, b) in train_windows:
            if reject:
                w_prev = model.get_weights()
                p0 = np.asarray(model(X[a:b], training=False)).ravel()
                mse_prev = float(np.mean((y[a:b] - p0) ** 2))
            model = incremental_fit(model, X[a:b], y[a:b], epochs=epochs,
                                    freeze=list(freeze), reset=reset, seed=seed)
            train_steps.append(int(b))
            if reject:
                p1 = np.asarray(model(X[a:b], training=False)).ravel()
                if float(np.mean((y[a:b] - p1) ** 2)) > mse_prev:
                    model.set_weights(w_prev)
                    reject_steps.append(int(b))

        if verbose and (i // chunk) % 50 == 0:
            print(f"  {mode}: {j}/{n} Punkte, {len(train_steps)} Nachtrainings")
        i = j

    errors = y - preds
    errors_norm = (errors - norm_mean) / norm_std
    return dict(preds=preds, errors=errors, errors_norm=errors_norm,
                train_steps=train_steps, detect_steps=detect_steps,
                reject_steps=reject_steps)


# ===========================================================================
# Hyperparameter-Tuning der Adaption (analog zu drift_detection.tune_detector)
# ===========================================================================
# Im Gegensatz zur Detektion ist hier jeder Trial teuer, da run_adaptation das
# Modell wiederholt nachtrainiert. Daher wird typischerweise auf einem groeber
# downgesampelten Strom (kuerzere Laufzeit) mit wenigen Trials getunt und die
# beste Konfiguration anschliessend mit crosscheck_candidates auf voller
# Aufloesung gegengeprueft. Anders als bei der Detektion wird keine
# Drift-Ground-Truth benoetigt: Da die gemessene Systemantwort als Label
# vorliegt, ist der RMSE direkt verfuegbar.

# Freeze-Muster werden als String kodiert (Optuna-Categoricals erlauben nur
# einfache Typen), Mapping auf die Bool-Tupel fuer run_adaptation:
FREEZE_CHOICES = {
    "TTF": (True, True, False),
    "TFF": (True, False, False),
    "FFF": (False, False, False),
}

_FREEZE_STRINGS = {v: k for k, v in FREEZE_CHOICES.items()}


def decode_adapt_params(params: dict) -> dict:
    """Dekodiert Optuna-best_params fuer run_adaptation (Freeze-String -> Tupel)."""
    p = dict(params)
    if isinstance(p.get("freeze"), str):
        p["freeze"] = FREEZE_CHOICES[p["freeze"]]
    return p


def encode_adapt_params(params: dict) -> dict:
    """Gegenstueck zu :func:`decode_adapt_params`: Freeze-Tupel -> String.

    Wird benoetigt, um dekodierte Parameter (z. B. Einzeloptima) als
    Warmstart-Kandidaten via ``study.enqueue_trial`` einzureihen, da Optuna die
    rohe (String-)Kodierung des Suchraums erwartet.
    """
    p = dict(params)
    fz = p.get("freeze")
    if isinstance(fz, (tuple, list)):
        p["freeze"] = _FREEZE_STRINGS[tuple(fz)]
    return p


def scale_adapt_params(params: dict, rescale: float = 1.0,
                       keys: Sequence[str] = SCALE_KEYS) -> dict:
    """Skaliert Zaehlparameter (Fensterlaengen) von der Tuning- auf die
    Zielaufloesung, z. B. rescale = STRIDE_TUNE / STRIDE."""
    out = dict(params)
    for k in keys:
        if k in out:
            out[k] = max(1, int(round(out[k] * rescale)))
    return out


def apply_det_params(detector, params: dict):
    """Entnimmt ``det_*``-Schluessel aus params und konfiguriert den Detektor.

    Die Detektorparameter werden im Adaptions-Tuning mitoptimiert, da sich das
    Fehlerniveau im geschlossenen Regelkreis vom statischen Fall des
    Detektions-Notebooks unterscheidet. Sie sind keine run_adaptation-Argumente
    und muessen daher vor dem Aufruf entfernt werden.

    Konvention:
      * ``det_err_threshold`` -> Binarisierungsschwelle (nur DDM/EDDM), wird
        als Attribut am StreamingDetector gesetzt.
      * alle uebrigen ``det_<name>`` -> Konstruktionsparameter <name> des
        zugrundeliegenden Detektors (z. B. ``det_window``, ``det_threshold``
        fuer RMSE); sie werden in die Overrides geschrieben und der Detektor
        wird neu aufgebaut.

    Returns (detector, params_ohne_det_Schluessel).
    """
    p = dict(params)
    det = {k[4:]: p.pop(k) for k in list(p) if k.startswith("det_")}
    thr = det.pop("err_threshold", None)
    if detector is not None:
        if thr is not None:
            detector.err_threshold = float(thr)
        if det:
            detector._overrides.update(det)
            detector.reset()
    return detector, p


def estimate_cooldown(setpoints, x: float = 30.0) -> Tuple[int, float]:
    """Refraktaerzeit aus der mittleren Dauer stationaerer Phasen.

    setpoints : DataFrame der Betriebspunkt-/Sollwertsignale (z. B.
        ``stream[["w1", "w2"]]``); ein Betriebspunktwechsel liegt vor, wenn
        sich mindestens eines der Signale aendert.
    x : Vielfaches der mittleren stationaeren Phasendauer T_stat.

    Returns (cooldown, t_stat) in Punkten: cooldown = round(x * T_stat),
    T_stat = n / Anzahl Wechsel.
    """
    change = setpoints.diff().fillna(0).ne(0).any(axis=1)
    t_stat = len(setpoints) / max(1, int(change.sum()))
    return int(round(x * t_stat)), float(t_stat)


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


def resolve_cooldown(params: dict, t_stat: float) -> dict:
    """Wandelt den dimensionslosen Multiplikator ``cooldown_x`` in eine
    Refraktaerzeit in Punkten um: cooldown = round(cooldown_x * T_stat).

    So bleibt die physikalische Interpretation (Vielfaches der mittleren
    stationaeren Phasendauer) erhalten und die Konfiguration ist zwischen
    Tuning- und Zielaufloesung uebertragbar, ohne skaliert zu werden.
    """
    p = dict(params)
    if "cooldown_x" in p:
        p["cooldown"] = int(round(float(p.pop("cooldown_x")) * float(t_stat)))
    return p


def _suggest_adapt_params(strategy: str, trial, chunk: int = 144,
                          det_name: str = None) -> dict:
    """Optuna-Suchraum je Strategie. Detektorparameter werden im geschlossenen
    Regelkreis mitgetunt (die im Detektions-Notebook getunten Werte sind am
    offenen Fehlerstrom kalibriert und dort systematisch fehlangepasst). Die
    Refraktaerzeit wird als Vielfaches der stationaeren Phasendauer (cooldown_x)
    optimiert, da sie sich als detektorspezifischer Haupthebel erwiesen hat.
    """
    strategy = strategy.lower()
    det_name = (det_name or "").upper()
    freeze_choices = list(FREEZE_CHOICES)
    if strategy in ("informed", "combined"):
        freeze_choices = [c for c in freeze_choices if c != "TTF"]
    params = dict(
        lr=trial.suggest_float("lr", 1e-4, 1.5e-2, log=True),
        epochs=trial.suggest_int("epochs", 1, 20),
        freeze=FREEZE_CHOICES[trial.suggest_categorical("freeze", freeze_choices)],
        reset=trial.suggest_categorical("reset", [False, True]),
    )
    if strategy in ("blind", "combined"):
        params["blind_window"] = trial.suggest_int("blind_window", 15, 100)
        params["blind_period"] = trial.suggest_int("blind_period", chunk, 30 * chunk)
    if strategy in ("informed", "combined"):
        params["window_prev"] = trial.suggest_int("window_prev", 5, 100)
        params["window_post"] = trial.suggest_int("window_post", 5, 100)
        params["cooldown_x"] = trial.suggest_float("cooldown_x", 0.0, 60.0)
        if det_name == "KSWIN":
            _mi = trial.suggest_int("det_min_num_instances", 50, 400)
            params["det_alpha"] = trial.suggest_float("det_alpha", 1e-6, 5e-3, log=True)
            params["det_min_num_instances"] = _mi
            params["det_num_test_instances"] = trial.suggest_int(
                "det_num_test_instances", 20, max(20, _mi // 2))
        elif det_name == "ADWIN":
            params["det_delta"] = trial.suggest_float("det_delta", 1e-3, 0.4, log=True)
            params["det_clock"] = trial.suggest_int("det_clock", 1, 64)
            params["det_min_window_size"] = trial.suggest_int("det_min_window_size", 5, 64)
        elif det_name == "DDM":
            _dl = trial.suggest_float("det_drift_level", 1.2, 3.5)
            params["det_drift_level"] = _dl
            # warning_level an drift_level koppeln (frouros verlangt
            # drift_level > warning_level; ueberschreibt zudem einen evtl. aus
            # dem Detektions-Warmstart stammenden, hoeheren warning_level)
            params["det_warning_level"] = _dl / 2.0
            params["det_min_num_instances"] = trial.suggest_int("det_min_num_instances", 30, 300)
            params["det_err_threshold"] = trial.suggest_float("det_err_threshold", 0.5, 2.5)
        elif det_name == "EDDM":
            _a = trial.suggest_float("det_alpha", 0.92, 0.999)
            params["det_alpha"] = _a
            params["det_beta"] = trial.suggest_float("det_beta", 0.80, _a)
            params["det_min_num_misclassified_instances"] = trial.suggest_int(
                "det_min_num_misclassified_instances", 20, 200)
            params["det_err_threshold"] = trial.suggest_float("det_err_threshold", 0.5, 2.5)
        elif det_name == "RMSE":
            params["det_window"] = trial.suggest_int("det_window", 15, 100)
            params["det_threshold"] = trial.suggest_float("det_threshold", 0.5, 3.0)
    return params


def tune_adaptation(strategy: str, base, X, y, *, fixed: dict,
                    detector_factory=None, rmse_baseline: float = None,
                    n_trials: int = 20, weights: Tuple[float, float] = (1.0, 0.1),
                    seed: int = 42, show_progress_bar: bool = False,
                    enqueue: List[dict] = None, t_stat: float = 1.0):
    """Optimiert die Adaptions-Hyperparameter einer Strategie mit Optuna (TPE).

    Parameters
    ----------
    strategy : {"blind", "informed", "combined"} (``baseline`` hat nichts zu tunen).
    base : kompiliertes Keras-Basismodell (wird je Trial geklont).
    X, y : Feature-/Label-Arrays des (ggf. downgesampelten) Tuning-Stroms.
    fixed : nicht getunte Argumente fuer run_adaptation
        (z. B. ``chunk``, ``cooldown``, ``norm_mean``, ``norm_std``, ``seed``).
    detector_factory : Callable -> StreamingDetector (fuer informed/combined),
        liefert pro Trial einen frischen Detektor.
    rmse_baseline : RMSE ohne Adaption; falls None, wird er einmal bestimmt.
    weights : (w_rmse, w_train) der Zielfunktion :func:`score_adaptation`.
    enqueue : Liste roher Optuna-Parameterdicts (Freeze als String, vgl.
        :func:`encode_adapt_params`), die als Startkandidaten eingereiht werden
        (Warmstart, z. B. Vereinigung der Einzeloptima fuer ``combined``).

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

    # Welche Detektorparameter mitgetunt werden, haengt vom Detektortyp ab
    det_name = (getattr(detector_factory(), "name", None)
                if (strategy in ("informed", "combined") and detector_factory is not None)
                else None)

    def objective(trial):
        params = _suggest_adapt_params(strategy, trial, chunk=chunk, det_name=det_name)
        detector = (detector_factory()
                    if (strategy in ("informed", "combined") and detector_factory is not None)
                    else None)
        detector, params = apply_det_params(detector, params)
        params = resolve_cooldown(params, t_stat)
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
        study.enqueue_trial(_p, skip_if_exists=True)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=show_progress_bar)
    return study, rmse_baseline


def crosscheck_candidates(base, X, y, *, best_params: dict, fixed: dict,
                          t_stat: float = 1.0, detector_factory=None, study=None,
                          top_k: int = 3, rescale: float = 1.0,
                          mode: str = "combined", seed: int = None,
                          extra: Dict[str, dict] = None, verbose: bool = True):
    """Prueft Konfigurationskandidaten auf dem voll aufgeloesten Strom gegen.

    Da das Tuning auf einem groeber abgetasteten Strom erfolgt, ist die
    Uebertragung der besten Konfiguration eine Extrapolation. Diese Funktion
    evaluiert daher mehrere Kandidaten per vollstaendigem Adaptionslauf auf der
    Zielaufloesung und gibt die dort beste Konfiguration zurueck:

      * ``tpe_best``  – bestes Tuning-Ergebnis der Strategie ``mode``
      * ``union``     – Vereinigung der Einzeloptima (nur mode="combined":
                        informed-Optimum + blinde Fenster-/Schwellenparameter)
      * ``trial_<n>`` – Top-k-Trials der uebergebenen Optuna-Study
      * ``extra``     – optionale manuelle Kandidaten {name: params}, z. B. die
                        Konfiguration einer anderen Strategie als Quervergleich

    Parameters
    ----------
    best_params : dict je Strategie mit dekodierten Optima (Tuning-Aufloesung).
    fixed : nicht getunte run_adaptation-Argumente der ZIELaufloesung
        (``chunk``, ``norm_mean``, ``norm_std``; OHNE ``seed``/``cooldown``).
    rescale : Skalierungsfaktor der Zaehlparameter, z. B. STRIDE_TUNE / STRIDE.

    Returns
    -------
    (best, table) : beste Parameter (Tuning-Aufloesung, unskaliert) und
    Ergebnistabelle {name: {"rmse", "n_train", "params"}}.
    """
    import tensorflow as tf

    candidates = {}
    if mode in best_params:
        candidates["tpe_best"] = dict(best_params[mode])
    # union: Vereinigung der Einzeloptima (informed + passive Komponente)
    bl, inf = best_params.get("blind"), best_params.get("informed")
    if mode == "combined" and bl and inf:
        candidates["union"] = {**bl, **inf,
                               "blind_window": bl["blind_window"],
                               "blind_period": bl["blind_period"]}
    if study is not None:
        trials = sorted([t for t in study.trials if t.value is not None],
                        key=lambda t: t.value)
        for t in trials[:top_k]:
            candidates[f"trial_{t.number}"] = decode_adapt_params(t.params)
    for name, p in (extra or {}).items():
        candidates[name] = dict(p)

    table = {}
    for name, p in candidates.items():
        if seed is not None:
            tf.keras.utils.set_random_seed(seed)
        det = detector_factory() if detector_factory is not None else None
        det, p_run = apply_det_params(det, scale_adapt_params(p, rescale))
        p_run = resolve_cooldown(p_run, t_stat)
        cfg = {**fixed, **p_run}
        res = run_adaptation(base, X, y, mode=mode, detector=det, seed=seed, **cfg)
        rmse = float(np.sqrt(np.mean(np.asarray(res["errors"], float) ** 2)))
        table[name] = dict(rmse=rmse, n_train=len(res["train_steps"]),
                           n_detect=len(res["detect_steps"]), params=dict(p))
        if verbose:
            print(f"{name:12s} RMSE={rmse:.4f}  n_train={len(res['train_steps'])}"
                  f"  n_detect={len(res['detect_steps'])}")

    best = min(table, key=lambda k: table[k]["rmse"])
    if verbose:
        print(f"uebernommen: {best} (RMSE={table[best]['rmse']:.3f})")
    return dict(table[best]["params"]), table
