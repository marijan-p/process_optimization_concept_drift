"""Zentrale Erzeugung der umfangreichen Ergebnis-JSONs fuer die Dissertation.

Gegenstueck zu :mod:`latex_export`: Waehrend ``MacroExport`` die knappen
``\\newcommand``-Werte fuer den Fliesstext erzeugt, sammelt ``ResultDoc`` die
*vollstaendigen* Ergebnisdaten (Kennzahlentabellen, getunte Parameter, Detektor-
Ausgaben) und schreibt sie als JSON. Beide Builder sind bewusst gleich aufgebaut:
verkettbare, typisierte Setter und ein fluessiges ``.save(store, case, cfg,
final=...)``, das ueber denselben ``OutputStore`` (Sidecar, Manifest, RunLedger)
laeuft.

Motivation
----------
Vor diesem Modul baute jedes Notebook sein ``comprehensive``-dict von Hand und
definierte dabei jeweils eigene Helfer (``_num``, ``_jsonable``) sowie verstreute
``int(...)``/``float(...)``/``[int(i) for i in ...]``-Casts neu. Das ist fehler-
anfaellig (Helfer driften auseinander, ein vergessener Cast bricht ``json.dump``)
und dupliziert Provenienz (``generated``, ``run_id``, ``idv``), die die Sidecar
ohnehin fuehrt.

``ResultDoc`` zentralisiert beides:

* **JSON-Coercion** an genau einer Stelle (:func:`to_jsonable`): numpy-Skalare
  und -Arrays -> native Typen/Listen, ``tuple`` -> ``list``, ``NaN``/``inf`` ->
  ``None`` (analog zu ``run_registry._canon``, aber JSON-tauglich statt Fehler).
* **Provenienz** wird nicht mehr pro Notebook von Hand gesetzt, sondern von
  :meth:`ResultDoc.save` kompakt aus ``cfg`` abgeleitet (``_provenance``-Block;
  abschaltbar via ``provenance=False``). Die volle Provenienz (config,
  code_version, created) steht weiterhin in der Sidecar. Fallspezifische
  Parameter gehoeren als benannte Sektion in ``cfg`` (``cfg.compose(...)``) und
  sind damit Teil von ``id``.

Konvention fuer die typisierten Setter (spiegelt ``MacroExport``):
    integer()  -> Ganzzahl (None/NaN -> None)
    num()      -> Dezimalzahl (optional gerundet; None/NaN -> None)
    set()      -> beliebige (verschachtelte) Struktur, per to_jsonable gehaertet
    stats()    -> DataFrame-Kennzahlen als {zeile: {name: wert}} (typisiert)
"""

from __future__ import annotations

import math

# numpy ist optional (identische Erkennung wie in run_registry), damit das Modul
# auch ohne installiertes numpy importierbar bleibt.
try:
    import numpy as _np
except ImportError:  # pragma: no cover
    _np = None

def _is_nan(x):
    return isinstance(x, float) and x != x


def to_jsonable(obj):
    """Rekursive, JSON-taugliche Kanonisierung eines beliebigen Objekts.

    Strukturell identisch zu ``run_registry._canon`` (numpy-Skalare/-Arrays,
    dict/list-Rekursion), mit einem bewussten Unterschied: nicht-finite Werte
    (``NaN``, ``+/-inf``) werden zu ``None`` gemappt, statt einen Fehler zu
    werfen -- denn hier geht es um *Ausgabe*, nicht um Konfigurations-Hashing.
    ``tuple`` wird zu ``list``. dict-Schluessel werden fuer die JSON-Ausgabe
    nativ gemacht (numpy-Skalar -> Python-Skalar).
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if _np is not None and isinstance(k, _np.generic):
                k = k.item()
            out[k] = to_jsonable(v)
        return out
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if _np is not None:
        if isinstance(obj, _np.generic):
            obj = obj.item()
        elif isinstance(obj, _np.ndarray):
            return [to_jsonable(x) for x in obj.tolist()]
    if isinstance(obj, float) and (obj != obj or math.isinf(obj)):
        return None
    return obj


class ResultDoc:
    r"""Sammelt Ergebnis-Sektionen und rendert sie als JSON-taugliches ``dict``.

    Alle Mutator-Methoden geben ``self`` zurueck und sind damit verkettbar
    (identisch zur Bedienung von :class:`latex_export.MacroExport`).

    Beispiel
    --------
    >>> import pandas as pd
    >>> frame = pd.DataFrame({"rmse": {"MLP": 0.065}, "n_train": {"MLP": 12}})
    >>> doc = (ResultDoc()
    ...        .integer("n_samples", 1000)
    ...        .stats(frame, [("rmse", "rmse", "num"),
    ...                       ("n_train", "n_train", "int")], into="models"))
    >>> doc.render() == {"n_samples": 1000,
    ...                  "models": {"MLP": {"rmse": 0.065, "n_train": 12}}}
    True
    """

    def __init__(self):
        self._d = {}

    # -- Einzelwerte (typisiert, spiegelt MacroExport) ----------------------
    def integer(self, key, value):
        """Ganzzahl; ``None``/``NaN`` -> ``None``."""
        self._d[key] = None if value is None or _is_nan(value) else int(value)
        return self

    def num(self, key, value, nd=None):
        """Dezimalzahl; ``None``/``NaN`` -> ``None``. ``nd`` rundet optional."""
        if value is None or _is_nan(value):
            self._d[key] = None
        else:
            v = float(value)
            self._d[key] = round(v, nd) if nd is not None else v
        return self

    def set(self, key, value):
        """Beliebige (verschachtelte) Struktur, per :func:`to_jsonable` gehaertet."""
        self._d[key] = to_jsonable(value)
        return self

    def update(self, mapping=None, **kw):
        """Mehrere Schluessel auf einmal setzen (jeweils via :func:`to_jsonable`)."""
        for k, v in {**(mapping or {}), **kw}.items():
            self._d[k] = to_jsonable(v)
        return self

    # -- Kennzahlentabellen (spiegelt MacroExport.stats) --------------------
    def stats(self, frame, keys, *, into, rows=None):
        """Emittiert je Zeile x Kennzahl eines DataFrame einen typisierten Wert.

        Parameters
        ----------
        frame : pandas.DataFrame
            Statistik-Tabelle.
        keys : list[tuple[str, str, str]]
            Tripel ``(spalte, ausgabename, kind)`` mit ``kind`` in
            ``{"num", "int"}``. ``NaN``/``None`` -> ``None``.
        into : str
            Schluessel, unter dem die verschachtelte Tabelle
            ``{zeilenname: {ausgabename: wert}}`` abgelegt wird.
        rows : iterable, optional
            Zeilenauswahl/-reihenfolge; Default ``frame.index``.
        """
        rows = list(frame.index) if rows is None else list(rows)
        out = {}
        for row in rows:
            rec = {}
            for col, name, kind in keys:
                v = frame.loc[row, col]
                if v is None or _is_nan(v):
                    rec[name] = None
                elif kind == "int":
                    rec[name] = int(v)
                elif kind == "num":
                    rec[name] = float(v)
                else:
                    raise ValueError(f"Unbekannter kind {kind!r} fuer Spalte {col!r}")
            out[row] = rec
        self._d[into] = to_jsonable(out)
        return self

    # -- Ausgabe ------------------------------------------------------------
    def render(self):
        """Vollstaendiges, JSON-taugliches ``dict`` (Kopie)."""
        return dict(self._d)

    @staticmethod
    def _provenance(cfg, parents):
        """Kompakter Provenienz-Block aus cfg -- konsistent zur Sidecar."""
        meta = {}
        rid = getattr(cfg, "id", None)
        bid = getattr(cfg, "base_id", None)
        if rid is not None:
            meta["id"] = rid
        if bid is not None:
            meta["base_id"] = bid
        sections = getattr(cfg, "sections", None)
        if sections:
            meta["sections"] = to_jsonable(dict(sections))
        if parents:
            meta["parents"] = to_jsonable(parents)
        return meta

    def save(self, store, case, cfg, *, final, parents=None,
             provenance=True, echo=True):
        """Rendert und speichert via ``store.save_json(...)``; gibt den Pfad zurueck.

        ``store`` ist ein ``OutputStore`` (z. B. ``rr.synthetic_results_store``).
        Mit ``provenance=True`` (Default) wird ein kompakter ``_provenance``-Block
        aus ``cfg``/``parents`` vorangestellt, damit auch die stabile, nachgelagert
        eingebundene JSON-Datei selbstbeschreibend bleibt (die vollstaendige
        Provenienz liegt zusaetzlich in der Sidecar). ``parents`` wird an
        ``save_json`` durchgereicht und so in der Sidecar vermerkt.
        """
        obj = self.render()
        if provenance:
            meta = self._provenance(cfg, parents)
            if meta:
                obj = {"_provenance": meta, **obj}
        path, _ = store.save_json(obj, case, cfg, final=final, parents=parents)
        if echo:
            print(f"Umfassende Ergebnisse -> {path}")
        return path

    def __str__(self):
        import json
        return json.dumps(self.render(), indent=2, ensure_ascii=False)


if __name__ == "__main__":
    # Selbsttest ohne externe Abhaengigkeiten (numpy optional).
    import json

    # Coercion: numpy, tuple, NaN/inf
    sample = {"a": (1, 2), "b": float("nan"), "c": float("inf")}
    if _np is not None:
        sample["d"] = _np.int64(7)
        sample["e"] = _np.array([1.0, 2.0])
        sample["f"] = _np.float64("nan")
    js = to_jsonable(sample)
    json.dumps(js)  # muss serialisierbar sein
    assert js["a"] == [1, 2] and js["b"] is None and js["c"] is None
    if _np is not None:
        assert js["d"] == 7 and js["e"] == [1.0, 2.0] and js["f"] is None

    # Typisierte Setter
    doc = (ResultDoc()
           .integer("n", 3.0)
           .num("x", 0.12345, 3)
           .num("y", float("nan"))
           .set("cfg", {"w": (1, 2), "t": 5}))
    r = doc.render()
    assert r == {"n": 3, "x": 0.123, "y": None, "cfg": {"w": [1, 2], "t": 5}}, r

    # stats mit einfachem frame-Ersatz (dict-of-dict via kleiner Shim-Klasse)
    class _Loc:
        def __init__(self, d): self.d = d
        def __getitem__(self, k): return self.d[k[0]][k[1]]

    class _Frame:
        def __init__(self, cols):
            self.cols = cols
            self.index = list(next(iter(cols.values())).keys())
            self.loc = _Loc({r: {c: cols[c][r] for c in cols} for r in self.index})

    frame = _Frame({"rmse": {"MLP": 0.065, "GRU": float("nan")},
                    "n_train": {"MLP": 12, "GRU": 0}})
    doc2 = ResultDoc().stats(
        frame, [("rmse", "rmse", "num"), ("n_train", "n_train", "int")], into="models")
    assert doc2.render() == {"models": {
        "MLP": {"rmse": 0.065, "n_train": 12},
        "GRU": {"rmse": None, "n_train": 0}}}, doc2.render()

    # Provenienz-Block
    class _Cfg:
        id = "abcd1234"
        base_id = "0000ffff"
        sections = {"error": {"idv": 5, "amp": 1.0}}
    meta = ResultDoc._provenance(_Cfg(), {"model": "deadbeef"})
    assert meta["id"] == "abcd1234" and meta["sections"]["error"]["idv"] == 5
    assert meta["parents"] == {"model": "deadbeef"}

    # save() gegen Fake-Store
    class _Store:
        def __init__(self): self.saved = None
        def save_json(self, obj, case, cfg, *, final, parents=None):
            self.saved = (obj, case, final, parents)
            return f"/tmp/{case}.json", None

    st = _Store()
    ResultDoc().integer("n_samples", 10).save(
        st, "model_error", _Cfg(), final=True, echo=False)
    obj = st.saved[0]
    assert "_provenance" in obj and obj["n_samples"] == 10
    json.dumps(obj)

    print("results_export Selbsttest OK")
