"""Fortschritt langer Notebook-Laeufe: Konsole, Statusdatei und Telegram.

Ohne Zugangsdaten bleibt Telegram stumm. Token und Chat-ID kommen aus den
Umgebungsvariablen ``TELEGRAM_BOT_TOKEN`` / ``TELEGRAM_CHAT_ID`` oder aus
``~/.config/podc/telegram.env`` (Zeilen ``NAME=wert``).

Aufruf als Skript zeigt alle Statusdateien an:
``python3 src/utils/run_status.py [verzeichnis]`` bzw. ``--test`` fuer eine
Testnachricht.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

__all__ = ["telegram", "RunStatus", "show"]

TOKEN_ENV, CHAT_ENV = "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"
CREDENTIALS_FILE = Path.home() / ".config" / "podc" / "telegram.env"
DEFAULT_DIR = Path("_temp") / "status"


def _read_env_file(path: Path) -> dict:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    pairs = (ln.split("=", 1) for ln in lines if "=" in ln and not ln.lstrip().startswith("#"))
    return {k.strip(): v.strip().strip('"').strip("'") for k, v in pairs}


def _credentials() -> tuple[str, str]:
    file_vals = _read_env_file(CREDENTIALS_FILE)
    token = os.environ.get(TOKEN_ENV) or file_vals.get(TOKEN_ENV, "")
    chat = os.environ.get(CHAT_ENV) or file_vals.get(CHAT_ENV, "")
    return token.strip(), chat.strip()


def telegram(text: str, timeout: float = 10.0) -> bool:
    """Sendet ``text`` an den konfigurierten Chat; ``False`` ohne Zugangsdaten oder Netz."""
    token, chat = _credentials()
    if not (token and chat):
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": text[:4000]}).encode()
    try:
        with urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage",
                                    data=data, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def _fmt_s(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}h{m:02d}" if h else f"{m}m{s:02d}"


class RunStatus:
    """Stufenweiser Fortschritt mit Restzeit, Statusdatei und gedrosselten Telegram-Meldungen."""

    def __init__(self, name: str, status_dir: str | Path = DEFAULT_DIR,
                 notify_every: float = 3600.0, print_every: float = 30.0):
        self.name = name
        self.host = socket.gethostname()
        self.path = Path(status_dir) / f"{name}.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.notify_every = notify_every
        self.print_every = print_every
        self.t0 = time.time()
        self.history: list[dict] = []
        self.label, self.total, self.i, self.info = None, None, 0, ""
        self._t_stage = self._t_print = self._t_notify = self.t0
        self._write("laeuft")

    def stage(self, label: str, total: int | None = None, notify: bool = False):
        if self.label is not None:
            self.done(notify=False)
        self.label, self.total, self.i, self.info = label, total, 0, ""
        self._t_stage = self._t_print = time.time()
        self._emit(force=True, notify=notify)

    def step(self, info: str = "", n: int = 1):
        self.i += n
        self.info = info
        self._emit()

    def eta(self) -> float | None:
        if not self.total or not self.i:
            return None
        return (time.time() - self._t_stage) / self.i * (self.total - self.i)

    def optuna_callback(self):
        def _cb(study, trial):
            try:
                best = f"bester Score {study.best_value:.3f}"
            except ValueError:
                best = ""
            self.step(best)
        return _cb

    def done(self, message: str = "", notify: bool = False):
        if self.label is None:
            return
        dt = time.time() - self._t_stage
        self.history.append({"stage": self.label, "seconds": round(dt), "message": message})
        text = f"{self.label} fertig nach {_fmt_s(dt)}" + (f": {message}" if message else "")
        print(f"[{self.name}] {text}", flush=True)
        self.label, self.total, self.i, self.info = None, None, 0, ""
        self._write("laeuft")
        if notify:
            self._send(text)

    def finish(self, message: str = ""):
        self.done(notify=False)
        text = f"Lauf beendet nach {_fmt_s(time.time() - self.t0)}" + (f"\n{message}" if message else "")
        print(f"[{self.name}] {text}", flush=True)
        self._write("fertig", message)
        self._send(text)

    def fail(self, error: BaseException | str):
        self._write("fehler", str(error))
        self._send(f"FEHLER in {self.label or '-'}: {error}")

    def line(self) -> str:
        part = f"{self.i}/{self.total}" if self.total else f"{self.i}"
        eta = self.eta()
        return (f"{self.label} {part} | {_fmt_s(time.time() - self._t_stage)}"
                + (f" | Rest ~{_fmt_s(eta)}" if eta is not None else "")
                + (f" | {self.info}" if self.info else ""))

    def _emit(self, force: bool = False, notify: bool = False):
        now = time.time()
        finished = bool(self.total) and self.i >= self.total
        if force or finished or now - self._t_print >= self.print_every:
            print(f"[{self.name}] {self.line()}", flush=True)
            self._t_print = now
        self._write("laeuft")
        if notify or now - self._t_notify >= self.notify_every:
            self._send(self.line())

    def _send(self, text: str):
        self._t_notify = time.time()
        telegram(f"{self.name}@{self.host}\n{text}")

    def _write(self, state: str, message: str = ""):
        doc = {"name": self.name, "host": self.host, "state": state, "message": message,
               "started": self.t0, "updated": time.time(),
               "stage": self.label, "i": self.i, "total": self.total, "info": self.info,
               "eta_s": self.eta(), "history": self.history}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)


def show(status_dir: str | Path = DEFAULT_DIR) -> str:
    rows = []
    for p in sorted(Path(status_dir).glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        age = time.time() - d["updated"]
        part = f"{d['i']}/{d['total']}" if d.get("total") else str(d.get("i", ""))
        rest = f"Rest ~{_fmt_s(d['eta_s'])}" if d.get("eta_s") is not None else ""
        rows.append(f"{d['name']:16s} {d['state']:7s} {d.get('stage') or '-'} {part} {rest}"
                    f" | gesamt {_fmt_s(d['updated'] - d['started'])}, Stand vor {_fmt_s(age)}"
                    + (f" | {d['message']}" if d.get("message") else ""))
        rows += [f"{'':16s}   {h['stage']}: {_fmt_s(h['seconds'])}" for h in d["history"][-3:]]
    return "\n".join(rows) or f"keine Statusdateien in {status_dir}"


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["--test"]:
        ok = telegram(f"Testnachricht von {socket.gethostname()}")
        print("gesendet" if ok else "nicht gesendet (Zugangsdaten oder Netz pruefen)")
    elif args[:1] == ["--send"]:
        sys.exit(0 if telegram(" ".join(args[1:])) else 1)
    else:
        print(show(args[0] if args else DEFAULT_DIR))
