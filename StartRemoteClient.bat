@echo off
setlocal
set "MOGOBE_REMOTE_URL=%~1"
if not defined MOGOBE_REMOTE_URL set "MOGOBE_REMOTE_URL=%MOGOBE_SERVER_URL%"
if not defined MOGOBE_REMOTE_URL goto missing
call "%~dp0StartClient.bat" --server "%MOGOBE_REMOTE_URL%"
exit /b %errorlevel%
:missing
echo Usage: StartRemoteClient.bat https://mogobe.example.com
echo Or set MOGOBE_SERVER_URL in your environment.
exit /b 1
