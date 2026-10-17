"""One native window: original shop, purchases, live admin edits and admin badge."""
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
from PIL import ImageGrab

from verify_desktop import CLIENT, ROOT, DesktopBridge, wait_http

OUT = ROOT / "verification/shops"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result={"suite":"shops","account_count":1,"checks":{}}
    processes=[];bridge=None
    with tempfile.TemporaryDirectory(prefix="mogobe-shops-",ignore_cleanup_errors=True) as tmp:
        directory=Path(tmp);database=directory/'test.sqlite3'
        with (OUT/'backend.log').open('w',encoding='utf-8') as blog,(OUT/'client.log').open('w',encoding='utf-8') as clog:
            try:
                env=os.environ.copy();env['MOGOBE_DATABASE_URL']='sqlite+aiosqlite:///'+database.as_posix()
                env['PYTHONPATH']=str(ROOT/'server/.venv/Lib/site-packages')
                env['MOGOBE_UI_TEST_SECRET']=secrets.token_urlsafe(32);env['MOGOBE_UI_TEST_PROFILE']=str(directory/'webview')
                backend=subprocess.Popen([sys._base_executable,'run.py','--port','18080'],cwd=ROOT/'server',env=env,stdout=blog,stderr=subprocess.STDOUT);processes.append(backend)
                wait_http('http://127.0.0.1:18080/api/health')
                api=httpx.Client(base_url='http://127.0.0.1:18080')
                assert api.post('/api/auth/registration-drafts',json={'username':'ShopNative','password':'Shop1234','color_id':7}).status_code==201
                assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                with sqlite3.connect(database) as db:db.execute('UPDATE auth_account SET is_admin=1');db.commit()
                admin='/api/admin/shops'
                for ident in [100,101]:assert api.put(admin+'/items/'+str(ident),json={'id':ident,'name':'Фиолетовая рубашка' if ident==100 else 'Красная рубашка','main_type':1}).status_code==200
                assert api.put(admin+'/items/20',json={'id':20,'name':'Синяя футболка','main_type':1}).status_code==200
                assert api.put(admin+'/native',json={'key':'native','title':'Проверка магазина','kind':'clothing'}).status_code==200
                cat=api.post(admin+'/native/categories',json={'name':'Вещи','icon_id':4}).json()['id']
                for ident in [100,101]:assert api.put(admin+'/native/offers/'+str(ident),json={'item_id':ident,'category_id':cat,'price':10 if ident==100 else 30,'stock':2}).status_code==200
                assert api.post(admin+'/accounts/ShopNative/balance',json={'coins':25}).status_code==200
                config=directory/'client.json';config.write_text(json.dumps({'server_url':'http://127.0.0.1:18080','request_timeout_seconds':10}))
                client=subprocess.Popen([str(CLIENT),'--config',str(config)],cwd=directory,env=env,stdout=clog,stderr=subprocess.STDOUT);processes.append(client);time.sleep(2)
                c=bridge=DesktopBridge(client,env['MOGOBE_UI_TEST_SECRET'])
                c.wait("window.mogobeLogin?.view==='single'",60)
                c.control('txtUserName');c.type_text('ShopNative');c.control('txtPassword');c.type_text('Shop1234');c.control('btnLogin');c.wait("window.mogobeLogin?.view==='servers'");c.stage_click(384,140)
                c.wait("window.mogobeScene?.state==='world'",60)
                c.chat_send('/shop native')
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.items.length===2",45)
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.items.every(i=>i.graphics>0)",30)
                info=c.js("window.player.ruffle().callExternalInterface('getShopInfo')")
                assert info['coins']==25 and info['avatar'] and not info['luxuryVisible'] and info['coinY']>=285,info
                for item in info['items']:
                    art=item['art']
                    assert art and abs(art['x']+art['width']/2-42.85)<.2 and abs(art['y']+art['height']/2-31.95)<.2,item
                    assert art['x']>=18.5 and art['x']+art['width']<=67.2 and art['y']>=9.9 and art['y']+art['height']<=54,item
                    assert abs(art['width']-48.1)<.3 or abs(art['height']-43.5)<.3,item
                result['checks']['clothes_centered_and_fill_preview_with_padding']=True
                c.capture('shops/01-original-shop')
                result['checks']['command_opens_original_shop_and_graphics']=True
                first=info['items'][0];c.stage_click(first['hitX'],first['hitY'])
                c.wait("window.player.ruffle().callExternalInterface('getLoginControlBounds','btnBuyItem')?.enabled===true")
                c.control('btnBuyItem')
                c.wait("fetch('/api/inventory').then(r=>r.json()).then(i=>i.items.length===1 && i.coins===15)")
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.coins===15")
                result['checks']['native_purchase_debits_and_persists_inventory']=True
                c.control('btnConfirm')
                # Independent admin session edits the live server; no admin page
                # or privileged endpoints are embedded in the game client.
                with httpx.Client(base_url='http://127.0.0.1:18080') as editor:
                    assert editor.post(admin+'/login',json={'username':'ShopNative','password':'Shop1234'}).status_code==200
                    assert editor.put(admin+'/native/offers/101',json={'item_id':101,'category_id':cat,'price':7,'stock':2}).status_code==200
                assert c.js("fetch('/admin/shops').then(r=>r.status)")==404
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.items.some(i=>i.id===101 && i.price===7)")
                result['checks']['separate_admin_edits_live_shop_without_reconnect']=True
                info=c.js("window.player.ruffle().callExternalInterface('getShopInfo')")
                second=next(i for i in info['items'] if i['id']==101);c.stage_click(second['hitX'],second['hitY']);c.control('btnBuyItem')
                c.wait("fetch('/api/inventory').then(r=>r.json()).then(i=>i.items.length===2 && i.coins===8)")
                result['checks']['edited_price_used_by_original_buy_button']=True
                c.control('btnConfirm')
                c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                c.wait("window.player.ruffle().callExternalInterface('getExperienceInfo')?.shown>=2")
                c.chat_send('/give exp 1490')
                c.wait("window.player.ruffle().callExternalInterface('getExperienceInfo')?.shown>=3")
                assert '1490' in c.js("window.player.ruffle().callExternalInterface('getExperienceInfo')")["last"]
                c.capture('shops/02-original-experience-sign')
                c.chat_send('/give item 20')
                c.wait("fetch('/api/inventory').then(r=>r.json()).then(i=>i.items.length===3)")
                result['checks']['give_item_and_exp_use_authoritative_inventory_and_original_popup']=True
                c.control('btnProfile')
                c.wait("window.player.ruffle().callExternalInterface('getProfileInfo')?.adminBadge === true")
                c.wait("window.player.ruffle().callExternalInterface('getProfileInfo')?.visible===true && window.player.ruffle().callExternalInterface('getProfileInfo')?.iconBoxes.length===4")
                c.wait("window.player.ruffle().callExternalInterface('getProfileInfo')?.score===1510")
                profile=c.js("window.player.ruffle().callExternalInterface('getProfileInfo')")
                assert profile['level']==2 and profile['levelName']=='Уровень: 2',profile
                assert not profile['luxuryVisible'] and not profile['luxuryIconVisible'],profile
                centers=[v['center'] for v in profile['counters']]
                assert len(centers)==4 and all(abs(a-b)<.2 for a,b in zip(centers,[182.125,218.125,254.125,290.125])),profile
                assert len(profile['iconBoxes'])==4,profile
                stage=json.loads(c.js("JSON.stringify(document.getElementById('stage').getBoundingClientRect().toJSON())"))
                # DesktopBridge coordinates are client-relative. Convert to
                # screen coordinates with Win32, as real pointer clicks do.
                import ctypes
                from ctypes import wintypes
                point=wintypes.POINT(0,0)
                c.user32.ClientToScreen(c.hwnd,ctypes.byref(point))
                shot=ImageGrab.grab()
                for box in profile['iconBoxes']:
                    left=point.x+stage['x']+box['x']*stage['width']/768
                    top=point.y+stage['y']+box['y']*stage['height']/480
                    crop=shot.crop((left,top,left+box['width']*stage['width']/768,top+box['height']*stage['height']/480)).convert('RGB')
                    gold=sum(1 for r,g,b in crop.getdata() if r>150 and r>g*1.04 and b<r*.65)
                    assert gold>8,('Original counter icon missing',box,gold)
                result['checks']['four_original_profile_icons_have_visible_pixels']=True
                with httpx.Client(base_url='http://127.0.0.1:18080') as manager:
                    assert manager.post('/api/auth/registration-drafts',json={'username':'ShopManager','password':'Shop1234','color_id':3}).status_code==201
                    assert manager.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                    with sqlite3.connect(database) as db:db.execute("UPDATE auth_account SET is_admin=1 WHERE username='ShopManager'");db.commit()
                    own_id=c.js('window.mogobeScene.user.id')
                    assert manager.put(admin+'/accounts/'+str(own_id)+'/admin',json={'is_admin':False}).status_code==200
                    c.wait("window.player.ruffle().callExternalInterface('getProfileInfo')?.adminBadge===false")
                    assert manager.put(admin+'/accounts/'+str(own_id)+'/admin',json={'is_admin':True}).status_code==200
                    c.wait("window.player.ruffle().callExternalInterface('getProfileInfo')?.adminBadge===true")
                result['checks']['gold_mogocard_badge_updates_with_admin_role_without_relogin']=True
                level_box=c.js("window.player.ruffle().callExternalInterface('getProfileControlBounds','mogobeLevelIndicator')")
                if level_box:c.stage_click(level_box['x']+level_box['width']/2,level_box['y']+level_box['height']/2)
                c.capture('shops/03-profile-level-and-admin')
                result['checks']['original_mogocard_icon_marks_admin']=True
                c.control('btnClose')
                assert api.put(admin+'/empty',json={'key':'empty','title':'Пустой магазин','kind':'objects'}).status_code==200
                c.chat_send('/shop empty')
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.key==='empty'")
                c.wait("window.player.ruffle().callExternalInterface('getShopInfo')?.avatar===false")
                result['checks']['new_empty_objects_shop_opens_without_restart']=True
                c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                c.control('btnMap')
                c.wait("window.player.ruffle().callExternalInterface('getWorldMapInfo')?.ready===true")
                result['checks']['world_map_still_loads_with_relative_asset_urls']=True

                result['checks']['self_contained_server_graphics']=api.get('/api/shop-assets/Display/100.swf').status_code==200
                api.close()
            except Exception:
                result['error']=traceback.format_exc()
                if bridge:
                    try:
                        result['state']=bridge.js("JSON.stringify({shop:window.player?.ruffle().callExternalInterface('getShopInfo'),scene:window.mogobeScene,notice:document.querySelector('#notice')?.textContent,resources:performance.getEntriesByType('resource').filter(r=>r.name.includes('Items/')).map(r=>r.name.split('?')[0])})")
                        bridge.capture('shops/failure')
                    except Exception:pass
            finally:
                for process in reversed(processes):
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:process.kill()
    result['passed']=not result.get('error') and all(result['checks'].values())
    (OUT/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=True,indent=2),flush=True)
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
