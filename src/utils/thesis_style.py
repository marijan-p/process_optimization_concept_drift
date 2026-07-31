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
    # --- Box-/Statistik-Overlay (z. B. Boxplot ueber Violinplot) ---------- #
    "box":            dict(color=PALETTE["grey"],      linestyle="-",  marker=None, alpha=1.0),
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

# ColorBrewer/seaborn "Set2" (erste sechs Farben, fest hinterlegt statt seaborn-
# Abhaengigkeit). Genutzt fuer reine Nominalskalen mit vielen Kategorien, bei denen
# die Rollen-Semantik nicht greift (z. B. Modellarchitekturen im model_comparison).
SET2 = ["#66c2a5", "#fc8d62", "#8da0cb", "#e78ac3", "#a6d854", "#ffd92f"]


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


def text_width(width_scale: float = 1.0) -> float:
    """Reine Geometrie: Textbreite der Diss-Vorlage in Zoll, OHNE rcParams-Nebenwirkung.

    Bewusst vom Styling getrennt (im Gegensatz zu ``fig_width``), damit Notebooks mit
    eigenem Theme (z. B. seaborn/whitegrid) nur die Breite beziehen koennen, ohne den
    Diss-Stil (Spines aus, eigene Fonts) aufzuzwingen.
    """
    return TEXTWIDTH_PT * INCH_PER_PT * width_scale


def fig_width(width_scale: float = 1.0) -> float:
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
    return text_width(width_scale)


def violin_box(data, x, y, *, order=None, palette=None, box_color=None,
               box_width=0.12, ax=None, figsize=None):
    """Kombinierter Violin- (Verteilung) + schmaler Box-Overlay (Median/Quartile)
    fuer eine kategoriale x-Achse — der arbeitsweit einheitliche Verteilungsplot.

    Zeichnet unter den aktuell gesetzten rcParams (i. d. R. via ``fig_width``); ruft
    KEIN eigenes Theme und SPEICHERT NICHT — Achsentitel, Figure-Groesse und Ablage
    bleiben beim Aufrufer, da die Notebooks sich darin unterscheiden. Farben je
    Kategorie aus ``palette`` (Default ``SET2``), Box-Overlay in ``box_color``
    (Default Rolle ``box``), Median in Weiss; horizontales Hilfsgitter inklusive.

    data : long-form DataFrame; ``x`` kategorial, ``y`` numerisch (Spaltennamen).
    order : Kategorienreihenfolge. palette : Farbliste. box_width : Box-Breite
    (z. B. schmaler bei vielen Kategorien). ax / figsize : in vorhandene Achse
    zeichnen bzw. neue Figure dieser Groesse anlegen.

    Gibt ``(fig, ax)`` zurueck.
    """
    import matplotlib.pyplot as plt
    import seaborn as sns

    if ax is None:
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    if palette is None:
        palette = SET2
    if order is not None and isinstance(palette, (list, tuple)) and len(palette) > len(order):
        palette = list(palette)[:len(order)]
    if box_color is None:
        box_color = color("box")

    sns.violinplot(data=data, x=x, y=y, order=order,
                   hue=x, legend=False, palette=palette,
                   cut=0, inner=None, ax=ax)
    sns.boxplot(data=data, x=x, y=y, order=order,
                width=box_width, fill=True, showcaps=True, showfliers=False,
                boxprops=dict(facecolor=box_color, color=box_color),
                medianprops={"color": "w", "linewidth": 2},
                whiskerprops={"linewidth": 1.5, "color": box_color},
                capprops={"color": box_color}, ax=ax)
    ax.grid(True, axis="y", alpha=0.2)
    return fig, ax


def _symlog_ticks(ylim, linthresh):
    """Dekaden-Ticks fuer eine symlog-Achse: ..., -10^1, 0, 10^1, ... innerhalb ylim."""
    import numpy as np
    lo, hi = ylim
    k0 = max(1, int(np.ceil(np.log10(linthresh))))
    neg = [-(10.0 ** k) for k in range(k0, 99) if 10.0 ** k <= abs(lo) + 1e-9]
    pos = [+(10.0 ** k) for k in range(k0, 99) if 10.0 ** k <= abs(hi) + 1e-9]
    ticks = sorted(neg) + [0.0] + pos
    labels = ([rf"$-10^{{{int(np.log10(-v))}}}$" for v in sorted(neg)] + [r"$0$"]
              + [rf"$10^{{{int(np.log10(v))}}}$" for v in pos])
    return ticks, labels


def error_timeseries(t, series, cd=None, *, ylabel="Norm. Fehler", xlabel=None,
                     detections=None, detection_label="Drift erkannt",
                     detection_lw=0.9, ylim=(-1e3, 1e3),
                     linthresh=3.0, linscale=0.8, yticks=None, ref_lines=True,
                     frac=1.0, rng=None, s=6, alpha=0.5,
                     cd_label="Driftsignal $c[k]$", cd_amp=None,
                     cd_tick_step=None, cd_linewidth=1.5, align_zero=True,
                     legend=False, legend_series=None,
                     month_interval=1, date_format="%b",
                     width_scale=1.0, height_scale=0.33,
                     ax=None, figsize=None):
    """Fehler-Zeitreihe ueber der Zeit mit Driftsignal auf der zweiten Ordinate —
    der arbeitsweit einheitliche Modellgueten-Plot (Modellbildung, Detektion, Adaption).

    Zeichnet den (optional geduennten) Fehler-Scatter auf einer symlog-Achse, das
    Driftsignal ``c[k]`` als gruene Linie auf der rechten Achse (an den Aufwaerts-
    Spruengen segmentiert, damit der Saegezahn-Ruecksprung keine senkrechte Linie
    erzeugt), Detektionszeitpunkte als senkrechte Linien und richtet die Nullpunkte
    beider Ordinaten auf dieselbe Bildhoehe aus. SPEICHERT NICHT — Ablage
    (``plot_store.save_figure``) bleibt beim Aufrufer, analog ``violin_box``.

    t : gemeinsame Zeitachse (DatetimeIndex/Array) aller Reihen.
    series : eine Wertereihe, oder Liste von ``(y, rolle)`` bzw. ``(y, rolle, label)``.
        Bei mehreren Reihen werden die Punkte gemischt gezeichnet, damit keine Reihe
        systematisch verdeckt wird. ``rolle`` ist ein Rollenname (s. ``ROLES``) oder
        eine Farbe.
    cd : Driftsignal (gleiche Laenge wie ``t``) oder ``None``.
    detections : x-Positionen erkannter Drifts (z. B. ``idx[d]``).
    frac / rng : Anteil geplotteter Punkte und Generator fuer die Duennung.
    ylim / linthresh / linscale / yticks : symlog-Konfiguration der linken Achse;
        ``yticks`` per Default automatisch als Dekaden aus ``ylim``.
    ref_lines : gepunktete Hilfslinien bei ``+-linthresh`` (Grenze linear/logarithmisch).
    cd_amp : halber Wertebereich der rechten Achse (Default ``1.05*max|c[k]|``).
    cd_tick_step : Tick-Abstand der rechten Achse. align_zero : Nullpunkte ausrichten.
    legend : ``True`` oder dict mit ``ax.legend``-Kwargs; Handles werden aus den
        Reihen-Labels, ``cd_label`` und ``detection_label`` gebaut.
    legend_series : Liste ``(rolle, label)``, falls die Legende Zustaende zeigen soll,
        die im aktuellen Panel nicht vorkommen (z. B. "adaptiert" im Baseline-Panel).
    height_scale / width_scale : Figure-Groesse als Vielfaches der Textbreite.
    ax / figsize : in vorhandene Achse zeichnen bzw. Figure-Groesse erzwingen.

    Gibt ``(fig, ax, ax2)`` zurueck (``ax2`` ist ``None`` ohne ``cd``).
    """
    import locale
    import numpy as np
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.lines import Line2D
    from matplotlib.ticker import MultipleLocator

    try:                                   # deutsche Monatsnamen, falls verfuegbar
        locale.setlocale(locale.LC_TIME, "de_DE.UTF-8")
    except locale.Error:
        pass

    # --- Reihen normalisieren -------------------------------------------------- #
    if isinstance(series, (list, tuple)) and series and isinstance(series[0], (list, tuple)):
        items = [tuple(e) for e in series]
    else:
        items = [(series, "drift_afflicted")]
    items = [(np.asarray(e[0], dtype=float), e[1], e[2] if len(e) > 2 else None)
             for e in items]

    if ax is None:
        if figsize is None:
            figsize = (fig_width(width_scale), fig_width(height_scale))
        fig, ax = plt.subplots(figsize=figsize)
    else:
        fig = ax.figure
    if rng is None:
        rng = np.random.default_rng()

    # --- Hilfslinien an der linear/log-Grenze ---------------------------------- #
    if ref_lines:
        for v in (linthresh, -linthresh):
            ax.axhline(v, color=color("box"), lw=0.6, ls=":", alpha=0.6, zorder=1)

    # --- Fehler-Scatter (geduennt, Reihenfolge gemischt) ----------------------- #
    t_arr = np.asarray(t)
    xs, ys, cs = [], [], []
    for y, role, _lab in items:
        m = rng.random(len(y)) < frac if frac < 1.0 else np.ones(len(y), dtype=bool)
        col = color(role) if role in ROLES else role
        xs.append(t_arr[m]); ys.append(y[m]); cs.append(np.full(int(m.sum()), col))
    xs, ys, cs = np.concatenate(xs), np.concatenate(ys), np.concatenate(cs)
    o = rng.permutation(len(xs)) if len(items) > 1 else np.arange(len(xs))
    ax.scatter(xs[o], ys[o], c=cs[o], s=s, alpha=alpha, zorder=3, rasterized=True)

    # --- Driftsignal auf der zweiten Ordinate --------------------------------- #
    ax2 = None
    if cd is not None:
        cd = np.asarray(cd, dtype=float)
        ax2 = ax.twinx()
        cut = np.flatnonzero(np.diff(cd) > 0) + 1
        for a, b in zip(np.r_[0, cut], np.r_[cut, len(cd)]):
            ax2.plot(t_arr[a:b], cd[a:b], **line("drift_signal", linewidth=cd_linewidth))
        ax2.set_ylabel(cd_label)
        ax2.spines["right"].set_visible(True)
        ax2.spines["top"].set_visible(False)
        if cd_tick_step is not None:
            ax2.yaxis.set_major_locator(MultipleLocator(cd_tick_step))

    # --- Detektionen ---------------------------------------------------------- #
    for d in (detections or []):
        ax.axvline(d, zorder=2, **vline("detection", lw=detection_lw, linestyle="--"))

    # --- linke Achse: symlog ------------------------------------------------- #
    ax.set_yscale("symlog", linthresh=linthresh, linscale=linscale)
    ax.set_ylim(*ylim)
    if yticks is None:
        ticks, labels = _symlog_ticks(ylim, linthresh)
    elif isinstance(yticks, tuple):
        ticks, labels = yticks
    else:
        ticks, labels = yticks, None
    ax.set_yticks(ticks)
    if labels is not None:
        ax.set_yticklabels(labels)
    ax.set_ylabel(ylabel)
    ax.margins(x=0)
    if len(t_arr):
        ax.set_xlim(t_arr[0], t_arr[-1])
    ax.grid(True, alpha=0.2)

    # --- rechte Achse: Nullpunkt auf gleicher Bildhoehe ---------------------- #
    if ax2 is not None:
        amp = cd_amp if cd_amp is not None else 1.05 * float(np.nanmax(np.abs(cd)))
        if align_zero:
            tr = ax.transData
            y0, ylo, yhi = (tr.transform((0, v))[1] for v in (0, ylim[0], ylim[1]))
            f = min(max((y0 - ylo) / (yhi - ylo), 1e-3), 1 - 1e-3)
            total = max(amp / f, amp / (1 - f))
            ax2.set_ylim(-f * total, (1 - f) * total)
        else:
            ax2.set_ylim(-amp, amp)

    # --- Zeitachse ----------------------------------------------------------- #
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=month_interval))
    ax.xaxis.set_major_formatter(mdates.DateFormatter(date_format))
    if xlabel:
        ax.set_xlabel(xlabel)

    # --- Legende ------------------------------------------------------------- #
    if legend:
        proxies = (legend_series if legend_series is not None
                   else [(role, lab) for _y, role, lab in items if lab])
        handles = [Line2D([0], [0], marker="o", linestyle="", alpha=alpha,
                          color=(color(role) if role in ROLES else role), label=lab)
                   for role, lab in proxies]
        if ax2 is not None and cd_label:
            handles.append(Line2D([0], [0], label=cd_label, **line("drift_signal")))
        if detections is not None and len(detections) and detection_label:
            handles.append(Line2D([0], [0], label=detection_label,
                                  **line("detection", linestyle="--")))
        kw = dict(frameon=False)
        kw.update(legend if isinstance(legend, dict) else {})
        ax.legend(handles=handles, **kw)

    return fig, ax, ax2


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
    fig_width()
    swatch()
