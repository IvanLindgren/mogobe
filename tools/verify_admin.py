"""Verify the separate admin application and Ruffle previews in Microsoft Edge.

Uses a temporary database/profile. Requires httpx, Pillow and websockets in the
test Python environment; none are runtime dependencies of the game client.
"""
import base64
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import traceback

import httpx
from PIL import Image
from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'verification/admin'


class Browser:
    def __init__(self, url):
        self.socket = connect(url, max_size=20*1024*1024)
        self.serial = 0

    def call(self, method, **params):
        self.serial += 1
        ident = self.serial
        self.socket.send(json.dumps({'id': ident, 'method': method, 'params': params}))
        while True:
            message = json.loads(self.socket.recv(timeout=45))
            if message.get('id') == ident:
                if 'error' in message:
                    raise RuntimeError(message['error'])
                return message.get('result', {})

    def js(self, expression):
        value = self.call('Runtime.evaluate', expression='{'+expression+'}', awaitPromise=True, returnByValue=True)
        if 'exceptionDetails' in value:
            raise RuntimeError(value['exceptionDetails'])
        return value['result'].get('value')

    def wait(self, expression, timeout=40):
        deadline = time.monotonic()+timeout
        while time.monotonic()<deadline:
            try:
                if self.js(expression):
                    return
            except RuntimeError:
                pass
            time.sleep(.2)
        raise TimeoutError(expression)

    def capture(self, name):
        data = self.call('Page.captureScreenshot', format='png')['data']
        path=OUT/(name+'.png')
        path.write_bytes(base64.b64decode(data))
        return path


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    result={'suite':'admin','checks':{}}
    processes=[]
    with tempfile.TemporaryDirectory(prefix='mogobe-admin-',ignore_cleanup_errors=True) as tmp:
        folder=Path(tmp)
        with (OUT/'backend.log').open('w',encoding='utf-8') as log:
            try:
                env=os.environ.copy()
                env["MOGOBE_BOOTSTRAP_DEFAULTS"]="false"
                db=folder/'test.sqlite3'
                env['MOGOBE_DATABASE_URL']='sqlite+aiosqlite:///'+db.as_posix()
                env['PYTHONPATH']=str(ROOT/'server/.venv/Lib/site-packages')
                backend=subprocess.Popen([sys._base_executable,'run.py','--port','18081'],cwd=ROOT/'server',env=env,stdout=log,stderr=subprocess.STDOUT)
                processes.append(backend)
                for _ in range(100):
                    try:
                        if httpx.get('http://127.0.0.1:18081/api/health').status_code==200:break
                    except httpx.HTTPError:pass
                    time.sleep(.2)
                with httpx.Client(base_url='http://127.0.0.1:18081') as api:
                    assert api.post('/api/auth/registration-drafts',json={'username':'AdminPreview','password':'Admin1234','color_id':7}).status_code==201
                    assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                    api.cookies.clear()
                    assert api.post('/api/auth/registration-drafts',json={'username':'AdminTarget','password':'Admin1234','color_id':3}).status_code==201
                    assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                with sqlite3.connect(db) as sql:
                    sql.execute("UPDATE auth_account SET is_admin=1 WHERE username='AdminPreview'");sql.commit()
                edge=Path(os.environ['ProgramFiles(x86)'])/'Microsoft/Edge/Application/msedge.exe'
                browser=subprocess.Popen([str(edge),'--headless=new','--mute-audio','--no-first-run','--disable-gpu', '--remote-debugging-port=18082','--user-data-dir='+str(folder/'edge'),'about:blank'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                processes.append(browser)
                for _ in range(100):
                    try:
                        pages=httpx.get('http://127.0.0.1:18082/json/list').json()
                        if pages:break
                    except httpx.HTTPError:pass
                    time.sleep(.2)
                c=Browser(next(p for p in pages if p['type']=='page')['webSocketDebuggerUrl'])
                c.call('Emulation.setDeviceMetricsOverride',width=1200,height=900,deviceScaleFactor=1,mobile=False)
                c.call('Page.navigate',url='http://127.0.0.1:18081/admin')
                c.wait("document.querySelector('#login [name=username]') !== null")
                c.js("document.querySelector('#login [name=username]').value='AdminPreview';document.querySelector('#login [name=password]').value='Admin1234';document.querySelector('#login').requestSubmit()")
                c.wait("document.querySelector('#workspace')?.hidden===false")
                c.wait("document.querySelector('#summary-accounts').textContent==='2'")
                assert c.js("document.title")=='Могоби — администрирование'
                assert c.js("document.querySelector('#overview').hidden") is False
                assert c.js("document.querySelector('#summary-administrators').textContent")=='1'
                assert c.js("document.querySelector('#summary-online').textContent")=='0'
                assert c.js("document.querySelector('#asset-list').options.length")==0
                result['checks']['shared_login_opens_server_overview_without_loading_shop_assets']=True
                c.js("document.querySelector('[data-tab=items]').click()")
                c.wait("document.querySelector('#asset-list')?.options.length>2000")
                result['checks']['separate_browser_login_and_asset_catalog']=True
                c.js("document.querySelector('[data-tab=items]').click();const s=document.querySelector('#asset-list');s.value='100';s.dispatchEvent(new Event('change'))")
                c.wait("document.querySelector('#preview ruffle-player')?.ruffle().readyState===2",60)
                time.sleep(2)
                path=c.capture('01-original-shirt-preview')
                # The original purple shirt has opaque purple/red pixels;
                # a white, clipped or failed preview cannot satisfy this.
                box=c.js("document.querySelector('#preview').getBoundingClientRect().toJSON()")
                image=Image.open(path).convert('RGB').crop((box['x'],box['y'],box['right'],box['bottom']))
                colored=sum(1 for r,g,b in image.getdata() if r>g*1.2 and b>g*1.3 and max(r,g,b)-min(r,g,b)>40)
                assert colored>100,('No visible shirt',colored)
                result['checks']['original_swf_preview_renders_shirt']=True
                # Save using the real admin form, then create shop/category/offer.
                c.js("const f=document.querySelector('#item-form');f.elements.name.value='Фиолетовая рубашка';f.elements.main_type.value='1';f.requestSubmit()")
                c.wait("document.querySelector('#message').textContent==='Предмет сохранён'")
                c.js("document.querySelector('[data-tab=shops]').click();document.querySelector('#new-shop').click();const f=document.querySelector('#shop-form');f.elements.key.value='style';f.elements.title.value='Одежда';f.elements.points.querySelector('[value=\"mall.mcShopPoint_1\"]').selected=true;f.requestSubmit()")
                c.wait("document.querySelector('#catalog').hidden===false")
                c.js("const f=document.querySelector('#category-form');f.elements.name.value='Верх';f.elements.inventory_category.value='4';f.elements.icon_id.value='4';f.elements.icon_id.dispatchEvent(new Event('change'));f.requestSubmit()")
                c.wait("document.querySelector('#category-list').children.length===1")
                c.js("const f=document.querySelector('#offer-form');f.elements.price.value='15';f.elements.experience.value='37';f.requestSubmit()")
                c.wait("document.querySelector('#message').textContent==='Ассортимент обновлён'")
                c.wait("document.querySelector('#category-preview').naturalWidth>0")
                c.capture('02-original-category-and-offer')
                result['checks']['real_forms_create_clothes_shop_and_original_category']=True
                assert c.js("fetch('/api/admin/shops/style/catalog').then(r=>r.json()).then(x=>x.shop.points[0])")=='mall.mcShopPoint_1'
                assert c.js("fetch('/api/admin/shops/style/catalog').then(r=>r.json()).then(x=>x.categories[0].inventory_category)")==4
                assert c.js("fetch('/api/admin/items').then(r=>r.json()).then(x=>x.find(i=>i.id===100).inventory_category)")==4
                result['checks']['room_point_and_inventory_slot_are_editable_in_real_forms']=True
                assert c.js("fetch('/api/admin/shops/style/catalog').then(r=>r.json()).then(x=>x.offers[0].experience)")==37
                c.js("document.querySelector('[data-tab=mogobes]').click()")
                c.wait("document.querySelector('#mogobes-list').children.length===2")
                c.js("const f=document.querySelector('#mogobes-search');f.elements.q.value='AdminTarget';f.requestSubmit()")
                c.wait("document.querySelector('#mogobes-list').children.length===1")
                c.js("document.querySelector('#mogobes-list button').click()")
                c.wait("document.querySelector('#mogobes-list button').textContent==='Снять права'")
                assert c.js("fetch('/api/admin/accounts?q=AdminTarget').then(r=>r.json()).then(x=>x.accounts[0].is_admin)") is True
                c.capture('03-account-directory')
                c.js("document.querySelector('#mogobes-list button').click()")
                c.wait("document.querySelector('#mogobes-list button').textContent==='Назначить администратором'")
                result['checks']['account_directory_assigns_and_revokes_administrators']=True
                result['checks']['purchase_reward_is_editable_in_real_form']=True
                c.js("document.querySelector('[data-tab=overview]').click()")
                c.wait("document.querySelector('#summary-items').textContent==='1' && document.querySelector('#summary-shops').textContent==='1'")
                c.capture('04-server-overview')
                result['checks']['overview_refreshes_shared_accounts_items_and_shops']=True
                c.js("document.querySelector('[data-tab=wallet]').click();const f=document.querySelector('#wallet-form');f.elements.username.value='AdminTarget';f.elements.coins.value='123';f.requestSubmit()")
                c.wait("document.querySelector('#message').textContent==='AdminTarget: 123 монет'")
                assert c.js("fetch('/api/admin/accounts?q=AdminTarget').then(r=>r.json()).then(x=>x.accounts[0].coins)")==123
                result['checks']['shared_account_balance_form_works']=True
                c.call('Page.navigate',url='http://127.0.0.1:18081/admin/shops')
                c.wait("location.pathname==='/admin' && document.querySelector('#workspace')?.hidden===false")
                result['checks']['old_bookmark_redirects_into_same_admin_session']=True
                c.js("document.querySelector('[data-tab=shops]').click();document.querySelector('#fill-admin-shop').click()")
                c.wait("document.querySelector('#message').textContent.includes('2456 предметов')",60)
                assert c.js("Promise.all(['admin1','admin2','admin3'].map(k=>fetch('/api/admin/shops/'+k+'/catalog').then(r=>r.json()).then(x=>x.offers.length))).then(counts=>counts.reduce((a,b)=>a+b,0))")==2456
                c.js("document.querySelector('[data-tab=items]').click();const s=document.querySelector('#asset-family');s.value='bumags';s.dispatchEvent(new Event('change'))")
                assert c.js("document.querySelector('#asset-list').options.length")==190
                assert c.js("[...document.querySelector('#asset-list').options].some(o=>o.value==='1')")
                assert not c.js("[...document.querySelector('#asset-list').options].some(o=>o.value==='100')")
                c.js("const s=document.querySelector('#asset-family');s.value='home';s.dispatchEvent(new Event('change'))")
                assert c.js("document.querySelector('#asset-list').options.length")==308
                c.js("const s=document.querySelector('#asset-family');s.value='';s.dispatchEvent(new Event('change'))")
                result['checks']['three_catalogs_and_item_family_filters']=True
                c.js("document.querySelector('[data-tab=items]').click();const s=document.querySelector('#asset-list');s.value='2387';s.dispatchEvent(new Event('change'))")
                c.wait("document.querySelector('#preview ruffle-player')?.ruffle().readyState===2",45)
                time.sleep(1)
                image_path=c.capture('05-walking-only-preview')
                box=c.js("document.querySelector('#preview').getBoundingClientRect().toJSON()")
                crop=Image.open(image_path).convert('RGB').crop((box['x']+2,box['y']+2,box['right']-2,box['bottom']-2))
                colored=sum(1 for pixel in crop.getdata() if min(pixel)<210 and max(pixel)-min(pixel)>20)
                assert colored>100,('Walking-only preview is empty',colored)
                result['checks']['bulk_import_button_populates_all_assets_and_walking_only_preview_renders']=True
                c.js("document.querySelector('#logout').click()")
                c.wait("document.querySelector('#login')?.hidden===false")
                result['checks']['shared_logout_ends_admin_session']=True
                c.socket.close()
            except Exception:
                result['error']=traceback.format_exc()
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
