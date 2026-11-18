@echo off
rem Refresh every data source now (shows progress), then open the dashboard.
rem Uses the same pipeline as the dashboard server (refresh_data.py).
setlocal
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 goto :no_python
python refresh_data.py
if errorlevel 1 echo Some sources failed; their last good data was kept. See messages above.
call "%~dp0Open_Indian_Macro_Dashboard.cmd"
pause
exit /b 0

:no_python
echo Python 3 was not found. Install it from https://www.python.org/downloads/
pause
exit /b 1
