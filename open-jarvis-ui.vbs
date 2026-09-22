' Silent launcher for open-jarvis-ui.ps1 -- no console flash, no visible window.
' Used by the Shortcut Pad entry "Jarvis UI" and its Ctrl+Alt+J hotkey.
' Finds open-jarvis-ui.ps1 next to this file, so the folder can live anywhere.
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & here & "\open-jarvis-ui.ps1""", 0, False
