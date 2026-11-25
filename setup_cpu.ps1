$ErrorActionPreference = 'Continue'
$root = 'D:\deepfile\pianoforge'
$env:TMP = "$root\tmp"; $env:TEMP = "$root\tmp"; $env:PYTHONPATH = "$root\shim"
$py = "$root\.venv\Scripts\python.exe"
$idx = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$log = "$root\logs\setup.log"
function Log($msg) { $ts = Get-Date -Format 'HH:mm:ss'; Write-Output "[$ts] $msg"; Add-Content -Path $log -Value "[$ts] $msg" }
Log '=== install torch cpu + audio core ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check -i $idx torch torchaudio numpy scipy librosa soundfile audioread
Log "torch/core exit=$LASTEXITCODE"
Log '=== install midi/score ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check -i $idx mido pretty_midi music21 demucs
Log "midi exit=$LASTEXITCODE"
Log '=== install extras ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check -i $idx torchcrepe pyfluidsynth
Log "extras exit=$LASTEXITCODE"
Log '=== versions ==='
& $py -c "import importlib"
& $py -c "import torch,librosa,soundfile,music21,pretty_midi;print('torch',torch.__version__,'librosa',librosa.__version__,'m21',music21.__version__)"
Log '=== SETUP DONE ==='