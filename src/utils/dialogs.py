"""Zentrale Dialog- und Anzeige-Hilfsfunktionen (tkinter).

Fällt automatisch auf Konsolenausgabe zurück, wenn kein Display verfügbar ist.
"""

# Notwendig, damit die Signaturen (str | None, list[tuple[str, str]] | None) auch
# unter Python < 3.10 importierbar bleiben -- der TEP-Kernel ist aelter als die
# uebrigen Umgebungen. Analog zu den anderen Modulen in src/.
from __future__ import annotations

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

__all__ = [
    "has_display",
    "show_copyable",
    "show_info",
    "show_warning",
    "show_error",
    "ask_yes_no",
    "ask_text",
    "ask_number",
    "ask_choice",
    "select_file",
    "select_directory",
    "save_file_as",
    "show_dataframe",
    "copy_to_clipboard",
    "notify",
    "show_with_copy_button",
    "progress",
]


# --- Hilfsfunktionen ---------------------------------------------------------

def has_display() -> bool:
    """True, wenn eine GUI verfügbar ist (z. B. nicht auf headless Cluster)."""
    if sys.platform in ("win32", "darwin"):
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def _bring_to_front(window: tk.Misc) -> None:
    window.lift()
    window.attributes("-topmost", True)
    window.after(100, lambda: window.attributes("-topmost", False))
    window.focus_force()


def _hidden_root() -> tk.Tk:
    """Unsichtbares Root-Fenster für messagebox/filedialog/simpledialog."""
    root = tk.Tk()
    root.withdraw()
    _bring_to_front(root)
    return root


def _with_hidden_root(func):
    """Führt func(root) mit temporärem Root aus und räumt danach auf."""
    root = _hidden_root()
    try:
        return func(root)
    finally:
        root.destroy()


# --- Anzeige -----------------------------------------------------------------

def show_copyable(title: str, message: str, height: int = 5, width: int = 40) -> None:
    """Zeigt Text in einem markier- und kopierbaren Fenster."""
    if not has_display():
        return notify(title, message)

    root = tk.Tk()
    root.title(title)

    frame = tk.Frame(root)
    frame.pack(padx=10, pady=10, fill="both", expand=True)

    scrollbar = tk.Scrollbar(frame)
    scrollbar.pack(side="right", fill="y")

    text = tk.Text(frame, wrap="word", height=height, width=width,
                   yscrollcommand=scrollbar.set)
    text.insert("1.0", message)
    text.configure(state="disabled")
    text.pack(side="left", fill="both", expand=True)
    scrollbar.configure(command=text.yview)

    tk.Button(root, text="OK", command=root.destroy).pack(pady=(0, 10))
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    _bring_to_front(root)
    root.mainloop()


def show_info(title: str, message: str) -> None:
    if not has_display():
        return notify(title, message)
    _with_hidden_root(lambda r: messagebox.showinfo(title, message, parent=r))


def show_warning(title: str, message: str) -> None:
    if not has_display():
        return notify(f"WARNUNG: {title}", message)
    _with_hidden_root(lambda r: messagebox.showwarning(title, message, parent=r))


def show_error(title: str, message: str) -> None:
    if not has_display():
        return notify(f"FEHLER: {title}", message)
    _with_hidden_root(lambda r: messagebox.showerror(title, message, parent=r))


# --- Eingaben ----------------------------------------------------------------

def ask_yes_no(title: str, question: str, default: bool = False) -> bool:
    if not has_display():
        notify(title, f"{question} -> Standard: {default}")
        return default
    return _with_hidden_root(
        lambda r: messagebox.askyesno(title, question, parent=r)
    )


def ask_text(title: str, prompt: str, initial: str = "") -> str | None:
    if not has_display():
        return None
    return _with_hidden_root(
        lambda r: simpledialog.askstring(title, prompt, initialvalue=initial, parent=r)
    )


def ask_number(title: str, prompt: str, initial: float | None = None,
               minimum: float | None = None, maximum: float | None = None) -> float | None:
    if not has_display():
        return None
    kwargs = {"parent": None}
    if initial is not None:
        kwargs["initialvalue"] = initial
    if minimum is not None:
        kwargs["minvalue"] = minimum
    if maximum is not None:
        kwargs["maxvalue"] = maximum

    def _ask(root):
        kwargs["parent"] = root
        return simpledialog.askfloat(title, prompt, **kwargs)

    return _with_hidden_root(_ask)


def ask_choice(title: str, prompt: str, options: list[str],
               default: str | None = None) -> str | None:
    """Auswahl aus einer Liste per Combobox. None bei Abbruch."""
    if not has_display():
        return default

    result: list[str | None] = [None]

    root = tk.Tk()
    root.title(title)

    tk.Label(root, text=prompt).pack(padx=10, pady=(10, 5))

    var = tk.StringVar(value=default or options[0])
    combo = ttk.Combobox(root, textvariable=var, values=options,
                         state="readonly", width=40)
    combo.pack(padx=10, pady=5)

    def confirm():
        result[0] = var.get()
        root.destroy()

    button_frame = tk.Frame(root)
    button_frame.pack(pady=10)
    tk.Button(button_frame, text="OK", command=confirm).pack(side="left", padx=5)
    tk.Button(button_frame, text="Abbrechen", command=root.destroy).pack(side="left", padx=5)

    combo.bind("<Return>", lambda _: confirm())
    root.protocol("WM_DELETE_WINDOW", root.destroy)

    _bring_to_front(root)
    root.mainloop()
    return result[0]


# --- Dateien -----------------------------------------------------------------

def select_file(title: str = "Datei wählen",
                filetypes: list[tuple[str, str]] | None = None,
                initial_dir: str | Path | None = None) -> Path | None:
    if not has_display():
        return None
    filetypes = filetypes or [("Alle Dateien", "*.*")]

    def _ask(root):
        return filedialog.askopenfilename(
            title=title, filetypes=filetypes,
            initialdir=str(initial_dir) if initial_dir else None, parent=root,
        )

    path = _with_hidden_root(_ask)
    return Path(path) if path else None


def select_directory(title: str = "Ordner wählen",
                     initial_dir: str | Path | None = None) -> Path | None:
    if not has_display():
        return None

    def _ask(root):
        return filedialog.askdirectory(
            title=title,
            initialdir=str(initial_dir) if initial_dir else None, parent=root,
        )

    path = _with_hidden_root(_ask)
    return Path(path) if path else None


def save_file_as(title: str = "Speichern unter",
                 default_name: str = "",
                 filetypes: list[tuple[str, str]] | None = None,
                 initial_dir: str | Path | None = None) -> Path | None:
    if not has_display():
        return None
    filetypes = filetypes or [("Alle Dateien", "*.*")]

    def _ask(root):
        return filedialog.asksaveasfilename(
            title=title, initialfile=default_name, filetypes=filetypes,
            initialdir=str(initial_dir) if initial_dir else None, parent=root,
        )

    path = _with_hidden_root(_ask)
    return Path(path) if path else None


# --- DataFrame ---------------------------------------------------------------

def show_dataframe(df, title: str = "DataFrame", max_rows: int = 1000) -> None:
    """Zeigt einen pandas DataFrame als scrollbare Tabelle."""
    if not has_display():
        return notify(title, df.head(max_rows).to_string())

    root = tk.Tk()
    root.title(f"{title} ({len(df)} Zeilen x {len(df.columns)} Spalten)")

    frame = tk.Frame(root)
    frame.pack(fill="both", expand=True, padx=5, pady=5)

    columns = ["index"] + [str(c) for c in df.columns]
    tree = ttk.Treeview(frame, columns=columns, show="headings", height=20)

    for col in columns:
        tree.heading(col, text=col)
        tree.column(col, width=100, anchor="center")

    for idx, row in df.head(max_rows).iterrows():
        tree.insert("", "end", values=[idx] + [str(v) for v in row])

    y_scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
    x_scroll = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=y_scroll.set, xscrollcommand=x_scroll.set)

    tree.grid(row=0, column=0, sticky="nsew")
    y_scroll.grid(row=0, column=1, sticky="ns")
    x_scroll.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)

    if len(df) > max_rows:
        tk.Label(root, text=f"Nur die ersten {max_rows} Zeilen werden angezeigt.",
                 fg="gray").pack(pady=(0, 5))

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    _bring_to_front(root)
    root.mainloop()


# --- Sonstiges ---------------------------------------------------------------

def copy_to_clipboard(text: str) -> bool:
    """Kopiert Text in die Zwischenablage, ohne ein Fenster zu zeigen."""
    if not has_display():
        return False
    root = tk.Tk()
    root.withdraw()
    try:
        root.clipboard_clear()
        root.clipboard_append(text)
        root.update()  # nötig, damit der Inhalt persistiert
        return True
    finally:
        root.destroy()


def notify(title: str, message: str) -> None:
    """Konsolen-Fallback ohne GUI-Abhängigkeit."""
    print(f"\n--- {title} ---\n{message}\n", flush=True)


def show_with_copy_button(title: str, message: str, copy_value: str,
                          button_text: str = "ID kopieren",
                          wraplength: int = 500) -> None:
    """Zeigt Infotext mit Button, der copy_value in die Zwischenablage kopiert."""
    notify(title, message)
    if not has_display():
        return

    root = tk.Tk()
    root.title(title)

    tk.Label(root, text=message, justify="left", wraplength=wraplength).pack(
        padx=15, pady=(15, 5)
    )

    status_var = tk.StringVar(value="")
    tk.Label(root, textvariable=status_var, fg="gray").pack()

    def copy():
        root.clipboard_clear()
        root.clipboard_append(copy_value)
        root.update()
        status_var.set(f"'{copy_value}' kopiert.")

    button_frame = tk.Frame(root)
    button_frame.pack(pady=(5, 15))
    tk.Button(button_frame, text=button_text, command=copy).pack(side="left", padx=5)
    tk.Button(button_frame, text="OK", command=root.destroy).pack(side="left", padx=5)

    root.protocol("WM_DELETE_WINDOW", root.destroy)
    _bring_to_front(root)
    root.mainloop()


class progress:
    """Fortschrittsbalken für lange Läufe.

    Beispiel:
        for item in progress(items, title="Simulation"):
            ...
    """

    def __init__(self, iterable, title: str = "Fortschritt", label: str = ""):
        self.iterable = list(iterable)
        self.title = title
        self.label = label
        self.enabled = has_display()

    def __iter__(self):
        total = len(self.iterable)
        if not self.enabled or total == 0:
            yield from self.iterable
            return

        root = tk.Tk()
        root.title(self.title)
        root.resizable(False, False)

        text_var = tk.StringVar(value=self.label or f"0 / {total}")
        tk.Label(root, textvariable=text_var).pack(padx=20, pady=(15, 5))

        bar = ttk.Progressbar(root, length=300, maximum=total, mode="determinate")
        bar.pack(padx=20, pady=(0, 15))

        cancelled = [False]

        def cancel():
            cancelled[0] = True
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", cancel)
        _bring_to_front(root)

        try:
            for i, item in enumerate(self.iterable, start=1):
                if cancelled[0]:
                    break
                yield item
                bar["value"] = i
                text_var.set(self.label or f"{i} / {total}")
                root.update()
        finally:
            if not cancelled[0]:
                root.destroy()