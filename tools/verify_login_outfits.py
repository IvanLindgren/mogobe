"""Two saved mogobes: original login portraits, outfits, restart and removal."""

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

OUT = ROOT / "verification/login-outfits"


def stop(process):
    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {"account_count": 2, "checks": {}}
    processes = []
    bridge = None
    with tempfile.TemporaryDirectory(prefix="mogobe-login-outfits-", ignore_cleanup_errors=True) as tmp:
        directory = Path(tmp)
        database = directory / "test.sqlite3"
        with (OUT / "backend.log").open("w", encoding="utf-8") as blog, (OUT / "client.log").open("w", encoding="utf-8") as clog:
            try:
                env = os.environ.copy()
                env["MOGOBE_DATABASE_URL"] = "sqlite+aiosqlite:///" + database.as_posix()
                env["MOGOBE_BOOTSTRAP_DEFAULTS"] = "false"
                env["PYTHONPATH"] = str(ROOT / "server/.venv/Lib/site-packages")
                env["MOGOBE_UI_TEST_SECRET"] = secrets.token_urlsafe(32)
                env["MOGOBE_UI_TEST_PROFILE"] = str(directory / "webview")
                backend = subprocess.Popen([sys._base_executable, "run.py", "--port", "18080"], cwd=ROOT / "server", env=env, stdout=blog, stderr=subprocess.STDOUT)
                processes.append(backend)
                wait_http("http://127.0.0.1:18080/api/health")
                api = httpx.Client(base_url="http://127.0.0.1:18080")
                users = {}
                for name, color in [("МоГо_Ё", 7), ("ShoeTwo", 3)]:
                    assert api.post("/api/auth/registration-drafts", json={"username": name, "password": "Dress123", "color_id": color}).status_code == 201
                    account = api.post("/api/auth/register", json={"age": 12, "chat_mode": "open"})
                    assert account.status_code == 201, account.text
                    users[name] = {"id": account.json()["id"], "token": api.cookies.get("mogobe_session")}
                    api.cookies.clear()
                with sqlite3.connect(database) as db:
                    for ident, slot in [(100, 4), (16, 3), (14, 11)]:
                        db.execute("INSERT INTO shop_item(id,name,main_type,inventory_category,enabled) VALUES(?,?,1,?,1)", (ident, str(ident), slot))
                    for name, items in [("МоГо_Ё", [100, 16]), ("ShoeTwo", [14])]:
                        users[name]["owned"] = {}
                        for item in items:
                            cursor = db.execute("INSERT INTO shop_owned_item(account_id,item_id) VALUES(?,?)", (users[name]["id"], item))
                            users[name]["owned"][item] = cursor.lastrowid
                    db.commit()

                def change(name, item, action="equip"):
                    response = api.post("/api/inventory/" + action, json={"owned_item_id": users[name]["owned"][item]}, headers={"Authorization": "Bearer " + users[name]["token"]})
                    assert response.status_code == 200, response.text

                change("МоГо_Ё", 100)
                change("ShoeTwo", 14)
                config = directory / "client.json"
                config.write_text(json.dumps({"server_url": "http://127.0.0.1:18080", "request_timeout_seconds": 5}), encoding="utf-8")

                def start_client():
                    nonlocal bridge
                    process = subprocess.Popen([str(CLIENT), "--config", str(config)], cwd=directory, env=env, stdout=clog, stderr=subprocess.STDOUT)
                    processes.append(process)
                    time.sleep(2)
                    bridge = DesktopBridge(process, env["MOGOBE_UI_TEST_SECRET"])
                    bridge.wait("['single','saved'].includes(window.mogobeLogin?.view)", 60)
                    return process

                def snapshot(name):
                    return "fetch('/client/accounts').then(r=>r.json()).then(a=>a.find(x=>x.username===" + json.dumps(name) + ")?.item_ids)"

                portraits = "window.player.ruffle().callExternalInterface('getSavedAvatarInfo')"

                def assert_portrait(name, items, big=True):
                    # Inspect the original loaded mlBigItem clips in both the
                    # selected portrait and small cards, not only cached IDs.
                    username = json.dumps(name.lower())
                    types = json.dumps(sorted("mlBigItem" + str(item) for item in items))
                    where = "p.username===" + username
                    if not big:
                        where += " && p.holder!=='mcBigPreviewHolderInst'"
                    expression = portraits + ".filter(p=>" + where + ")"
                    expected = 2 if big else 1
                    bridge.wait(expression + ".length===" + str(expected), 30)
                    bridge.wait(expression + ".every(p=>JSON.stringify(p.clothing.map(c=>c.type).sort())===JSON.stringify(" + types + ") && p.clothing.every(c=>c.width>0&&c.height>0))", 30)

                def login_single(name, remember=False):
                    bridge.control("txtUserName")
                    bridge.type_text(name)
                    bridge.control("txtPassword")
                    bridge.type_text("Dress123")
                    if remember:
                        bridge.control("chkSavePass")
                    time.sleep(5.1)
                    bridge.control("btnLogin")
                    enter_world()

                def enter_world():
                    bridge.wait("window.mogobeLogin?.view==='servers'", 30)
                    bridge.stage_click(384, 140)
                    bridge.wait("window.mogobeScene?.state==='world'", 60)

                def leave():
                    bridge.chat_send("/exit")
                    bridge.wait("window.mogobeLogin?.view==='saved'", 45)

                client = start_client()
                login_single("МоГо_Ё")
                bridge.wait(snapshot("МоГо_Ё") + ".then(ids=>JSON.stringify(ids)==='[100]')", 20)
                leave()
                assert_portrait("МоГо_Ё", [100])
                bridge.capture("login-outfits/01-name-only-shirt")
                result["checks"]["name_only_login_has_original_shirt_in_big_and_small_portraits"] = True
                stop(client)
                client = start_client()
                assert_portrait("МоГо_Ё", [100])
                result["checks"]["name_only_appearance_survives_restart"] = True

                bridge.control("txtMultiLoginPassword")
                bridge.type_text("Dress123")
                bridge.control("chkMultiSavePass")
                bridge.control("btnLoginMultiInst")
                enter_world()
                change("МоГо_Ё", 16)
                bridge.wait(snapshot("МоГо_Ё") + ".then(ids=>ids.length===2 && ids.includes(100)&&ids.includes(16))", 20)
                leave()
                assert_portrait("МоГо_Ё", [100, 16])
                result["checks"]["server_equip_event_updates_cached_outfit_before_exit"] = True
                bridge.control("btnOtherUserI")
                bridge.wait("window.mogobeLogin?.view==='single'", 30)
                login_single("ShoeTwo", True)
                bridge.wait(snapshot("ShoeTwo") + ".then(ids=>JSON.stringify(ids)==='[14]')", 20)
                leave()
                assert_portrait("ShoeTwo", [14])
                assert_portrait("МоГо_Ё", [100, 16], False)
                bridge.control("mcSmallPreviewHolderInst2")
                bridge.wait("window.mogobeLogin?.selected==='МоГо_Ё'", 20)
                assert_portrait("МоГо_Ё", [100, 16])
                assert_portrait("ShoeTwo", [14], False)
                bridge.capture("login-outfits/02-two-different-outfits")
                result["checks"]["switching_saved_mogobes_keeps_each_original_outfit_separate"] = True

                stop(client)
                change("МоГо_Ё", 100, "unequip")
                client = start_client()
                assert_portrait("МоГо_Ё", [16], False)
                bridge.control("mcSmallPreviewHolderInst2")
                bridge.wait("window.mogobeLogin?.selected==='МоГо_Ё'", 20)
                assert_portrait("МоГо_Ё", [16])
                result["checks"]["startup_refreshes_server_outfit_without_entering_world"] = True
                bridge.control("btnLoginMultiInst")
                enter_world()
                change("МоГо_Ё", 16, "unequip")
                bridge.wait(snapshot("МоГо_Ё") + ".then(ids=>ids.length===0)", 20)
                leave()
                assert_portrait("МоГо_Ё", [])
                assert_portrait("ShoeTwo", [14], False)
                bridge.capture("login-outfits/03-removed-clothes")
                result["checks"]["unequipping_last_item_clears_only_the_matching_portraits"] = True
                api.close()
            except Exception:
                result["error"] = traceback.format_exc()
                if bridge:
                    try:
                        result["state"] = bridge.js("({login:window.mogobeLogin,portraits:" + portraits + "})")
                        bridge.capture("login-outfits/failure")
                    except Exception:
                        pass
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        stop(process)
    result["passed"] = not result.get("error") and all(result["checks"].values())
    (OUT / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=True, indent=2), flush=True)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
