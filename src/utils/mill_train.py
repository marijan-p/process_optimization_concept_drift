"""Vorverarbeitung und Training des statischen MLP (Kapitel 4).

Kapitel 2 hat das Modell ausgewaehlt und begruendet; hier wird es neu
trainiert, mit denselben Einstellungen, mit denen es an der Anlage laeuft.
Zwei Entscheidungen tragen alles Weitere:

**Skaliert wird auf feste Grenzen**, nicht auf die Daten. :class:`FixedRangeScaler`
liest sie aus ``mill_tags.csv``. Ein Bezugsrahmen, der sich mit dem Datenstrom
mitbewegt, verdeckt genau die Verschiebung, die Kapitel 4 untersucht -- und
``out_of_range`` waere dann nur eine Aussage ueber die Stichprobe statt ueber
den Betrieb.

**Gesplittet wird nach Betriebspunkt**, nicht nach Zeile. Benachbarte
Abtastzeilen eines stationaeren Punktes sind fast identisch; wandert eine ins
Training und eine in die Validierung, misst die Validierung die Interpolation
innerhalb eines Punktes statt die Verallgemeinerung auf einen neuen.

    from src.utils.mill_train import prepare, build_model, fit_model
    X, y, report = prepare(rows)
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

import numpy as np
import pandas as pd

from .mill_io import FEATURES, TAGS, TARGET

__all__ = ["ARCH", "ACT", "EPOCHS", "BATCH", "LR", "VAL_SPLIT", "PATIENCE",
           "THESIS_MIN_DURATION", "SMOOTH_ORDER", "BUTTER_WN", "ROLL_WINDOW",
           "FixedRangeScaler", "balance", "smooth", "thesis_rule", "clean",
           "prepare", "group_split", "build_model", "fit_model"]

#: Zwei verdeckte Schichten zu acht Neuronen -- die Architektur, die auf der
#: Anlage laeuft. 153 Parameter; bei acht Merkmalen und einer glatten
#: Zielfunktion ist das keine Einschraenkung.
ARCH = (8, 8)
ACT = "tanh"
EPOCHS = 500
BATCH = 64
LR = 1e-3
VAL_SPLIT = 0.2
PATIENCE = 50

#: Regel der Vorarbeit fuer Betriebspunkte: mindestens 70 Minuten Dauer. Die
#: eigene Verdichtung laesst schon ab zehn Minuten zu; fuer einen Vergleich mit
#: den dortigen Zahlen muss man nachfiltern.
THESIS_MIN_DURATION = 70.0

#: Glaettung: der Butterworth-Tiefpass schlug in der Vorarbeit den gleitenden
#: Mittelwert ueber alle Modelltypen. Ordnung und Grenzfrequenz sind dort nicht
#: genannt; ``ROLL_WINDOW`` ist die dokumentierte Fensterbreite des
#: Vergleichsverfahrens.
SMOOTH_ORDER = 3
BUTTER_WN = 0.05
ROLL_WINDOW = 5


# --- Skalierung -------------------------------------------------------------
class FixedRangeScaler:
    """Min-Max auf **konfigurierte** Grenzen, nicht auf die Daten gefittet.

    Schnittstelle wie ein sklearn-Skalierer, damit er an dieselbe Stelle passt
    -- aber ``fit`` sieht die Daten gar nicht erst an. Fehlt fuer eine Spalte
    eine Grenze, bricht der Aufbau ab; stillschweigend auf den Datenbereich
    auszuweichen waere der Fehler, den diese Klasse verhindern soll.
    """

    def __init__(self, columns: Sequence[str], tags: pd.DataFrame = None):
        g = (TAGS if tags is None else tags).set_index("name")
        self.columns = list(columns)
        missing = [c for c in self.columns
                   if c not in g.index or not np.isfinite(g.loc[c, "minimum"])
                   or not np.isfinite(g.loc[c, "maximum"])]
        if missing:
            raise KeyError(f"Keine Skalierungsgrenzen fuer: {missing}. Grenzen "
                           "eintragen oder die Spalte nicht als Merkmal fuehren.")
        self.min_ = np.array([float(g.loc[c, "minimum"]) for c in self.columns])
        self.max_ = np.array([float(g.loc[c, "maximum"]) for c in self.columns])

    def fit(self, X=None, y=None):
        return self

    def transform(self, X) -> np.ndarray:
        return (np.asarray(X, float) - self.min_) / (self.max_ - self.min_)

    def fit_transform(self, X, y=None) -> np.ndarray:
        return self.transform(X)

    def inverse_transform(self, X) -> np.ndarray:
        return np.asarray(X, float) * (self.max_ - self.min_) + self.min_

    def out_of_range(self, X) -> np.ndarray:
        """Zeilenweise: liegt ein Wert ausserhalb des Nennbereichs der Anlage?

        Mit festen Grenzen ist das eine physikalische Aussage und taugt damit
        als Erklaerung neben Drift -- eine Extrapolation ist kein Drift, sieht
        im Fehler aber genauso aus.
        """
        V = np.asarray(X, float)
        return ((V < self.min_) | (V > self.max_)).any(axis=1)

    def __repr__(self):
        return f"FixedRangeScaler({len(self.columns)} Spalten, feste Grenzen)"


# --- Vorverarbeitung --------------------------------------------------------
def balance(frames: Sequence[pd.DataFrame], seed: int = 42) -> List[pd.DataFrame]:
    """Gleich viele Zeilen aus jeder Quelle. Ohne das bestimmt die laengste."""
    frames = [f for f in frames if len(f)]
    if not frames:
        return []
    n = min(len(f) for f in frames)
    rng = np.random.default_rng(seed)
    return [f.iloc[np.sort(rng.choice(len(f), n, replace=False))] for f in frames]


def smooth(df: pd.DataFrame, columns: Sequence[str] = None, kind: str = "butter",
           order: int = SMOOTH_ORDER, wn: float = BUTTER_WN,
           window: int = ROLL_WINDOW) -> pd.DataFrame:
    """Glaettet Abtastzeilen -- Butterworth (nullphasig) oder gleitendes Mittel.

    NUR auf Abtastzeilen anwenden. Auf Betriebspunkten, die schon ueber Minuten
    gemittelt sind, glaettet das nichts mehr und verschmiert ueber
    Punktgrenzen hinweg.

    Und auch dort phasenweise aufrufen: ueber eine Sollwertaenderung hinweg zu
    filtern macht aus einer Stufe eine Rampe, also aus einem Ereignis einen
    Uebergang, den es nicht gab::

        tr = pd.concat([smooth(g) for _, g in rows.groupby("bp")])
    """
    from scipy.signal import butter, filtfilt
    out = df.copy()
    cols = [c for c in (columns or FEATURES) if c in out.columns]
    if kind == "roll":
        out[cols] = out[cols].rolling(window, center=True, min_periods=1).mean()
        return out
    if kind != "butter":
        raise ValueError(f"kind muss 'butter' oder 'roll' sein, nicht {kind!r}")
    b, a = butter(order, wn)
    n_min = 3 * max(len(a), len(b))
    for c in cols:
        # Kopie erzwingen: pandas kann eine schreibgeschuetzte Sicht liefern,
        # und filtfilt schreibt in das Ergebnisarray.
        v = np.array(out[c].to_numpy(), dtype=float, copy=True)
        m = np.isfinite(v)
        if m.sum() <= n_min:          # zu kurz fuer filtfilt
            continue
        v[m] = filtfilt(b, a, v[m])
        out[c] = v
    return out


def thesis_rule(df: pd.DataFrame, min_duration: float = THESIS_MIN_DURATION
                ) -> pd.DataFrame:
    """Nur Betriebspunkte, die die Mindestdauer der Vorarbeit erfuellen."""
    if "duration_min" not in df.columns:
        return df
    return df[df["duration_min"] >= min_duration]


def clean(X: np.ndarray, y: np.ndarray) -> Tuple[np.ndarray, np.ndarray, int]:
    """``inf -> NaN``, dann Zeilen mit NaN verwerfen. Nach dem Skalieren."""
    d = np.column_stack([np.asarray(X, float),
                         np.asarray(y, float).reshape(len(y), -1)])
    d = np.where(np.isinf(d), np.nan, d)
    good = ~np.isnan(d).any(axis=1)
    k = X.shape[1]
    return d[good, :k], d[good, k:].ravel(), int((~good).sum())


def prepare(df: pd.DataFrame, label: str = None, scale: bool = True
            ) -> Tuple[np.ndarray, np.ndarray, Dict]:
    """Merkmale und Label aus einem Betriebspunkt- oder Zeilenrahmen.

    Der Bericht nennt jede Zahl, die man spaeter braucht, um zu erklaeren,
    warum weniger Zeilen ankamen als losgeschickt.
    """
    label = label or TARGET
    missing = [c for c in FEATURES + [label] if c not in df.columns]
    if missing:
        raise KeyError(f"Diese Groessen fehlen im Datensatz: {missing}")

    X_raw = df[FEATURES].to_numpy(float)
    y_raw = df[label].to_numpy(float)
    x_scaler, y_scaler = FixedRangeScaler(FEATURES), FixedRangeScaler([label])
    out_of_range = x_scaler.out_of_range(X_raw)
    if scale:
        X = x_scaler.transform(X_raw)
        y = y_scaler.transform(y_raw.reshape(-1, 1)).ravel()
    else:
        X, y = X_raw, y_raw
    X, y, dropped = clean(X, y)

    return X, y, {"n_in": len(df), "n_out": len(X), "dropped": dropped,
                  "n_out_of_range": int(out_of_range.sum()),
                  "features": list(FEATURES), "label": label,
                  "x_scaler": x_scaler, "y_scaler": y_scaler}


def group_split(groups: np.ndarray, share: float = VAL_SPLIT, seed: int = 42
                ) -> np.ndarray:
    """Maske fuer die Validierung, gruppenweise -- nicht zeilenweise."""
    uniq = np.unique(groups)
    rng = np.random.default_rng(seed)
    n = max(1, int(round(share * len(uniq))))
    return np.isin(groups, rng.choice(uniq, size=n, replace=False))


# --- Modell -----------------------------------------------------------------
def build_model(n_features: int, arch: Sequence[int] = ARCH, act: str = ACT,
                lr: float = LR):
    """Statisches MLP: zwei verdeckte Schichten, ``tanh``, linearer Ausgang.

    Als ``Sequential`` und nicht als ``keras.Model``-Unterklasse:
    ``drift_adaptation.clone_compiled`` ruft ``tf.keras.models.clone_model``,
    und das braucht eine Architektur, die sich aus der Konfiguration
    wiederherstellen laesst.

    ``metrics=["mae"]``: MSE optimiert, MAE liest sich in der Einheit der
    Zielgroesse.
    """
    import tensorflow as tf
    layers = [tf.keras.layers.Input(shape=(n_features,))]
    layers += [tf.keras.layers.Dense(u, activation=act) for u in arch]
    layers += [tf.keras.layers.Dense(1, activation="linear")]
    m = tf.keras.Sequential(layers)
    m.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=lr),
              loss="mse", metrics=["mae"])
    return m


def fit_model(model, X, y, groups=None, epochs: int = EPOCHS, batch: int = BATCH,
              seed: int = 42, verbose: int = 2):
    """Training mit gruppenweiser Validierung, fruehem Stoppen, LR-Absenkung."""
    import tensorflow as tf
    tf.keras.utils.set_random_seed(seed)
    rng = np.random.default_rng(seed)
    val = (rng.random(len(X)) < VAL_SPLIT if groups is None
           else group_split(np.asarray(groups), seed=seed))
    perm = rng.permutation(int((~val).sum()))
    X_tr, y_tr = X[~val][perm], y[~val][perm]
    print(f"Training {len(X_tr)} Zeilen / Validierung {int(val.sum())} Zeilen")
    hist = model.fit(
        X_tr, y_tr, epochs=epochs, batch_size=batch, verbose=verbose,
        validation_data=(X[val], y[val]),
        callbacks=[
            tf.keras.callbacks.EarlyStopping(
                monitor="val_loss", patience=PATIENCE, restore_best_weights=True),
            tf.keras.callbacks.ReduceLROnPlateau(
                monitor="val_loss", factor=0.5, patience=PATIENCE // 2, min_lr=1e-5)])
    return model, {k: [float(x) for x in v] for k, v in hist.history.items()}
