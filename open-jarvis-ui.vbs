' Silent launcher for open-jarvis-ui.ps1 -- no console flash, no visible window.
' Used by the Shortcut Pad entry "Jarvis UI" and its Ctrl+Alt+J hotkey.
CreateObject("WScript.Shell").Run "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File ""C:\Users\anshu\Desktop\Claude\daily-overview\open-jarvis-ui.ps1""", 0, False
