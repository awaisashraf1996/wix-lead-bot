@echo off
setlocal EnableDelayedExpansion
title Build WixLeadBot.exe
cd /d "%~dp0"
echo.
echo ===============================================
echo   NA Developers - building WixLeadBot.exe
echo ===============================================
echo.

rem ---- Find a real Python (skip the Microsoft Store shortcut) ----
set "PY="

rem 1) The "py" launcher that the python.org installer adds
py -3 -c "import sys" >nul 2>nul && set "PY=py -3"

rem 2) "python" on PATH, but only if it really runs
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)

rem 3) Usual install folders (newest first)
if not defined PY (
  for /d %%D in ("%LocalAppData%\Programs\Python\Python3*" "%ProgramFiles%\Python3*" "%ProgramFiles(x86)%\Python3*") do (
    if exist "%%~D\python.exe" set "PY=%%~D\python.exe"
  )
  if defined PY set "PY="!PY!""
)

if not defined PY (
  echo Python could not be found on this computer.
  echo.
  echo Please install it from https://www.python.org/downloads/
  echo and on the first screen TICK "Add python.exe to PATH".
  echo Then run this file again.
  echo.
  pause
  exit /b 1
)

echo Using Python: !PY!
!PY! --version
echo.

echo [1/3] Installing the tools the bot needs...
!PY! -m pip install --upgrade pip >nul 2>nul
!PY! -m pip install -r requirements.txt pyinstaller
if errorlevel 1 goto :fail

rem Optional parts: Overture deep search (duckdb) and the Yellow Pages window (pywebview)
set "EXTRA="
!PY! -m pip install duckdb
!PY! -c "import duckdb" >nul 2>nul && set "EXTRA=!EXTRA! --hidden-import duckdb --collect-binaries duckdb"
!PY! -c "import duckdb" >nul 2>nul || echo NOTE: Overture deep search will be off ^(duckdb did not install^).
!PY! -m pip install pywebview
!PY! -c "import webview" >nul 2>nul && set "EXTRA=!EXTRA! --collect-data webview --hidden-import webview.platforms.edgechromium --hidden-import clr"
!PY! -c "import webview" >nul 2>nul || echo NOTE: the built-in Yellow Pages window will be off ^(pywebview did not install^). The Chrome helper still works.

echo.
echo [2/3] Building the program (this takes 2-4 minutes)...
!PY! -m PyInstaller --noconfirm --clean --onefile --windowed ^
  --name WixLeadBot ^
  --icon "assets\icon.ico" ^
  --add-data "categories.json;." ^
  --add-data "assets;assets" ^
  --add-data "chrome-extension;chrome-extension" ^
  --collect-data tzdata ^
  !EXTRA! ^
  gui.py
if errorlevel 1 goto :fail

echo.
echo [3/3] Copying files next to the program...
copy /Y "dist\WixLeadBot.exe" "WixLeadBot.exe" >nul
if not exist "output" mkdir output

echo.
echo ===============================================
echo   Done!  Double-click WixLeadBot.exe to start.
echo   Your leads from the old version are kept (wixbot.sqlite).
echo ===============================================
echo.
pause
exit /b 0

:fail
echo.
echo Something went wrong. Take a screenshot of this window and send it to Claude.
pause
exit /b 1
