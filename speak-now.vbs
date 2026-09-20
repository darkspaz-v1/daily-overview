' Silent launcher for speak-now.ps1 -- no console flash, no visible window.
' Used by the Shortcut Pad entry "Speak Jarvis Briefing" and its Ctrl+Alt+J hotkey.
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\Users\anshu\Desktop\Claude\daily-overview\speak-now.ps1""", 0, False
