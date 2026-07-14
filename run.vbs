' Launch Flow State with NO visible console window (window style 0).
' Runs pythonw (GUI subsystem) directly, so nothing flashes on screen.
Dim sh, fso, here
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = here
sh.Run """" & here & "\.venv\Scripts\pythonw.exe"" flow.py", 0, False
