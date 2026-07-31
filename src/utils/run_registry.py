"""Zentrale Hash- und Metadatenverwaltung fuer Daten- und Modellartefakte.

RunConfig kapselt eine Konfiguration und bildet daraus die Kennung. Jede Datei
traegt genau eine Kennung: den sha1 ueber ein *zusammengesetztes* Konfigurations-
dokument. Ein reines Basisartefakt hasht die Basiskonfiguration direkt (base_id
bleibt bit-genau erhalten); abgeleitete Artefakte haengen ihre Parameter als
benannte Sektionen an (compose), sodass das Dokument {"base": ..., "model": ...,
"detector": ..., "cooldown": ...} in einem Zug gehasht wird. Es gibt keine
Eltern-Kette und kein Einbetten fremder Kennungen mehr.

ArtifactStore uebernimmt Pfadbau, Speichern und Laden inklusive Sidecar-JSON,
Manifest und Legacy-Fallback. Die Sidecar enthaelt das vollstaendige Dokument.
Fallspezifische Parameter (variant) werden als lesbares, kanonisches Token
kodiert (z. B. amp1.0-idv29).

Beispiel:
    from run_registry import RunConfig, tep_store
    store = tep_store(data_dir)
    cfg = RunConfig(run_cfg)
    store.save(train_data, "train", cfg)
    model_cfg = cfg.compose(model=model_params)
    store.save(model, "model", model_cfg)
"""

import datetime
import glob
import hashlib
import json
import os
import pickle
import re
import subprocess

try:
    import numpy as _np
except ImportError:
    _np = None


def _canon(obj):
    if isinstance(obj, dict):
        return {k: _canon(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_canon(x) for x in obj]
    if _np is not None:
        if isinstance(obj, _np.generic):
            obj = obj.item()
        elif isinstance(obj, _np.ndarray):
            return [_canon(x) for x in obj.tolist()]
    if isinstance(obj, float) and (obj != obj or obj in (float("inf"), float("-inf"))):
        raise ValueError(f"Nicht-finiter Wert in Konfiguration: {obj!r}")
    return obj


def _dumps(obj):
    return json.dumps(_canon(obj), sort_keys=True)


def _hash(obj, n=8):
    return hashlib.sha1(_dumps(obj).encode()).hexdigest()[:n]


def _is_subdocument(old, new):
    """True, wenn ``new`` das Dokument ``old`` unveraendert enthaelt (nur ergaenzt).

    Dicts duerfen in ``new`` zusaetzliche Schluessel haben; alle in ``old``
    vorhandenen Schluessel muessen mit gleichem Wert auch in ``new`` stehen.
    Listen muessen elementweise (und in Laenge) uebereinstimmen.
    """
    old, new = _canon(old), _canon(new)
    if isinstance(old, dict):
        return isinstance(new, dict) and all(
            k in new and _is_subdocument(v, new[k]) for k, v in old.items())
    if isinstance(old, list):
        return (isinstance(new, list) and len(old) == len(new)
                and all(_is_subdocument(a, b) for a, b in zip(old, new)))
    return old == new


def _fmt_val(v):
    s = str(v.item() if _np is not None and isinstance(v, _np.generic) else v)
    return re.sub(r"[^0-9A-Za-z.+-]", "", s)


def _variant_token(variant):
    """Kanonisches, lesbares Token: sortierte key-value-Paare, mit '-' verbunden."""
    if not variant:
        return None
    return "-".join(f"{k}{_fmt_val(variant[k])}" for k in sorted(variant))


def _git_version(path):
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                             cwd=os.path.dirname(path) or ".",
                             capture_output=True, text=True, timeout=3)
        return out.stdout.strip() or None
    except Exception:
        return None


class RunConfig:
    """Konfiguration mit deterministischer, flacher Kennung.

    Die Basis wird direkt gehasht (base_id). Zusaetzliche Sektionen (model,
    detector, cooldown, tuning, adaptation, ...) werden ueber compose() angehaengt
    und in ein Dokument {"base": ..., <sektion>: ...} gefaltet, das als Ganzes den
    id bildet. Das Schluesselwort "base" ist reserviert und darf in einer
    Basiskonfiguration nicht vorkommen.
    """

    def __init__(self, cfg, *, sections=None):
        self.cfg = dict(cfg)
        self.sections = dict(sections) if sections else {}

    @classmethod
    def from_document(cls, document):
        """Rekonstruiert eine RunConfig aus einem Sidecar-Dokument (config)."""
        doc = dict(document)
        if "base" in doc:
            base = doc.pop("base")
            return cls(base, sections=doc or None)
        return cls(doc)

    @property
    def base_id(self):
        return _hash(self.cfg)

    @property
    def document(self):
        base = _canon(self.cfg)
        if not self.sections:
            return base
        return {"base": base, **{k: _canon(v) for k, v in self.sections.items()}}

    @property
    def id(self):
        return _hash(self.document)

    def compose(self, **sections):
        """Fuegt benannte Parametersektionen hinzu und gibt eine neue RunConfig zurueck."""
        merged = dict(self.sections)
        merged.update(sections)
        return RunConfig(self.cfg, sections=merged)

    def __repr__(self):
        return f"RunConfig(id={self.id}, base={self.base_id}, sections={list(self.sections)})"


class ArtifactStore:
    """Speichert und laedt Artefakte konsistent inkl. Sidecar-JSON und Manifest."""

    def __init__(self, data_dir, prefix, *, legacy=None, legacy_glob=None):
        self.data_dir = data_dir
        self.prefix = prefix
        self.legacy = legacy or {}
        self.legacy_glob = legacy_glob or {}
        os.makedirs(data_dir, exist_ok=True)

    def stem(self, case, rid, variant=None):
        s = f"{self.prefix}_{case}_{rid}"
        vt = _variant_token(variant)
        if vt:
            s += f"_{vt}"
        return s

    def path(self, case, cfg=None, *, run_id=None, variant=None, ext="pkl"):
        rid = run_id if run_id is not None else cfg.id
        return os.path.join(self.data_dir, self.stem(case, rid, variant) + "." + ext)

    def _sidecar_path(self, pkl_path):
        return os.path.splitext(pkl_path)[0] + ".json"

    def _legacy_path(self, case, rid, variant, ext, cfg=None):
        fn = self.legacy.get(case)
        if fn is None or rid is None:
            return None
        name = fn(rid, variant or {}, cfg)
        if not name:
            return None
        if not name.endswith("." + ext):
            name += "." + ext
        return os.path.join(self.data_dir, name)

    def _find_superset_source(self, case, cfg, variant, ext):
        """Sucht ein vorhandenes Artefakt, dessen config ein Teil-Dokument von
        ``cfg.document`` ist (d. h. cfg ergaenzt es nur). Gibt dessen Kennung zurueck,
        wenn *genau eines* passt, sonst None (bei Mehrdeutigkeit wird nicht geraten)."""
        if cfg is None:
            return None
        pat = os.path.join(self.data_dir, f"{self.prefix}_{case}_*.{ext}")
        cands = []
        for p in glob.glob(pat):
            scp = self._sidecar_path(p)
            if not os.path.exists(scp):
                continue
            with open(scp, encoding="utf-8") as f:
                sc = json.load(f)
            if sc.get("id") == cfg.id or sc.get("variant") != variant:
                continue
            doc = sc.get("config")
            if doc is not None and _is_subdocument(doc, cfg.document):
                cands.append(sc.get("id"))
        return cands[0] if len(cands) == 1 else None

    def resolve(self, case, cfg=None, *, run_id=None, variant=None, ext="pkl", rekey=False):
        """Gibt (Pfad, from_legacy) des vorhandenen Artefakts zurueck oder (None, False).

        Mit ``rekey=True`` wird -- falls unter der Kennung von ``cfg`` nichts vorliegt --
        ein vorhandenes Artefakt uebernommen, dessen config ``cfg`` nur ergaenzt
        (Superset), und unter der neuen Kennung materialisiert. Analog zu ``rename``
        ist das ein bewusster, schreibender Nebeneffekt beim Zugriff.
        """
        rid = run_id if run_id is not None else (cfg.id if cfg else None)
        p = self.path(case, run_id=rid, variant=variant, ext=ext)
        if os.path.exists(p):
            return p, False
        lp = self._legacy_path(case, rid, variant, ext, cfg=cfg)
        if lp and os.path.exists(lp):
            return lp, True
        if rekey and cfg is not None and run_id is None:
            src_id = self._find_superset_source(case, cfg, variant, ext)
            if src_id is not None:
                return self.rekey(case, src_id, cfg, variant=variant, ext=ext), False
        return None, False

    def exists(self, case, cfg=None, *, run_id=None, variant=None, ext="pkl", rekey=False):
        return self.resolve(case, cfg, run_id=run_id, variant=variant, ext=ext,
                            rekey=rekey)[0] is not None

    def _sidecar(self, case, cfg, variant, meta):
        return {
            "stem": self.stem(case, cfg.id, variant),
            "prefix": self.prefix,
            "case": case,
            "id": cfg.id,
            "base_id": cfg.base_id,
            "variant": variant,
            "variant_token": _variant_token(variant),
            "config": cfg.document,
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "code_version": _git_version(self.data_dir),
            "extra": meta or {},
        }

    def _update_manifest(self, sidecar):
        mpath = os.path.join(self.data_dir, f"{self.prefix}_manifest.json")
        index = {}
        if os.path.exists(mpath):
            try:
                with open(mpath, encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = {}
        index[sidecar["stem"]] = {k: sidecar[k] for k in
                                  ("case", "id", "base_id", "variant", "created")}
        tmp = mpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, mpath)

    def save(self, obj, case, cfg, *, variant=None, ext="pkl", meta=None):
        p = self.path(case, cfg, variant=variant, ext=ext)
        sc = self._sidecar(case, cfg, variant, meta)
        if hasattr(obj, "attrs"):
            try:
                obj.attrs = {"run_id": cfg.id, "base_id": cfg.base_id, "case": case,
                             "variant": variant, "config": sc["config"], **(meta or {})}
            except Exception:
                pass
        with open(p, "wb") as f:
            pickle.dump(obj, f)
        with open(self._sidecar_path(p), "w", encoding="utf-8") as f:
            json.dump(sc, f, indent=2, ensure_ascii=False)
        self._update_manifest(sc)
        return p

    def load(self, case, cfg=None, *, run_id=None, variant=None, ext="pkl",
             verify=True, rename=False, rekey=False):
        p, from_legacy = self.resolve(case, cfg, run_id=run_id, variant=variant, ext=ext,
                                      rekey=rekey)
        if p is None:
            raise FileNotFoundError(
                f"Kein Artefakt fuer case={case!r}, id="
                f"{run_id or (cfg.id if cfg else '?')}, variant={variant} in {self.data_dir}")
        with open(p, "rb") as f:
            obj = pickle.load(f)
        if verify and cfg is not None and not from_legacy:
            scp = self._sidecar_path(p)
            if os.path.exists(scp):
                with open(scp, encoding="utf-8") as f:
                    stored = json.load(f).get("config")
                if stored is not None and _canon(stored) != cfg.document:
                    raise ValueError(f"Config-Mismatch fuer {p}: Sidecar weicht von cfg ab.")
        if rename and from_legacy and cfg is not None:
            self.save(obj, case, cfg, variant=variant, ext=ext, meta=meta_from_legacy(obj))
        return obj

    def rekey(self, case, old, new_cfg, *, variant=None, ext="pkl",
              keep_old=True, require_superset=True):
        """Uebertraegt ein vorhandenes Artefakt auf eine neue Konfiguration (neuer Hash),
        ohne es neu zu berechnen.

        Anwendungsfall: Der Konfiguration wird ein Parameter *neu hinzugefuegt* (z. B.
        COOLDOWN), der den bereits gecachten Zwischenstand nicht veraendert bzw. dessen
        Wert genau dem entspricht, mit dem der Cache erzeugt wurde. Das Artefakt wird
        unter ``new_cfg.id`` neu abgelegt: Pickle uebernommen, Sidecar + Manifest
        aktualisiert und -- fuer Objekte mit ``attrs`` -- die eingebettete ``config`` auf
        ``new_cfg.document`` umgeschrieben (damit nachgelagerte Notebooks ueber
        ``from_document`` die neue Kennung rekonstruieren).

        Parameters
        ----------
        old : RunConfig | str
            Alte Konfiguration oder deren Kennung (run_id) des vorhandenen Artefakts.
        require_superset : bool
            Wenn True (Default), muss ``new_cfg.document`` die alte Konfiguration
            unveraendert enthalten und darf nur ergaenzen -- verhindert das stille
            Umschluesseln ueber eine tatsaechliche Parameteraenderung hinweg.

        Voraussetzung (nicht automatisch pruefbar): Der neue Parameterwert entspricht
        dem, mit dem der Cache erzeugt wurde. Dafuer ist der Aufrufer verantwortlich.
        """
        old_id = old.id if isinstance(old, RunConfig) else old
        if old_id == new_cfg.id:
            return self.path(case, new_cfg, variant=variant, ext=ext)  # nichts zu tun
        # Wird eine RunConfig uebergeben, kann auch der Legacy-Name (ueber base_id)
        # aufgeloest werden; bei bloszer id nur der kanonische/legacy-run_id-Name.
        if isinstance(old, RunConfig):
            src, _ = self.resolve(case, old, variant=variant, ext=ext)
        else:
            src, _ = self.resolve(case, run_id=old_id, variant=variant, ext=ext)
        if src is None:
            raise FileNotFoundError(
                f"Kein Artefakt fuer case={case!r}, id={old_id} zum Uebertragen in {self.data_dir}")
        scp = self._sidecar_path(src)
        if require_superset and os.path.exists(scp):
            with open(scp, encoding="utf-8") as f:
                old_doc = json.load(f).get("config")
            if old_doc is not None and not _is_subdocument(old_doc, new_cfg.document):
                raise ValueError(
                    "rekey abgelehnt: new_cfg enthaelt die alte Konfiguration nicht "
                    "unveraendert (require_superset). Es wurde nicht nur ergaenzt, "
                    "sondern ein bestehender Parameter geaendert -- das Ergebnis waere "
                    "nicht mehr gueltig.")
        dst = self.path(case, new_cfg, variant=variant, ext=ext)
        if os.path.exists(dst):
            return dst  # bereits uebertragen (idempotent)
        with open(src, "rb") as f:
            obj = pickle.load(f)
        p = self.save(obj, case, new_cfg, variant=variant, ext=ext)  # attrs/Sidecar/Manifest neu
        if not keep_old and os.path.realpath(src) != os.path.realpath(p):
            os.remove(src)
            if os.path.exists(scp):
                os.remove(scp)
        return p

    def latest(self, case, *, ext="pkl"):
        pat = os.path.join(self.data_dir, f"{self.prefix}_{case}_*.{ext}")
        cands = sorted(glob.glob(pat), key=os.path.getmtime)
        if not cands and case in self.legacy_glob:
            cands = sorted(glob.glob(os.path.join(self.data_dir, self.legacy_glob[case])),
                           key=os.path.getmtime)
        return cands[-1] if cands else None

    def latest_id(self, case, *, ext="pkl"):
        p = self.latest(case, ext=ext)
        if p is None:
            return None
        scp = self._sidecar_path(p)
        if os.path.exists(scp):
            with open(scp, encoding="utf-8") as f:
                return json.load(f)["id"]
        return self.parse_id(p, case, ext=ext)

    def parse_id(self, path, case, *, ext="pkl"):
        """Extrahiert die Kennung aus einem Dateinamen (neu oder legacy)."""
        stem = os.path.basename(path)[:-(len(ext) + 1)]
        new_prefix = f"{self.prefix}_{case}_"
        if stem.startswith(new_prefix):
            rest = stem[len(new_prefix):]
            return rest.split("_")[0]
        for token in stem.split("_"):
            if len(token) == 8 and all(c in "0123456789abcdef" for c in token):
                return token
        return None


def meta_from_legacy(obj):
    return {"attrs": dict(getattr(obj, "attrs", {}) or {})} if hasattr(obj, "attrs") else {}


def _bid(rid, c):
    """Basis-Kennung: fuer abgeleitete Artefakte der base_id, sonst die uebergebene rid."""
    return c.base_id if c is not None else rid


def _method(v, c):
    if c is not None and c.sections:
        t = c.sections.get("tuning")
        if isinstance(t, dict) and "method" in t:
            return t["method"]
    return v.get("method") if v else None


# Fall-Zuordnung je Domaene: reine Generierung (data) vs. modellabhaengige
# Artefakte (model). Analog zu plot_store/results_store bekommt jede Gruppe einen
# eigenen Store mit eigenem Verzeichnis; der Domaenen-Prefix bleibt gleich, sodass
# die Dateinamen bit-stabil bleiben.
# Sauberer Schnitt: keine Legacy-Namen mehr fuer Daten-Artefakte. Alle Faelle
# folgen einheitlich dem Schema {prefix}_data_{kategorie}_{id}, mit Kategorien
# raw/doe/train/scored (syn) bzw. train/test/error/prerun/scored_test/scored_error (tep).
_SYN_DATA_LEGACY = {}
_SYN_MODEL_LEGACY = {
    "model": lambda rid, v, c: f"model_{_bid(rid, c)}.pkl",
    "adapt_tuning": lambda rid, v, c: f"adaptation_tuning_{_method(v, c)}_{_bid(rid, c)}.pkl",
    "detect_tuning": lambda rid, v, c: f"detector_tuning_{_bid(rid, c)}.pkl",
    "detections": lambda rid, v, c: f"detections_{_bid(rid, c)}.pkl",
    "adaptation": lambda rid, v, c: f"adaptation_{_bid(rid, c)}.pkl",
}
_TEP_DATA_LEGACY = {}
_TEP_MODEL_LEGACY = {
    "model": lambda rid, v, c: f"tep_model_{_bid(rid, c)}.pkl",
    "test_scored": lambda rid, v, c: f"tep_test_scored_{_bid(rid, c)}.pkl",
    "error_scored": lambda rid, v, c: f"tep_error_scored_{_bid(rid, c)}_idv{v.get('idv')}_{v.get('amp')}.pkl",
}


def synthetic_data_store(data_dir):
    return ArtifactStore(data_dir, "syn")


def synthetic_model_store(model_dir):
    return ArtifactStore(model_dir, "syn", legacy=_SYN_MODEL_LEGACY,
                         legacy_glob={"model": "model_*.pkl"})


def tep_data_store(data_dir):
    return ArtifactStore(data_dir, "tep")


def tep_model_store(model_dir):
    return ArtifactStore(model_dir, "tep", legacy=_TEP_MODEL_LEGACY,
                         legacy_glob={"model": "tep_model_*.pkl"})


class RunConsistencyError(RuntimeError):
    """Wird ausgeloest, wenn finale Ausgaben aus inkonsistenten Laeufen stammen."""


class RunLedger:
    """Zentrales Verzeichnis der aktuell final publizierten Laeufe je Stufe.

    Die Notebooks bauen aufeinander auf (data -> model -> detections ->
    adaptation). Jede Stufe traegt hier beim *finalen* Speichern ihre Kennung
    (``cfg.id``) und die Kennungen der Vorstufen ein, auf denen sie aufbaut.
    Vor dem Eintragen wird geprueft, dass jede angegebene Vorstufe noch dem
    aktuell final publizierten Stand entspricht -- andernfalls
    :class:`RunConsistencyError`.

    Damit kann kein finaler Plot und keine finale JSON- oder TeX-Datei
    geschrieben werden, die auf einem ueberholten Zwischenstand beruht. Die
    Pruefung sitzt zentral in :meth:`OutputStore.publish` und gilt so einheitlich
    fuer alle Ausgabetypen -- unabhaengig von den .tex-Dateien.

    Verwendung im Notebook::

        ledger = rr.run_ledger(base_dir)
        ledger.bind("model", parents={"data": data_cfg.base_id})
        plot_store = rr.synthetic_plot_store(plot_dir, ledger=ledger)
        res_store  = rr.synthetic_results_store(results_dir, ledger=ledger)
        # ... jedes save_figure/save_json/save_text mit final=True prueft & stempelt
        ledger.verify()   # optional: ganze Kette vor dem Thesis-Build pruefen
    """

    def __init__(self, path):
        self.path = path
        self._ctx = None            # (stage, parents) des aktuellen Notebooks
        self._recorded = set()      # (skey, id) bereits in diesem Prozess geschrieben

    # -- Kontext des aktuellen Notebooks -----------------------------------
    def bind(self, stage, parents=None):
        """Legt Stufe und Vorstufen fuer die folgenden finalen Speichervorgaenge fest.

        ``parents``: dict ``{vorstufe: erwartete_id}``, z. B.
        ``{"data": data_cfg.base_id}``. Ohne Vorstufen (Wurzel) leer lassen.
        """
        self._ctx = (stage, dict(parents or {}))
        return self

    # -- Persistenz ---------------------------------------------------------
    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"stages": {}}

    def _save(self, index):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)

    # -- Aufruf aus publish() ----------------------------------------------
    def on_final(self, prefix, cfg):
        """Hook fuer OutputStore.publish() (nur bei final=True aufgerufen)."""
        if self._ctx is None:
            return
        stage, parents = self._ctx
        self.record(prefix, stage, cfg, parents)

    def record(self, prefix, stage, cfg, parents):
        """Prueft die Vorstufen und stempelt die Stufe; RunConsistencyError bei Bruch."""
        skey = f"{prefix}:{stage}" if prefix else stage
        rid = cfg.id if isinstance(cfg, RunConfig) else str(cfg)
        if (skey, rid) in self._recorded:
            return
        base_id = cfg.base_id if isinstance(cfg, RunConfig) else None
        index = self._load()
        stages = index.setdefault("stages", {})
        stored_parents = {}
        for pstage, pid in parents.items():
            pkey = f"{prefix}:{pstage}" if prefix else pstage
            stored_parents[pkey] = pid
            cur = stages.get(pkey)
            if cur is None:
                raise RunConsistencyError(
                    f"Stufe {skey!r} baut auf {pkey!r} auf, aber dafuer ist noch kein "
                    f"finaler Stand publiziert. Bitte zuerst {pkey!r} final ausfuehren.")
            if cur["id"] != pid:
                raise RunConsistencyError(
                    f"Stufe {skey!r} wurde auf {pkey!r}={pid} gebaut, final publiziert "
                    f"ist aber {cur['id']}. Bitte {skey!r} auf dem aktuellen Stand neu "
                    f"ausfuehren (oder die Vorstufe zurueckrollen).")
        stages[skey] = {
            "id": rid,
            "base_id": base_id,
            "parents": stored_parents,
            "updated": datetime.datetime.now().isoformat(timespec="seconds"),
        }
        self._save(index)
        self._recorded.add((skey, rid))

    # -- Globale Pruefung ---------------------------------------------------
    def verify(self):
        """Prueft die gesamte publizierte Kette; RunConsistencyError bei Bruch.

        Faengt insbesondere den Fall ab, dass eine Vorstufe neu publiziert wurde,
        die zugehoerige Nachstufe aber nie neu ausgefuehrt wurde.
        """
        stages = self._load().get("stages", {})
        problems = []
        for skey, entry in stages.items():
            for pkey, pid in entry.get("parents", {}).items():
                cur = stages.get(pkey)
                if cur is None:
                    problems.append(f"{skey}: Elternstufe {pkey} fehlt im Ledger")
                elif cur["id"] != pid:
                    problems.append(
                        f"{skey}: baut auf {pkey}={pid}, aktuell final ist {cur['id']}")
        if problems:
            raise RunConsistencyError(
                "Inkonsistente Lauf-Kette:\n  " + "\n  ".join(problems))
        return True


def run_ledger(base_dir, filename="run_ledger.json"):
    """Zentrales Ledger fuer alle Stores unter ``base_dir`` (data/model/plots/results)."""
    return RunLedger(os.path.join(str(base_dir), filename))


# Ergebnisse und Plots werden weiterhin je Datei archiviert (siehe OutputStore),
# aber ueber die RunLedger konsistent zu einem Lauf verklammert: publish() stempelt
# beim finalen Speichern Stufe + Vorstufen und bricht bei Inkonsistenz ab.
class OutputStore:
    """Archiviert und stempelt Ausgabedateien (Plots, Ergebnisse) mit Provenienz.

    Anders als ArtifactStore behaelt die stabile, nachgelagert eingebundene Datei
    (LaTeX-includegraphics, Notebook-load) ihren festen Namen. Zusaetzlich wird je
    veraenderter Konfiguration eine gehashte Archivkopie abgelegt (Plots als PNG).
    final=True schreibt die stabile Datei und markiert die Version als final,
    final=False archiviert nur.

    Fallspezifische Parameter gehoeren als benannte Sektion in ``cfg``
    (``cfg.compose(error=...)``) und sind damit Teil von ``id`` -- anders als bei
    ``ArtifactStore``, wo ``variant`` zusaetzlich den Dateinamen praegt.

    Beispiel:
        from run_registry import plot_store
        store = plot_store(plot_dir)
        store.save_figure(fig, "tep_detection_kswin", det_run, final=IS_FINAL)
    """

    def __init__(self, out_dir, prefix="", *, archive_subdir="archive", ledger=None):
        self.out_dir = out_dir
        self.prefix = prefix
        self.archive_dir = os.path.join(out_dir, archive_subdir)
        self.ledger = ledger
        os.makedirs(self.archive_dir, exist_ok=True)

    def _name(self, name):
        return f"{self.prefix}_{name}" if self.prefix else name

    def _identity(self, key):
        if isinstance(key, RunConfig):
            return key.id, {"id": key.id, "base_id": key.base_id, "config": key.document}
        if isinstance(key, str):
            return key, {"id": key}
        return _hash(key), {"id": _hash(key), "inputs": _canon(key)}

    def stable_path(self, name, ext):
        return os.path.join(self.out_dir, f"{self._name(name)}.{ext}")

    def archive_path(self, name, rid, ext):
        return os.path.join(self.archive_dir, f"{self._name(name)}_{rid}.{ext}")

    def _manifest_path(self):
        mname = f"{self.prefix}_outputs_manifest.json" if self.prefix else "outputs_manifest.json"
        return os.path.join(self.archive_dir, mname)

    def _update_manifest(self, name, rid, entry, final):
        mpath = self._manifest_path()
        index = {}
        if os.path.exists(mpath):
            try:
                with open(mpath, encoding="utf-8") as f:
                    index = json.load(f)
            except Exception:
                index = {}
        versions = index.setdefault(name, {})
        if final:
            for v in versions.values():
                v["final"] = False
        versions[rid] = entry
        tmp = mpath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
        os.replace(tmp, mpath)

    def publish(self, name, key, *, writer, final, parents=None,
                stable_ext="pgf", archive_ext="png", meta=None, force=False):
        """Schreibt Archivkopie (nur bei neuer Konfiguration) und optional die stabile Datei.

        writer(path) erzeugt die Datei am Pfad; das Format folgt der Endung. Gibt
        (stable_path_oder_None, archive_path) zurueck.
        """
        # Fail-fast VOR jedem Schreibvorgang: baut dieser finale Stand auf dem
        # aktuell publizierten Stand der Vorstufen auf? (Prueft Plots/JSON/TeX gleich.)
        if final and self.ledger is not None:
            self.ledger.on_final(self.prefix, key)
        rid, prov = self._identity(key)
        ap = self.archive_path(name, rid, archive_ext)
        if not os.path.exists(ap) or force:
            writer(ap)
        sc = {
            "name": name, "id": rid, "final": bool(final),
            "parents": parents, "provenance": prov,
            "stable_ext": stable_ext, "archive_ext": archive_ext,
            "archive": os.path.basename(ap),
            "created": datetime.datetime.now().isoformat(timespec="seconds"),
            "code_version": _git_version(self.out_dir),
            "extra": meta or {},
        }
        with open(os.path.splitext(ap)[0] + ".json", "w", encoding="utf-8") as f:
            json.dump(sc, f, indent=2, ensure_ascii=False)
        self._update_manifest(name, rid, {k: sc[k] for k in
            ("id", "final", "created", "archive")}, final)
        sp = None
        if final:
            sp = self.stable_path(name, stable_ext)
            writer(sp)
        return sp, ap

    def save_figure(self, fig, name, key, *, final, parents=None,
                    stable_ext="pgf", archive_ext="png", savefig_kwargs=None,
                    archive_kwargs=None, meta=None, force=False):
        base = {"transparent": True, "bbox_inches": "tight"}
        def writer(p):
            kw = dict(base, **(savefig_kwargs or {}))
            if archive_ext != stable_ext and p.endswith("." + archive_ext) \
                    and archive_kwargs is not None:
                kw = dict(base, **archive_kwargs)
            fig.savefig(p, **kw)
        return self.publish(name, key, writer=writer, final=final,
                            parents=parents, stable_ext=stable_ext,
                            archive_ext=archive_ext, meta=meta, force=force)

    def save_json(self, obj, name, key, *, final, parents=None,
                  meta=None, force=False):
        def writer(p):
            with open(p, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)
        return self.publish(name, key, writer=writer, final=final,
                            parents=parents, stable_ext="json", archive_ext="json",
                            meta=meta, force=force)

    def save_text(self, text, name, key, *, final, ext="tex",
                  parents=None, meta=None, force=False):
        def writer(p):
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
        return self.publish(name, key, writer=writer, final=final,
                            parents=parents, stable_ext=ext, archive_ext=ext,
                            meta=meta, force=force)

    def final_id(self, name):
        mpath = self._manifest_path()
        if not os.path.exists(mpath):
            return None
        with open(mpath, encoding="utf-8") as f:
            versions = json.load(f).get(name, {})
        for rid, v in versions.items():
            if v.get("final"):
                return rid
        return None


def synthetic_plot_store(plot_dir, prefix="syn", *, ledger=None):
    return OutputStore(plot_dir, prefix, ledger=ledger)


def synthetic_results_store(results_dir, prefix="syn", *, ledger=None):
    return OutputStore(results_dir, prefix, ledger=ledger)


def tep_plot_store(plot_dir, prefix="tep", *, ledger=None):
    return OutputStore(plot_dir, prefix, ledger=ledger)


def tep_results_store(results_dir, prefix="tep", *, ledger=None):
    return OutputStore(results_dir, prefix, ledger=ledger)


def adopt_legacy(store, case, new_cfg, *, dropped=("gamma_tau", "K_p", "cd_band_div"),
                 variant=None, quiet=False):
    """Uebernimmt ein Artefakt der alten Basis-Kennung auf ``new_cfg`` (einmalige Migration).

    Anwendungsfall: Zuvor implizite Konstanten (z. B. ``gamma_tau``, ``K_p``,
    ``cd_band_div``) sind als Basis-Parameter in die Config gewandert. Die Werte sind
    unveraendert, nur der Hash (``base_id``) ist neu -- der bereits gecachte Stand ist
    also weiterhin gueltig. Diese Funktion rekonstruiert die alte Kennung (Config
    *ohne* ``dropped``, gleiche Sektionen) und schluesselt ein vorhandenes Artefakt
    per :meth:`ArtifactStore.rekey` auf ``new_cfg`` um -- kanonische *und* Legacy-Namen
    werden aufgeloest. Liegt bereits etwas unter ``new_cfg`` vor oder findet sich kein
    altes Artefakt, passiert nichts.

    Gibt True zurueck, wenn tatsaechlich uebernommen wurde.
    """
    if store.exists(case, new_cfg, variant=variant):
        return False
    base_old = {k: v for k, v in new_cfg.cfg.items() if k not in dropped}
    old = RunConfig(base_old, sections=new_cfg.sections or None)
    if not store.exists(case, old, variant=variant):
        return False
    store.rekey(case, old, new_cfg, variant=variant, require_superset=False)
    if not quiet:
        print(f"{case}: altes Artefakt {old.id} -> {new_cfg.id} uebernommen "
              f"(keine Neuberechnung).")
    return True


def _available_sections(store, case, cfg, section, *, ext="pkl"):
    """Alle Auspraegungen von ``section``, die auf ``cfg`` aufbauen (aus den Sidecars)."""
    out = []
    pat = os.path.join(store.data_dir, f"{store.prefix}_{case}_*.{ext}")
    for p in sorted(glob.glob(pat)):
        scp = store._sidecar_path(p)
        if not os.path.exists(scp):
            continue
        with open(scp, encoding="utf-8") as f:
            doc = json.load(f).get("config")
        if doc is None:
            continue
        art = RunConfig.from_document(doc)
        vals = art.sections.get(section)
        if vals is not None and cfg.compose(**{section: vals}).id == art.id:
            out.append(vals)
    return out


def load_section(store, case, cfg, section, values=None, *, ext="pkl", rename=True):
    """Laedt ein fallspezifisches Artefakt, das ``cfg`` um genau eine Sektion ergaenzt.

    Fallspezifische Parameter (z. B. der IDV des Fehlerfalls) gehoeren als benannte
    Sektion in die Konfiguration -- ``cfg.compose(error={"idv": 29, "amp": 1.0})``.
    Die Kennung ist damit aus ``cfg`` und den Werten *berechenbar*; ein separat
    einzugebender run_id eruebrigt sich.

    ``values``
        Gibt die Sektion vor. Geladen wird direkt ueber die berechnete Kennung;
        :meth:`ArtifactStore.load` prueft dabei die Sidecar-Konfiguration gegen
        ``cfg``. Achtung: ``{"amp": 1}`` und ``{"amp": 1.0}`` sind verschiedene
        Dokumente und ergeben verschiedene Kennungen -- schlaegt das Laden fehl,
        nennt die Fehlermeldung die tatsaechlich vorhandenen Auspraegungen.
    ``values=None``
        Nimmt das neueste Artefakt des Falls und prueft, dass es ``cfg`` nur um
        diese eine Sektion ergaenzt (faengt also einen Stand aus einem anderen
        Lauf ab).

    Gibt ``(objekt, konfiguration_mit_sektion)`` zurueck.
    """
    if values is not None:
        art_cfg = cfg.compose(**{section: dict(values)})
        try:
            return store.load(case, art_cfg, ext=ext, rename=rename), art_cfg
        except FileNotFoundError:
            avail = _available_sections(store, case, cfg, section, ext=ext)
            raise FileNotFoundError(
                f"Kein {case!r} mit {section}={dict(values)} zu Konfiguration "
                f"{cfg.id}. Vorhanden: {avail if avail else 'nichts'}") from None

    rid = store.latest_id(case, ext=ext)
    if rid is None:
        raise FileNotFoundError(
            f"Kein Artefakt fuer case={case!r} in {store.data_dir}")
    obj = store.load(case, run_id=rid, ext=ext, rename=rename)
    p, from_legacy = store.resolve(case, run_id=rid, ext=ext)
    doc = None
    if p is not None and not from_legacy:
        scp = store._sidecar_path(p)
        if os.path.exists(scp):
            with open(scp, encoding="utf-8") as f:
                doc = json.load(f).get("config")
    if doc is None:
        doc = dict(getattr(obj, "attrs", {}) or {}).get("config")
    if doc is None:
        raise ValueError(f"{case} {rid}: keine Konfiguration hinterlegt.")
    art_cfg = RunConfig.from_document(doc)
    vals = art_cfg.sections.get(section)
    if vals is None:
        raise ValueError(
            f"{case} {rid} hat keine {section!r}-Sektion (alter Stand). Bitte das "
            f"erzeugende Notebook einmal ausfuehren.")
    if cfg.compose(**{section: vals}).id != art_cfg.id:
        raise ValueError(
            f"{case} {rid} baut nicht auf der geladenen Konfiguration {cfg.id} auf. "
            f"Bitte {section}-Auspraegung explizit angeben oder das erzeugende "
            f"Notebook neu ausfuehren.")
    return obj, art_cfg


if __name__ == "__main__":
    syn_cfg = {
        "seed": 44, "Ts": 1.0, "num_segments": 5, "cd_range": [-0.5, 0.5],
        "range_w1": [0, 5], "n_changes_w1": 500, "range_w2": [0, 10], "n_changes_w2": 750,
        "kappa_w_factor": 0.8, "K_act": 1.0, "T_act": [4.0, 5.0],
        "alpha": [2 / 5, 1 / 3], "kappa": -7 / 4, "T_y": 3.0, "n_doe": 32, "hold_s": 600,
        "noise_u1": [(0.02, 0.6), (0.12, 0.35), (0.5, 0.05)],
        "noise_u2": [(0.003, 0.9), (0.02, 0.08), (0.2, 0.02)],
        "noise_y": [(0.003, 9.0), (0.02, 0.8), (0.08, 0.2)],
    }
    tep_cfg = {"seed": 44, "n": 300, "ramp_h": 48.0, "soak_h": 96.0, "test_split": 0.5}

    syn, tep = RunConfig(syn_cfg), RunConfig(tep_cfg)
    assert syn.base_id == "f0744790", syn.base_id
    assert tep.base_id == "ac4425b8", tep.base_id
    # Basisartefakt: id == base_id (unveraendert gegenueber altem Verfahren)
    assert syn.id == syn.base_id and tep.id == tep.base_id

    # compose: flache, parameterabhaengige, reihenfolgenunabhaengige Kennung
    m1 = syn.compose(model={"lr": 3e-3, "epochs": 9})
    m2 = syn.compose(model={"lr": 3e-3, "epochs": 9})
    m3 = syn.compose(model={"lr": 1e-3, "epochs": 9})
    assert m1.id == m2.id and m1.id != m3.id and m1.id != syn.id
    assert m1.document["base"] == _canon(syn_cfg) and "model" in m1.document

    # verkettetes compose bleibt flach (keine Eltern-Kette)
    d = syn.compose(detector={"x": 1}).compose(cooldown=5)
    assert set(d.document) == {"base", "detector", "cooldown"}

    # from_document: Rundlauf ueber das Sidecar-Dokument
    assert RunConfig.from_document(m1.document).id == m1.id
    assert RunConfig.from_document(syn.document).id == syn.base_id

    # variant-Token: lesbar, kanonisch, ordnungsunabhaengig
    assert _variant_token({"idv": 29, "amp": 1.0}) == _variant_token({"amp": 1.0, "idv": 29})
    assert _variant_token({"idv": 29, "amp": 1.0}) == "amp1.0-idv29"

    import tempfile
    with tempfile.TemporaryDirectory() as d:
        store = ArtifactStore(d, "syn")
        store.save({"x": 1}, "data", syn)
        assert store.load("data", syn) == {"x": 1}
        assert store.path("data", syn).endswith(f"syn_data_{syn.base_id}.pkl")
        # Modell: eigene, flache Kennung (m3, kollidiert nicht mit Legacy-Test unten)
        store.save({"m": 1}, "model", m3)
        assert store.load("model", m3) == {"m": 1}
        # Daten-Artefakte kennen keine Legacy-Namen mehr (sauberer Schnitt)
        ls = synthetic_data_store(d)
        assert ls.legacy == {}
        # Legacy-Fallback fuer abgeleitetes Modell via base_id (nur Modell-Store)
        lm = synthetic_model_store(d)
        with open(os.path.join(d, f"model_{syn.base_id}.pkl"), "wb") as f:
            pickle.dump({"legacy_model": True}, f)
        pm, ml = lm.resolve("model", m1)
        assert ml and lm.load("model", m1, verify=False) == {"legacy_model": True}

    # Getrennte Stores: Daten und Modelle in eigenen Verzeichnissen, gleicher Prefix
    with tempfile.TemporaryDirectory() as dd, tempfile.TemporaryDirectory() as dm:
        ds, mstore = tep_data_store(dd), tep_model_store(dm)
        ds.save({"t": 1}, "train", tep)
        mstore.save({"m": 1}, "model", tep)
        assert ds.load("train", tep) == {"t": 1}
        assert mstore.load("model", tep) == {"m": 1}
        # gleicher Prefix -> bit-stabile Dateinamen, aber getrennte Ordner
        assert ds.path("train", tep).endswith(f"tep_train_{tep.base_id}.pkl")
        assert mstore.path("model", tep).endswith(f"tep_model_{tep.base_id}.pkl")
        assert os.path.dirname(ds.path("train", tep)) != os.path.dirname(mstore.path("model", tep))
        # Fall-Trennung: Modell-Store kennt keine Daten-Legacy und umgekehrt
        assert "train" not in mstore.legacy and "model" not in ds.legacy

    # Legacy-Fallback greift je Store nur fuer die eigene Gruppe. Geprueft wird mit
    # einer *abgeleiteten* Konfiguration: nur dort unterscheiden sich kanonischer
    # Name (ueber id) und Legacy-Name (ueber base_id) ueberhaupt.
    with tempfile.TemporaryDirectory() as dm2:
        mstore2 = tep_model_store(dm2)
        tep_m = tep.compose(model={"arch": [5, 5, 1]})
        with open(os.path.join(dm2, f"tep_model_{tep.base_id}.pkl"), "wb") as f:
            pickle.dump({"legacy_model": True}, f)
        assert mstore2.resolve("model", tep_m)[1]
        assert tep_data_store(dm2).resolve("model", tep_m)[0] is None

    # load_section: Kennung aus Basis + Sektion, mit und ohne Vorgabe
    with tempfile.TemporaryDirectory() as d:
        ds = tep_data_store(d)
        e29 = tep.compose(error={"idv": 29, "amp": 1.0})
        e13 = tep.compose(error={"idv": 13, "amp": 1.0})
        ds.save({"e": 29}, "data_error", e29)
        ds.save({"e": 13}, "data_error", e13)
        # mit Vorgabe: Kennung berechnet, kein run_id noetig
        obj, ec = load_section(ds, "data_error", tep, "error", {"idv": 29, "amp": 1.0})
        assert obj == {"e": 29} and ec.id == e29.id and ec.base_id == tep.base_id
        obj, ec = load_section(ds, "data_error", tep, "error", {"idv": 13, "amp": 1.0})
        assert obj == {"e": 13} and ec.id == e13.id
        # ohne Vorgabe: neuestes Artefakt, Zugehoerigkeit geprueft
        obj, ec = load_section(ds, "data_error", tep, "error")
        assert ec.sections["error"] in ({"idv": 29, "amp": 1.0}, {"idv": 13, "amp": 1.0})
        # Tippfehler im Typ (1 statt 1.0) -> Fehlermeldung nennt die Auspraegungen
        try:
            load_section(ds, "data_error", tep, "error", {"idv": 29, "amp": 1})
            raise AssertionError("haette fehlschlagen muessen")
        except FileNotFoundError as exc:
            assert "idv" in str(exc) and "29" in str(exc), str(exc)
        # fremder Lauf -> abgelehnt
        other = RunConfig({**tep_cfg, "seed": 7})
        try:
            load_section(ds, "data_error", other, "error")
            raise AssertionError("haette fehlschlagen muessen")
        except ValueError as exc:
            assert "baut nicht auf" in str(exc)

    # OutputStore: Archiv-Dedup, final-Promotion, Sidecar/Manifest
    with tempfile.TemporaryDirectory() as d:
        out = OutputStore(d)
        sp, ap = out.publish("fig", syn, writer=lambda p: open(p, "w").close(),
                             final=False, stable_ext="pgf", archive_ext="png")
        assert sp is None and os.path.exists(ap)
        assert not os.path.exists(out.stable_path("fig", "pgf"))
        assert os.path.exists(os.path.splitext(ap)[0] + ".json")
        calls = []
        out.publish("fig", syn, writer=calls.append, final=False, archive_ext="png")
        assert calls == []  # gleiche Konfiguration -> keine zweite Archivkopie
        sp2, _ = out.publish("fig", syn, writer=lambda p: open(p, "w").close(),
                             final=True, stable_ext="pgf", archive_ext="png")
        assert sp2 and os.path.exists(sp2) and out.final_id("fig") == syn.id
        sp3, ap3 = out.publish("fig", m1, writer=lambda p: open(p, "w").close(),
                              final=True, stable_ext="pgf", archive_ext="png")
        assert ap3 != ap and out.final_id("fig") == m1.id  # neue Konfiguration uebernimmt final
        out.save_json({"metric": 1}, "res", syn, final=True)
        assert os.path.exists(out.stable_path("res", "json"))

    # OutputStore mit Prefix: praefigiert Datei- und Manifest-Namen
    with tempfile.TemporaryDirectory() as d:
        pout = OutputStore(d, "tep")
        sp, ap = pout.publish("fig", syn, writer=lambda p: open(p, "w").close(),
                              final=True, stable_ext="pgf", archive_ext="png")
        assert os.path.basename(sp) == "tep_fig.pgf"
        assert os.path.basename(ap) == f"tep_fig_{syn.id}.png"
        assert os.path.exists(pout._manifest_path())
        assert os.path.basename(pout._manifest_path()) == "tep_outputs_manifest.json"
        assert pout.final_id("fig") == syn.id

    print("run_registry Selbsttest OK:",
          f"syn={syn.base_id} tep={tep.base_id} model={m1.id} variant={_variant_token({'idv':29,'amp':1.0})}")
