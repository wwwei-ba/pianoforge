$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:PYTHONPATH = "$root\src"
$env:PYTHONIOENCODING = "utf-8"
$env:MPLCONFIGDIR = "$root\cache\mpl"
$env:TMP = "$root\tmp"
$env:TEMP = "$root\tmp"
$env:HF_ENDPOINT = "https://hf-mirror.com"
$env:TORCH_HOME = "$root\cache\torch"
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
& "$root\.venv\Scripts\python.exe" -m pianoforge.cli @args
exit $LASTEXITCODE
