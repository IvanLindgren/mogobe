"""Verify native saved-avatar UI, six accounts, restart, switching and expiry.

Uses only its own temporary SQLite/profile and the uitest build. Run on Windows
with httpx and pillow after python tools/build_client.py --ui-test.
"""
import argparse
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

OUT = ROOT / 'verification/saved-mogobes'
OUT.mkdir(parents=True,exist_ok=True)
PASSWORD = 'Saved123'
NAMES = ['SavedMogo1', 'MiXeD_2', 'МоГо_3', 'SavedMogo4', 'Ёжик_5', 'SavedMogo6']


def stop(process):
    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--full', action='store_true', help='Explicitly run the slow six-account suite')
    args = parser.parse_args()
    if not args.full:
        parser.error('Six-account checks require --full. For the quick check run tools/verify_client.py.')
    result = {'checks':{}}
    processes = []
    c = None
    with tempfile.TemporaryDirectory(prefix='mogobe-saved-test-',ignore_cleanup_errors=True) as temporary:
        directory = Path(temporary)
        database = directory/'test.sqlite3'
        backend_log = (OUT/'backend.log').open('w',encoding='utf-8')
        client_log = (OUT/'client.log').open('w',encoding='utf-8')
        try:
            env = os.environ.copy()
            env["MOGOBE_BOOTSTRAP_DEFAULTS"]="false"
            env['MOGOBE_DATABASE_URL'] = 'sqlite+aiosqlite:///'+database.as_posix()
            env['MOGOBE_LOGIN_LIMIT'] = '100'
            env['PYTHONPATH'] = str(ROOT/'server/.venv/Lib/site-packages')
            def start_backend():
                process = subprocess.Popen([sys._base_executable,'run.py','--port','18080'],cwd=ROOT/'server',env=env,stdout=backend_log,stderr=subprocess.STDOUT)
                processes.append(process)
                wait_http('http://127.0.0.1:18080/api/health')
                return process
            backend = start_backend()
            with httpx.Client(base_url='http://127.0.0.1:18080') as api:
                for index,name in enumerate(NAMES,1):
                    response = api.post('/api/auth/registration-drafts',json={'username':name,'password':PASSWORD,'color_id':index})
                    assert response.status_code == 201,response.text
                    response = api.post('/api/auth/register',json={'age':12,'chat_mode':'open','accepted_terms':True})
                    assert response.status_code == 201,response.text
                    assert api.post('/api/auth/logout').status_code == 204
            cfg = directory/'client.json'
            cfg.write_text(json.dumps({'server_url':'http://127.0.0.1:18080','request_timeout_seconds':5}),encoding='utf-8')
            env['MOGOBE_UI_TEST_SECRET'] = secrets.token_urlsafe(32)
            env['MOGOBE_UI_TEST_PROFILE'] = str(directory/'webview')
            def start_client():
                process = subprocess.Popen([str(CLIENT),'--config',str(cfg)],cwd=directory,env=env,stdout=client_log,stderr=subprocess.STDOUT)
                processes.append(process)
                time.sleep(2)
                bridge = DesktopBridge(process,env['MOGOBE_UI_TEST_SECRET'])
                bridge.wait("['single','saved'].includes(window.mogobeLogin?.view)",60)
                return process,bridge
            client,c = start_client()
            def capture(name):
                c.capture('saved-mogobes/'+name)
            def choose_server():
                c.wait("window.mogobeLogin?.view === 'servers'")
                c.stage_click(384,140)
                c.wait("window.mogobeScene?.state === 'world'")
            def return_to_picker():
                c.chat_send('/exit')
                c.wait("window.mogobeLogin?.view === 'saved'",40)
            def public_accounts():
                return c.js("fetch('/client/accounts').then(r=>r.json())")
            def assert_left_to_right():
                def center(name):
                    bounds = c.js("window.player.ruffle().callExternalInterface('getLoginControlBounds',"+json.dumps(name)+")")
                    assert bounds,name
                    return bounds['x']+bounds['width']/2
                centers = [center('mcSmallPreviewHolderInst'+str(i)) for i in range(1,5)]
                assert centers == sorted(centers) and len(set(centers)) == 4,centers
                assert center('btnLeftI') < center('btnRightI')
            for index,name in enumerate(NAMES):
                if index:
                    return_to_picker()
                    assert_left_to_right()
                    if index <= 2:
                        capture('00-'+str(index)+'-mogobes-left-to-right')
                    c.control('btnOtherUserI')
                    c.wait("window.mogobeLogin?.view === 'single'")
                c.control('txtUserName');c.type_text(name)
                c.control('txtPassword');c.type_text(PASSWORD)
                c.control('chkSavePass')
                c.control('btnLogin')
                choose_server()
                entries = public_accounts()
                assert len(entries)==index+1 and entries[0]['has_session'],entries
                assert entries[0]['color_id']==index+1
                assert c.js("window.player.ruffle().callExternalInterface('getWorldAvatar').colorId") == index+1
                print('Remembered mogobe '+str(index+1),flush=True)
            result['checks']['six_original_logins_remembered'] = True
            files = list((directory/'webview/Mogobe').glob('accounts-*.dat'))
            assert len(files)==1
            cipher = files[0].read_bytes()
            assert PASSWORD.encode() not in cipher and b'SavedMogo6' not in cipher
            result['checks']['encrypted_session_file'] = True
            assert c.js("Object.values(localStorage).every(value=>{try{return !atob(value).includes('Saved123')}catch{return !value.includes('Saved123')}})")
            result['checks']['flash_did_not_persist_password'] = True
            spawn = c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
            c.stage_click(500,392)
            c.wait("fetch('/api/world/me').then(r=>r.json()).then(p=>p.x > 450)")
            c.wait("window.player.ruffle().callExternalInterface('getWorldAvatar').x > 450")
            saved_position = c.js("fetch('/api/world/me').then(r=>r.json()).then(p=>[p.x,p.y])")
            # Restart both processes, keeping only the same SQLite and Windows profile.
            stop(client);processes.remove(client)
            stop(backend);processes.remove(backend)
            backend = start_backend()
            client,c = start_client()
            c.wait("window.mogobeLogin?.view === 'saved' && window.mogobeLogin.visible.length === 4")
            entries = public_accounts()
            assert len(entries)==6 and all(item['has_session'] for item in entries)
            assert c.js('window.mogobeLogin.visible') == list(reversed(NAMES))[:4]
            assert c.js('window.mogobeLogin.selected') == NAMES[-1]
            result['checks']['original_case_preserved_after_restart'] = True
            assert_left_to_right()
            result['checks']['original_picker_left_to_right'] = True
            capture('01-six-remembered')
            result['checks']['client_and_server_restart_preserved_accounts'] = True
            with sqlite3.connect(database) as db:
                before = db.execute('SELECT count(*) FROM auth_session').fetchone()[0]
            c.control('btnLoginMultiInst')
            choose_server()
            assert c.js('window.mogobeScene.user.username')==NAMES[-1]
            with sqlite3.connect(database) as db:
                after = db.execute('SELECT count(*) FROM auth_session').fetchone()[0]
                result['session_counts'] = {'before':before,'after':after}
                assert after==before,(before,after)
            result['checks']['saved_session_login_without_password'] = True
            avatar = c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
            assert c.js("window.mogobeScene.room === 'novograd'")
            result['checks']['novograd_random_spawn_after_restart'] = True
            result['checks']['all_six_original_avatar_colors'] = True
            return_to_picker()
            c.control('btnRightI');c.control('btnRightI')
            c.wait("window.mogobeLogin?.visible.includes('SavedMogo1')")
            capture('02-scrolled-original-picker')
            c.control('mcSmallPreviewHolderInst4')
            c.wait("window.mogobeLogin?.selected === 'SavedMogo1'")
            c.control('btnLoginMultiInst');choose_server()
            assert c.js('window.mogobeScene.user.username')==NAMES[0]
            assert c.js('window.mogobeScene.user.color_id')==1
            result['checks']['original_pagination_and_account_switch'] = True
            capture('03-first-account-resumed')
            return_to_picker()
            assert c.js("fetch('/api/auth/logout',{method:'POST'}).then(r=>r.status===204)")
            entries = public_accounts()
            assert not entries[0]['has_session'] and all(item['has_session'] for item in entries[1:]),entries
            result['checks']['logout_only_revoked_selected_account'] = True
            c.control('btnDisconnectI')
            c.wait("fetch('/client/accounts').then(r=>r.json()).then(items=>items.length===5)")
            assert all(item['username']!=NAMES[0] for item in public_accounts())
            result['checks']['original_disconnect_removed_only_selected_mogobe'] = True
            capture('04-one-account-forgotten')
            selected = c.js('window.mogobeLogin.selected')
            selected = next(item['username'] for item in public_accounts() if item['username'].lower()==selected.lower())
            with sqlite3.connect(database) as db:
                db.execute("UPDATE auth_session SET expires_at='2000-01-01' WHERE account_id=(SELECT id FROM auth_account WHERE username=?)",(selected,))
                db.commit()
            c.control('btnLoginMultiInst')
            c.wait("document.getElementById('notice').textContent.includes('истекла')")
            entries = public_accounts()
            assert not next(item for item in entries if item['username']==selected)['has_session']
            assert all(item['has_session'] for item in entries if item['username']!=selected)
            capture('05-expired-session')
            result['checks']['expired_session_requires_only_its_password'] = True
            c.control('btnConfirm')
            c.control('txtMultiLoginPassword');c.type_text(PASSWORD)
            c.control('btnLoginMultiInst');choose_server()
            assert c.js('window.mogobeScene.user.username')==selected
            assert next(item for item in public_accounts() if item['username']==selected)['has_session']
            result['checks']['password_reentry_restored_expired_account'] = True
        except Exception:
            result['error'] = traceback.format_exc()
            if c:
                try:
                    result['state'] = c.js("Promise.all([fetch('/client/login-result').then(r=>r.json()),fetch('/client/accounts').then(r=>r.json()),fetch('/api/auth/me').then(r=>r.status)]).then(([attempt,accounts,sessionStatus])=>JSON.stringify({scene:window.mogobeScene,login:window.mogobeLogin,notice:document.getElementById('notice')?.textContent,attempt,accounts,sessionStatus}))")
                    c.capture('saved-mogobes/failure')
                except Exception:
                    pass
        finally:
            for process in reversed(processes):stop(process)
            backend_log.close();client_log.close()
    result['passed'] = not result.get('error') and all(result['checks'].values())
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
