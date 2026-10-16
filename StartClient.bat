@echo off
setlocal
if exist "%~dp0dist\Mogobe\Mogobe.exe" (
  start "" "%~dp0dist\Mogobe\Mogobe.exe" %*
  exit /b 0
)
echo Client is not built. Run: python tools\build_client.py
pause
exit /b 1
