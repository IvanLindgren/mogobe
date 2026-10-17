"""One native window: original shop, purchases, live admin edits and admin badge."""
import json
import argparse
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
    global OUT
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--catalog',action='store_true')
    parser.add_argument('--world-points',action='store_true')
    parser.add_argument('--point-room',action='append',help='Limit repeated room checks after a focused change')
    args=parser.parse_args()
    if args.catalog:OUT=ROOT/'verification/admin-catalog'
    if args.world_points:OUT=ROOT/'verification/world-shops'
    OUT.mkdir(parents=True, exist_ok=True)
    result={"suite":"world-shops" if args.world_points else "admin-catalog" if args.catalog else "shops","account_count":1,"checks":{}}
    processes=[];bridge=None
    with tempfile.TemporaryDirectory(prefix="mogobe-shops-",ignore_cleanup_errors=True) as tmp:
        directory=Path(tmp);database=directory/'test.sqlite3'
        with (OUT/'backend.log').open('w',encoding='utf-8') as blog,(OUT/'client.log').open('w',encoding='utf-8') as clog:
            try:
                env=os.environ.copy();env['MOGOBE_DATABASE_URL']='sqlite+aiosqlite:///'+database.as_posix()
                env["MOGOBE_BOOTSTRAP_DEFAULTS"]="true" if args.catalog or args.world_points else "false"
                env['PYTHONPATH']=str(ROOT/'server/.venv/Lib/site-packages')
                env['MOGOBE_UI_TEST_SECRET']=secrets.token_urlsafe(32);env['MOGOBE_UI_TEST_PROFILE']=str(directory/'webview')
                backend=subprocess.Popen([sys._base_executable,'run.py','--port','18080'],cwd=ROOT/'server',env=env,stdout=blog,stderr=subprocess.STDOUT);processes.append(backend)
                wait_http('http://127.0.0.1:18080/api/health')
                api=httpx.Client(base_url='http://127.0.0.1:18080')
                assert api.post('/api/auth/registration-drafts',json={'username':'ShopNative','password':'Shop1234','color_id':7}).status_code==201
                assert api.post('/api/auth/register',json={'age':12,'chat_mode':'open'}).status_code==201
                with sqlite3.connect(database) as db:db.execute('UPDATE auth_account SET is_admin=1');db.commit()
                admin='/api/admin/shops'
                for ident in [100,101]:assert api.put(admin+'/items/'+str(ident),json={'id':ident,'name':'Фиолетовая рубашка' if ident==100 else 'Красная рубашка','main_type':1,'inventory_category':4 if args.catalog else 1}).status_code==200
                assert api.put(admin+'/items/20',json={'id':20,'name':'Синяя футболка','main_type':1,'inventory_category':4 if args.catalog else 1}).status_code==200
                assert api.put(admin+'/native',json={'key':'native','title':'Проверка магазина','kind':'clothing'}).status_code==200
                cat=api.post(admin+'/native/categories',json={'name':'Вещи','icon_id':4}).json()['id']
                for ident in [100,101]:assert api.put(admin+'/native/offers/'+str(ident),json={'item_id':ident,'category_id':cat,'price':10 if ident==100 else 30,'stock':2}).status_code==200
                assert api.post(admin+'/accounts/ShopNative/balance',json={'coins':25}).status_code==200
                if args.catalog:
                    imported=api.post('/api/admin/shops/admin/import-assets')
                    assert imported.status_code==200 and imported.json()['total_assets']==2456
                    # One owned garment per original inventory category. The
                    # purchased hat 16 remains separate for the purchase check.
                    with sqlite3.connect(database) as db:
                        for item in [70,20,18,14,41,11]:
                            db.execute("INSERT INTO shop_owned_item(account_id,item_id) SELECT id,? FROM auth_account WHERE username_key='admin'",(item,))
                        db.commit()
                    catalog=api.get('/api/admin/shops/admin1/catalog').json()
                    offer=next(o for o in catalog['offers'] if o['item_id']==16)
                    offer={k:v for k,v in offer.items() if k not in ('id','shop_id')};offer['price']=37
                    assert api.put('/api/admin/shops/admin1/offers/16',json=offer).status_code==200
                    assert api.post('/api/admin/accounts/admin/balance',json={'coins':100}).status_code==200

                    assert api.put('/api/admin/shops/walking',json={'key':'walking','title':'Анимация без иконки','kind':'objects','admin_only':True}).status_code==200
                    category=api.post('/api/admin/shops/walking/categories',json={'name':'Анимации','icon_id':4}).json()['id']
                    assert api.put('/api/admin/shops/walking/offers/2387',json={'item_id':2387,'category_id':category,'price':0,'experience':0}).status_code==200
                config=directory/'client.json';config.write_text(json.dumps({'server_url':'http://127.0.0.1:18080','request_timeout_seconds':10}))
                client=subprocess.Popen([str(CLIENT),'--config',str(config)],cwd=directory,env=env,stdout=clog,stderr=subprocess.STDOUT);processes.append(client);time.sleep(2)
                c=bridge=DesktopBridge(client,env['MOGOBE_UI_TEST_SECRET'])
                c.wait("window.mogobeLogin?.view==='single'",60)
                c.control('txtUserName');c.type_text('admin' if args.catalog or args.world_points else 'ShopNative')
                c.control('txtPassword');c.type_text('admin' if args.catalog or args.world_points else 'Shop1234')
                if args.catalog or args.world_points:time.sleep(5.1)
                c.control('btnLogin');c.wait("window.mogobeLogin?.view==='servers'");c.stage_click(384,140)
                c.wait("window.mogobeScene?.state==='world'",60)
                if args.world_points:
                    info="window.player.ruffle().callExternalInterface('getShopInfo')"
                    points="window.player.ruffle().callExternalInterface('getWorldShopPoints')"
                    c.chat_send('/shop admin1')
                    c.wait(info+"?.key==='admin1' && "+info+".items.length>0",40)
                    tab=c.js(info)['categories'][1]
                    c.stage_click(tab['hitX'],tab['hitY'])
                    c.wait(info+"?.selectedCategory==="+str(tab['id']),20)
                    before_first=c.js(info)['items'][0]['id']
                    c.control('btnNext')
                    c.wait(info+"?.items[0].id!=="+str(before_first),20)
                    c.wait(info+".items.every(i=>i.graphics>0)",25)
                    before=c.js(info);item=before['items'][0]
                    page=[i['id'] for i in before['items']]
                    c.stage_click(item['hitX'],item['hitY'])
                    c.wait(info+"?.tryOn!==null",20)
                    c.wait("window.player.ruffle().callExternalInterface('getLoginControlBounds','btnBuyItem')?.enabled===true",20)
                    c.control('btnBuyItem')
                    c.wait("fetch('/api/inventory').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId==="+str(item['id'])+"))",20)
                    c.wait(info+"?.items.some(i=>i.id==="+str(item['id'])+" && !i.available)",20)
                    c.control('btnConfirm');time.sleep(1)
                    after=c.js(info)
                    assert [i['id'] for i in after['items']]==page,(before,after)
                    assert after['selectedCategory']==tab['id'] and after['selectedItem']==item['id'],after
                    c.capture('world-shops/purchase-keeps-page-and-category')
                    c.control('btnNext')
                    c.wait(info+"?.items[0].id!=="+str(page[0]),20)
                    result['checks']['purchase_keeps_second_page_category_selection_and_pagination']=True
                    c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                    defaults=json.loads((ROOT/'assets/catalogs/world-shops.json').read_text(encoding='utf-8'))['shops']
                    if args.point_room:defaults=[row for row in defaults if row['key'] in args.point_room]
                    for row in defaults:
                        key=row['key']
                        c.chat_send('/room '+key)
                        c.wait("window.mogobeScene?.state==='world' && window.mogobeScene.room==="+json.dumps(key),45)
                        c.wait(points+".some(p=>p.id==="+json.dumps(row['point'])+")",30)
                        point=next(p for p in c.js(points) if p['id']==row['point'])
                        left,right,top,bottom=point['bounds']
                        state="window.player.ruffle().callExternalInterface('getWorldShopState')"
                        openings=c.js(state)['nativeOpenings']
                        windows=c.js(state)['windowsCreated']
                        avatar=c.js("window.player.ruffle().callExternalInterface('getWorldAvatar')")
                        assert c.js(info) is None,key
                        c.stage_click(avatar['x'],avatar['y'])
                        time.sleep(.25)
                        assert c.js(info) is None,('Shop opened away from original point',key)
                        c.stage_click((left+right)/2,(top+bottom)/2)
                        c.wait(info+"?.key==="+json.dumps(key)+" && "+info+".items.length>0",40)
                        reached=c.js(state)
                        assert reached['at']==row['point'] and reached['nativeOpenings']>openings,(key,reached)
                        assert c.js(info)['sourcePoint']==row['point'],key
                        assert reached['windowsCreated']==windows+1,('An extra empty window was created',key,reached,windows)
                        c.wait(info+".items.every(i=>i.graphics>0)",30)
                        assert c.js(info)['avatar']==(row['kind']=='clothing'),key
                        if row['kind']=='objects':
                            visible=c.js(info)['items'];first=visible[min(1,len(visible)-1)];c.stage_click(first['hitX'],first['hitY'])
                            c.wait(info+"?.preview?.width>0",30)
                            art=c.js(info)['preview'];assert art['width']<=120.1 and art['height']<=140.1,(key,art)
                        c.capture('world-shops/'+key)
                        result['checks']['original_point_opens_'+key]=True
                        c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                    c.chat_send('/room mall')
                    c.wait("window.mogobeScene?.room==='mall' && "+points+".length>0",40)
                    assert api.put(admin+'/native',json={'key':'native','title':'Новая привязка','kind':'clothing','points':['mall.mcShopPoint_1']}).status_code==200
                    c.wait(points+".some(p=>p.shop_key==='native')",20)
                    point=c.js(points)[0];l,r,t,b=point['bounds'];c.stage_click((l+r)/2,(t+b)/2)
                    c.wait(info+"?.key==='native'",30)
                    result['checks']['binding_changes_live_without_client_rebuild']=True
                    c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                    assert api.put('/api/admin/items/20',json={'id':20,'name':'Синяя футболка','main_type':1,'inventory_category':4}).status_code==200
                    c.chat_send('/give item 20')
                    c.wait("fetch('/api/inventory').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId===20))",20)
                    c.control('btnProfile')
                    profile="window.player.ruffle().callExternalInterface('getProfileInfo')"
                    inventory="window.player.ruffle().callExternalInterface('getInventoryInfo')"
                    c.wait(profile+"?.visible===true && "+profile+"?.popupId===7")
                    def inventory_tab(name):
                        button=c.js("window.player.ruffle().callExternalInterface('getProfileControlBounds',"+json.dumps(name)+")")
                        c.stage_click(button['x']+button['width']/2,button['y']+button['height']/2)
                    inventory_tab('mc_4_8_13_14_21')
                    c.wait(inventory+"?.cells.some(i=>i.typeId===20 && i.width>0)",30)
                    assert api.put('/api/admin/items/20',json={'id':20,'name':'Синяя футболка','main_type':1,'inventory_category':1}).status_code==200
                    c.wait(inventory+"?.cells.every(i=>i.typeId!==20)",25)
                    inventory_tab('mc_1')
                    c.wait(inventory+"?.cells.some(i=>i.typeId===20 && i.width>0)",30)
                    c.capture('world-shops/live-inventory-category')
                    cell=next(i for i in c.js(inventory)['cells'] if i['typeId']==20)
                    c.stage_click(cell['x']+cell['width']/2,cell['y']+cell['height']/2)
                    c.wait("fetch('/api/inventory/equipped').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId===20 && i.pCat===1))",20)
                    assert api.put('/api/admin/items/20',json={'id':20,'name':'Синяя футболка','main_type':1,'inventory_category':4}).status_code==200
                    c.wait("fetch('/api/inventory/equipped').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId===20 && i.pCat===4))",20)
                    c.wait("window.player.ruffle().callExternalInterface('getWorldAvatars').some(v=>v.clothing.some(i=>i.type==='mlIconSItem20'))",30)
                    result['checks']['owned_and_worn_item_moves_in_open_inventory_without_relogin']=True
                elif args.catalog:
                    info="window.player.ruffle().callExternalInterface('getShopInfo')"
                    c.chat_send('/shop admin1')
                    c.wait(info+"?.itemCount===1958 && "+info+"?.items.length>0",45)
                    c.wait(info+".items.every(i=>i.graphics>0)",30)
                    first=c.js(info)['items'];assert len(first)==8
                    assert c.js(info)["avatar"]
                    def hover(x,y):
                        r=json.loads(c.js("JSON.stringify(document.getElementById('stage').getBoundingClientRect().toJSON())"))
                        c.call('Input.dispatchMouseEvent',type='mouseMoved',x=r['x']+x*r['width']/768,y=r['y']+y*r['height']/480)
                    c.wait(info+".items.every(i=>i.priceVisible && i.priceText===String(i.price))",20)
                    item=c.js(info)['items'][0];assert item['price']==37
                    hover(item['priceX'],item['priceY'])
                    c.wait(info+".items.every(i=>i.priceVisible && i.priceText===String(i.price))",10)
                    time.sleep(.3)
                    assert c.js(info)['items'][0]['priceText']=='37'
                    c.capture('admin-catalog/price-hover')
                    result['checks']['price_remains_visible_on_real_pointer_hover']=True

                    c.stage_click(first[0]["hitX"],first[0]["hitY"])
                    c.wait(info+"?.tryOn==='mlBigItem16'",20)
                    result["checks"]["admin_clothing_uses_original_avatar_try_on"]=True
                    c.capture('admin-catalog/01-complete-catalog')
                    c.wait("window.player.ruffle().callExternalInterface('getLoginControlBounds','btnBuyItem')?.enabled===true")
                    c.control('btnBuyItem')
                    c.wait("fetch('/api/inventory').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId===16))",20)
                    c.control('btnConfirm')
                    c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                    c.control('btnProfile')
                    profile="window.player.ruffle().callExternalInterface('getProfileInfo')"
                    inventory="window.player.ruffle().callExternalInterface('getInventoryInfo')"
                    c.wait(profile+"?.visible===true && "+profile+"?.popupId===7")
                    button=c.js("window.player.ruffle().callExternalInterface('getProfileControlBounds','mc_3_7')")
                    c.stage_click(button['x']+button['width']/2,button['y']+button['height']/2)
                    c.wait(inventory+"?.cells.some(i=>i.typeId===16 && i.width>0)",30)
                    cell=next(i for i in c.js(inventory)['cells'] if i['typeId']==16)
                    c.stage_click(cell['x']+cell['width']/2,cell['y']+cell['height']/2)
                    c.wait("fetch('/api/inventory/equipped').then(r=>r.json()).then(x=>x.items.some(i=>i.typeId===16))",20)
                    c.wait("window.player.ruffle().callExternalInterface('getWorldAvatars').some(v=>v.clothing.some(i=>i.type==='mlIconSItem16'))",30)
                    c.capture('admin-catalog/purchased-hat-equipped')
                    for name, expected in [('mc_3_7',70),('mc_4_8_13_14_21',20),('mc_1',18),('mc_11',14),('mc_2_12_10_9_23',41),('mc_18_19',11),('mc_3_7',70)]:
                        button=c.js("window.player.ruffle().callExternalInterface('getProfileControlBounds',"+json.dumps(name)+")")
                        assert button,name
                        c.stage_click(button['x']+button['width']/2,button['y']+button['height']/2)
                        c.wait(inventory+"?.cells.length===1 && "+inventory+".cells[0].typeId==="+str(expected)+" && "+inventory+".cells[0].width>0",20)
                    c.capture('admin-catalog/inventory-categories')
                    result['checks']['all_six_original_inventory_categories_filter_owned_items']=True

                    button=c.js("window.player.ruffle().callExternalInterface('getProfileControlBounds','btnClose')")
                    c.stage_click(button['x']+button['width']/2,button['y']+button['height']/2)
                    result['checks']['admin_clothes_can_be_bought_and_worn_from_original_inventory']=True
                    c.chat_send('/shop admin1')
                    c.wait(info+"?.items.length>0 && "+info+".items.every(i=>i.graphics>0)",30)
                    c.control('btnNext')
                    c.wait(info+".items.every(i=>i.graphics>0) && "+info+".items[0].id!=="+str(first[0]["id"]),30)
                    c.capture('admin-catalog/02-next-page')
                    result['checks']['clothing_catalog_fits_gateway_and_original_shop_paginates']=True
                    c.js("window.shopErrors=[];for(const name of ['error','warn']){const saved=console[name];console[name]=(...args)=>{window.shopErrors.push(args.map(String).join(' '));saved(...args)}}")
                    tabs=c.js(info)['categories'];assert len(tabs)==8
                    assert max(t['hitY'] for t in tabs)-min(t['hitY'] for t in tabs)<1,tabs
                    for index, minimum in [(6,661),(7,2351)]:
                        c.stage_click(tabs[index]['hitX'],tabs[index]['hitY'])
                        c.wait(info+".items.length>0 && "+info+".items.every(i=>i.id>="+str(minimum)+" && i.graphics>0)",30)

                    for index in [0,1,0,6,2,7,0]:
                        tabs=c.js(info)['categories'];tab=tabs[index]
                        c.stage_click(tab['hitX'],tab['hitY'])
                        hover(100,80)
                        c.wait(info+".categories.every(t=>t.iconVisible) && "+info+".categoryScrollers===0",10)
                    tabs=c.js(info)['categories'];hover(tabs[0]['hitX'],tabs[0]['hitY'])
                    c.user32.mouse_event(0x0800,0,0,-120,0)
                    time.sleep(.3)
                    after=c.js(info)
                    assert after['categoryScrollers']==0 and after['categories']==tabs
                    result['checks']['category_icons_survive_selection_and_scrollbar_is_removed']=True
                    c.capture('admin-catalog/all-eight-categories')
                    result['checks']['all_eight_clothing_categories_fit_and_are_clickable']=True
                    for key, count in [('admin2',190),('admin3',308)]:
                        c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                        c.chat_send('/shop '+key)
                        c.wait(info+"?.key==='"+key+"' && "+info+"?.itemCount==="+str(count)+" && "+info+".items.length>0 && "+info+".items.every(i=>i.graphics>0)",45)
                        item=c.js(info)['items'][1]
                        c.stage_click(item['hitX'],item['hitY'])
                        c.wait(info+"?.preview?.width>0",30)
                        art=c.js(info)['preview']
                        assert abs(art['x']+art['width']/2-99.825)<.2 and abs(art['y']+art['height']/2-119.6)<.2,art
                        assert art['x']>=14 and art['y']>=20 and art['x']+art['width']<=186 and art['y']+art['height']<=220,art
                        c.capture('admin-catalog/'+key)
                    result['checks']['pets_and_home_open_separately_with_original_previews']=True
                    c.js("window.player.ruffle().callExternalInterface('closeOriginalShop')")
                    c.chat_send('/shop walking')
                    c.wait(info+"?.key==='walking' && "+info+".items.length===1 && "+info+".items[0].graphics>0",40)
                    item=c.js(info)['items'][0]
                    art=item['art']
                    assert abs(art['x']+art['width']/2-42.85)<.2 and abs(art['y']+art['height']/2-31.95)<.2,item
                    c.stage_click(item['hitX'],item['hitY'])
                    c.capture('admin-catalog/03-walking-only-original-shop')
                    result['checks']['walking_only_item_with_initial_empty_frame_renders_centered']=True
                else:
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
                        result['state']=bridge.js("JSON.stringify({errors:window.shopErrors,shop:window.player?.ruffle().callExternalInterface('getShopInfo'),scene:window.mogobeScene,notice:document.querySelector('#notice')?.textContent,resources:performance.getEntriesByType('resource').filter(r=>r.name.includes('Items/')).map(r=>r.name.split('?')[0])})")
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
