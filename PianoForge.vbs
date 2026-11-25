' PianoForge launcher: sets the local environment and starts the GUI without a console window.
Option Explicit
Dim sh, root
Set sh = CreateObject("WScript.Shell")
root = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)

sh.Environment("PROCESS")("PYTHONPATH") = root & "\src"
sh.Environment("PROCESS")("PYTHONIOENCODING") = "utf-8"
sh.Environment("PROCESS")("MPLCONFIGDIR") = root & "\cache\mpl"
sh.Environment("PROCESS")("TMP") = root & "\tmp"
sh.Environment("PROCESS")("TEMP") = root & "\tmp"
sh.Environment("PROCESS")("HF_ENDPOINT") = "https://hf-mirror.com"
sh.Environment("PROCESS")("TORCH_HOME") = root & "\cache\torch"
sh.CurrentDirectory = root

sh.Run """" & root & "\.venv\Scripts\pythonw.exe"" -m pianoforge.gui", 0, False
