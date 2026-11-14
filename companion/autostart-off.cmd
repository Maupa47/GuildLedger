@echo off
rem GuildLedger: stop starting the companion automatically.
powershell -NoProfile -ExecutionPolicy Bypass -Command "$l = Join-Path ([Environment]::GetFolderPath('Startup')) 'GuildLedger companion.lnk'; if (Test-Path $l) { Remove-Item $l; Write-Host 'Autostart is OFF.' } else { Write-Host 'Autostart was not on.' }"
pause
