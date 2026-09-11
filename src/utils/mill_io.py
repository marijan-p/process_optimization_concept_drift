"""Datenzugang fuer den Muehlenanwendungsfall (Kapitel 4).

Liest die aufbereiteten Betriebspunkte und stellt die Kenngroessen bereit, die
Kapitel 4 ueber den Strom braucht. Die Aufbereitung selbst -- Verdichtung der
Rohdaten zu Betriebspunkten, Auswahl der Groessen, Verschiebung der Zeitachse --
ist abgeschlossen und nicht Teil dieses Moduls.

**Das Vokabular kommt aus ``mill_tags.csv``** neben dieser Datei: Namen,
Einheiten und die Skalierungsgrenzen, mit denen die Modelle an der Anlage
arbeiten. Eine Quelle der Wahrheit, geteilt mit ``mill_train``.

**Das Datenverzeichnis wird uebergeben**, nicht erraten. Jede Ladefunktion
nimmt es als erstes Argument; wo die Daten liegen, entscheidet das Notebook --
es muss die Repository-Wurzel ohnehin kennen, bevor es dieses Modul ueberhaupt
importieren kann.
"""

from __future__ import annotations

import pathlib
from typing import List, Sequence

import numpy as np
import pandas as pd

__all__ = [
    "TAGS", "FEATURES", "TARGET", "CONTEXT", "SOURCES",
    "load_operating_points", "load_production", "load_doe",
    "load_calibrations", "calibration_dates",
    "range_report", "gaps", "points_per_day", "days_to_points",
    "describe_stream", "NOISE_TOL",
]


# --------------------------------------------------------------------------- #
# Vokabular
# --------------------------------------------------------------------------- #
TAGS_CSV = pathlib.Path(__file__).with_name("mill_tags.csv")

#: Namen, Rollen, Einheiten, Skalierungsgrenzen.
TAGS: pd.DataFrame = pd.read_csv(TAGS_CSV)

#: Die acht Merkmale des Anlagenmodells.
FEATURES: List[str] = TAGS.loc[TAGS["role"] == "feature", "name"].tolist()
#: Die Zielgroesse: Summe der drei Antriebsleistungen je Aufgabemenge [kWh/t].
TARGET: str = TAGS.loc[TAGS["role"] == "label", "name"].iloc[0]
#: Verschleiss- und Kalibrierkontext -- kein Modelleingang.
CONTEXT: List[str] = TAGS.loc[TAGS["role"] == "context", "name"].tolist()

SOURCES = ("production", "doe1", "doe2")


# --------------------------------------------------------------------------- #
# Betriebspunkte lesen
# --------------------------------------------------------------------------- #
def _select(df: pd.DataFrame, roles=("feature", "label", "context"),
            keep: Sequence[str] = ()) -> pd.DataFrame:
    """Spalten der genannten Rollen, ``keep`` unveraendert davor.

    Fehlt ein Merkmal oder das Label, bricht die Auswahl ab: ein stillschweigend
    um eine Spalte kuerzerer Merkmalssatz ist der Fehler, den man erst drei
    Auswertungen spaeter bemerkt.
    """
    want = TAGS.loc[TAGS["role"].isin(roles), "name"].tolist()
    missing = [n for n in want
               if n not in df.columns
               and TAGS.loc[TAGS["name"] == n, "role"].iloc[0] != "context"]
    if missing:
        raise KeyError(f"Diese Groessen fehlen im Datensatz: {missing}")
    cols = [c for c in keep if c in df.columns] + [n for n in want if n in df.columns]
    return df[cols]


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Zeitindex, Reihenfolge: Metadaten, Merkmale, Label, Kontext."""
    df = df.dropna(subset=["start"]).sort_values("start")
    df = df.set_index(pd.DatetimeIndex(df["start"], name="start")).drop(columns=["start"])
    front = [c for c in ("end", "duration_min") if c in df.columns]
    feats = [c for c in FEATURES if c in df.columns]
    rest = [c for c in df.columns if c not in front + feats + [TARGET]]
    return df[front + feats + [TARGET] + rest]


def _from_points(raw: pd.DataFrame) -> pd.DataFrame:
    raw.columns = [str(c).strip() for c in raw.columns]
    meta = [c for c in raw.columns if c not in FEATURES + CONTEXT + [TARGET]]
    d = _select(raw, keep=meta).copy()
    d["start"] = pd.to_datetime(d["start"], errors="coerce")
    if "end" in d.columns:
        d["end"] = pd.to_datetime(d["end"], errors="coerce")
    return _finalize(d)


def load_production(data_dir, name="operation_points_production.csv") -> pd.DataFrame:
    """Der Produktionsstrom: stationaere Betriebspunkte ueber knapp fuenf Jahre.

    Die Fenster-Metadaten (``duration_min``, ``running_share``, ``nominal_hz``,
    ``source`` ...) bleiben erhalten; Kapitel 4 filtert und erklaert damit.
    """
    path = pathlib.Path(data_dir) / name
    if not path.exists():
        raise FileNotFoundError(f"{path} nicht gefunden.")
    return _from_points(pd.read_csv(path, low_memory=False))


def load_doe(data_dir, which="1", level="points") -> pd.DataFrame:
    """Eine Feldexperiment-Kampagne, als Betriebspunkte oder als Rohzeilen.

    level="points"
        Ein Mittelwert je gefahrenem Betriebspunkt.
    level="rows"
        Alle Abtastzeilen der Segmente, mit Spalte ``bp`` je Betriebspunkt.
        Das ist der Trainingsdatensatz des statischen MLP -- auf achtzehn
        Mittelwerten waere ein Netz nicht trainierbar.
    """
    if level not in ("points", "rows"):
        raise ValueError(f"level={level!r}, erwartet 'points' oder 'rows'")
    which = str(which)
    d = pathlib.Path(data_dir) / f"doe{which}"
    if not d.exists():
        raise FileNotFoundError(f"{d} nicht gefunden.")

    if level == "points":
        f = d / f"operation_points_doe{which}.csv"
        if not f.exists():
            raise FileNotFoundError(f"{f} nicht gefunden.")
        out = _from_points(pd.read_csv(f))
        out["doe"] = which
        return out

    files = sorted((d / "segments").glob("*.csv")) or \
        sorted((d / "segments").glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"Keine Segmente in {d / 'segments'}.")
    parts = []
    for f in files:
        g = pd.read_parquet(f) if f.suffix == ".parquet" else pd.read_csv(f)
        if "time" in g.columns:
            g = g.set_index(pd.DatetimeIndex(pd.to_datetime(g["time"]))).drop(columns=["time"])
        g.index.name = "time"
        g["bp"] = f.stem
        parts.append(g)
    out = pd.concat(parts).sort_index()
    out["doe"] = which
    return out


def load_operating_points(data_dir, source="production", **kw) -> pd.DataFrame:
    """Betriebspunkte einer Quelle, immer im selben Schema."""
    source = str(source).lower()
    if source == "production":
        return load_production(data_dir, **kw)
    if source in ("doe1", "doe2"):
        return load_doe(data_dir, source[-1], **kw)
    raise ValueError(f"source={source!r}, erwartet {SOURCES}")


# --------------------------------------------------------------------------- #
# Kalibrierungen
# --------------------------------------------------------------------------- #
def load_calibrations(data_dir, name="calibration_events.csv") -> pd.DataFrame:
    """Jede Nullsetzung eines Walzen-Offsets, eine Zeile je Walze.

    Der Offset wird bei der Wartung auf null gesetzt, wenn die Walzen auf dem
    Teller liegen. Jede Aenderung ist ein protokollierter Schreibvorgang der
    Steuerung -- kein aus dem Signal geschaetzter Zeitpunkt.
    """
    path = pathlib.Path(data_dir) / name
    if not path.exists():
        raise FileNotFoundError(f"{path} nicht gefunden.")
    d = pd.read_csv(path).rename(columns={"datierbar": "datable"})
    for c in ("time", "not_before", "not_after", "time_exact"):
        if c in d.columns:
            d[c] = pd.to_datetime(d[c], errors="coerce")
    return d.sort_values("time").reset_index(drop=True)


def calibration_dates(data_dir, datable_only=True, **kw) -> List[pd.Timestamp]:
    """Ein Zeitpunkt je Wartungskampagne -- die Ereignisreferenz des Kapitels.

    ``datable_only`` laesst Kampagnen weg, deren Zeitstempel nur eine obere
    Schranke ist, weil die Aenderung in eine Datenluecke fiel.
    """
    d = load_calibrations(data_dir, **kw)
    if datable_only and "datable" in d.columns:
        d = d[d["datable"].astype(str).str.lower().isin(("true", "1"))]
    if "campaign" in d.columns and len(d):
        return [pd.Timestamp(t) for t in d.groupby("campaign")["time"].min()]
    return [pd.Timestamp(t) for t in d["time"].unique()]


# --------------------------------------------------------------------------- #
# Kenngroessen des Stroms
# --------------------------------------------------------------------------- #
#: Ab welcher Ueberschreitung eine Grenzverletzung mehr ist als Rauschen am
#: Anschlag -- Anteil der Spannweite.
NOISE_TOL = 0.01


def range_report(df: pd.DataFrame, features: Sequence[str] = None,
                 noise_tol: float = NOISE_TOL) -> pd.DataFrame:
    """Deckt der konfigurierte Nennbereich den gefahrenen Betrieb noch ab?

    Die Skalierung ist nicht auf die Daten gefittet, sondern kommt aus
    ``mill_tags.csv`` -- denselben Grenzen, mit denen die Modelle an der Anlage
    arbeiten. Eine Ueberschreitung ist damit eine Aussage ueber den Betrieb und
    keine Eigenschaft der Stichprobe.

    ``kind`` trennt die Ursachen: *Betrieb ueber Nennbereich* (viele Fenster,
    deutliche Ueberschreitung), *Anschlagrauschen* (unter ``noise_tol`` der
    Spannweite) und *Stillstandsfenster* (Werte unter dem Minimum).
    """
    features = list(features or FEATURES)
    g = TAGS.set_index("name")
    rows = []
    for f in features:
        if f not in df.columns:
            continue
        lo, hi = float(g.loc[f, "minimum"]), float(g.loc[f, "maximum"])
        v = df[f].dropna()
        span = hi - lo
        n_below, n_above = int((v < lo).sum()), int((v > hi).sum())
        excess = max(float(v.max()) - hi, 0.0) / span if len(v) else 0.0
        deficit = max(lo - float(v.min()), 0.0) / span if len(v) else 0.0
        if not (n_below or n_above):
            kind = "-"
        elif max(excess, deficit) < noise_tol:
            kind = "Anschlagrauschen"
        elif n_above and excess >= noise_tol:
            kind = "Betrieb ueber Nennbereich"
        else:
            kind = "Stillstandsfenster"
        rows.append({
            "name": f, "unit": g.loc[f, "unit"],
            "range_min": lo, "range_max": hi,
            "observed_min": float(v.min()) if len(v) else np.nan,
            "observed_max": float(v.max()) if len(v) else np.nan,
            "n_below": n_below, "n_above": n_above,
            "share_pct": 100.0 * (n_below + n_above) / max(len(df), 1),
            "scale_ratio": (float(v.max()) - lo) / span if len(v) else np.nan,
            "kind": kind,
        })
    return pd.DataFrame(rows)


def gaps(df: pd.DataFrame, min_days: float = 1.0) -> pd.DataFrame:
    """Zeitraeume ohne einen einzigen Betriebspunkt.

    Kapitel 3 rechnet Fenster in Sample-Zahlen. Ein Fenster von 32 Punkten sind
    hier gut zwei Tage -- es kann aber auch ueber ein mehrtaegiges Loch reichen
    und dann zwei Zustaende vergleichen, zwischen denen Wochen liegen. Wer
    Fenster in Punkten bildet, legt diese Tabelle daneben.
    """
    idx = pd.DatetimeIndex(df.index).sort_values()
    d = pd.Series(idx).diff().dt.total_seconds() / 86400.0
    m = (d >= min_days).to_numpy()[1:]
    if not m.any():
        return pd.DataFrame(columns=["von", "bis", "tage"])
    out = pd.DataFrame({"von": idx[:-1][m], "bis": idx[1:][m]})
    out["tage"] = (out["bis"] - out["von"]).dt.total_seconds() / 86400.0
    return out.sort_values("tage", ascending=False).reset_index(drop=True)


def points_per_day(index) -> float:
    idx = pd.DatetimeIndex(index)
    span = (idx[-1] - idx[0]).total_seconds() / 86400.0
    return len(idx) / span if span > 0 else float("nan")


def days_to_points(days: float, index) -> int:
    """Rechnet eine Zeitspanne in eine Punktzahl des Stroms um.

    Der einzige zulaessige Weg, Fenster und Toleranzen aus Kapitel 3 zu
    uebertragen: dort sind es Sample-Zahlen auf aequidistantem Raster, hier
    kommen die Punkte unregelmaessig an.
    """
    return max(1, int(round(days * points_per_day(index))))


def describe_stream(df: pd.DataFrame, target=None) -> pd.Series:
    """Kenngroessen des Stroms fuer Konsole, JSON und Makros."""
    target = target or TARGET
    idx = df.index
    g = pd.Series(idx).diff().dt.total_seconds().div(86400.0).dropna()
    return pd.Series({
        "n_points": len(df),
        "t_start": idx[0], "t_end": idx[-1],
        "span_days": (idx[-1] - idx[0]).total_seconds() / 86400.0,
        "points_per_day": points_per_day(idx),
        "gap_median_days": float(g.median()) if len(g) else np.nan,
        "gap_max_days": float(g.max()) if len(g) else np.nan,
        "duration_median_min": float(df["duration_min"].median())
        if "duration_min" in df else np.nan,
        "target_mean": float(df[target].mean()),
        "target_std": float(df[target].std()),
        "n_missing": int(df[[c for c in FEATURES if c in df.columns]]
                         .isna().any(axis=1).sum()),
    })
