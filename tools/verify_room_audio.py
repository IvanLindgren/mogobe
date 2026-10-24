"""One-account original room music cycle in isolated Edge and embedded Go preview."""
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
    out=ROOT/'verification/room-audio'
    out.mkdir(parents=True,exist_ok=True)
    result={'suite':'room-audio','account_count':1,'checks':{}}
    processes=[]
    bridge=None
    with tempfile.TemporaryDirectory(prefix='mogobe-room-audio-',ignore_cleanup_errors=True) as temporary:
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
                    assert api.post('/api/auth/registration-drafts',json={'username':'AudioNative','password':'Fish1234','color_id':7}).status_code==201
                    assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                    assert api.post('/api/auth/logout').status_code==204
                with sqlite3.connect(database) as db:
                    db.execute("UPDATE auth_account SET is_admin=1 WHERE username='AudioNative'")
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
                audio_probe_source='''
                  window.roomAudioStarts=[];window.roomAudioRequests=[];window.roomAudioContexts=[];window.roomAudioNodes=[];
                  if(window.AudioContext){
                    window.AudioContext=new Proxy(window.AudioContext,{construct(Target,args){
                      const context=new Target(...args);roomAudioContexts.push(context);return context;
                    }});
                  }
                  if(window.BaseAudioContext){
                    const create=BaseAudioContext.prototype.createBufferSource;
                    BaseAudioContext.prototype.createBufferSource=function(){
                      const node=create.apply(this,arguments);roomAudioNodes.push(node);return node;
                    };
                  }
                  const originalFetch=window.fetch;
                  window.fetch=function(input,options){
                    const url=new URL(typeof input==='string'?input:input.url,location.href);
                    if(url.pathname.startsWith('/Sound/'))roomAudioRequests.push(url.pathname);
                    return originalFetch.apply(this,arguments);
                  };
                  if(window.AudioBufferSourceNode){
                    const start=AudioBufferSourceNode.prototype.start;
                    AudioBufferSourceNode.prototype.start=function(){
                      roomAudioStarts.push({duration:this.buffer?.duration||0});
                      return start.apply(this,arguments);
                    };
                  }
                '''
                c.call('Page.enable')
                c.call('Page.addScriptToEvaluateOnNewDocument',source=audio_probe_source)
                c.call('Page.navigate',url='http://127.0.0.1:18089/')
                c.wait("window.mogobeLogin?.view==='single'",60)
                c.js('if(!window.roomAudioStarts){'+audio_probe_source+'}')
                c.control('txtUserName');c.type_text('AudioNative')
                c.control('txtPassword');c.type_text('Fish1234')
                time.sleep(5)
                c.control('btnLogin')
                c.wait("window.mogobeLogin?.view==='servers'",40)
                c.stage_click(384,140)
                c.wait("window.mogobeScene?.state==='world'",60)

                def info():
                    return c.js("window.player.ruffle().callExternalInterface('getRoomAudioInfo')")

                def wait_audio(room,track=None):
                    c.wait("window.mogobeScene?.state==='world' && window.mogobeScene.room==="+json.dumps(room),60)
                    if track:
                        c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo')?.loaded===true",30)
                        audio=info()
                        assert audio['url'].endswith('/Sound/Rooms/'+track),audio
                        assert audio['bytesLoaded']==audio['bytesTotal'] and audio['length']>5000,audio
                    else:
                        c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo')?.loaded===false")
                    return info()

                def change_room(room,track=None):
                    c.chat_send('/room '+room)
                    return wait_audio(room,track)

                def toggle_mute():
                    bounds=info()['muteButton']
                    c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)

                music=wait_audio('novograd','Novograd.mp3')
                assert not music['muted'],music
                c.wait('window.roomAudioStarts.length>0',10)
                result['checks']['novograd_original_manager_decodes_mp3_and_starts_audio']=True
                for track in ['Novograd.mp3','otdyhaevo.mp3','DukeMaze.mp3']:
                    response=c.js("fetch('/Sound/Rooms/"+track+"').then(async r=>({status:r.status,type:r.headers.get('Content-Type'),bytes:Array.from(new Uint8Array(await r.arrayBuffer()))}))")
                    expected=(ROOT/'assets/original/Sound/Rooms'/track).read_bytes()
                    assert response['status']==200 and 'audio' in response['type'],response.keys()
                    assert bytes(response['bytes'])==expected,track
                result['checks']['three_original_mp3s_are_served_from_embedded_client']=True

                toggle_mute()
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').muted===true")
                audio=change_room('summercamp','otdyhaevo.mp3')
                assert audio['muted'],audio
                restarts=audio['restarts']
                starts=c.js('window.roomAudioStarts.length')
                toggle_mute()
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').muted===false")
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').restarts>"+str(restarts))
                c.wait('window.roomAudioStarts.length>'+str(starts))
                result['checks']['original_mute_button_survives_room_change_and_unmute_restarts_music']=True
                change_room('infoboard')
                result['checks']['leaving_music_room_clears_background_binding']=True
                change_room('maze_entrance','DukeMaze.mp3')
                result['checks']['maze_entrance_uses_preserved_dukemaze_track']=True
                change_room('pool')
                toggle_mute()
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').muted===true")
                toggle_mute()
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').muted===false")
                result['checks']['embedded_pool_sound_uses_same_global_mute']=True
                change_room('novograd','Novograd.mp3')
                c.chat_send('/game goldfishing')
                c.wait("window.mogobeMinigame?.state==='playing'",40)
                assert info()['suspended']
                bounds=c.js("window.player.ruffle().callExternalInterface('getMinigameInfo').exit")
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                c.wait("window.mogobeMinigame?.state==='result'",30)
                bounds=c.js("window.player.ruffle().callExternalInterface('getMinigameInfo').resultExit")
                c.stage_click(bounds['x']+bounds['width']/2,bounds['y']+bounds['height']/2)
                audio=wait_audio('novograd','Novograd.mp3')
                assert not audio['suspended'],audio
                result['checks']['minigame_suspends_room_music_and_original_exit_restores_it']=True
                # Wait for a real SoundManager SOUND_COMPLETE, not a synthetic event.
                # The original BaseRoom handles this event by replaying BackSoundKey.
                completed=audio['completions']
                c.wait("window.player.ruffle().callExternalInterface('getRoomAudioInfo').completions>"+str(completed),80)
                assert info()['loaded']
                result['checks']['original_background_completion_and_repeat_path_runs']=True
                c.js('window.roomAudioGeneration=true;window.onMogobeReconnect()')
                c.wait("window.roomAudioGeneration===undefined && window.mogobeScene?.state==='world'",60)
                wait_audio('novograd','Novograd.mp3')
                result['checks']['f5_reconnect_restores_current_room_music']=True
                c.chat_send('/exit')
                c.wait("window.mogobeScene?.state==='lobby'",40)
                assert not info()['loaded']
                result['checks']['exit_returns_to_picker_without_world_music']=True
            except Exception:
                result['error']=traceback.format_exc()
                if bridge:
                    try:
                        result['state']=bridge.js("JSON.stringify({scene:window.mogobeScene,game:window.mogobeMinigame,info:window.player?.ruffle().callExternalInterface('getRoomAudioInfo'),popup:window.mogobePopup,audioRequests:window.roomAudioRequests,audioStarts:window.roomAudioStarts,audioNodes:window.roomAudioNodes?.length,audioContexts:window.roomAudioContexts?.map(c=>({state:c.state,time:c.currentTime}))})")
                        bridge.capture('room-audio/failure')
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
