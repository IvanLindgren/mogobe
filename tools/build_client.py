"""Build the Windows client and create dist/Mogobe with portable configuration."""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
WAILS_VERSION = "v2.15.0"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ui-test", action="store_true")
    args = parser.parse_args()
    if os.name != "nt":
        raise SystemExit("Build using Windows Python and Go on Windows.")
    compiler = shutil.which("go")
    if not compiler:
        candidate = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Go/bin/go.exe"
        if candidate.exists():
            compiler = str(candidate)
    if not compiler:
        raise SystemExit("Install Go 1.25+ before building.")
    subprocess.run([sys.executable, str(ROOT / "tools/prepare_assets.py")], check=True)
    environment = os.environ.copy()
    environment["GOFLAGS"] = "-buildvcs=false"
    command = [compiler, "run", f"github.com/wailsapp/wails/v2/cmd/wails@{WAILS_VERSION}",
               "build", "-skipbindings", "-s", "-webview2", "error"]
    if args.ui_test:
        # Wails packages the original Windows icon for both build variants.
        command += ["-tags", "uitest", "-o", "Mogobe-UI-test.exe"]
    subprocess.run(command, cwd=ROOT / "client", env=environment, check=True)
    if args.ui_test:
        return
    output = ROOT / "dist/Mogobe"
    output.mkdir(parents=True, exist_ok=True)
    executable = output / "Mogobe.exe"
    try:
        shutil.copy2(ROOT / "client/build/bin/Mogobe.exe", executable)
    except PermissionError as error:
        if getattr(error, "winerror", None) != 32:
            raise
        executable = output / "Mogobe-update.exe"
        shutil.copy2(ROOT / "client/build/bin/Mogobe.exe", executable)
        print("Mogobe.exe is open; saved the new build beside it. Close the old client before starting this build.")
    # Rebuilding must not reset a user's chosen remote server.
    if not (output / "client.json").exists():
        shutil.copy2(ROOT / "client/client.json", output / "client.json")
    (output / "README.txt").write_text(
        "Mogobe 0.1.0\n\nStart the FastAPI server with StartServer.bat in the repository, "
        f"then open {executable.name}.\nDefault server: http://localhost:8000\n"
        "To use a remote server, edit server_url in client.json next to this EXE.\n"
        "Python and Go are not needed for the client. WebView2 Runtime is required.\n"
        "Registration, saved logins, the original world map and 50 rooms with walking avatars are available.\nNew logins start in Novograd; F5 reconnects to the current room.\nUse the map or /room Novograd in chat; /exit returns to saved avatars.\n",
        encoding="utf-8",
    )
    print(f"Ready: {executable}")


if __name__ == "__main__":
    main()
