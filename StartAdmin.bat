@echo off
setlocal
set "MOGOBE_ADMIN_SERVER=http://127.0.0.1:8000"
if not "%~1"=="" set "MOGOBE_ADMIN_SERVER=%~1"
set "MOGOBE_ADMIN_EDGE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not exist "%MOGOBE_ADMIN_EDGE%" set "MOGOBE_ADMIN_EDGE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not exist "%MOGOBE_ADMIN_EDGE%" goto fallback
start "" "%MOGOBE_ADMIN_EDGE%" --user-data-dir="%LOCALAPPDATA%\Mogobe\Admin" --no-first-run --app="%MOGOBE_ADMIN_SERVER%/admin"
exit /b 0
:fallback
start "" "%MOGOBE_ADMIN_SERVER%/admin"
