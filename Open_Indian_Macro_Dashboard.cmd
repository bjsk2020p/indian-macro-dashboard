@echo off
rem Opens the India + US Macro Dashboard with automatic data updates.
rem Starts (or reuses) a local server on 127.0.0.1 and opens your browser. Safe to double-click again.
setlocal
set "APPDIR=%~dp0"

where pyw >nul 2>nul
if not errorlevel 1 goto :use_pyw
where pythonw >nul 2>nul
if not errorlevel 1 goto :use_pythonw
where python >nul 2>nul
if not errorlevel 1 goto :use_python
goto :no_python

:use_pyw
start "" pyw -3 "%APPDIR%launcher.py"
exit /b 0

:use_pythonw
start "" pythonw "%APPDIR%launcher.py"
exit /b 0

:use_python
rem Visible console fallback: launcher prints any error here.
python "%APPDIR%launcher.py"
if errorlevel 1 pause
exit /b

:no_python
echo.
echo  Python 3 was not found, so the dashboard server cannot start.
echo  Install Python 3.9+ from https://www.python.org/downloads/ (tick "Add python.exe to PATH"),
echo  then double-click this file again.
echo.
echo  Without Python you can still open india_macro_dashboard_v5.html directly to see saved data,
echo  but it will not update automatically.
echo.
pause
exit /b 1
