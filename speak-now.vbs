' Silent launcher for speak-now.ps1 -- no console flash, no visible window.
' Used by the Shortcut Pad entry "Speak Jarvis Briefing".
' Finds speak-now.ps1 next to this file, so the folder can live anywhere.
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & here & "\speak-now.ps1""", 0, False
