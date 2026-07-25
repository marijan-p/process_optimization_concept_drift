# -*- coding: utf-8 -*-
"""thesis_style — Zentrales Farb- und Stilkonzept fuer alle Plots der Dissertation.

Leitgedanke (vgl. Wong 2011, Nature Methods; Crameri et al. 2020, Nature Comms):
Es gibt nicht genug gut unterscheidbare Farben fuer jedes einzelne Signal.
Deshalb wird Farbe NICHT pro Signal, sondern pro *semantischer Rolle* vergeben,
die ueber die gesamte Arbeit konsistent bleibt. Zusaetzliche Information wird
ueber weitere Kanaele kodiert (Linienstil, Alpha, Marker, Panel) -> redundante,
auch in Graustufen lesbare, farbfehlsichtigkeitssichere Darstellung.

KANAELE (loest die Farbknappheit auf):
  * Concept Drift -> KANAL: Farbe (Hauptkanal, ueberall konsistent)
        drift_free      = blau    (ohne Drift)
        drift_afflicted = orange  (mit Drift)
        adapted         = violett (nach Adaption)
  * Diskrete Signale -> gefuellte Marker (ts.scatter(role)); Linien bleiben den
    kontinuierlichen Groessen c[k] (drift_signal) und Setpoints vorbehalten.
  * Rauschen -> eigene Akzentfarbe, LOKAL: Wo rauschfrei UND verrauscht direkt
    verglichen werden (Rausch-Plot, nur drift-freie Signale), bekommt das
    verrauschte Signal die Rolle "noise" (grau). Bewusst lokal, da dort die
    Farbachse nicht mit Drift belegt ist; in Plots mit beiden Drift-Zustaenden
    bleibt Farbe == Drift.

Weitere eigenstaendige Rollen:
  * gruen    -> Driftursache selbst (drift_signal c[k], drift_event)
  * schwarz  -> treibendes Fuehrungssignal / Setpoint als Kontext (setpoint)
  * grau     -> verrauschtes Signal im lokalen Rausch-Vergleich (noise)
  * hellblau -> algorithmische Detektion (detection)
  * violett  -> adaptierter Zustand (adapted), dritte Option der Drift-Achse

Verwendung:
    import thesis_style as ts
    fig_width_in = ts.apply_rc()                      # rcParams + Textbreite
    ax.scatter(t, u_clean, **ts.scatter("drift_free"))         # rauschfreie Referenz
    ax.scatter(t, u_noisy, **ts.scatter("noise", alpha=0.85))  # verrauscht (lokal)
    ax.plot(t, c_k,        **ts.line("drift_signal"))          # kontinuierlich
    ax.axvline(x=ts0,      **ts.vline("drift_event"))
    ts.swatch()                                       # Farbtafel zur Kontrolle
"""

from __future__ import annotations

# Hinweis: matplotlib wird bewusst NICHT auf Modulebene importiert, sondern erst
# innerhalb der Funktionen (lazy). So loest "import thesis_style" selbst keine
# matplotlib-Initialisierung aus -> kein Risiko fuer den Fehler
# "module 'matplotlib' has no attribute 'get_data_path'" (partielle/zirkulaere
# Initialisierung) beim blossen Import des Stils.

# --------------------------------------------------------------------------- #
# 1) Basis-Palette (seaborn "colorblind" / Okabe-Ito-Familie) — nur benannte
#    Farben, damit im Code nie ein nackter Hex-Wert steht.
# --------------------------------------------------------------------------- #
PALETTE = {
    "black":    "#000000",
    "grey":     "#4D4D4D",
    "blue":     "#0173b2",
    "vermilion":"#d55e00",
    "green":    "#029e73",
    "skyblue":  "#56b4e9",
    "purple":   "#cc78bc",
    "amber":    "#de8f05",
    "tan":      "#ca9161",
}

# --------------------------------------------------------------------------- #
# 2) Semantische Rollen -> vollstaendiger Stil (Farbe + redundante Kanaele).
#    Pro Rolle ist neben der Farbe auch der bevorzugte Linien-/Markerstil
#    hinterlegt, damit "gleiche Groesse, anderer Zustand" sich auch ohne Farbe
#    unterscheiden laesst.
# --------------------------------------------------------------------------- #
ROLES = {
    # --- Achse "Concept Drift" (Kanal Farbe); Rauschen ueber clean()/noisy() -- #
    "drift_free":     dict(color=PALETTE["blue"],      linestyle="-",  marker="o",  alpha=1.0),
    "drift_afflicted":dict(color=PALETTE["vermilion"], linestyle="-",  marker="o",  alpha=1.0),
    # Dritter Zustand der Concept-Drift-Achse: nach erfolgter Adaption. Eine
    # einzige Rolle fuer alle Adaptionsstrategien (keine Unterscheidung zwischen
    # blind/informed/combined), farblich von drift-frei und drift-behaftet
    # abgesetzt (violett). Setpoint nutzt schwarz, noise nutzt grau.
    "adapted":        dict(color=PALETTE["purple"],     linestyle="--", marker="D",  alpha=1.0),
    # --- treibendes Fuehrungssignal / Setpoint als Kontext ---------------- #
    "setpoint":       dict(color=PALETTE["black"],     linestyle="--", marker=None, alpha=1.0),
    # --- Driftursache ----------------------------------------------------- #
    "drift_signal":   dict(color=PALETTE["green"],     linestyle="-",  marker=None, alpha=0.9),
    "drift_event":    dict(color=PALETTE["green"],     linestyle="--", marker=None, alpha=0.6),
    # --- algorithmische Detektion ----------------------------------------- #
    "detection":      dict(color=PALETTE["skyblue"],   linestyle=":",  marker=None, alpha=1.0),
    # --- verrauschtes Signal im LOKALEN Rausch-Vergleich (nur drift-frei) -- #
    "noise":          dict(color=PALETTE["grey"],      linestyle="-",  marker="o",  alpha=1.0),
    # --- optionaler Hervorhebungsakzent ----------------------------------- #
    "highlight":      dict(color=PALETTE["amber"],     linestyle="-",  marker="D",  alpha=1.0),
}

# Mehrere drift-behaftete Varianten EINER Groesse (z. B. PT1: T-, K-, T&K-Einfluss):
# alle in derselben Farbe (drift_afflicted), Unterscheidung NUR ueber die
# Markerform. Keine Dreiecke.
DRIFT_VARIANT_MARKERS = ["o", "x", "D"]

# Reine Kategorial-Liste fuer echte Nominalskalen ohne semantische Rolle.
CATEGORICAL = [PALETTE["blue"], PALETTE["vermilion"], PALETTE["green"],
               PALETTE["purple"], PALETTE["skyblue"], PALETTE["amber"],
               PALETTE["tan"], PALETTE["grey"]]


# --------------------------------------------------------------------------- #
# 3) Zugriffs-Helfer
# --------------------------------------------------------------------------- #
def color(role: str) -> str:
    """Nur die Farbe einer Rolle."""
    return ROLES[role]["color"]


def style(role: str, **overrides) -> dict:
    """Vollstaendiges Stil-Dict einer Rolle (color/linestyle/alpha/marker)."""
    s = dict(ROLES[role])
    s.update(overrides)
    return s


def line(role: str, **overrides) -> dict:
    """Kwargs fuer ax.plot(): color, linestyle, alpha (ohne marker)."""
    s = ROLES[role]
    out = dict(color=s["color"], linestyle=s["linestyle"], alpha=s["alpha"])
    out.update(overrides)
    return out


def scatter(role: str, s: int = 6, **overrides) -> dict:
    """Kwargs fuer ax.scatter(): color, alpha, marker, s."""
    r = ROLES[role]
    out = dict(color=r["color"], alpha=r["alpha"], s=s)
    if r["marker"] is not None:
        out["marker"] = r["marker"]
    out.update(overrides)
    return out


def vline(role: str, lw: float = 1.0, **overrides) -> dict:
    """Kwargs fuer ax.axvline(): color, linestyle, alpha, lw."""
    r = ROLES[role]
    out = dict(color=r["color"], linestyle=r["linestyle"], alpha=r["alpha"], lw=lw)
    out.update(overrides)
    return out


# Bequemer dict-artiger Zugriff: ts.C["drift_free"] -> Hexfarbe
class _ColorView:
    def __getitem__(self, role): return color(role)
    def __getattr__(self, role): return color(role)
C = _ColorView()


# --------------------------------------------------------------------------- #
# 4) Globales matplotlib-Stylesheet (ersetzt das per-Notebook rcParams.update)
# --------------------------------------------------------------------------- #
TEXTWIDTH_PT = 458.08954        # \the\textwidth der Diss-Vorlage
INCH_PER_PT = 1.0 / 72.27


def apply_rc(width_scale: float = 1.0) -> float:
    """Setzt die rcParams der Arbeit und gibt die Textbreite in Zoll zurueck.

    Ersetzt die bisherige manuelle rcParams.update-Zelle in den Notebooks.
    """
    # pyplot zuerst importieren -> erzwingt die vollstaendige Initialisierung von
    # matplotlib. Verhindert "module 'matplotlib' has no attribute 'get_data_path'",
    # das auftreten kann, wenn rcParams als allererste matplotlib-Operation im
    # Kernel angefasst wird.
    import matplotlib.pyplot as plt
    from cycler import cycler

    plt.rcParams.update({
        "font.size": 11,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "legend.fontsize": 10,
        "lines.linewidth": 2.0,
        "grid.alpha": 0.25,
        "axes.spines.top": False,
        "axes.spines.right": False,
        # Standard-Farbzyklus = Kategorial-Liste (falls einmal ohne Rolle geplottet)
        "axes.prop_cycle": cycler(color=CATEGORICAL),
    })
    return TEXTWIDTH_PT * INCH_PER_PT * width_scale


# --------------------------------------------------------------------------- #
# 5) Kontroll-Tafel
# --------------------------------------------------------------------------- #
def swatch():
    """Zeigt alle Rollen mit Farbe und Linienstil als Legende-Tafel."""
    import matplotlib.pyplot as plt
    roles = list(ROLES)
    fig, ax = plt.subplots(figsize=(7, 0.5 * len(roles) + 1))
    for i, r in enumerate(reversed(roles)):
        st = ROLES[r]
        y = i
        ax.plot([0, 1], [y, y], color=st["color"], linestyle=st["linestyle"],
                lw=2.5, alpha=st["alpha"])
        if st["marker"]:
            ax.scatter([0.5], [y], color=st["color"], marker=st["marker"],
                       s=40, alpha=st["alpha"], zorder=3)
        ax.text(1.1, y, f"{r}  ({st['color']})", va="center", fontsize=10)
    ax.set_xlim(0, 3); ax.set_ylim(-1, len(roles))
    ax.axis("off"); ax.set_title("thesis_style — Rollen", loc="left")
    plt.tight_layout(); plt.show()


if __name__ == "__main__":
    apply_rc()
    swatch()
