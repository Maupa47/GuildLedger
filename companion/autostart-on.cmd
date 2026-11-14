@echo off
rem GuildLedger: start the companion automatically (minimised) whenever you log in to Windows.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Join-Path ([Environment]::GetFolderPath('Startup')) 'GuildLedger companion.lnk'; $s = (New-Object -ComObject WScript.Shell).CreateShortcut($l); $s.TargetPath = '%~dp0start-companion.cmd'; $s.WorkingDirectory = '%~dp0'; $s.WindowStyle = 7; $s.Save(); Write-Host 'Autostart is ON. The companion now starts minimised when you log in to Windows.'"
pause
