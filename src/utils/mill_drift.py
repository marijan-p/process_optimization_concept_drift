"""Tuning von Detektion und Adaption mit Suchraumgrenzen in Tagen (Kapitel 4).

``drift_detection`` und ``drift_adaptation`` bleiben unveraendert: ihre Suchraeume
(``_suggest_params``, ``_suggest_adapt_params``) werden hier ueber einen Trial
aufgerufen, der einzelne Grenzen ersetzt. Die Grenzen kommen aus dem Notebook,
dort in Tagen festgelegt und ueber ``mill_io.days_to_points`` umgerechnet. Sie
gehoeren in den Cache-Schluessel des Aufrufers, die Suchraum-Kennungen aus
Kapitel 3 aendern sich dadurch nicht.
"""

from __future__ import annotations

import contextlib
import warnings
from typing import Callable, Dict, Sequence, Tuple

import numpy as np

import drift_adaptation as da
import drift_detection as dd

__all__ = ["BoundedTrial", "points_bounds", "bounds_position", "tune_detector",
           "tune_adaptation", "holdout_tracker"]


class BoundedTrial:
    """Optuna-Trial, der fuer benannte Parameter eigene Grenzen einsetzt."""

    def __init__(self, trial, bounds: Dict[str, Tuple[float, float]]):
        self._trial, self._bounds = trial, dict(bounds or {})

    def _range(self, name, low, high):
        return self._bounds.get(name, (low, high))

    def suggest_int(self, name, low, high, **kwargs):
        lo, hi = self._range(name, low, high)
        return self._trial.suggest_int(name, int(lo), int(hi), **kwargs)

    def suggest_float(self, name, low, high, **kwargs):
        lo, hi = self._range(name, low, high)
        return self._trial.suggest_float(name, float(lo), float(hi), **kwargs)

    def __getattr__(self, attr):
        return getattr(self._trial, attr)


def points_bounds(days: Dict[str, Tuple[float, float]], to_points: Callable[[float], int],
                  minimum: Dict[str, int] = None) -> Dict[str, Tuple[int, int]]:
    """Grenzen in Tagen -> Grenzen in Punkten; ``minimum`` haelt strukturelle Untergrenzen."""
    minimum = minimum or {}
    out = {}
    for name, (lo, hi) in days.items():
        lo_p = max(int(minimum.get(name, 1)), to_points(lo))
        out[name] = (lo_p, max(lo_p + 1, to_points(hi)))
    return out


def bounds_position(params: dict, bounds: Dict[str, Tuple[float, float]]) -> Dict[str, float]:
    """Lage jedes Optimums in seinem Intervall (0 = Unter-, 1 = Obergrenze)."""
    return {k: float((params[k] - lo) / (hi - lo))
            for k, (lo, hi) in bounds.items() if k in params and hi > lo}


def tune_detector(name: str, error: Sequence[float], sudden_idx: Sequence[int],
                  drift_active: Sequence[bool], tolerance: int, *,
                  bounds: Dict[str, Tuple[float, float]] = None, n_trials: int = 50,
                  downsample: int = 1, weights=(1.0, 0.3, 1.0), fa_decades: float = 3.0,
                  seed: int = 42, cooldown: int = 0, err_threshold_bounds=None,
                  callbacks: list = None):
    """Wie ``dd.tune_detector``, mit ``bounds`` (Punkte des Tuningrasters) je Parameter."""
    import optuna

    name = name.upper()
    err = np.asarray(error, float)
    active = np.asarray(drift_active, bool)
    if err_threshold_bounds is None and name in dd.ERROR_RATE_DETECTORS:
        stable = np.abs(err[~active])
        lo = float(np.percentile(stable, 60)) if stable.size else 0.5
        hi = float(np.percentile(np.abs(err), 99.5))
        err_threshold_bounds = (lo if lo < hi else max(0.0, 0.5 * hi), hi)

    q = max(1, int(downsample))
    err_eval, active_eval = err[::q], active[::q]
    n_eval = len(err_eval)
    sudden_eval = sorted({int(s) // q for s in sudden_idx if 0 <= int(s) // q < n_eval})
    tol_eval, cd_eval = max(1, tolerance // q), cooldown // q

    def objective(trial):
        params, et = dd._suggest_params(name, BoundedTrial(trial, bounds), err_threshold_bounds)
        drifts, _ = dd.run_detector(name, dd.build_detector(name, **params), err_eval,
                                    err_threshold=(et if et is not None else 0.5),
                                    cooldown=cd_eval)
        s = dd.score_detections(drifts, sudden_eval, active_eval, tolerance=tol_eval,
                                n=n_eval, weights=weights, fa_decades=fa_decades)
        for k, v in s.items():
            trial.set_user_attr(k, v)
        return s["score"]

    study = optuna.create_study(direction="minimize",
                                sampler=optuna.samplers.TPESampler(seed=seed))
    study.optimize(objective, n_trials=n_trials, callbacks=callbacks)
    return study


def tune_adaptation(strategy: str, base, X, y, *, fixed: dict,
                    bounds: Dict[str, Tuple[float, float]] = None,
                    detector_factory=None, rmse_baseline: float = None,
                    n_trials: int = 20, weights=(1.0, 0.1), seed: int = 42,
                    enqueue: list = None, t_stat: float = 1.0,
                    base_params: dict = None, callbacks: list = None):
    """Wie ``da.tune_adaptation``, mit ``bounds`` (Punkte des Tuningrasters) je Parameter."""
    import optuna

    strategy = strategy.lower()
    mode, selector = da.split_strategy(strategy)
    if base_params is not None and selector != "recurrence":
        raise ValueError(f"base_params verlangt eine Strategie mit {da.REC_SUFFIX!r}")
    chunk = int(fixed.get("chunk", 144))
    n_units = int(np.ceil(len(X) / chunk))
    if rmse_baseline is None:
        res = da.run_adaptation(base, X, y, mode="baseline", **fixed)
        rmse_baseline = float(np.sqrt(np.mean(np.asarray(res["errors"], float) ** 2)))
    active = mode in ("informed", "combined") and detector_factory is not None
    det_name = getattr(detector_factory(), "name", None) if active else None

    def objective(trial):
        bounded = BoundedTrial(trial, bounds)
        if base_params is None:
            params = da._suggest_adapt_params(strategy, bounded, chunk=chunk, det_name=det_name)
        else:
            params = {**base_params, **da._suggest_selector_params(bounded, chunk=chunk)}
        detector, params = da.apply_det_params(detector_factory() if active else None, params)
        params = da.resolve_cooldown(params, t_stat)
        res = da.run_adaptation(base, X, y, mode=strategy, detector=detector,
                                **{**fixed, **params})
        s = da.score_adaptation(res, rmse_baseline, n_units, weights=weights)
        for k, v in s.items():
            trial.set_user_attr(k, v)
        return s["score"]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", optuna.exceptions.ExperimentalWarning)
        sampler = optuna.samplers.TPESampler(seed=seed, **da.TPE_SETTINGS)
    study = optuna.create_study(direction="minimize", sampler=sampler)
    for p in (enqueue or []):
        # "TTF" ist nur fuer blind zulaessig; als Warmstart einer aktiven Strategie bricht es ab
        if mode != "blind" and p.get("freeze") == "TTF":
            p = {k: v for k, v in p.items() if k != "freeze"}
        study.enqueue_trial(p, skip_if_exists=True)
    study.optimize(objective, n_trials=n_trials, callbacks=callbacks)
    return study, rmse_baseline


class _Holdout:
    def __init__(self, X, y):
        self.X, self.y = X, np.asarray(y, float)
        self.model, self.trace = None, []

    def rmse(self, model) -> float:
        p = np.asarray(model(self.X, training=False)).ravel()
        return float(np.sqrt(np.mean((self.y - p) ** 2)))

    def final_rmse(self, base) -> float:
        return self.rmse(self.model if self.model is not None else base)


@contextlib.contextmanager
def holdout_tracker(X, y):
    """Schneidet waehrend ``da.run_adaptation`` den Fehler auf einem Holdout mit.

    ``trace`` haelt nach jedem Nachtraining die Zahl der bis dahin gelaufenen
    Nachtrainings und den Holdout-RMSE, ``final_rmse`` den Endstand. Der Holdout
    geht nie in ein Training ein.
    """
    hold = _Holdout(X, y)
    clone, fit = da.clone_compiled, da.incremental_fit

    def _clone(*args, **kwargs):
        hold.model = clone(*args, **kwargs)
        return hold.model

    def _fit(model, *args, **kwargs):
        hold.model = fit(model, *args, **kwargs)
        hold.trace.append((len(hold.trace) + 1, hold.rmse(hold.model)))
        return hold.model

    da.clone_compiled, da.incremental_fit = _clone, _fit
    try:
        yield hold
    finally:
        da.clone_compiled, da.incremental_fit = clone, fit
