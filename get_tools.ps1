$ErrorActionPreference = 'Continue'
$root = 'D:\deepfile\pianoforge'
$env:TMP = "$root\tmp"; $env:TEMP = "$root\tmp"
$dl = "$root\dl"; New-Item -ItemType Directory -Force -Path $dl | Out-Null
function Log($m) { $ts = Get-Date -Format 'HH:mm:ss'; Write-Output "[$ts] $m" }

Log "downloading ffmpeg"
try {
  Invoke-WebRequest -Uri 'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip' -OutFile "$dl\ffmpeg.zip" -UseBasicParsing
  Log ("ffmpeg.zip " + (Get-Item "$dl\ffmpeg.zip").Length)
  Expand-Archive -Path "$dl\ffmpeg.zip" -DestinationPath "$root\bin\ffmpeg_tmp" -Force
  $ff = Get-ChildItem "$root\bin\ffmpeg_tmp" -Recurse -Filter ffmpeg.exe | Select-Object -First 1
  Copy-Item $ff.FullName "$root\bin\ffmpeg.exe" -Force
  Log "ffmpeg installed"
} catch { Log "ffmpeg FAILED: $_" }

Log "downloading fluidsynth"
try {
  $rel = Invoke-RestMethod -Uri 'https://api.github.com/repos/FluidSynth/fluidsynth/releases/latest' -Headers @{ 'User-Agent' = 'pianoforge' }
  Log ("fluidsynth latest: " + $rel.tag_name)
  $asset = $rel.assets | Where-Object { $_.name -match 'win10-x64.zip$|win64.zip$' } | Select-Object -First 1
  if ($asset) {
    Log ("asset: " + $asset.name)
    Invoke-WebRequest -Uri $asset.browser_download_url -OutFile "$dl\fluidsynth.zip" -UseBasicParsing
    Expand-Archive -Path "$dl\fluidsynth.zip" -DestinationPath "$root\bin\fluidsynth_tmp" -Force
    $exe = Get-ChildItem "$root\bin\fluidsynth_tmp" -Recurse -Filter fluidsynth.exe | Select-Object -First 1
    Log ("fluidsynth exe: " + $exe.FullName)
    Copy-Item "$($exe.Directory.FullName)\*" "$root\bin\fluidsynth\" -Recurse -Force
  } else { Log "no matching fluidsynth asset" }
} catch { Log "fluidsynth FAILED: $_" }

Log "downloading soundfont GeneralUser GS"
try {
  Invoke-WebRequest -Uri 'https://github.com/mrbumpy409/GeneralUser-GS/raw/main/GeneralUser-GS.sf2' -OutFile "$root\bin\soundfonts\GeneralUser-GS.sf2" -UseBasicParsing
  Log ("sf2 " + (Get-Item "$root\bin\soundfonts\GeneralUser-GS.sf2").Length)
} catch { Log "sf2 FAILED: $_" }

Log "TOOLS DONE"
