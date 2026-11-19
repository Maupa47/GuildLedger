@echo off
rem GuildLedger companion: double-click to start. Keep this window open while you play.
rem It finds your WoW folder itself, installs Python if it is missing, and updates itself.
setlocal
cd /d "%~dp0"
title GuildLedger companion
if not exist config.toml (
  echo config.toml is missing.
  echo Ask your guild's GuildLedger admin for your collector package: it contains your config.toml.
  echo ^(Or copy config.example.toml to config.toml and fill it in, see COLLECTOR.md.^)
  pause
  exit /b 1
)
call :findpython
if not defined PY call :installpython
if not defined PY (
  echo.
  echo Python could not be installed automatically.
  echo Install Python 3.12 from https://www.python.org/downloads/ ^(tick "Add python.exe to PATH"^),
  echo then start this file again.
  pause
  exit /b 1
)
if not exist ".autostart-asked" call :askautostart
%PY% -m guildledger --config config.toml watch
echo.
echo GuildLedger companion stopped.
pause
exit /b 0

:findpython
set "PY="
call :try py -3
if not defined PY call :try python
for %%V in (314 313 312 311) do if not defined PY if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" call :try "%LocalAppData%\Programs\Python\Python%%V\python.exe"
for %%V in (314 313 312 311) do if not defined PY if exist "%ProgramFiles%\Python%%V\python.exe" call :try "%ProgramFiles%\Python%%V\python.exe"
exit /b 0

:try
%* -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 set PY=%*
exit /b 0

:installpython
where winget >nul 2>nul
if errorlevel 1 exit /b 0
echo Python is needed and not installed yet. Installing it now ^(once, takes about a minute^)...
winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
call :findpython
exit /b 0

:askautostart
echo asked>".autostart-asked"
if exist "%AppData%\Microsoft\Windows\Start Menu\Programs\Startup\GuildLedger companion.lnk" exit /b 0
echo.
choice /C YN /M "Start the companion automatically whenever you log in to Windows"
if errorlevel 2 exit /b 0
call "%~dp0autostart-on.cmd" quiet
exit /b 0
