Set WshShell = CreateObject("WScript.Shell")
Set FSO = CreateObject("Scripting.FileSystemObject")
CurrentDir = FSO.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = CurrentDir
WshShell.Run "pythonw.exe " & Chr(34) & CurrentDir & "\armidm.py" & Chr(34), 0, False
