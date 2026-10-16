@echo off
setlocal
set "PYTHONUNBUFFERED=1"
cd /d "%~dp0server"
set "MOGOBE_UV=%USERPROFILE%\.local\bin\uv.exe"
if not exist "%MOGOBE_UV%" set "MOGOBE_UV=uv"
"%MOGOBE_UV%" sync --locked
if errorlevel 1 goto failed
echo Mogobe backend - live logs below. Press Ctrl+C to stop.
"%MOGOBE_UV%" run --no-sync python -u run.py --log-level info %*
if errorlevel 1 goto failed
exit /b 0
:failed
echo Server could not start. See the error above. Python 3.12+ and uv are required.
pause
exit /b 1
