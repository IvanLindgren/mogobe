"""Exercise the built Windows WebView2 client with a test-only Go bridge.

Build first: python tools/build_client.py --ui-test
Run with Windows Python with httpx and pillow. The test uses its own SQLite
and WebView2 profile; the distributed production EXE contains no test bridge.
"""
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import time
import traceback
import tempfile
import secrets
import sys

import httpx
from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "verification"
OUT.mkdir(exist_ok=True)
CLIENT = ROOT / "client/build/bin/Mogobe-UI-test.exe"
PYTHON = ROOT / "server/.venv/Scripts/python.exe"


class DesktopBridge:
    def __init__(self, process, secret, port=19225):
        self.secret = secret
        self.port = port
        self.user32 = ctypes.windll.user32
        self.user32.SetProcessDPIAware()
        self.hwnd = None
        def window(hwnd, _):
            pid = wintypes.DWORD()
            self.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value == process.pid and self.user32.IsWindowVisible(hwnd):
                self.hwnd = hwnd
            return True
        callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)(window)
        self.user32.EnumWindows(callback, 0)
        if not self.hwnd:
            raise RuntimeError('Test window not found')
        self.user32.SetForegroundWindow(self.hwnd)

    def call(self, method, **params):
        if method == 'Page.enable':
            return {}
        if method == 'Input.dispatchMouseEvent':
            point = wintypes.POINT(round(params['x']), round(params['y']))
            self.user32.ClientToScreen(self.hwnd, ctypes.byref(point))
            self.user32.SetCursorPos(point.x, point.y)
            if params['type'] == 'mousePressed':
                self.user32.mouse_event(2, 0, 0, 0, 0)
            elif params['type'] == 'mouseReleased':
                self.user32.mouse_event(4, 0, 0, 0, 0)
            time.sleep(.05)
            return {}
        if method == 'Input.insertText':
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [('wVk',wintypes.WORD),('wScan',wintypes.WORD),('dwFlags',wintypes.DWORD),('time',wintypes.DWORD),('extra',ctypes.c_size_t)]
            class DATA(ctypes.Union):
                _fields_ = [('keyboard',KEYBDINPUT),('padding',ctypes.c_byte*32)]
            class INPUT(ctypes.Structure):
                _fields_ = [('type',wintypes.DWORD),('data',DATA)]
            for character in params['text']:
                for flags in [4,6]:
                    event = INPUT(type=1, data=DATA(keyboard=KEYBDINPUT(wScan=ord(character),dwFlags=flags)))
                    self.user32.SendInput(1,ctypes.byref(event),ctypes.sizeof(INPUT))
                time.sleep(.03)
            return {}
        raise RuntimeError(method)

    def js(self, expression):
        response = httpx.post(f'http://127.0.0.1:{self.port}/eval', headers={'Authorization':'Bearer '+self.secret},json={'expression':expression},timeout=30)
        response.raise_for_status()
        result = response.json()
        if 'error' in result:
            raise RuntimeError(result['error'])
        return result.get('value')

    def wait(self, expression, timeout=30):
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            try:
                if self.js(expression):
                    return
            except (RuntimeError, KeyError):
                pass
            time.sleep(.2)
        raise TimeoutError(expression)

    def click(self, x, y):
        self.user32.SetForegroundWindow(self.hwnd)
        time.sleep(.05)
        self.call("Input.dispatchMouseEvent", type="mouseMoved", x=x, y=y)
        self.call("Input.dispatchMouseEvent", type="mousePressed", x=x, y=y, button="left", clickCount=1)
        self.call("Input.dispatchMouseEvent", type="mouseReleased", x=x, y=y, button="left", clickCount=1)

    def stage_click(self, x, y):
        bounds = self.js("JSON.stringify(document.getElementById('stage').getBoundingClientRect().toJSON())")
        r = json.loads(bounds)
        self.click(r["x"]+x*r["width"]/768, r["y"]+y*r["height"]/480)

    def control(self, name):
        self.user32.SetForegroundWindow(self.hwnd)
        if name in ['btnLogin','btnLoginMultiInst']:
            # Original Button.clickDelay is 5000 ms. Wait for its click handler
            # to return instead of clicking a grey button during that delay.
            self.wait("window.player.ruffle().callExternalInterface('getLoginControlBounds',"+json.dumps(name)+")?.enabled === true",12)
        bounds = self.js("window.player.ruffle().callExternalInterface('getLoginControlBounds',"+json.dumps(name)+")")
        if not bounds:
            raise RuntimeError('Original SWF control not found: '+name)
        self.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)

    def chat_send(self, text='/exit', send_button=False):
        self.control('txtSpeak')
        self.type_text(text)
        if send_button:
            self.control('btnSend')
        else:
            self.user32.keybd_event(0x0D,0,0,0)
            self.user32.keybd_event(0x0D,0,2,0)

    def popup_confirm(self):
        self.wait("window.mogobePopup?.state === 'open' && window.mogobePopup.original",30)
        bounds = self.js("window.registrationPopupPlayer.ruffle().callExternalInterface('getPopupControlBounds','btnConfirm')")
        assert bounds,'Original popup confirmation button missing'
        rect = self.js("window.registrationPopupPlayer.getBoundingClientRect().toJSON()")
        self.click(rect['x']+(bounds['x']+bounds['width']/2)*rect['width']/768,
                   rect['y']+(bounds['y']+bounds['height']/2)*rect['height']/480)
        self.wait("window.mogobePopup?.state === 'closed'")

    def type_text(self, text):
        # Flash may insert a literal letter for synthetic Ctrl+A under a
        # Russian keyboard layout. Select the single-line field without letters.
        self.user32.keybd_event(0x24,0,0,0)  # Home
        self.user32.keybd_event(0x24,0,2,0)
        time.sleep(.1)
        self.user32.keybd_event(0x10,0,0,0)  # Shift+End
        time.sleep(.05)
        self.user32.keybd_event(0x23,0,0,0)
        self.user32.keybd_event(0x23,0,2,0)
        self.user32.keybd_event(0x10,0,2,0)
        time.sleep(.1)
        self.user32.keybd_event(0x08,0,0,0)  # Backspace
        self.user32.keybd_event(0x08,0,2,0)
        time.sleep(.1)
        self.call('Input.insertText',text=text)

    def capture(self, name):
        self.user32.SetForegroundWindow(self.hwnd)
        time.sleep(.2)
        rect = wintypes.RECT()
        self.user32.GetWindowRect(self.hwnd,ctypes.byref(rect))
        ImageGrab.grab(bbox=(rect.left,rect.top,rect.right,rect.bottom)).save(OUT / f"{name}.png")


def wait_http(url):
    for _ in range(100):
        try:
            response = httpx.get(url, timeout=1)
            if response.status_code == 200:
                return response
        except httpx.HTTPError:
            pass
        time.sleep(.2)
    raise RuntimeError(f"Endpoint not ready: {url}")


def main():
    result = {"checks": {}}
    processes = []
    with tempfile.TemporaryDirectory(prefix="mogobe-auth-test-", ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        database = directory / "test.sqlite3"
        backend_log = (OUT / "backend.log").open("w", encoding="utf-8")
        client_log = (OUT / "client.log").open("w", encoding="utf-8")
        try:
            env = os.environ.copy()
            env["MOGOBE_DATABASE_URL"] = "sqlite+aiosqlite:///"+database.as_posix()
            env['PYTHONPATH'] = str(ROOT/'server/.venv/Lib/site-packages')
            # Target port exists only in the config; no --server argument is passed.
            cfg = directory / "client.json"
            cfg.write_text(json.dumps({"server_url":"http://127.0.0.1:18080", "request_timeout_seconds":5}), encoding="utf-8")
            secret = secrets.token_urlsafe(32)
            env['MOGOBE_UI_TEST_SECRET'] = secret
            env['MOGOBE_UI_TEST_PROFILE'] = str(directory / 'webview')
            processes.append(subprocess.Popen([str(CLIENT), "--config", str(cfg)], cwd=directory, env=env, stdout=client_log, stderr=subprocess.STDOUT))
            time.sleep(2)
            c = DesktopBridge(processes[-1], secret)
            c.call("Page.enable")
            c.wait("window.originalConnectionLoaderReady && window.mogobeConnection === 'connecting'", 60)
            time.sleep(3)
            assert c.js("window.mogobeScene?.state === 'connecting' && !window.mogobeReady")
            c.capture("00-connecting-original-preloader")
            result["checks"]["original_preloader_while_server_offline"] = True
            processes.append(subprocess.Popen([sys._base_executable, "run.py", "--port", "18080"], cwd=ROOT / "server", env=env, stdout=backend_log, stderr=subprocess.STDOUT))
            wait_http("http://127.0.0.1:18080/api/health")
            c.wait("window.mogobeScene?.state === 'lobby'", 60)
            assert c.js("window.mogobeConnection === 'connected'")
            result["checks"]["automatic_connection_after_server_start"] = True
            c.capture("01-original-login")
            result["checks"]["original_login_visible"] = True
            # Original registration Flash button.
            c.stage_click(384, 338)
            c.wait("location.pathname === '/Registration2.aspx' && !!window.selectColor")
            c.wait("document.querySelector('ruffle-object,ruffle-embed,ruffle-player') !== null")
            time.sleep(2)
            # Click the actual first color avatar. Bounds come from the original object.
            bounds = json.loads(c.js("JSON.stringify(document.querySelector('ruffle-object,ruffle-embed,ruffle-player').getBoundingClientRect().toJSON())"))
            # Hit the avatar's face after its original hover animation rises.
            color_x = bounds["x"]+65*bounds["width"]/630
            color_y = bounds["y"]+100*bounds["height"]/340
            c.call("Input.dispatchMouseEvent", type="mouseMoved", x=color_x, y=color_y)
            time.sleep(.6)
            c.click(color_x, color_y)
            c.wait("Number(document.getElementById('userColor')?.value) >= 1")
            c.capture("02-original-color")
            selected_color = c.js("Number(document.getElementById('userColor').value)")
            result["checks"]["original_color_callback"] = True
            c.js("document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration3.aspx' && !!window.MOGO_REG_STEP")
            c.capture("03-credentials")
            for invalid_name in ['Bad Name','Bad!Name',' Name12','Name12 ']:
                assert c.js("field('txtNick').value="+json.dumps(invalid_name)+"; field('txtNick').validity.patternMismatch")
            result["checks"]["nickname_rejects_spaces_and_special_characters"] = True
            c.js("document.getElementById('aspnetForm').requestSubmit()")
            c.wait("window.mogobePopup?.state === 'open' && window.mogobePopup.original",30)
            assert c.js("window.mogobePopup.message.includes('Без пробелов')")
            c.capture('03a-original-invalid-name-popup')
            c.popup_confirm()
            assert c.js("field('txtNick').value === 'Name12 '")
            result["checks"]["original_popup_for_invalid_nickname"] = True
            c.js("field('txtNick').value='Desktop_12';field('txtPass').value='Pass1234';field('txtRePass').value='Other123';document.getElementById('aspnetForm').requestSubmit()")
            c.wait("window.mogobePopup?.state === 'open' && window.mogobePopup.original && window.mogobePopup.message.includes('не совпадают')")
            c.capture('03b-original-password-popup')
            c.popup_confirm()
            result["checks"]["original_popup_for_password_mismatch"] = True
            c.js("field('txtNick').value='Desktop_12';field('txtPass').value='Pass1234';field('txtRePass').value='Pass1234';document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration4.aspx' && !!field('ddlAge')")
            with sqlite3.connect(database) as db:
                result["checks"]["account_not_created_early"] = db.execute("SELECT count(*) FROM auth_account").fetchone()[0] == 0
            c.capture("04-age-chat")
            c.js("field('ddlAge').value='12';field('imgYoung').click();document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration5.aspx' && field('btnAgree')?.type === 'checkbox'")
            c.capture("05-rules")
            assert c.js("!field('btnAgree').checked && !field('btnEmailAgree').checked")
            c.js("document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration7.aspx' && !!field('txtParentEmail')")
            c.capture("06-email")
            c.js("document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration8.aspx'")
            c.capture("07-complete")
            with sqlite3.connect(database) as db:
                row = db.execute("SELECT color_id,age,chat_mode,password_hash FROM auth_account WHERE username='Desktop_12'").fetchone()
                result["checks"]["profile_persisted"] = row[0] == selected_color and row[1:3] == (12,"closed") and row[3].startswith("$argon2id$")
                assert db.execute("SELECT terms_accepted_at,newsletter FROM auth_account WHERE username='Desktop_12'").fetchone() == (None,0)
                result["checks"]["registration_without_both_checkboxes"] = True
            assert c.js("fetch('/api/auth/me').then(r=>r.json()).then(user=>user.username==='Desktop_12')")
            c.js("document.querySelector('a[href=\"/?registered=1\"] img[src$=\"PlayReg.gif\"]').closest('a').click()")
            c.wait("window.mogobeLogin?.view === 'servers'", 60)
            result["checks"]["registration_opens_original_server_selection"] = True
            with sqlite3.connect(database) as db:
                assert db.execute('SELECT count(*) FROM auth_session').fetchone()[0] == 1
            c.capture("08-server-selection")
            # Verify authenticated server-side session before clicking its original server button.
            c.wait("fetch('/api/auth/me').then(r=>r.ok)")
            result["checks"]["original_login_authenticated"] = True
            c.js("window.testErrors=[]; addEventListener('error', e=>testErrors.push(String(e.message))); addEventListener('unhandledrejection', e=>testErrors.push(String(e.reason)))")
            c.stage_click(384, 140)
            c.wait("window.mogobeScene?.state === 'world' && window.mogobeScene.room === 'novograd'", 90)
            c.capture("09-infoboard")
            assert c.js("window.mogobeScene.panelReady && window.mogobeScene.avatarReady")
            before = c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
            assert before['visible'] and before['type'].endswith('MyAvatar')
            assert before['colorId'] == selected_color
            c.stage_click(600, 396)
            c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar')?.action === 1", 10)
            c.wait("fetch('/api/world/me').then(r=>r.json()).then(p=>p.x > 570)", 30)
            c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar')?.x > 570", 30)
            time.sleep(1)
            after = c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
            assert abs(after['x']-before['x']) > 50
            c.capture('09-infoboard-walking')
            result['checks']['original_novograd_panel_and_avatar'] = True
            result['checks']['original_avatar_walks_with_transient_position'] = True
            result["checks"]["server_selected"] = True
            result["checks"]["configured_backend_used"] = True
            assert c.js("document.querySelector('#signed-in,#switch-account,#logout') === null")
            result['checks']['external_exit_buttons_removed'] = True
            with sqlite3.connect(database) as db:
                assert db.execute("SELECT name FROM sqlite_master WHERE name='world_player'").fetchone() is None
            result['checks']['no_position_table_in_sqlite'] = True
            c.chat_send('hello /exit')
            time.sleep(.5)
            assert c.js("window.mogobeScene?.state === 'world'")
            c.chat_send(' /ExIt ')
            c.wait("window.mogobeLogin?.view === 'saved'",40)
            result['checks']['chat_exit_via_enter'] = True
            result['checks']['exit_preserved_session'] = c.js("fetch('/api/auth/me').then(r=>r.ok)")
            assert c.js("window.mogobeLogin.selected === 'Desktop_12' && window.mogobeLogin.visible[0] === 'Desktop_12'")
            original = c.js("window.player.ruffle().callExternalInterface('getLoginControlBounds','txtNameSmall')")
            displayed = c.js("window.player.ruffle().callExternalInterface('getLoginControlBounds','mogobeDisplayName')")
            assert all(abs(original[key]-displayed[key]) < 1 for key in ['x','y','width','height']), (original,displayed)
            time.sleep(2)
            c.capture('10-original-nickname-case')
            result["checks"]["original_nickname_case_preserved"] = True
            c.control('txtMultiLoginPassword');c.type_text('Pass1234')
            c.control('btnLoginMultiInst')
            c.wait("window.mogobeLogin?.view === 'servers'")
            result["checks"]["normal_login_after_chat_exit"] = True
            c.stage_click(384,140)
            c.wait("window.mogobeScene?.state === 'world'",60)
            returned = c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
            assert c.js("window.mogobeScene.room === 'novograd'")
            result['checks']['reentry_starts_in_novograd'] = True
            c.capture('10-infoboard-new-spawn')
            c.chat_send('/exit',send_button=True)
            c.wait("window.mogobeLogin?.view === 'saved'",40)
            result['checks']['chat_exit_via_send_button'] = True
            c.control('btnRegisterI')
            c.wait("location.pathname === '/Registration2.aspx' && !!window.selectColor")
            c.wait("document.querySelector('ruffle-object,ruffle-embed,ruffle-player') !== null")
            time.sleep(2)
            rect = c.js("document.querySelector('ruffle-object,ruffle-embed,ruffle-player').getBoundingClientRect().toJSON()")
            c.call("Input.dispatchMouseEvent", type="mouseMoved", x=rect['x']+65*rect['width']/630, y=rect['y']+100*rect['height']/340)
            time.sleep(.6)
            c.click(rect['x']+65*rect['width']/630,rect['y']+100*rect['height']/340)
            c.wait("Number(document.getElementById('userColor')?.value) >= 1")
            c.js("document.getElementById('aspnetForm').requestSubmit()")
            c.wait("location.pathname === '/Registration3.aspx' && !!window.MOGO_REG_STEP")
            c.js("field('txtNick').value='Desktop_12';field('txtPass').value='Pass1234';field('txtRePass').value='Pass1234';document.getElementById('aspnetForm').requestSubmit()")
            c.wait("window.mogobePopup?.state === 'open' && window.mogobePopup.original")
            assert c.js("window.mogobePopup.message.includes('занято')")
            c.capture('11-original-server-error-popup')
            c.popup_confirm()
            assert c.js("field('txtNick').value === 'Desktop_12'")
            result["checks"]["original_popup_for_server_validation_error"] = True
        except Exception:
            result["error"] = traceback.format_exc()
            try:
                result['state'] = c.js("JSON.stringify({url:location.href,text:document.body.innerText.slice(0,2000),popup:window.mogobePopup,scene:window.mogobeScene,errors:window.testErrors})")
                c.capture('failure')
            except Exception:
                pass
        finally:
            for process in reversed(processes):
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            backend_log.close(); client_log.close()
    result["passed"] = not result.get("error") and all(result["checks"].values())
    (OUT / "result.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
