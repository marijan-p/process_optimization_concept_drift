"""Zentrale Erzeugung von LaTeX-Makros (\\newcommand) fuer die Dissertation.

Wird von den Ergebnis-Notebooks (syn_model, syn_detection, syn_adaptation, ...)
genutzt, um Parameter- und Ergebniswerte konsistent als \\newcommand-Makros in
.tex-Dateien zu schreiben. Die Logik ist bewusst dependency-frei gehalten, damit
sie unabhaengig vom sys.path-Setup der einzelnen Notebooks importierbar ist.

LaTeX-Hinweis: \\newcommand-Namen duerfen nur Buchstaben enthalten (keine Ziffern,
keine Unterstriche). Deshalb camelCase fuer die Makronamen. Die Python-Variablen
bleiben snake_case; die Umsetzung in camelCase passiert ausschliesslich hier.

Konvention fuer die Praefixe:
    param...  -> Eingangsparameter (idealerweise Hash-relevant)
    stat...   -> Modellfehler-Statistiken (syn_model)
    drift...  -> Detektionskennzahlen (syn_detection)
    adapt...  -> Adaptionskennzahlen (syn_adaptation)
"""

from __future__ import annotations

import math
from fractions import Fraction


# Deutsche Zahlwoerter fuer die Option spell_out (attributiv: "ein"/"zwei"/... vor
# einem Substantiv). Ueblich werden Zahlen bis zwoelf ausgeschrieben.
_DE_NUMBER_WORDS = {
    0: "null", 1: "ein", 2: "zwei", 3: "drei", 4: "vier", 5: "fünf",
    6: "sechs", 7: "sieben", 8: "acht", 9: "neun", 10: "zehn",
    11: "elf", 12: "zwölf",
}


def format_de(x, nd):
    """Formatiert eine Zahl mit deutschem Dezimalkomma; '--' fuer None/NaN.

    Das Komma wird als LaTeX-Gruppe ``{,}`` geschrieben, damit siunitx bzw. der
    Mathemodus den Abstand korrekt setzt (identisch zum bisherigen ``_de`` in den
    Notebooks).

    Parameters
    ----------
    x : float | int | None
        Zu formatierender Wert.
    nd : int
        Anzahl der Nachkommastellen.
    """
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "--"
    return f"{x:.{nd}f}".replace(".", "{,}")


class MacroExport:
    r"""Sammelt ``\newcommand``-Zeilen und rendert sie als .tex-Inhalt.

    Beispiel
    --------
    >>> mx = MacroExport("automatisch erzeugt aus syn_model.ipynb - nicht editieren")
    >>> mx.comment("Parameter (Hash-relevant)")          # doctest: +ELLIPSIS
    <...>
    >>> mx.integer("paramEpochs", 500)                   # doctest: +ELLIPSIS
    <...>
    >>> mx.raw("paramBeta", r"\tfrac{1}{5}")             # doctest: +ELLIPSIS
    <...>
    >>> mx.comment("Ergebnisse")                         # doctest: +ELLIPSIS
    <...>
    >>> mx.num("statMLPRmseFree", 0.065, 3)              # doctest: +ELLIPSIS
    <...>
    >>> print(mx.render())                               # doctest: +NORMALIZE_WHITESPACE
    % automatisch erzeugt aus syn_model.ipynb - nicht editieren
    <BLANKLINE>
    % Parameter (Hash-relevant)
    \newcommand{\paramEpochs}{500}
    \newcommand{\paramBeta}{\tfrac{1}{5}}
    <BLANKLINE>
    % Ergebnisse
    \newcommand{\statMLPRmseFree}{0{,}065}

    Alle Mutator-Methoden geben ``self`` zurueck und sind damit verkettbar.
    """

    def __init__(self, source_note):
        self._lines = [f"% {source_note}"]

    # -- Struktur -----------------------------------------------------------
    def comment(self, text):
        """Fuegt eine Kommentarzeile als Block-Trenner ein (mit Leerzeile davor)."""
        self._lines.append("")
        self._lines.append(f"% {text}")
        return self

    def blank(self):
        """Fuegt eine Leerzeile ein."""
        self._lines.append("")
        return self

    # -- Einzelne Makros ----------------------------------------------------
    def _emit(self, name, body):
        self._lines.append(rf"\newcommand{{\{name}}}{{{body}}}")
        return self

    def num(self, name, value, nd, *, unit=None, si_command="SI"):
        r"""Dezimalzahl mit deutschem Komma und ``nd`` Nachkommastellen.

        Ist ``unit`` gesetzt (z. B. ``r"\percent"``), wird die Einheit wie bei
        :meth:`param` direkt am Wert gespeichert: das Makro expandiert zu
        ``\SI{<zahl>}{<unit>}`` (Kommando ueber ``si_command`` waehlbar). Die
        Zahl wird dann mit Dezimalpunkt und stets ``nd`` Nachkommastellen
        uebergeben, da siunitx das Dezimaltrennzeichen selbst setzt.
        None/NaN -> ``--`` (ohne Einheit).
        """
        if unit is None:
            return self._emit(name, format_de(value, nd))
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return self._emit(name, "--")
        return self._emit(name, rf"\{si_command}{{{value:.{nd}f}}}{{{unit}}}")

    def integer(self, name, value):
        """Ganzzahl; None/NaN -> '--'."""
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return self._emit(name, "--")
        return self._emit(name, str(int(value)))

    def raw(self, name, latex):
        r"""Beliebiger LaTeX-String, 1:1 uebernommen (z. B. Brueche ``\tfrac{...}``)."""
        return self._emit(name, latex)

    def param(self, name, value, *, nd=1, is_frac=True, unit=None,
              si_command="SI", spell_out=False, max_spell=12, max_denominator=1_000_000):
        r"""Parameterwert typgerecht ausgeben -- direkt aus dem (gehashten) Wert.

        Fuer *jeden* Wert wird zuerst geprueft, ob er ganzzahlig ist. Nicht
        ganzzahlige Werte werden standardmaessig als Bruch gespeichert:

        - ganzzahliger Wert       -> als Ganzzahl (z. B. ``60``, ``3.0`` -> ``3``)
          bzw. mit ``spell_out=True`` als deutsches Zahlwort, sofern
          ``0 <= wert <= max_spell`` (Default 12): ``2`` -> ``zwei``, groessere
          Werte bleiben Ziffer (``32`` -> ``32``).
        - sonst, ``is_frac=True``  -> als gekuerzter Bruch ``\tfrac{p}{q}`` (Default)
          (z. B. ``0.4`` -> ``2/5``, ``0.375`` -> ``3/8``, ``0.333...`` -> ``1/3``)
        - ``is_frac=False``        -> Dezimalzahl mit ``nd`` Nachkommastellen

        Ist ``unit`` gesetzt (z. B. ``r"\second"``), wird die Einheit direkt am Wert
        gespeichert: das Makro expandiert zu ``\SI{<zahl>}{<unit>}`` (Kommando ueber
        ``si_command`` waehlbar, z. B. ``"qty"`` fuer siunitx v3). Im Text genuegt
        dann ``\paramWindow`` ohne separate Einheit. Die Zahl wird mit Dezimalpunkt
        uebergeben, da siunitx das Dezimaltrennzeichen selbst setzt; ``\tfrac`` ist
        mit Einheit nicht moeglich, daher gilt bei ``unit`` reine Zahldarstellung
        (Ganzzahl, sonst ``nd`` noetig).

        Der Bruch wird per :func:`fractions.Fraction.limit_denominator` unmittelbar
        aus dem uebergebenen Wert rekonstruiert. Damit gibt es keinen separat
        hartkodierten Zaehler/Nenner mehr, der vom gehashten Wert abweichen koennte;
        die Darstellung ist per Konstruktion konsistent. None/NaN -> ``--``.
        Ein negatives Vorzeichen wird vor den Bruch gezogen; der Wert selbst bleibt
        unveraendert.
        """
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return self._emit(name, "--")
        if unit is not None:
            return self._emit(name, rf"\{si_command}{{{self._si_number(name, value, nd)}}}{{{unit}}}")
        if float(value).is_integer():
            iv = int(value)
            if spell_out and iv in _DE_NUMBER_WORDS and iv <= max_spell:
                return self._emit(name, _DE_NUMBER_WORDS[iv])
            return self._emit(name, str(iv))
        if is_frac:
            f = Fraction(value).limit_denominator(max_denominator)
            sign = "-" if f < 0 else ""
            return self._emit(name, rf"{sign}\tfrac{{{abs(f.numerator)}}}{{{f.denominator}}}")
        return self._emit(name, format_de(value, nd))

    @staticmethod
    def _si_number(name, value, nd):
        """Zahl fuer das Argument von \\SI/\\qty: Punkt als Trenner (siunitx setzt das Komma)."""
        if float(value).is_integer():
            return str(int(value))
        if nd is None:
            raise ValueError(
                f"Nicht-ganzzahliger Wert {value!r} mit Einheit (Makro {name!r}) "
                f"verlangt nd (Nachkommastellen)."
            )
        return f"{value:.{nd}f}"

    def stats(self, frame, keys, *, prefix=""):
        """Emittiert je Zeile x Kennzahl eines DataFrame ein Zahlen-Makro.

        Parameters
        ----------
        frame : pandas.DataFrame
            Statistik-Tabelle; ``frame.index`` liefert die Zeilennamen.
        keys : list[tuple[str, str, int]]
            Tripel ``(spalte, suffix, nachkommastellen)``.
            Makroname = ``prefix + zeilenname + suffix``.
        prefix : str
            Gemeinsames Namenspraefix (z. B. ``'stat'``).
        """
        for row in frame.index:
            for col, suffix, nd in keys:
                self.num(f"{prefix}{row}{suffix}", frame.loc[row, col], nd)
        return self

    # -- Batch aus Spezifikation -------------------------------------------
    def extend(self, spec):
        """Verarbeitet eine Liste von ``(name, value, kind, nd)``-Tupeln.

        ``kind`` ist eines von ``'num'``, ``'int'`` oder ``'raw'``. Bei ``'raw'``
        ist ``value`` der LaTeX-String und ``nd`` wird ignoriert (Konvention: None).
        """
        for name, value, kind, nd in spec:
            if kind == "num":
                self.num(name, value, nd)
            elif kind == "int":
                self.integer(name, value)
            elif kind == "raw":
                self.raw(name, value)
            else:
                raise ValueError(f"Unbekannter kind {kind!r} fuer Makro {name!r}")
        return self

    # -- Ausgabe ------------------------------------------------------------
    def render(self):
        """Vollstaendiger .tex-Inhalt inkl. abschliessendem Newline."""
        return "\n".join(self._lines) + "\n"

    def save(self, store, case, cfg, *, final, echo=True):
        """Rendert und speichert via ``store.save_text(...)``; gibt den Pfad zurueck.

        ``store`` ist ein Results-Store (z. B. ``rr.synthetic_results_store``),
        der eine Methode ``save_text(text, case, cfg, final=...)`` bereitstellt.
        """
        tex = self.render()
        path, _ = store.save_text(tex, case, cfg, final=final)
        if echo:
            print(f"LaTeX-Makros -> {path}\n\n{tex}")
        return path

    def __str__(self):
        return self.render()
