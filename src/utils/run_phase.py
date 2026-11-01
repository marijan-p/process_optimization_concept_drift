"""Phasensteuerung langer Notebook-Laeufe.

Ein Notebook beendet eine Phase, indem es eine Gate-Datei unter
``_temp/gates/<name>_<phase>.json`` schreibt und :class:`PhaseDone` wirft.
papermill bricht damit ab; ``run_all.sh`` erkennt das planmaessige Ende an der
Gate-Datei und entscheidet anhand ihres Inhalts ueber die naechste Phase.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

__all__ = ["PHASES", "PhaseDone", "gate_path", "finish_phase"]

PHASES = ("probe", "tune", "full")


class PhaseDone(Exception):
    """Planmaessiges Ende einer Phase, kein Fehler."""


def gate_path(base_dir, name: str, phase: str) -> Path:
    return Path(base_dir) / "_temp" / "gates" / f"{name}_{phase}.json"


def _plain(obj):
    return obj.item() if hasattr(obj, "item") else str(obj)


def finish_phase(base_dir, name: str, phase: str, doc: dict):
    """Schreibt die Gate-Datei und beendet die Phase."""
    path = gate_path(base_dir, name, phase)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"name": name, "phase": phase, "time": time.time(), **doc},
                              ensure_ascii=False, indent=1, default=_plain), encoding="utf-8")
    tmp.replace(path)
    raise PhaseDone(f"{name}: Phase {phase} beendet, Gate {path}")


def _summary(phase: str, doc: dict) -> tuple[bool, str]:
    if phase == "probe":
        rows = [f"  {q['strategy']} {q['param']} ({q['side']}): "
                f"{'bindet' if q['binding'] else 'bindet nicht'}" for q in doc["probes"]]
        return bool(doc["binding"]), "\n".join(rows) or "  keine Parameter am Rand"
    rows = [f"  Rand: {s} {e['param']} ({e['side']}, Lage {e['pos']:.2f})"
            for s, es in doc["edges"].items() for e in es]
    rows += [f"  Verduennung: {s} {d['new']:.3f} gegen {d['old']:.3f}"
             for s, d in doc["dilution"].items() if d.get("diluted")]
    return bool(doc["pass"]), "\n".join(rows) or "  keine Befunde"


def decide(phase: str, gates_dir, names, since: float) -> int:
    """Wertet die Gate-Dateien einer Phase aus. Rueckgabe 0 = weiter, 1 = Abbruch
    nach Regel, 2 = Gate fehlt oder ist aelter als ``since``. Weiter geht es nach
    der Sonde, wenn in mindestens einem Fall eine Grenze bindet, nach dem Tuning
    nur, wenn beide Faelle die Pruefung bestehen."""
    verdicts = []
    for name in names:
        path = Path(gates_dir) / f"{name}_{phase}.json"
        if not path.exists() or json.loads(path.read_text(encoding="utf-8"))["time"] < since:
            print(f"{name}: kein aktuelles Gate fuer Phase {phase}")
            return 2
        ok, text = _summary(phase, json.loads(path.read_text(encoding="utf-8")))
        verdicts.append(ok)
        print(f"{name}:\n{text}")
    go = any(verdicts) if phase == "probe" else all(verdicts)
    print("-> weiter" if go else "-> Abbruch nach Regel")
    return 0 if go else 1


if __name__ == "__main__":
    import sys

    _, cmd, phase, gates_dir, since, *names = sys.argv
    assert cmd == "decide" and phase in PHASES[:2], sys.argv
    sys.exit(decide(phase, gates_dir, names, float(since)))
