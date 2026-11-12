@echo off
rem GuildLedger companion: double-click to start. Keep this window open while you play.
cd /d "%~dp0"
if not exist config.toml (
  echo config.toml is missing: copy config.example.toml to config.toml and fill it in ^(see COLLECTOR.md^).
  pause
  exit /b 1
)
where python >nul 2>nul || (
  echo Python is not installed: get Python 3.12 from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^).
  pause
  exit /b 1
)
title GuildLedger companion
python -m guildledger --config config.toml watch
echo.
echo GuildLedger companion stopped.
pause
