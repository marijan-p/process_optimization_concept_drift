<#
.SYNOPSIS
    Setzt beide Python-Umgebungen des Projekts auf.

.DESCRIPTION
    .venv      Python 3.11, von uv aus pyproject.toml und uv.lock
    .venv_tep  Python 3.7, von pip aus requirements\venv_tep.txt,
               dazu die MATLAB-Engine und pytep

    Das Skript ist wiederholbar. Vorhandene Umgebungen werden uebersprungen,
    ausser mit -Force.

.EXAMPLE
    .\requirements\setup_envs.ps1
    .\requirements\setup_envs.ps1 -Force -MatlabRoot "D:\MATLAB\R2020b"
#>
[CmdletBinding()]
param(
    [string]$Python37   = "C:\Program Files\Python\Python37\python.exe",
    [string]$MatlabRoot = "C:\Program Files\MATLAB\R2020b",
    [string]$PytepPath  = "C:\git\pytep",
    [switch]$SkipMain,
    [switch]$SkipTep,
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$Root    = Split-Path -Parent $PSScriptRoot
$MainEnv = Join-Path $Root ".venv"
$TepEnv  = Join-Path $Root ".venv_tep"

function Step($text) { Write-Host "`n=== $text" -ForegroundColor Cyan }
function Note($text) { Write-Host "    $text" -ForegroundColor DarkGray }
function Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

# PowerShell laesst native Programme still scheitern. Exitcode selbst pruefen.
# Der Parameter heisst bewusst nicht $Args - das ist eine automatische Variable
# und kommt in einer Funktion leer an, das Programm liefe dann ohne Argumente.
function Invoke-Checked {
    param([string]$Exe, [string[]]$ArgList)
    & $Exe @ArgList
    if ($LASTEXITCODE -ne 0) {
        throw ("Abbruch mit Code $LASTEXITCODE. Die eigentliche Meldung steht oberhalb " +
               "dieser Zeile in der Ausgabe des Programms.`n  $Exe $($ArgList -join ' ')")
    }
}

function Write-LocalPaths {
    param([string]$VenvDir)
    $sp = Join-Path $VenvDir "Lib\site-packages"
    if (-not (Test-Path $sp)) { throw "site-packages fehlt in $VenvDir." }
    # src/ und die Wurzel auf den Suchpfad. Die Notebooks importieren
    # `from src.utils import ...` aus Unterordnern heraus und finden es sonst nicht.
    Set-Content -Path (Join-Path $sp "local_paths.pth") `
                -Value @("$Root\", (Join-Path $Root "src")) -Encoding ascii
    Note "local_paths.pth geschrieben"
}

# ---------------------------------------------------------------- Vorpruefung

Step "Vorpruefung"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw "uv nicht gefunden. Installation: winget install astral-sh.uv"
}
Note "uv $((uv --version) -replace '^uv ', '')"

# uv legt die Projektumgebung nach .venv, sofern diese Variable nicht dazwischenfunkt.
# Es gibt dafuer keinen Schluessel in pyproject.toml oder uv.toml, nur die Variable.
if ($env:UV_PROJECT_ENVIRONMENT -and $env:UV_PROJECT_ENVIRONMENT -ne ".venv") {
    Warn "UV_PROJECT_ENVIRONMENT steht auf '$env:UV_PROJECT_ENVIRONMENT'."
    Warn "Fuer diesen Lauf auf .venv gesetzt. Dauerhaft entfernen mit:"
    Warn '  [Environment]::SetEnvironmentVariable("UV_PROJECT_ENVIRONMENT", $null, "User")'
}
$env:UV_PROJECT_ENVIRONMENT = ".venv"

if (-not $SkipTep) {
    if (-not (Test-Path $Python37)) {
        throw "Python 3.7 nicht gefunden unter $Python37. Pfad mit -Python37 angeben."
    }
    $v = & $Python37 -c "import sys; print('%d.%d' % sys.version_info[:2])"
    if ($v -ne "3.7") { throw "$Python37 meldet Python $v, erwartet wird 3.7." }
    Note "Python 3.7 unter $Python37"

    $engineDir = Join-Path $MatlabRoot "extern\engines\python"
    if (-not (Test-Path (Join-Path $engineDir "setup.py"))) {
        throw "MATLAB-Engine nicht gefunden unter $engineDir. Pfad mit -MatlabRoot angeben."
    }
    Note "MATLAB-Engine unter $engineDir"

    if (-not (Test-Path (Join-Path $PytepPath "setup.py"))) {
        throw "pytep nicht gefunden unter $PytepPath. Pfad mit -PytepPath angeben."
    }
    Note "pytep unter $PytepPath"
}

# ------------------------------------------------------------------- .venv

if (-not $SkipMain) {
    Step ".venv - Python 3.11 ueber uv"

    if ((Test-Path $MainEnv) -and $Force) {
        Note "vorhandene Umgebung wird entfernt"
        Remove-Item $MainEnv -Recurse -Force
    }

    Push-Location $Root
    try { Invoke-Checked "uv" @("sync") } finally { Pop-Location }

    Write-LocalPaths $MainEnv
}

# --------------------------------------------------------------- .venv_tep

if (-not $SkipTep) {
    Step ".venv_tep - Python 3.7 ueber pip"

    if ((Test-Path $TepEnv) -and $Force) {
        Note "vorhandene Umgebung wird entfernt"
        Remove-Item $TepEnv -Recurse -Force
    }

    $tepPy = Join-Path $TepEnv "Scripts\python.exe"

    if (-not (Test-Path $tepPy)) {
        Invoke-Checked $Python37 @("-m", "venv", "--prompt", "tep-py37", $TepEnv)
        Note "Umgebung angelegt"
    } else {
        Note "Umgebung besteht bereits, Pakete werden aktualisiert"
    }

    # Genau die Staende aus venv_37, unter denen die Engine-Installation auf diesem
    # Rechner funktioniert hat. Aktuelle pip-Versionen laufen ohnehin nicht mehr
    # unter 3.7, und setuptools stolpert ab 67 ueber die Versionsangabe "R2020b"
    # der Engine, die nicht PEP-440-konform ist.
    Invoke-Checked $tepPy @("-m", "pip", "install", "--upgrade", "--quiet",
                            "pip==24.0", "setuptools==65.6.3", "wheel==0.37.1")
    Note "pip 24.0, setuptools 65.6.3 und wheel 0.37.1 gesetzt"

    # --no-deps ist zwingend. Sonst loest pip neu auf und bricht mit
    # ResolutionImpossible ab, sobald Reste einer frueheren Installation liegen.
    # Die Datei ist bereits die vollstaendige Huelle.
    Invoke-Checked $tepPy @("-m", "pip", "install", "--no-deps",
                            "-r", (Join-Path $PSScriptRoot "venv_tep.txt"))
    Note "39 Pakete installiert"

    Step "MATLAB-Engine"
    $engineDir = Join-Path $MatlabRoot "extern\engines\python"

    $prev = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $tepPy -c "import matlab.engine" 2>&1 | Out-Null
    $engineOk = ($LASTEXITCODE -eq 0)
    $ErrorActionPreference = $prev

    if ($engineOk) {
        Note "bereits installiert, uebersprungen"
    } else {
        # Zwingend aus dem MATLAB-Verzeichnis heraus. setup.py leitet den
        # MATLAB-Wurzelpfad aus seiner eigenen Lage ab und meldet aus jedem anderen
        # Ordner "The installation of MATLAB is corrupted". Eine Kopie ins TEMP,
        # um Schreibzugriffe auf Program Files zu vermeiden, funktioniert deshalb nicht.
        $tmpBuild = Join-Path $env:TEMP "matlabengine-build"
        $tmpDist  = Join-Path $env:TEMP "matlabengine-dist"
        $tmpEgg   = Join-Path $env:TEMP "matlabengine-egginfo"
        foreach ($d in @($tmpBuild, $tmpDist, $tmpEgg)) {
            Remove-Item $d -Recurse -Force -ErrorAction SilentlyContinue
            New-Item -ItemType Directory -Path $d -Force | Out-Null
        }

        # Erster Weg: echtes distutils statt der setuptools-Fassung. Dann ist
        # `install` ein schlichtes Kopieren nach site-packages, ohne egg_info und
        # ohne bdist_egg. Genau die beiden schreiben sonst neben setup.py und nach
        # dist\, also unter Program Files, und scheitern dort an den Rechten.
        # Ohne diese Variable zieht distutils-precedence.pth die setuptools-Fassung.
        $wegA = @("setup.py", "build", "--build-base", $tmpBuild, "install")

        # Zweiter Weg, falls setuptools sich nicht abwaehlen laesst: die
        # setuptools-Fassung mit allen drei Ausgabepfaden im TEMP.
        $wegB = @("setup.py",
                  "egg_info",  "--egg-base",   $tmpEgg,
                  "build",     "--build-base", $tmpBuild,
                  "bdist_egg", "--dist-dir",   $tmpDist,
                  "install")

        Push-Location $engineDir
        try {
            $prev = $ErrorActionPreference
            $ErrorActionPreference = "Continue"

            $env:SETUPTOOLS_USE_DISTUTILS = "stdlib"
            & $tepPy @wegA
            Remove-Item Env:\SETUPTOOLS_USE_DISTUTILS -ErrorAction SilentlyContinue

            & $tepPy -c "import matlab.engine" 2>&1 | Out-Null
            if ($LASTEXITCODE -ne 0) {
                Warn "Erster Weg ohne Erfolg, zweiter Anlauf ueber setuptools."
                & $tepPy @wegB
                & $tepPy -c "import matlab.engine" 2>&1 | Out-Null
            }
            $engineOk = ($LASTEXITCODE -eq 0)

            $ErrorActionPreference = $prev

            # Nicht auf den Exitcode verlassen. setup.py der Engine kann mit 0 enden,
            # ohne dass in site-packages etwas ankommt. Der Import ist der Beweis.
            if (-not $engineOk) {
                throw @"
Die MATLAB-Engine ist nach dem Installationsversuch nicht importierbar.
Die Meldungen stehen oben. Bleibt es bei einem Schreibfehler, den Schritt in einer
als Administrator gestarteten PowerShell nachholen und das Skript danach erneut
aufrufen:
  cd "$engineDir"
  `$env:SETUPTOOLS_USE_DISTUTILS = "stdlib"
  & "$tepPy" $($wegA -join ' ')
"@
            }
        } finally { Pop-Location }
        Note "installiert und importierbar"
    }

    Step "pytep"
    # --no-deps, weil setup.py der Fork dash und pytest deklariert, obwohl das
    # Paket nur matlab.engine, numpy und pandas importiert.
    Invoke-Checked $tepPy @("-m", "pip", "install", "-e", $PytepPath, "--no-deps")
    Note "editierbar aus $PytepPath"

    Write-LocalPaths $TepEnv
}

# ----------------------------------------------------------------- Kontrolle

Step "Kontrolle"

if (-not $SkipMain) {
    Push-Location $Root
    try {
        Invoke-Checked "uv" @("run", "python", "-c",
            "import frouros, optuna, seaborn, tensorflow, sklearn; from src.utils import run_registry; print('  .venv       ok  frouros', frouros.__version__)")
    } finally { Pop-Location }
}

if (-not $SkipTep) {
    $tepPy = Join-Path $TepEnv "Scripts\python.exe"
    Invoke-Checked $tepPy @("-c",
        "import matlab.engine, pytep, numpy, pandas, scipy, matplotlib, seaborn; from src.utils import run_registry; print('  .venv_tep   ok  pandas', pandas.__version__)")

    # Muss 29 ergeben. Eine alte, 28-spaltige Datei erzeugt sonst einen
    # Shape-Mismatch im DataFrame, und zwar erst mitten im Simulationslauf.
    $labels = & $tepPy -c "import pandas as pd, pytep, pathlib; print(len(pd.read_pickle(str(pathlib.Path(pytep.__file__).parent / 'setupinfo' / 'idv_labels.pkl'))))"
    if ($labels.Trim() -ne "29") {
        Warn "idv_labels.pkl hat $labels Eintraege, erwartet werden 29."
    } else {
        Note "idv_labels.pkl mit 29 Eintraegen"
    }
}

$dll = Join-Path $Root "src\drift_function.dll"
if (Test-Path $dll) {
    Warn "src\drift_function.dll ist vorhanden. Stammt sie von einem anderen Rechner,"
    Warn "loeschen - die Notebook-Zelle prueft nur den Zeitstempel und wuerde sie"
    Warn "fuer aktuell halten, statt neu zu uebersetzen."
}

Step "Fertig"
Note "In VS Code beide Interpreter einmal neu auswaehlen."
Note "  Notebooks unter ipynb\tep\tep_generation  ->  .venv_tep"
Note "  alle uebrigen                             ->  .venv"
