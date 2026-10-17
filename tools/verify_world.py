"""Fast native check: one mogobe, Novograd, walking, /exit and fresh spawn.

Uses the existing uitest EXE and its own temporary database and profile.
Run the accounts suite explicitly when changing the saved-avatar list.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback

import httpx

from verify_desktop import CLIENT, ROOT, DesktopBridge, wait_http

OUT = ROOT / "verification/world"


def main():
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--spawns',action='store_true',help='Random spawns, entrance sides, original FearCaveGate and F5 room retention')
    args=parser.parse_args()
    scope='spawns' if args.spawns else 'world'
    OUT=ROOT/'verification'/scope
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    result = {"suite": scope, "account_count": 1, "checks": {}}
    processes = []
    bridge = None
    with tempfile.TemporaryDirectory(prefix="mogobe-world-test-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        database = directory / "test.sqlite3"
        with (OUT / "backend.log").open("w", encoding="utf-8") as backend_log, (OUT / "client.log").open("w", encoding="utf-8") as client_log:
            try:
                env = os.environ.copy()
                env["MOGOBE_BOOTSTRAP_DEFAULTS"]="false"
                env["MOGOBE_DATABASE_URL"] = "sqlite+aiosqlite:///" + database.as_posix()
                env["PYTHONPATH"] = str(ROOT / "server/.venv/Lib/site-packages")
                env["MOGOBE_UI_TEST_SECRET"] = secrets.token_urlsafe(32)
                env["MOGOBE_UI_TEST_PROFILE"] = str(directory / "webview")
                backend = subprocess.Popen([sys._base_executable, "run.py", "--port", "18080"], cwd=ROOT / "server", env=env, stdout=backend_log, stderr=subprocess.STDOUT)
                processes.append(backend)
                wait_http("http://127.0.0.1:18080/api/health")
                with httpx.Client(base_url="http://127.0.0.1:18080") as api:
                    assert api.post("/api/auth/registration-drafts", json={"username":"World_1", "password":"World123", "color_id":7}).status_code == 201
                    assert api.post("/api/auth/register", json={"age":12,"chat_mode":"open","accepted_terms":False}).status_code == 201
                    assert api.post("/api/auth/logout").status_code == 204
                config = directory / "client.json"
                config.write_text(json.dumps({"server_url":"http://127.0.0.1:18080","request_timeout_seconds":5}), encoding="utf-8")
                client = subprocess.Popen([str(CLIENT), "--config", str(config)], cwd=directory, env=env, stdout=client_log, stderr=subprocess.STDOUT)
                processes.append(client)
                time.sleep(2)
                bridge = DesktopBridge(client, env["MOGOBE_UI_TEST_SECRET"])
                c = bridge
                c.wait("window.mogobeLogin?.view === 'single'",60)
                c.control("txtUserName"); c.type_text("World_1")
                c.control("txtPassword"); c.type_text("World123")
                c.control("chkSavePass")
                c.control("btnLogin")

                def enter_world():
                    c.wait("window.mogobeLogin?.view === 'servers'")
                    c.stage_click(384,140)
                    c.wait("window.mogobeScene?.state === 'world' && window.mogobeScene.room === 'novograd'",60)
                    return c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")

                spawn = enter_world()
                assert spawn["visible"] and spawn["colorId"] == 7
                assert c.js("window.mogobeScene.panelReady && window.mogobeScene.avatarReady")
                result["checks"]["original_novograd_and_avatar"] = True
                assert c.js("document.querySelector('#signed-in,#switch-account,#logout') === null")
                result["checks"]["external_exit_buttons_removed"] = True
                with sqlite3.connect(database) as db:
                    assert db.execute("SELECT name FROM sqlite_master WHERE name='world_player'").fetchone() is None
                    session_count = db.execute("SELECT count(*) FROM auth_session").fetchone()[0]
                result["checks"]["positions_not_stored_in_sqlite"] = True
                c.stage_click(600,396)
                c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar').action === 1",10)
                c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar').x > 570")
                result["checks"]["original_walking_animation"] = True
                if args.spawns:
                    def wait_room(name):
                        c.wait("window.mogobeScene?.state==='world' && window.mogobeScene?.room==="+json.dumps(name.lower()),45)
                        c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar')?.visible === true",20)
                    def door(token,destination):
                        bounds=c.js("window.player.ruffle().callExternalInterface('getLoginControlBounds',"+json.dumps('mcEntryPoint_'+token)+")")
                        assert bounds,(token,destination)
                        c.stage_click(max(8,min(760,bounds['x']+bounds['width']/2)),max(8,min(440,bounds['y']+bounds['height']/2)))
                        wait_room(destination)
                    door('6','InfoBoard')
                    info=c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
                    assert info['x']<160,info
                    time.sleep(1);assert c.js("window.mogobeScene.room === 'infoboard'")
                    door('3','Novograd')
                    info=c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
                    assert info['x']>600,info
                    time.sleep(1);assert c.js("window.mogobeScene.room === 'novograd'")
                    result['checks']['entrance_side_spawns_without_bouncing_back']=True
                    c.chat_send('/room FearCaveGate');wait_room('FearCaveGate')
                    raw=c.js("fetch('/Swf/Rooms/FearCaveGate.swf').then(r=>r.arrayBuffer()).then(b=>Array.from(new Uint8Array(b)))")
                    assert hashlib.sha256(bytes(raw)).hexdigest()==hashlib.sha256((ROOT/'assets/original/Swf/Rooms/FearCaveGate.swf').read_bytes()).hexdigest()
                    c.capture(scope+'/01-replaced-fear-cave-gate')
                    result['checks']['replaced_fear_cave_gate_embedded_in_client']=True
                    for room in ['FearCaveGate','JewelryExhibition']:
                        if room!='FearCaveGate': c.chat_send('/room '+room);wait_room(room)
                        before=c.js("fetch('/client/accounts').then(r=>r.json())")
                        if room=='FearCaveGate':
                            c.control('btnMap')
                            c.wait("window.player.ruffle().callExternalInterface('getWorldMapInfo')?.ready === true")
                        c.js("window.beforeF5=true")
                        c.user32.SetForegroundWindow(c.hwnd)
                        c.user32.keybd_event(0x74,0,0,0);c.user32.keybd_event(0x74,0,2,0)
                        c.wait("window.beforeF5 === undefined && window.mogobeScene?.state==='world' && window.mogobeScene?.room==="+json.dumps(room.lower()),60)
                        assert c.js("fetch('/client/accounts').then(r=>r.json())")==before
                        c.wait("fetch('/api/world/me').then(r=>r.json()).then(p=>p.entered && p.room==="+json.dumps(room.lower())+")")
                    result['checks']['F5_keeps_room_from_map_and_another_room_without_changing_saved_login']=True
                c.chat_send("/exit")
                c.wait("window.mogobeLogin?.view === 'saved'",40)
                assert c.js("fetch('/api/auth/me').then(r=>r.ok)")
                assert c.js("fetch('/client/accounts').then(r=>r.json()).then(a=>a.length===1 && a[0].has_session)")
                result["checks"]["chat_exit_enter_preserves_session"] = True
                c.control("btnLoginMultiInst")
                returned = enter_world()
                assert c.js("window.mogobeScene.room === 'novograd'")
                result["checks"]["normal_reentry_starts_in_novograd"] = True
                c.capture(scope+"/02-novograd-reentry")
                c.chat_send("/exit", send_button=True)
                c.wait("window.mogobeLogin?.view === 'saved'",40)
                result["checks"]["chat_exit_send_button"] = True
                with sqlite3.connect(database) as db:
                    assert db.execute("SELECT count(*) FROM auth_account").fetchone()[0] == 1
                    assert db.execute("SELECT count(*) FROM auth_session").fetchone()[0] == session_count
                result["checks"]["saved_login_reused_without_extra_session"] = True
            except Exception:
                result["error"] = traceback.format_exc()
                if bridge:
                    try:
                        result["state"] = bridge.js("JSON.stringify({scene:window.mogobeScene,login:window.mogobeLogin,notice:document.getElementById('notice')?.textContent})")
                        bridge.capture("world/failure")
                    except Exception:
                        pass
            finally:
                for process in reversed(processes):
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
    result["elapsed_seconds"] = round(time.monotonic()-started,1)
    result["passed"] = not result.get("error") and all(result["checks"].values())
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2), flush=True)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
