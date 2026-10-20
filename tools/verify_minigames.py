"""One-account original GoldFishing cycle in isolated Edge and embedded Go preview."""
import base64
import json
import math
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
from verify_admin import Browser


class IsolatedBrowser(Browser):
    """Use the embedded client through its loopback preview, without desktop input."""
    def focus(self, timeout=10):
        pass

    def click(self, x, y):
        self.call('Input.dispatchMouseEvent',type='mouseMoved',x=x,y=y)
        self.call('Input.dispatchMouseEvent',type='mousePressed',x=x,y=y,button='left',clickCount=1)
        self.call('Input.dispatchMouseEvent',type='mouseReleased',x=x,y=y,button='left',clickCount=1)
        time.sleep(.1)

    def type_text(self, text):
        self.call('Input.dispatchKeyEvent',type='keyDown',key='a',code='KeyA',windowsVirtualKeyCode=65,modifiers=2)
        self.call('Input.dispatchKeyEvent',type='keyUp',key='a',code='KeyA',windowsVirtualKeyCode=65,modifiers=2)
        self.call('Input.insertText',text=text)

    def chat_send(self, text='/exit', send_button=False):
        self.control('txtSpeak')
        self.type_text(text)
        self.control('btnSend')

    stage_click=DesktopBridge.stage_click
    control=DesktopBridge.control
    popup_confirm=DesktopBridge.popup_confirm

    def capture(self,name):
        path=ROOT/'verification'/(name+'.png')
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(base64.b64decode(self.call('Page.captureScreenshot',format='png')['data']))


def main():
    out=ROOT/'verification/minigames'
    out.mkdir(parents=True,exist_ok=True)
    result={'suite':'minigames','account_count':1,'checks':{}}
    processes=[]
    bridge=None
    with tempfile.TemporaryDirectory(prefix='mogobe-minigame-',ignore_cleanup_errors=True) as temporary:
        directory=Path(temporary)
        database=directory/'test.sqlite3'
        with (out/'backend.log').open('w',encoding='utf-8') as blog, (out/'client.log').open('w',encoding='utf-8') as clog:
            try:
                env=os.environ.copy()
                env['MOGOBE_BOOTSTRAP_DEFAULTS']='false'
                env['MOGOBE_DATABASE_URL']='sqlite+aiosqlite:///'+database.as_posix()
                env['PYTHONPATH']=str(ROOT/'server/.venv/Lib/site-packages')
                env['MOGOBE_UI_TEST_SECRET']=secrets.token_urlsafe(32)
                env['MOGOBE_UI_TEST_PROFILE']=str(directory/'webview')
                backend=subprocess.Popen([sys._base_executable,'run.py','--port','18080'],cwd=ROOT/'server',env=env,stdout=blog,stderr=subprocess.STDOUT)
                processes.append(backend)
                wait_http('http://127.0.0.1:18080/api/health')
                with httpx.Client(base_url='http://127.0.0.1:18080') as api:
                    assert api.post('/api/auth/registration-drafts',json={'username':'FishNative','password':'Fish1234','color_id':7}).status_code==201
                    assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                    assert api.post('/api/auth/logout').status_code==204
                with sqlite3.connect(database) as db:
                    db.execute("UPDATE auth_account SET is_admin=1 WHERE username='FishNative'")
                config=directory/'client.json'
                config.write_text(json.dumps({'server_url':'http://127.0.0.1:18080','request_timeout_seconds':10}),encoding='utf-8')
                client=subprocess.Popen([str(CLIENT),'--config',str(config),'--preview','127.0.0.1:18089'],cwd=directory,env=env,stdout=clog,stderr=subprocess.STDOUT)
                processes.append(client)
                wait_http('http://127.0.0.1:18089/')
                edge=Path(os.environ['ProgramFiles(x86)'])/'Microsoft/Edge/Application/msedge.exe'
                browser=subprocess.Popen([str(edge),'--headless=new','--mute-audio','--no-first-run','--disable-gpu',
                    '--remote-debugging-port=18090','--user-data-dir='+str(directory/'edge'),'about:blank'],
                    env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                processes.append(browser)
                wait_http('http://127.0.0.1:18090/json/list')
                pages=httpx.get('http://127.0.0.1:18090/json/list').json()
                bridge=IsolatedBrowser(next(p for p in pages if p['type']=='page')['webSocketDebuggerUrl'])
                c=bridge
                c.call('Emulation.setDeviceMetricsOverride',width=1000,height=720,deviceScaleFactor=1,mobile=False)
                c.call('Page.navigate',url='http://127.0.0.1:18089/')
                c.wait("window.mogobeLogin?.view==='single'",60)
                c.control('txtUserName');c.type_text('FishNative')
                c.control('txtPassword');c.type_text('Fish1234')
                time.sleep(5)
                c.control('btnLogin')
                c.wait("window.mogobeLogin?.view==='servers'",40)
                c.stage_click(384,140)
                c.wait("window.mogobeScene?.state==='world'",60)

                def info():
                    return c.js("window.player.ruffle().callExternalInterface('getMinigameInfo')")

                # Exercise the shared original alert through the actual chat command,
                # then after the distinct left-aligned command-list layout.
                c.chat_send('/alert Проверка сообщения')
                c.wait("window.mogobePopup?.state==='open'")
                assert c.js('window.mogobePopup.original')
                def centered():
                    layout=c.js("window.registrationPopupPlayer.ruffle().callExternalInterface('getMessageInfo')")
                    assert layout['align']=='center' and abs(layout['centerOffsetX'])<1 and abs(layout['centerOffsetY'])<1,layout
                    assert layout['textBottom']<layout['panel']['y']+layout['panel']['height'],layout
                    return layout
                centered()
                c.capture('minigames/00-alert-centered')
                c.popup_confirm()
                c.chat_send('/help')
                c.wait("window.mogobePopup?.state==='open'")
                assert c.js("window.registrationPopupPlayer.ruffle().callExternalInterface('getMessageInfo').align")== 'left'
                c.popup_confirm()
                for message in ['Первая строка\nВторая строка', 'Длинное сообщение для проверки переноса строк. '*18, 'Готово!']:
                    c.js('window.showMogobePopup('+json.dumps(message)+')')
                    c.wait("window.mogobePopup?.state==='open'")
                    centered()
                    c.popup_confirm()
                result['checks']['alert_centered_both_axes_after_command_help_and_long_text']=True

                def close_result(screenshot):
                    c.wait("window.mogobeMinigame?.state==='result'",30)
                    view=info()
                    assert view['resultClass']=='mlGameOverSingle',view
                    outcome=c.js('window.mogobeMinigame.result')
                    assert str(outcome['score']) in view['resultScore'],view
                    assert str(outcome['coins_awarded']) in view['resultScore'],view
                    assert c.js("window.mogobePopup?.state")!='open'
                    c.capture(screenshot)
                    bounds=view['resultExit']
                    c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                    c.wait("window.mogobeScene?.state==='world' && window.mogobeMinigame?.state==='closed'",30)
                    return outcome

                c.chat_send('/game goldfishing')
                c.wait("window.mogobeMinigame?.state==='playing'",40)
                first=info()
                assert first['ready'] and first['avatarColor']==7 and first['frameRate']==15,first
                c.wait("window.mogobeScene?.state==='minigame'")
                c.capture('minigames/01-original-menu')
                result['checks']['command_loads_original_swf_with_player_color']=True
                bounds=info()['help']
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                c.wait("window.player.ruffle().callExternalInterface('getMinigameInfo')?.helpOpen===true")
                text=info()['helpText']
                assert text.startswith('Цель игры - достать сокровища из под воды!'),text
                c.capture('minigames/02-original-help')
                bounds=info()['helpBack']
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                c.wait("window.player.ruffle().callExternalInterface('getMinigameInfo')?.helpOpen===false")
                result['checks']['original_help_frame_and_saved_russian_instruction']=True
                c.stage_click(392,250)
                time.sleep(3)
                c.capture('minigames/02-original-gameplay')
                # Aim by read-only original scene geometry; use real mouse input.
                # No score mutation and no synthetic end-game event.
                for attempt in range(3):
                    current=info()
                    if current['score']>=100:break
                    targets=[t for t in current.get('targets',[]) if t['value']>=100]
                    assert targets,current
                    targets.sort(key=lambda t:(t['x']-current['hookX'])**2+(t['y']-current['hookY'])**2)
                    target=targets[min(attempt,len(targets)-1)]
                    angle=math.degrees(math.atan2(current['hookX']-target['x'],target['y']-current['hookY']))
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline:
                        if abs(info()['hookAngle']-angle)<5:break
                        time.sleep(.04)
                    c.stage_click(384,350)
                    deadline=time.monotonic()+8
                    while time.monotonic()<deadline and info()['score']<100:time.sleep(.2)
                earned=info()['score']
                assert earned>=100,earned
                bounds=info()['exit']
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                first_result=close_result('minigames/03-original-early-result')
                assert c.js("window.mogobeScene.room")=='novograd'
                assert c.js("fetch('/api/minigames/results').then(r=>r.json()).then(x=>x.results[0].status)")=='stopped'
                assert first_result['score']==earned,first_result
                assert first_result['coins_awarded']==first_result['experience_awarded']==min(earned//100,100)
                assert c.js("fetch('/api/inventory').then(r=>r.json()).then(x=>x.coins)")==first_result['coins_awarded']
                result['checks']['original_exit_returns_to_room_and_saves_earned_result']=True
                c.chat_send('/room severburg')
                c.wait("window.mogobeScene?.state==='world'&&window.mogobeScene?.room==='severburg'",45)
                bounds=c.js("window.player.ruffle().callExternalInterface('getLoginControlBounds','mcEntryPoint_81')")
                assert bounds,bounds
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                c.wait("window.mogobeMinigame?.state==='playing'",40)
                second=info()
                assert second['id']!=first['id']
                result['checks']['original_severburg_entry_opens_fishing']=True
                c.stage_click(392,250)
                c.capture('minigames/03-severburg-fishing')
                # Let the original game finish without an artificial AS3 end event.
                # A caught item can advance the game to another round.
                c.wait("window.mogobeMinigame?.state==='result'",180)
                outcome=close_result('minigames/04-original-result-popup')
                c.wait("window.mogobeScene?.state==='world'&&window.mogobeScene?.room==='severburg'",20)
                assert outcome['status']=='finished' and outcome['score']>=0,outcome
                assert outcome['coins_awarded']==min(outcome['score']//100,100),outcome
                result['checks']['natural_game_over_persists_result_and_returns_to_severburg']=True
                with sqlite3.connect(database) as db:
                    rows=db.execute('SELECT status,score,coins FROM minigame_run ORDER BY started_at').fetchall()
                    assert rows==[('stopped',earned,first_result['coins_awarded']),('finished',outcome['score'],outcome['coins_awarded'])],rows
                result['checks']['sqlite_contains_both_runs']=True
                avatar=c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
                c.stage_click(550,380)
                c.wait("Math.abs(window.player.ruffle().callExternalInterface('getWorldAvatar').x-"+str(avatar['x'])+")>10",15)
                result['checks']['walking_works_after_original_game_entry']=True
                c.chat_send('/game goldfishing')
                c.wait("window.mogobeMinigame?.state==='playing'",30)
                c.js('window.onMogobeReconnect()')
                c.wait("window.mogobeScene?.state==='world'&&window.mogobeScene?.room==='severburg'",60)
                assert info() is None
                with sqlite3.connect(database) as db:
                    assert db.execute("SELECT count(*) FROM minigame_run WHERE status='active'").fetchone()[0]==0
                result['checks']['f5_cancels_game_and_keeps_source_room']=True
            except Exception:
                result['error']=traceback.format_exc()
                if bridge:
                    try:
                        result['state']=bridge.js("JSON.stringify({scene:window.mogobeScene,game:window.mogobeMinigame,info:window.player?.ruffle().callExternalInterface('getMinigameInfo'),popup:window.mogobePopup})")
                        bridge.capture('minigames/failure')
                    except Exception:pass
            finally:
                for process in reversed(processes):
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill()
    result['passed']=not result.get('error') and all(result['checks'].values())
    (out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
