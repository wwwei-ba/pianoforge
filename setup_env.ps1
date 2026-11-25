$ErrorActionPreference = 'Continue'
$root = 'D:\deepfile\pianoforge'
$env:TMP = "$root\tmp"; $env:TEMP = "$root\tmp"
$env:PYTHONPATH = "$root\shim"
$py = "$root\.venv\Scripts\python.exe"
$log = "$root\logs\setup.log"
function Log($msg) { $ts = Get-Date -Format 'HH:mm:ss'; Write-Output "[$ts] $msg"; Add-Content -Path $log -Value "[$ts] $msg" }

Log "=== bootstrap pip ==="
D:\python\python.exe -m pip --python $py install --no-cache-dir --disable-pip-version-check pip setuptools wheel 2>&1 | Tee-Object -FilePath "$root\logs\pip_bootstrap.log"
Log "pip version: $(& $py -m pip --version)"

Log "=== install torch cu128 ==="
& $py -m pip install --no-cache-dir --disable-pip-version-check torch torchaudio --index-url https://download.pytorch.org/whl/cu128 2>&1 | Tee-Object -FilePath "$root\logs\pip_torch.log" | Select-Object -Last 20
Log "torch done exit=$LASTEXITCODE"

Log "=== install core audio + midi + score libs ==="
& $py -m pip install --no-cache-dir --disable-pip-version-check numpy scipy librosa soundfile audioread mido pretty_midi music21 demucs 2>&1 | Tee-Object -FilePath "$root\logs\pip_core.log" | Select-Object -Last 20
Log "core done exit=$LASTEXITCODE"

Log "=== install extras ==="
& $py -m pip install --no-cache-dir --disable-pip-version-check torchcrepe pyfluidsynth 2>&1 | Tee-Object -FilePath "$root\logs\pip_extras.log" | Select-Object -Last 20
Log "extras done exit=$LASTEXITCODE"

Log "=== versions ==="
& $py -c "import sys;print(sys.version)"
& $py -c "
import importlib
for m in ['numpy','scipy','librosa','soundfile','mido','pretty_midi','music21','torch','torchaudio','demucs']:
    try:
        mod=importlib.import_module(m); print(m, getattr(mod,'__version__','?'))
    except Exception as e:
        print(m,'MISSING', e)
"
Log "=== SETUP COMPLETE ==="
