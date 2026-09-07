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

import hashlib
import math
import pathlib

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


# --------------------------------------------------------------------------- #
# Selbstauskunft: erkennt ein veraltetes Modul im laufenden Kernel
# --------------------------------------------------------------------------- #
try:
    MODULE_SHA = hashlib.sha1(
        pathlib.Path(__file__).resolve().read_bytes()).hexdigest()[:8]
except Exception:          # eingefroren, kein Dateizugriff -- dann kein Abgleich
    MODULE_SHA = None


def assert_current():
    """Prueft, ob das geladene Modul noch der Quelldatei entspricht.

    Ein Jupyter-Kernel haelt bereits importierte Module fest; ``import
    drift_detection`` ist dann ein No-op und eine Aenderung an der Datei bleibt
    wirkungslos. ``MODULE_SHA`` wird beim Import berechnet und hier gegen einen
    frischen Blick auf die Datei gehalten -- der Vergleich deckt jede Aenderung
    ab, nicht nur ein einzelnes Merkmal.
    """
    if MODULE_SHA is None:
        return None
    disk = hashlib.sha1(pathlib.Path(__file__).resolve().read_bytes()).hexdigest()[:8]
    if disk != MODULE_SHA:
        raise RuntimeError(
            f"drift_detection.py auf der Platte ({disk}) weicht vom geladenen "
            f"Modul ({MODULE_SHA}) ab -- veralteter Kernel. Kernel neu starten "
            "und, falls schon getunt wurde, einmal mit FORCE_RECOMPUTE = True "
            "durchlaufen.")
    return MODULE_SHA


def _space_consts(code):
    """Konstanten eines Code-Objekts, verschachtelte Code-Objekte aufgeloest.

    ``repr`` eines Code-Objekts enthaelt Speicheradresse und Dateipfad und ist
    damit prozessabhaengig -- eine daraus gebildete Kennung waere bei jedem
    Kernelstart eine andere und wuerde jeden Cache verfehlen. Enthaelt eine
    Funktion kein Code-Objekt (kein Comprehension, kein Lambda), liefert der
    Helfer genau ``code.co_consts`` und die Kennung bleibt unveraendert.
    """
    import types
    out = []
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            out.append(("<code>", c.co_name, _space_consts(c), c.co_names))
        else:
            out.append(c)
    return tuple(out)


def _space_id_of(func, n: int = 8) -> str:
    """Kennung des von ``func`` aufgespannten Suchraums aus dem Code-Objekt."""
    code = func.__code__
    consts = _space_consts(code)
    if consts and consts[0] == func.__doc__:
        consts = consts[1:]        # Docstring raus
    return hashlib.sha1(repr((consts, code.co_names)).encode()).hexdigest()[:n]


def search_space_id(n: int = 8) -> str:
    """Kennung des Optuna-Suchraums aus dem GELADENEN Code-Objekt.

    Bewusst nicht ueber ``inspect.getsource``: das liest die Quelldatei von der
    Platte und liefert in einem veralteten Kernel die neue Fassung, waehrend die
    alte laeuft -- die Kennung waere dann ein falscher Zeuge, der den Cache
    verwirft und das Ergebnis der alten Grenzen unter der neuen Kennung ablegt.
    Genau das ist am 2026-09-01 passiert. ``co_consts`` traegt die Zahlenwerte
    der Grenzen, ``co_names`` die aufgerufenen Namen.
    """
    assert_current()
    return _space_id_of(_suggest_params, n)


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
    weights: Tuple[float, float, float] = (1.0, 0.3, 1.0),
    fa_decades: float = 3.0,
) -> Dict[str, float]:
    """Bewertet eine Detektionsliste gegen die Ground Truth.

    Fehlalarm ist jede Detektion ausserhalb aller Toleranzfenster -- unabhaengig
    davon, ob der Prozess dort gerade driftet. Die frueher benutzte Definition
    (nur Detektionen in nachweislich stabiler Phase) stellte bei inkrementellem
    Drift den Grossteil der Fehlalarme frei: ``drift_active`` deckt dort rund
    84 % des Stroms ab, gemessen wurde also nur auf einem Sechstel. Ein Detektor,
    der durchgehend feuert, wurde damit kaum bestraft und gewann das Tuning.

    Der Fehlalarm-Term im Score ist ``fa_term`` -- die Zahl der Fehlalarme je
    Ereignis, logarithmisch bewertet und auf [0, 1] gestaucht::

        fa_term = min(1, log10(1 + n_false / n_sudden) / fa_decades)

    0 heisst kein Fehlalarm, 1 heisst ``10**fa_decades`` Fehlalarme je Ereignis.
    Die logarithmische Skala ist noetig, weil sich die Detektoren ueber
    Groessenordnungen unterscheiden (im synthetischen Fall 23 bis 17808
    Detektionen auf 4 Ereignisse). Ein linearer Term aus ``1 - precision`` liegt
    in diesem Bereich fuer alle Kandidaten zwischen 0,98 und 0,99, traegt also
    keinen Gradienten -- das Tuning optimiert dann nur noch den Verzug und senkt
    ihn, indem es haeufiger feuert. Genau das ist am 2026-09-01 passiert.

    ``precision`` und ``fa_per_true`` bleiben als Kennzahlen erhalten, gehen aber
    nicht in den Score ein.

    Parameters
    ----------
    drift_active : wird nur noch fuer ``n_false_stable`` gebraucht, die alte
        Fehlalarm-Definition. Sie wird zum Vergleich mitberichtet.
    weights : (w_recall, w_delay, w_falsealarm).
    fa_decades : Zahl der Dekaden, ueber die der Fehlalarm-Term auf [0, 1]
        gestaucht wird. Geht in den Konfigurations-Hash der Notebooks ein.

    Returns
    -------
    dict mit recall, mean_delay, precision, fa_term, n_false (ausserhalb der
    Fenster), n_false_stable (alte Definition), n_hits, fa_per_true, n_sudden,
    n_detected und kombiniertem ``score`` (kleiner = besser).
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

    # Toleranzfenster: alles darin gilt als plausibel auf ein Ereignis bezogen.
    sudden_window = np.zeros(n, bool)
    for s in sudden:
        sudden_window[s:min(n, s + tolerance + 1)] = True

    inside = [bool(sudden_window[d]) for d in drifts if 0 <= d < n]
    n_valid = len(inside)
    n_hits = int(sum(inside))
    n_false = n_valid - n_hits
    precision = n_hits / n_valid if n_valid else 0.0
    fa_per_true = n_false / max(1, n_sudden)

    # Alte Definition, nur noch als Vergleichskennzahl (s. Docstring).
    n_false_stable = int(sum(1 for d in drifts if 0 <= d < n
                             and not active[d] and not sudden_window[d]))

    fa_term = min(1.0, math.log10(1.0 + fa_per_true) / fa_decades) if fa_decades > 0 else 0.0

    score = w_rec * (1.0 - recall) + w_del * norm_delay + w_fa * fa_term
    return dict(recall=recall, precision=precision, fa_term=float(fa_term),
                n_sudden=n_sudden, n_detected=int(drifts.size), n_hits=n_hits,
                mean_delay=mean_delay, n_false=n_false,
                n_false_stable=n_false_stable, fa_per_true=fa_per_true,
                score=float(score))


def _suggest_params(name: str, trial, err_threshold_bounds=None):
    """Optuna-Suchraum je Detektor. Returns (config_overrides, err_threshold|None).

    Geweitet wurde am 2026-09-01 nur dort, wo ein Optimum nachweislich am
    Anschlag lag: KSWIN ``alpha`` (in jedem Lauf auf 1e-6), DDM ``drift_level``
    (3.95 bei Deckel 4.0), EDDM ``alpha`` (0.99867 bei 0.999) und RMSE
    ``window`` (exakt 150 bei 150). Das hat KSWIN und RMSE deutlich verbessert
    (RMSE von 1852 auf 324 Detektionen bei Recall 1.0).

    Zusaetzlich geweitete Zaehlgrenzen von DDM und EDDM (500 -> 2000) sind am
    2026-09-02 wieder zurueckgenommen worden. Dort lag kein Optimum am Anschlag
    (372 bzw. 355 von 500), die Weitung hat nur das Suchvolumen verzwoelffacht:
    DDM fiel von Recall 0.75 auf 0.50, EDDM von 0.25 auf 0.00, obwohl ihre
    frueheren Optima im groesseren Raum enthalten waren. Ein Lauf mit 500 statt
    200 Trials aenderte daran nichts -- TPE zieht nur ``n_startup_trials`` = 10
    Zufallspunkte, unabhaengig von der Trial-Zahl, und findet das schmale gute
    Becken im grossen Raum schlicht nicht mehr. Regel daraus: eine Grenze nur
    weiten, wenn das Optimum an ihr klebt.

    Parameters
    ----------
    enqueue : Liste roher Optuna-Parameterdicts, die als Startkandidaten
        eingereiht werden. Gedacht fuer bereits bekannte gute Betriebspunkte:
        TPE zieht nur ``n_startup_trials`` = 10 Zufallspunkte, und ein schmales
        gutes Becken in einem weiten Suchraum wird darin oft nicht getroffen.
        Ein eingereihter Punkt wird reguler bewertet und konkurriert mit den
        uebrigen Trials -- das Ergebnis kann dadurch nie schlechter werden als
        der eingereihte Punkt. Werte ausserhalb der Verteilung werden von Optuna
        mit einer Warnung uebernommen, nicht auf den Rand gezogen.
    err_threshold_bounds : (float, float) | None
        Suchbereich fuer err_threshold bei DDM/EDDM als (lo, hi). Wird None
        uebergeben, greift der Fallback (0.5, 4.0). Empfohlener Ansatz: lo aus
        dem 80. Perzentil des stabilen Fehlers, hi aus dem 99.5. Perzentil
        des Gesamtfehlers (vgl. tune_detector).
    """
    et_lo, et_hi = err_threshold_bounds if err_threshold_bounds is not None else (0.5, 4.0)
    name = name.upper()
    if name == "KSWIN":
        min_inst = trial.suggest_int("min_num_instances", 50, 2000)
        return dict(
            alpha=trial.suggest_float("alpha", 1e-12, 5e-3, log=True),
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
        drift_level = trial.suggest_float("drift_level", 1.5, 12.0)
        return dict(
            drift_level=drift_level,
            warning_level=trial.suggest_float("warning_level", 1.0, drift_level),
            min_num_instances=trial.suggest_int("min_num_instances", 30, 500),
        ), trial.suggest_float("err_threshold", et_lo, et_hi)
    if name == "EDDM":
        alpha = trial.suggest_float("alpha", 0.90, 0.99999)
        return dict(
            alpha=alpha,
            beta=trial.suggest_float("beta", 0.70, alpha),
            min_num_misclassified_instances=trial.suggest_int(
                "min_num_misclassified_instances", 30, 500),
        ), trial.suggest_float("err_threshold", et_lo, et_hi)
    if name == "RMSE":
        window = trial.suggest_int("window", 15, 1000)
        return dict(
            window=window,
            threshold=trial.suggest_float("threshold", 0.5, 10.0),
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
    weights: Tuple[float, float, float] = (1.0, 0.3, 1.0),
    fa_decades: float = 3.0,
    seed: int = 42,
    reset_on_drift: bool = True,
    cooldown: int = 0,
    show_progress_bar: bool = False,
    err_threshold_bounds=None,
    enqueue: List[dict] = None,
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
                             tolerance=tol_eval, n=n_eval, weights=weights,
                             fa_decades=fa_decades)
        for k, v in s.items():
            trial.set_user_attr(k, v)
        return s["score"]

    study = optuna.create_study(
        direction="minimize",
        sampler=optuna.samplers.TPESampler(seed=seed),
    )
    for _p in (enqueue or []):
        study.enqueue_trial(dict(_p), skip_if_exists=True)
    study.optimize(objective, n_trials=n_trials, show_progress_bar=show_progress_bar)
    return study


if __name__ == "__main__":
    # Kleiner Selbsttest auf dem synthetischen Teststrom.
    c, error = synthetic_error_stream()
    print(f"Teststrom: {len(error)} Zeitschritte, Driftbeginn bei k=800")
    for name, (drifts, warnings) in run_all(error).items():
        first = drifts[0] if drifts else None
        print(f"{name:6s}: {len(drifts):2d} Drift(s) | erste Erkennung bei k={first}")
