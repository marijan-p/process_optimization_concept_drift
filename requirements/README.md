# Umgebungen aufsetzen

Nach einem frischen Klon genügt ein Aufruf in der Projektwurzel:

```powershell
.\requirements\setup_envs.ps1
```

Meldet PowerShell, dass die Ausführung von Skripts deaktiviert ist, betrifft das nur die
laufende Sitzung und lässt sich für diese eine aufheben:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Das gilt bis das Fenster geschlossen wird. Typisch ist der Fall in einer als
Administrator gestarteten Sitzung, weil dort die Richtlinie von `LocalMachine` greift
und nicht die von `CurrentUser`.

Das Skript legt beide Umgebungen an, installiert die MATLAB-Engine und pytep, schreibt
die Pfaddatei und prüft am Ende, ob alles importierbar ist. Weichen die Pfade zu
Python 3.7, MATLAB oder pytep ab, lassen sie sich als Parameter übergeben:

```powershell
.\requirements\setup_envs.ps1 -MatlabRoot "D:\MATLAB\R2020b" -PytepPath "D:\git\pytep"
```

Der Rest dieser Datei erklärt, was das Skript tut und warum.

---

## Die zwei Umgebungen

| Umgebung | Python | wofür | verwaltet von |
|---|---|---|---|
| `.venv` | 3.11.5 | alles außer `tep_generation` | uv, über `pyproject.toml` und `uv.lock` |
| `.venv_tep` | 3.7.9 | nur `ipynb/tep/tep_generation.ipynb` | pip, über `requirements/venv_tep.txt` |

Nur `tep_generation` hängt zwingend an 3.7, weil dort `pytep` und die MATLAB-Engine
gebraucht werden. `tep_model`, `tep_detection` und `tep_adaptation` laufen in `.venv`,
ebenso alle `syn_*`-Notebooks.

Beide Namen sind mit Bedacht gewählt. `.venv` ist der Vorgabename von uv, damit
funktioniert `uv sync` in einem Klon ohne jede weitere Einstellung. `.venv_tep` sagt,
wofür die zweite Umgebung da ist, statt nur welche Python-Version darin steckt.

> uv unterstützt offiziell erst ab Python 3.8. Für 3.7 gibt es Berichte, dass es
> funktioniert, aber keine Testabdeckung. Deshalb bleibt `.venv_tep` bei pip. Zwei
> Paketmanager sind der Preis für die MATLAB-Bindung, nicht eine Nachlässigkeit.

## Welche Dateien wozu gehören

```
pyproject.toml        Direktabhängigkeiten von .venv
uv.lock               aufgelöste Hülle dazu, gehört ins Repo
requirements/
  README.md           diese Anleitung
  setup_envs.ps1      richtet beide Umgebungen ein
  venv_tep.in         Direktabhängigkeiten von .venv_tep, von Hand gepflegt
  venv_tep.txt        aufgelöste Hülle dazu, aus pip freeze
```

`pyproject.toml` und `uv.lock` müssen im Wurzelverzeichnis bleiben, uv sucht sie genau
dort. Für `.venv` gibt es deshalb keine Datei unter `requirements/`.

Vier Schritte lassen sich in gar keiner Requirements-Datei ausdrücken, und genau dafür
gibt es das Skript: die MATLAB-Engine aus dem MATLAB-Verzeichnis, pytep editierbar, die
`local_paths.pth` in beiden Umgebungen und die Kontrolle am Ende.

---

## .venv

```powershell
uv sync
```

Das legt `.venv` an und installiert den in `uv.lock` festgehaltenen Stand.

> [!warning] UV_PROJECT_ENVIRONMENT
> uv legt die Projektumgebung nach `.venv`, sofern nicht die Umgebungsvariable
> `UV_PROJECT_ENVIRONMENT` dazwischenfunkt. Einen Schlüssel in `pyproject.toml` oder
> `uv.toml` gibt es dafür nicht, es ist ausschließlich die Variable. Steht sie noch von
> früher auf einem anderen Wert, entsteht still eine zweite Umgebung daneben:
> ```powershell
> [Environment]::SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", $null, "User")
> ```

Neue Abhängigkeiten immer mit `uv add` aufnehmen, nie mit `pip install` in die venv
schieben. pip schreibt weder `pyproject.toml` noch `uv.lock`, und der nächste
`uv sync` wirft das Paket wieder heraus.

Legt uv die Umgebung einmal neu an, etwa nach einem Wechsel der Python-Version, ist die
`local_paths.pth` weg und die Notebooks finden `src` nicht mehr. Dann `setup_envs.ps1`
noch einmal laufen lassen, es ist wiederholbar und schreibt die Datei neu.

### Was den numerischen Stack festlegt

`frouros` 0.9.0 ist die neueste Fassung und deckelt `numpy<2.2`, `scipy<1.15`,
`matplotlib<3.10` sowie Python `<3.13`. Es ist die einzige Detektor-Bibliothek, die der
Code importiert. Damit bestimmt frouros faktisch die Obergrenzen des gesamten Stacks.
Vor jedem `uv add` prüfen, ob die neue Abhängigkeit dagegen läuft.

`river` kann daneben nicht existieren, es fordert `numpy>=2.2.5`. Es wird nirgends
importiert und ist deshalb ausgetragen. Soll es später als Alternative zu frouros
geprüft werden, braucht das eine eigene Umgebung.

---

## .venv_tep

Die Reihenfolge ist bindend. MATLAB muss vor der Engine da sein, die Engine vor pytep.
Das Skript hält sie ein, hier stehen die Schritte einzeln.

**Python 3.7.9** von python.org, `python-3.7.9-amd64.exe`. Nicht über winget, nicht über
den Store. Bei der Installation "Add Python to PATH" nicht ankreuzen, damit 3.11 die
Standardversion bleibt.

```powershell
C:\Program Files\Python\Python37\python.exe -m venv --prompt tep-py37 .venv_tep
.\.venv_tep\Scripts\python.exe -m pip install --upgrade "pip==24.0" "setuptools==65.6.3" "wheel==0.37.1"
.\.venv_tep\Scripts\python.exe -m pip install --no-deps -r requirements\venv_tep.txt
```

Die drei Stände sind gepinnt, nicht gedeckelt. Aktuelle pip-Versionen laufen nicht mehr
unter 3.7, und setuptools meldet ab 67 die Versionsangabe `R2020b` der MATLAB-Engine als
nicht PEP-440-konform. 65.6.3 ist der Stand, unter dem die Installation auf diesem
Rechner funktioniert hat.

`--no-deps` ist ebenfalls kein Komfort: ohne die Option löst pip neu auf und bricht mit
`ResolutionImpossible` ab, sobald die Umgebung Reste einer früheren Installation trägt.
Die Datei ist bereits die vollständige Hülle.

**MATLAB-Engine**, aus dem MATLAB-Verzeichnis heraus:

```powershell
cd "C:\Program Files\MATLAB\R2020b\extern\engines\python"
$env:SETUPTOOLS_USE_DISTUTILS = "stdlib"
& C:\git\process_optimization_concept_drift\.venv_tep\Scripts\python.exe setup.py `
    build --build-base "$env:TEMP\matlabengine-build" install
Remove-Item Env:\SETUPTOOLS_USE_DISTUTILS
& C:\git\process_optimization_concept_drift\.venv_tep\Scripts\python.exe -c "import matlab.engine; print('engine ok')"
```

Zwei Zeilen davon sind der Kern, und beide brauchten mehrere Anläufe.

> [!warning] Nicht aus einer Kopie installieren
> `setup.py` leitet den MATLAB-Wurzelpfad aus seiner eigenen Lage ab. Kopiert man das
> Verzeichnis anderswohin, um Schreibzugriffe auf Program Files zu vermeiden, bricht es
> mit `The installation of MATLAB is corrupted` ab. Die Meldung ist irreführend, MATLAB
> ist in Ordnung. Der Aufruf muss im Originalverzeichnis stattfinden.

Damit steht das Arbeitsverzeichnis unter Program Files und ist nicht schreibbar. Ohne
`SETUPTOOLS_USE_DISTUTILS=stdlib` zieht `distutils-precedence.pth` die
setuptools-Fassung von distutils heran, und dann wird aus `install` ein Egg-Install über
`egg_info` und `bdist_egg`. Beide schreiben ins Arbeitsverzeichnis, das erste sein
`egg-info` neben `setup.py`, das zweite das fertige Egg nach `dist\`. Windows quittiert
das mit `[Errno 13] Permission denied: 'dist\matlabengineforpython-R2020b-py3.7.egg'`.

Mit dem echten distutils der Standardbibliothek ist `install` ein schlichtes Kopieren
nach `site-packages`, ohne jeden Schreibzugriff auf Program Files. `--build-base` lenkt
den einzigen verbleibenden Zwischenschritt ins TEMP.

Die letzte Zeile ist kein Beiwerk. `setup.py` der Engine kann mit Exitcode 0 enden, ohne
dass in `site-packages` etwas ankommt — der Import ist der einzige belastbare Nachweis.
Danach den Jupyter-Kernel neu starten, sonst behält er den fehlgeschlagenen Import im
Speicher.

Auf dem alten Rechner lag die Engine als Egg samt `easy-install.pth` in
`site-packages`, auf diesem Weg landet sie als gewöhnliches Paket. Für `import
matlab.engine` macht das keinen Unterschied. In `pip freeze` erscheint sie als
`matlabengineforpython===r2020b` und muss aus jeder installierbaren Datei heraus.

**pytep** editierbar, damit Änderungen am Fork sofort greifen und der veröffentlichte
Stand derselbe ist wie der benutzte:

```powershell
.\.venv_tep\Scripts\python.exe -m pip install -e C:\git\pytep --no-deps
```

`--no-deps`, weil `setup.py` der Fork `dash` und `pytest` deklariert, obwohl das Paket
nur `matlab.engine`, `numpy` und `pandas` importiert.

**Pfaddatei.** Beide Umgebungen brauchen
`Lib\site-packages\local_paths.pth` mit zwei Zeilen, sonst finden die Notebooks `src`
nicht:

```
C:\git\process_optimization_concept_drift\
C:\git\process_optimization_concept_drift\src
```

### Wheelhouse

Python 3.7 ist seit Juni 2023 am Ende seiner Lebenszeit, neue Pakete bauen keine Wheels
mehr dafür. Wenn ein Wheel nicht mehr erreichbar ist, hilft nur ein Vorrat aus einer
laufenden Umgebung:

```powershell
.\.venv_tep\Scripts\python.exe -m pip download --no-deps --prefer-binary `
    -r requirements\venv_tep.txt -d wheelhouse_tep
```

Installation daraus mit `--no-index --find-links wheelhouse_tep`.

### Wenn venv_tep.txt neu geschrieben wird

```powershell
.\.venv_tep\Scripts\python.exe -m pip freeze | Set-Content requirements\venv_tep.txt -Encoding ascii
```

`-Encoding ascii` ist wichtig. PowerShell schreibt mit `>` und mit `Out-File`
standardmäßig UTF-16, und daran scheitert pip beim Lesen. Danach die beiden Zeilen
`matlabengineforpython` und `-e git+…#egg=pytep` wieder von Hand entfernen. Beide sind
nicht installierbar, die pytep-Zeile zeigt auf einen Commit, den es nur lokal gibt.

---

## Was in .venv_tep bewusst fehlt

Die Umgebung ist auf das reduziert, was `tep_generation`, `src/utils/*` und `pytep`
tatsächlich importieren. Herausgefallen sind TensorFlow mit Keras und dem gesamten
tensorboard-Anhang, scikit-learn, dash mit Flask und plotly, pytest und pyDOE2. Nichts
davon steht in einer `import`-Zeile, die unter 3.7 ausgeführt wird. Aus 95 Paketen sind
39 geworden.

`seaborn` ist der einzige Fall, der nicht zwingend ist. `thesis_style` importiert es erst
innerhalb von `violin_box`, und `tep_generation` ruft die Funktion nicht auf. Da
`src/utils` von beiden Umgebungen geteilt wird, bleibt es trotzdem drin.

---

## Zwei Nahtstellen zwischen den Umgebungen

**pandas-Pickles laufen nur in eine Richtung.** `.venv_tep` schreibt, `.venv` liest.
`pickle.load` scheitert an DataFrames aus pandas 1.3.5, weil dort die Block-Platzierung
als `slice` abgelegt ist. `run_registry._load_pickle` fängt das ab und weicht auf
`pd.read_pickle` aus. Umgekehrt gibt es keinen Weg, pandas-3-Pickles sind unter 1.3.5
nicht lesbar.

**Der Cache-Schlüssel kennt die Umgebung nicht.** Identische Kennungen entstehen unter
3.7 und unter 3.11. Wird eine Stufe von einer Umgebung in die andere verlegt, die
betroffene Kette am Stück mit `FORCE_RECOMPUTE=True` neu rechnen und nicht stufenweise
mischen. Zur Nachvollziehbarkeit schreibt `ArtifactStore._sidecar` ein Feld `env` mit
venv-Name, Python-Version und den Versionen der bereits importierten Bibliotheken.

Aus derselben Bindung folgt, dass `src/utils/*` 3.7-tauglich bleiben muss, also
`from __future__ import annotations` in jedem Modul und keine Syntax jenseits von 3.7.

---

## Offene Punkte

**requires-python ohne Obergrenze.** `pyproject.toml` sagt `>=3.11.5`, frouros deckelt
auf `<3.13`. Bisher hat uv das ohne Konflikt aufgelöst. Für ein Projekt, das an genau
einer Python-Version hängt, wäre `">=3.11.5,<3.13"` ehrlicher. Änderung nur zusammen mit
`uv lock`, sonst passt der Lock nicht mehr zur Datei.

**pandas 3 gegen pandas 2.** `pyproject.toml` fordert `pandas>=2.0`, uv löst daraus 3.0.5
auf. Alle vorliegenden Ergebnisse und Abbildungen sind unter 2.3.1 entstanden, und pandas
3.0 ändert Vorgaben, auf die die Notebooks durchgehend treffen. Soll der bisherige Stand
reproduzierbar bleiben, ist `uv add "pandas>=2.3,<3"` der Schritt.

**matplotlib in zwei Versionen.** `tep_generation` rendert seine Abbildungen mit
matplotlib 3.5.3, der Rest der Arbeit mit 3.9.4. Bleibt es dabei, stammen diese
Abbildungen aus einer anderen Renderer-Version als alle übrigen.
