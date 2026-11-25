$ErrorActionPreference = 'Continue'
$root = 'D:\deepfile\pianoforge'
$env:TMP = "$root\tmp"; $env:TEMP = "$root\tmp"; $env:PYTHONPATH = "$root\shim"
$py = "$root\.venv\Scripts\python.exe"
$pyRoot = 'D:\python\python.exe'
$idx = 'https://pypi.tuna.tsinghua.edu.cn/simple'
$torchLinks = 'https://mirrors.aliyun.com/pytorch-wheels/cu128/'
$log = "$root\logs\setup.log"
function Log($msg) { $ts = Get-Date -Format 'HH:mm:ss'; Write-Output "[$ts] $msg"; Add-Content -Path $log -Value "[$ts] $msg" }
Log '=== bootstrap pip ==='
& $pyRoot -m pip --python $py install --no-cache-dir --disable-pip-version-check -i $idx pip setuptools wheel
Log "pip: $(& $py -m pip --version 2>&1)"
Log '=== install torch 2.8.0+cu128 ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check 'torch==2.8.0+cu128' 'torchaudio==2.8.0+cu128' --find-links $torchLinks -i $idx
Log "torch exit=$LASTEXITCODE"
Log '=== install core libs ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check -i $idx numpy scipy librosa soundfile audioread mido pretty_midi music21 demucs
Log "core exit=$LASTEXITCODE"
Log '=== install extras ==='
& $py -m pip install --no-cache-dir --disable-pip-version-check -i $idx torchcrepe pyfluidsynth pypianoroll
Log "extras exit=$LASTEXITCODE"
Log '=== versions ==='
& $py -c "import importlib\nfor m in ['numpy','scipy','librosa','soundfile','mido','pretty_midi','music21','torch','torchaudio','demucs']:\n    try:\n        mod=importlib.import_module(m); print(m, getattr(mod,'__version__','?'))\n    except Exception as e:\n        print(m,'MISSING',repr(e)[:80])"
& $py -c "import torch;print('cuda', torch.cuda.is_available())"
Log '=== SETUP DONE ==='