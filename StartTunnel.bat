@echo off
setlocal
set "MOGOBE_CLOUDFLARED=%LOCALAPPDATA%\MogobeTools\cloudflared.exe"
set "MOGOBE_TUNNEL_CONFIG=%USERPROFILE%\.cloudflared\mogobe.yml"
if not exist "%MOGOBE_CLOUDFLARED%" set "MOGOBE_CLOUDFLARED=cloudflared"
if not exist "%MOGOBE_TUNNEL_CONFIG%" goto missing
"%MOGOBE_CLOUDFLARED%" tunnel --config "%MOGOBE_TUNNEL_CONFIG%" ingress validate
if errorlevel 1 goto failed
echo Starting Mogobe tunnel using your local cloudflared configuration.
echo Start StartServer.bat first. Keep both windows open. Ctrl+C stops the tunnel.
"%MOGOBE_CLOUDFLARED%" --no-autoupdate tunnel --config "%MOGOBE_TUNNEL_CONFIG%" --logfile "%LOCALAPPDATA%\MogobeTools\mogobe-tunnel.log" run
if errorlevel 1 goto failed
exit /b 0
:missing
echo Missing local tunnel config: %MOGOBE_TUNNEL_CONFIG%
echo Tunnel credentials belong outside the repository in your user profile.
pause
exit /b 1
:failed
echo Cloudflare Tunnel could not start. See the error above.
pause
exit /b 1
