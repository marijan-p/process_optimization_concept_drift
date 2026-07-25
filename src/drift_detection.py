"""Drift-Erkennung fuer zeitdiskrete Datenstroeme.

Universell importierbares Modul mit den vier statistischen Detektoren KSWIN,
ADWIN, DDM und EDDM (Bibliothek ``frouros``), sowie dem Schwellwert-Detektor
``RMSEThreshold`` als einfachster Form der Performance-Indikator-Ueberwachung
(Gama et al. 2014, Abschn. 3.2)

Beispiel
--------
>>> import numpy as np
>>> from drift_detection import detect, run_all
>>> error = np.random.default_rng(0).normal(0, 0.1, 1000)
>>> drifts, warnings = detect("KSWIN", error)
>>> results = run_all(error)            # alle vier Detektoren auf einmal

Voraussetzung: ``pip install frouros``
"""

from __future__ import annotations

import collections
from typing import Callable, Dict, List, Sequence, Tuple

import numpy as np
from frouros.detectors.concept_drift import (
    KSWIN, KSWINConfig, ADWIN, ADWINConfig,
    DDM, DDMConfig, EDDM, EDDMConfig,
)

__all__ = [
    "ERROR_RATE_DETECTORS",
    "DETECTOR_FACTORIES",
    "RMSEThreshold",
    "build_detector",
    "make_detectors",
    "run_detector",
    "detect",
    "run_all",
    "synthetic_error_stream",
    "sudden_drift_indices",
    "drift_active_mask",
    "score_detections",
    "tune_detector",
]

# DDM/EDDM sind fehlerraten-basiert und erwarten ein binaeres Fehlsignal,
# waehrend KSWIN/ADWIN den kontinuierlichen (absoluten) Fehler direkt verarbeiten.
ERROR_RATE_DETECTORS = frozenset({"DDM", "EDDM"})

class RMSEThreshold:
    """Schwellwert auf der rollenden RMSE eines Performance-Indikators.

    Einfachster Vertreter der von Gama et al. (2014, Abschn. 3.2) beschriebenen
    Drift-Erkennung durch Monitoring von Performance-Indikatoren (vgl. Widmer &
    Kubat 1996; Klinkenberg & Renz 1998): kein statistischer Test, keine
    Warnstufe, nur ein Schwellwert auf einem gleitenden Fenster.

    Dient als Referenz-Detektor gegenueber den statistischen Verfahren und
    entspricht der zuvor als "blind" gefuehrten fehlergetriebenen Ausloesung.

    Schnittstelle frouros-kompatibel (``update`` / ``status`` / ``reset``), damit
    der Detektor ohne Sonderbehandlung durch ``run_detector`` und
    ``StreamingDetector`` laeuft. Nach einer Detektion setzen beide den Detektor
    zurueck; das Leeren des Puffers wirkt dadurch als Refraktaerzeit von
    ``min_num_instances`` Punkten -- analog zum Reset von DDM/EDDM.
    """

    def __init__(self, window=44, threshold=1.5, min_num_instances=None):
        self.window = int(window)
        self.threshold = float(threshold)
        self.min_num_instances = int(min_num_instances or window)
        self.reset()

    def reset(self):
        self._buf = collections.deque(maxlen=self.window)
        self.status = {"drift": False, "warning": False}

    def update(self, value):
        self._buf.append(float(value))
        drift = (len(self._buf) >= self.min_num_instances
                 and float(np.sqrt(np.mean(np.square(self._buf)))) >= self.threshold)
        self.status = {"drift": drift, "warning": False}
        return None

# Standardparameter analog zur Masterarbeit / improved_adaptation_training.py.
# Ueber **overrides in build_detector() pro Aufruf anpassbar.
_DEFAULT_PARAMS: Dict[str, dict] = {
    "KSWIN": dict(seed=42, min_num_instances=180, num_test_instances=50, alpha=1e-4),
    "ADWIN": dict(clock=5, delta=0.15, m=10, min_window_size=5, min_num_instances=10),
    "DDM": dict(drift_level=2.0, warning_level=1.0, min_num_instances=10),
    "EDDM": dict(beta=0.9, alpha=0.999, min_num_misclassified_instances=10),
    "RMSE": dict(window=44, threshold=1.5),
}

# Bauanweisung je Detektor: Parameter-Dict -> konfigurierter frouros-Detektor.
DETECTOR_FACTORIES: Dict[str, Callable[[dict], object]] = {
    "KSWIN": lambda p: KSWIN(KSWINConfig(**p)),
    "ADWIN": lambda p: ADWIN(ADWINConfig(**p)),
    "DDM": lambda p: DDM(DDMConfig(**p)),
    "EDDM": lambda p: EDDM(EDDMConfig(**p)),
    "RMSE": lambda p: RMSEThreshold(**p),
}


def build_detector(name: str, **overrides):
    """Erzeugt einen einzelnen, konfigurierten frouros-Detektor.

    Parameters
    ----------
    name : {"KSWIN", "ADWIN", "DDM", "EDDM"}
    **overrides : einzelne Config-Parameter ueberschreiben (z. B. ``alpha=1e-3``).
    """
    name = name.upper()
    if name not in DETECTOR_FACTORIES:
        raise ValueError(f"Unbekannter Detektor '{name}'. Erlaubt: {list(DETECTOR_FACTORIES)}")
    params = {**_DEFAULT_PARAMS[name], **overrides}
    return DETECTOR_FACTORIES[name](params)


def make_detectors(**param_overrides: dict) -> Dict[str, object]:
    """Erzeugt alle vier Detektoren als Dict {name: detector}.

    ``param_overrides`` erlaubt detektor-spezifische Overrides, z. B.
    ``make_detectors(DDM=dict(drift_level=3.0))``.
    """
    return {
        name: build_detector(name, **param_overrides.get(name, {}))
        for name in DETECTOR_FACTORIES
    }


def run_detector(
    name: str,
    detector: object,
    error: Sequence[float],
    err_threshold: float = 0.5,
    reset_on_drift: bool = True,
    cooldown: int = 0,
) -> Tuple[List[int], List[int]]:
    """Streamt ``error`` durch einen Detektor und liefert (drifts, warnings).

    KSWIN/ADWIN erhalten den absoluten Fehler ``|e|``; DDM/EDDM ein binarisiertes
    Fehlsignal ``|e| > err_threshold`` (vgl. Masterarbeit Abschn. 4.4.1, dort 0.05
    auf normierten Daten -- die Schwelle ist an die Fehlerskala anzupassen).

    Parameters
    ----------
    name : Name des Detektors (steuert die Binarisierung).
    detector : zuvor mit :func:`build_detector` erzeugte Instanz.
    error : Sequenz von Residuen / Praediktionsfehlern.
    err_threshold : Schwelle fuer die Binarisierung (nur DDM/EDDM).
    reset_on_drift : nach erkanntem Drift zuruecksetzen (Folgedrifts erfassen).
    cooldown : Refraktaerzeit in Samples; 0 = Wiederholungen erlaubt, >0
        unterdrueckt weitere Detektionen fuer cooldown Schritte nach einer Detektion.
    """
    name = name.upper()
    is_rate_based = name in ERROR_RATE_DETECTORS
    drifts: List[int] = []
    warnings: List[int] = []
    last_accept = -(10 ** 18)   # fuer Refraktaerzeit (cooldown)
    for k, e in enumerate(error):
        value = float(abs(e) > err_threshold) if is_rate_based else abs(float(e))
        detector.update(value=value)
        status = detector.status
        # KSWIN/ADWIN (fensterbasiert) liefern kein "warning" im Status -> .get()
        if status["drift"]:
            if reset_on_drift:
                detector.reset()
            if k - last_accept > cooldown:
                drifts.append(k)
                last_accept = k
        elif status.get("warning", False):
            warnings.append(k)
    return drifts, warnings


def detect(
    name: str,
    error: Sequence[float],
    err_threshold: float = 0.5,
    reset_on_drift: bool = True,
    **detector_overrides,
) -> Tuple[List[int], List[int]]:
    """Komfortfunktion: Detektor bauen und direkt auf ``error`` anwenden."""
    detector = build_detector(name, **detector_overrides)
    return run_detector(name, detector, error, err_threshold, reset_on_drift)


def run_all(
    error: Sequence[float],
    err_threshold: float = 0.5,
    reset_on_drift: bool = True,
    param_overrides: Dict[str, dict] | None = None,
) -> Dict[str, Tuple[List[int], List[int]]]:
    """Wendet alle vier Detektoren auf ``error`` an und liefert {name: (drifts, warnings)}."""
    param_overrides = param_overrides or {}
    results: Dict[str, Tuple[List[int], List[int]]] = {}
    for name in DETECTOR_FACTORIES:
        detector = build_detector(name, **param_overrides.get(name, {}))
        results[name] = run_detector(name, detector, error, err_threshold, reset_on_drift)
    return results


def synthetic_error_stream(
    n_ref: int = 800,
    n_seg: int = 6,
    seg_len: int = 600,
    gain: float = 1.0,
    noise_sigma: float = 0.15,
    seed: int = 257,
) -> Tuple[np.ndarray, np.ndarray]:
    """Erzeugt einen Saegezahn-Drift-Teststrom (c, error) wie im Kapitel.

    Drift-freie Referenzphase (``n_ref``), danach ``n_seg`` Segmente mit linearem
    Abfall (Incremental Drift) und Sprung an den Grenzen (Sudden Drift). Der
    Fehler folgt ``c[k]`` ueberlagert mit gaussschem Rauschen.
    """
    rng = np.random.default_rng(seed)
    c = [np.zeros(n_ref)]
    for _ in range(n_seg):
        c_start = rng.uniform(0.6, 1.0)
        c_end = rng.uniform(-1.0, -0.6)
        c.append(np.linspace(c_start, c_end, seg_len))
    c = np.concatenate(c)
    error = gain * c + rng.normal(0.0, noise_sigma, size=c.shape)
    return c, error


# ===========================================================================
# Parameter-Tuning auf Basis der Ground Truth des synthetischen Datenstroms
# ===========================================================================
# Der synthetische Datensatz liefert im Gegensatz zu Realdaten bekannte
# Drift-Zeitpunkte. Daraus laesst sich eine Zielfunktion bilden und mit Optuna
# (TPE) effizient optimieren. Bewertung "Wiederholung erlaubt": mehrfache
# Detektionen waehrend aktiven (incremental) Drifts gelten NICHT als Fehlalarm;
# nur Detektionen in stabilen Phasen werden bestraft.


def sudden_drift_indices(cd: Sequence[float], jump: float = None) -> List[int]:
    """Indizes der Sudden Drifts (Aufwaertsspruenge im Driftsignal c[k])."""
    cd = np.asarray(cd, float)
    d = np.diff(cd)
    if len(d) == 0:
        return []
    thr = jump if jump is not None else 0.5 * float(np.nanmax(np.abs(d)))
    return (np.flatnonzero(d > thr) + 1).tolist()


def drift_active_mask(cd: Sequence[float], rel_floor: float = 0.1) -> np.ndarray:
    """Boolean-Maske: True, wo der Prozess driftet (|c[k]| ueber rel_floor*max)."""
    a = np.abs(np.asarray(cd, float))
    mx = float(np.nanmax(a)) if a.size else 0.0
    return a > (rel_floor * mx if mx > 0 else 0.0)


def score_detections(
    drifts: Sequence[int],
    sudden_idx: Sequence[int],
    drift_active: Sequence[bool],
    tolerance: int,
    n: int,
    weights: Tuple[float, float, float] = (1.0, 0.3, 0.05),
) -> Dict[str, float]:
    """Bewertet eine Detektionsliste gegen die Ground Truth.

    Returns dict mit recall (Sudden Drifts), mean_delay, n_false (Fehlalarme in
    stabilen Phasen), fa_per_true und kombiniertem ``score`` (kleiner = besser).
    """
    w_rec, w_del, w_fa = weights
    drifts = np.asarray(sorted(int(d) for d in drifts), int)
    sudden = np.asarray(sorted(int(s) for s in sudden_idx), int)
    active = np.asarray(drift_active, bool)
    n_sudden = len(sudden)

    # Recall + Detektionsverzug auf den Sudden Drifts
    detected, delays = 0, []
    for s in sudden:
        win = drifts[(drifts >= s) & (drifts <= s + tolerance)]
        if win.size:
            detected += 1
            delays.append(int(win[0] - s))
    recall = detected / n_sudden if n_sudden else 1.0
    mean_delay = float(np.mean(delays)) if delays else float(tolerance)
    norm_delay = min(mean_delay / tolerance, 1.0) if tolerance > 0 else 0.0

    # Fehlalarme: Detektionen in stabiler Phase (nicht aktiv & nicht im Sudden-Fenster)
    sudden_window = np.zeros(n, bool)
    for s in sudden:
        sudden_window[s:min(n, s + tolerance + 1)] = True
    n_false = int(sum(1 for d in drifts if 0 <= d < n
                      and not active[d] and not sudden_window[d]))
    fa_per_true = n_false / max(1, n_sudden)

    score = w_rec * (1.0 - recall) + w_del * norm_delay + w_fa * fa_per_true
    return dict(recall=recall, n_sudden=n_sudden, n_detected=int(drifts.size),
                mean_delay=mean_delay, n_false=n_false, fa_per_true=fa_per_true,
                score=float(score))


def _suggest_params(name: str, trial, err_threshold_bounds=None):
    """Optuna-Suchraum je Detektor. Returns (config_overrides, err_threshold|None).

    Parameters
    ----------
    err_threshold_bounds : (float, float) | None
        Suchbereich fuer err_threshold bei DDM/EDDM als (lo, hi). Wird None
        uebergeben, greift der Fallback (0.5, 4.0). Empfohlener Ansatz: lo aus
        dem 80. Perzentil des stabilen Fehlers, hi aus dem 99.5. Perzentil
        des Gesamtfehlers (vgl. tune_detector).
    """
    et_lo, et_hi = err_threshold_bounds if err_threshold_bounds is not None else (0.5, 4.0)
    name = name.upper()
    if name == "KSWIN":
        min_inst = trial.suggest_int("min_num_instances", 50, 400)
        return dict(
            alpha=trial.suggest_float("alpha", 1e-6, 5e-3, log=True),
            min_num_instances=min_inst,
            num_test_instances=trial.suggest_int("num_test_instances", 20, max(20, min_inst // 2)),
        ), None
    if name == "ADWIN":
        return dict(
            delta=trial.suggest_float("delta", 1e-3, 0.4, log=True),
            clock=trial.suggest_int("clock", 1, 64),
            min_window_size=trial.suggest_int("min_window_size", 5, 64),
        ), None
    if name == "DDM":
        drift_level = trial.suggest_float("drift_level", 1.5, 4.0)
        return dict(
            drift_level=drift_level,
            warning_level=trial.suggest_float("warning_level", 1.0, drift_level),
            min_num_instances=trial.suggest_int("min_num_instances", 30, 500),
        ), trial.suggest_float("err_threshold", et_lo, et_hi)
    if name == "EDDM":
        alpha = trial.suggest_float("alpha", 0.90, 0.999)
        return dict(
            alpha=alpha,
            beta=trial.suggest_float("beta", 0.70, alpha),
            min_num_misclassified_instances=trial.suggest_int(
                "min_num_misclassified_instances", 30, 500),
        ), trial.suggest_float("err_threshold", et_lo, et_hi)
    if name == "RMSE":
        window = trial.suggest_int("window", 15, 150)
        return dict(
            window=window,
            threshold=trial.suggest_float("threshold", 0.5, 4.0),
        ), None
    raise ValueError(f"Unbekannter Detektor '{name}'")


def tune_detector(
    name: str,
    error: Sequence[float],
    sudden_idx: Sequence[int],
    drift_active: Sequence[bool],
    tolerance: int,
    n_trials: int = 50,
    downsample: int = 1,
    weights: Tuple[float, float, float] = (1.0, 0.3, 0.05),
    seed: int = 42,
    reset_on_drift: bool = True,
    cooldown: int = 0,
    show_progress_bar: bool = False,
    err_threshold_bounds=None,
):
    """Optimiert die Parameter eines Detektors mit Optuna (TPE).

    Effizienz: ``downsample=q`` wertet nur jeden q-ten Punkt aus (alle Drifts
    bleiben erhalten, Toleranz/Verzug werden mitskaliert) und beschleunigt das
    Tuning etwa um Faktor q. Final mit ``downsample=1`` gegenpruefen.

    Parameters
    ----------
    err_threshold_bounds : (float, float) | None
        Suchbereich fuer err_threshold bei DDM/EDDM als (lo, hi). Wird None
        uebergeben, berechnet tune_detector die Grenzen automatisch aus dem
        uebergebenen Fehlerstrom: lo = 80. Perzentil |e| in stabilen Phasen,
        hi = 99.5. Perzentil |e| gesamt. Fuer KSWIN/ADWIN ohne Wirkung.

    Returns das Optuna-``study``-Objekt. Beste Parameter: ``study.best_params``.
    """
    import optuna   # lazy: Modul bleibt ohne Optuna importierbar

    name = name.upper()
    err = np.asarray(error, float)

    # err_threshold_bounds fuer DDM/EDDM automatisch bestimmen, falls nicht vorgegeben.
    if err_threshold_bounds is None and name in ERROR_RATE_DETECTORS:
        active_mask = np.asarray(drift_active, bool)
        stable_abs = np.abs(err[~active_mask])
        et_lo = float(np.percentile(stable_abs, 60)) if stable_abs.size else 0.5
        et_hi = float(np.percentile(np.abs(err), 99.5))
        if et_lo >= et_hi:
            et_lo = max(0.0, et_hi * 0.5)
        err_threshold_bounds = (et_lo, et_hi)

    q = max(1, int(downsample))
    err_eval = err[::q]
    active_eval = np.asarray(drift_active, bool)[::q]
    n_eval = len(err_eval)
    sudden_eval = sorted({int(s) // q for s in sudden_idx if 0 <= int(s) // q < n_eval})
    tol_eval = max(1, tolerance // q)
    cd_eval = cooldown // q   # Refraktaerzeit auf das Eval-Raster skalieren

    def objective(trial):
        params, et = _suggest_params(name, trial, err_threshold_bounds)
        detector = build_detector(name, **params)
        drifts, _ = run_detector(
            name, detector, err_eval,
            err_threshold=(et if et is not None else 0.5),
            reset_on_drift=reset_on_drift,
            cooldown=cd_eval,
        )
        s = score_detections(drifts, sudden_eval, active_eval,
                             tolerance=tol_eval, n=n_eval, weights=weights)
        for k, v in s.items():
            trial.set_user_attr(k, v)
        return s["score"]

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    study.optimize(objective, n_trials=n_trials, show_progress_bar=show_progress_bar)
    return study


if __name__ == "__main__":
    # Kleiner Selbsttest auf dem synthetischen Teststrom.
    c, error = synthetic_error_stream()
    print(f"Teststrom: {len(error)} Zeitschritte, Driftbeginn bei k=800")
    for name, (drifts, warnings) in run_all(error).items():
        first = drifts[0] if drifts else None
        print(f"{name:6s}: {len(drifts):2d} Drift(s) | erste Erkennung bei k={first}")
