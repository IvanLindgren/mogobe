'use strict';
const $=s=>document.querySelector(s), api='/api/admin', shopApi=api+'/shops';
let shops=[],items=[],assets=[],selected='',categories=[],offers=[],previewVersion=0;
function message(text,error=false){$('#message').textContent=text;$('#message').classList.toggle('error',error);}
async function request(path,method='GET',body){const r=await fetch(path,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(typeof d.detail==='string'?d.detail:'Проверьте заполнение полей ('+r.status+')');}return r.status===204?null:r.json();}
function formData(form){return Object.fromEntries(new FormData(form));}
function fill(form,data){for(const [k,v] of Object.entries(data)){const el=form.elements.namedItem(k);if(!el)continue;if(el.type==='checkbox')el.checked=!!v;else if(el.multiple){for(const o of el.options)o.selected=(v??[]).includes(o.value);}else el.value=v??'';}}
function option(select,value,text){const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);}
function row(parent,text,actions){const div=document.createElement('div');div.className='row';const span=document.createElement('span');span.textContent=text;div.append(span);for(const [label,action] of actions){const b=document.createElement('button');b.textContent=label;b.onclick=()=>run(action);div.append(b);}parent.append(div);}
async function run(action){try{await action();}catch(e){message(e.message,true);}}
async function reloadItems(){items=await request(api+'/items');$('#item-list').replaceChildren();const select=$('#offer-form').elements.item_id;select.replaceChildren();for(const i of items)option(select,i.id,i.id+' · '+i.name);renderAssets();}
async function reloadShops(){shops=await request(shopApi);$('#shop-list').replaceChildren();for(const shop of shops){const b=document.createElement('button');b.textContent=shop.key+' · '+shop.title+(shop.admin_only?' · админ':'')+(shop.enabled?'':' · закрыт');b.classList.toggle('selected',shop.key===selected);b.onclick=()=>run(()=>selectShop(shop.key));$('#shop-list').append(b);}}
async function selectShop(key){selected=key;const d=await request(shopApi+'/'+encodeURIComponent(key)+'/catalog');fill($('#shop-form'),d.shop);$('#shop-form').elements.key.readOnly=true;$('#catalog').hidden=false;$('#command').textContent='/shop '+key;categories=d.categories;offers=d.offers;$('#category-list').replaceChildren();const catSelect=$('#offer-form').elements.category_id;catSelect.replaceChildren();for(const c of categories){row($('#category-list'),c.name+' · ID '+c.id,[['Изменить',()=>{fill($('#category-form'),c);categoryPreview();}]]);option(catSelect,c.id,c.name);}$('#offer-list').replaceChildren();for(const o of offers){const i=items.find(i=>i.id===o.item_id);row($('#offer-list'),o.item_id+' · '+(i?.name??'')+' · '+o.price+' монет · '+o.experience+' опыта · остаток '+(o.stock??'∞')+(o.enabled?'':' · скрыт'),[['Изменить',()=>fill($('#offer-form'),o)],['Убрать',async()=>{await request(shopApi+'/'+key+'/offers/'+o.item_id,'DELETE');await selectShop(key);message('Предложение удалено');}]]);}await reloadShops();}
function newShop(){selected='';$('#shop-form').reset();$('#shop-form').elements.key.readOnly=false;$('#catalog').hidden=true;$('#command').textContent='Сначала сохраните магазин, затем добавьте категории и товары.';reloadShops().catch(e=>message(e.message,true));}
async function preview(id){const version=++previewVersion;$('#preview').replaceChildren();const asset=assets.find(a=>a.id===Number(id));$('#asset-info').textContent=asset?asset.category+'. '+(!asset.display?'Превью из Walking; полной анимации нет, надевание недоступно. ':asset.standing?'Есть изображение и анимации. ':'Есть изображение. ')+(asset.evidence==='placement-anchor'?'Слот определён по расположению графики; при необходимости уточните вручную.':'Разметка по оригинальной графике, исходное название не восстановлено.') : '';if(!asset)return;const player=RufflePlayer.newest().createPlayer();$('#preview').append(player);try{await player.ruffle().load({url:'/api/shop-assets/preview/'+id+'.swf',autoplay:'on',unmuteOverlay:'hidden'});if(version!==previewVersion)player.remove();}catch{if(version===previewVersion)message('Не удалось показать исходный SWF',true);}}
function itemFamily(item){return [1,3,4].includes(item.main_type)?'clothing':[6,7,8,9,10,11].includes(item.main_type)?'bumags':[2,5,12,13,14].includes(item.main_type)?'home':assets.find(a=>a.id===item.id)?.family;}
function renderAssets(){const q=$('#asset-search').value,family=$('#asset-family').value;$('#asset-list').replaceChildren();for(const a of assets.filter(a=>(!q||String(a.id).includes(q))&&(!family||itemFamily(items.find(i=>i.id===a.id)??{id:a.id})===family))){option($('#asset-list'),a.id,a.id+' · '+a.category+(a.standing?'':' · без полной анимации'));}renderItems();}
function renderItems(){const family=$('#asset-family').value;$('#item-list').replaceChildren();for(const i of items.filter(i=>!family||itemFamily(i)===family)){row($('#item-list'),i.id+' · '+i.name+(i.enabled?'':' · выключен'),[['Редактировать',()=>{fill($('#item-form'),i);preview(i.id);}]]);}}
let catalogReady=false;
async function loadCatalog(){
 if(catalogReady)return;
 assets=await request(api+'/assets');
 const icons=await request(api+'/items/category-icons');
 const points=await request(api+'/shop-points');
 const pointSelect=$('#shop-form').elements.points;pointSelect.replaceChildren();
 for(const p of points)option(pointSelect,p.id,p.room_title+' · '+p.name);
 const select=$('#category-form').elements.icon_id;select.replaceChildren();
 for(const icon of icons)option(select,icon.id,icon.name);
 categoryPreview();renderAssets();await reloadItems();await reloadShops();catalogReady=true;
}
async function reloadOverview(){
 const data=await request(api+'/overview');
 $('#server-name').textContent=data.server_name;
 for(const key of ['online','accounts','administrators','rooms','shops','items'])$('#summary-'+key).textContent=data[key];
}
async function start(){
 const user=await request(api+'/me');$('#identity').textContent=user.username;
 $('#login').hidden=true;$('#workspace').hidden=false;$('#logout').hidden=false;
 await reloadOverview();message('Админка готова');
}
$('#refresh-overview').onclick=()=>run(()=>reloadOverview());
$('#login').onsubmit=e=>{e.preventDefault();run(async()=>{await request(api+'/login','POST',formData(e.target));e.target.elements.password.value='';await start();});};
$('#logout').onclick=()=>run(async()=>{await request('/api/auth/logout','POST');location.reload();});
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=()=>run(async()=>{
 const tab=button.dataset.tab;
 for(const key of ['overview','shops','items','wallet','mogobes'])$('#'+key).hidden=key!==tab;
 for(const nav of document.querySelectorAll('[data-tab]')){nav.classList.toggle('selected',nav===button);if(nav===button)nav.setAttribute('aria-current','page');else nav.removeAttribute('aria-current');}
 if(tab==='shops'||tab==='items')await loadCatalog();
 if(tab==='mogobes')await reloadMogobes();
 if(tab==='overview')await reloadOverview();
 message('');
});
$('#new-shop').onclick=newShop;
$('#fill-admin-shop').onclick=()=>run(async()=>{
 const button=$('#fill-admin-shop');button.disabled=true;
 try {
  const result=await request(shopApi+'/admin/import-assets','POST');
  await reloadItems();await selectShop('admin1');
  message('Три админ-магазина: '+result.total_assets+' предметов. '+result.shops.map(s=>'/shop '+s.key+' — '+s.items).join('; ')+'. Добавлено: '+result.offers_created+', перенесено: '+result.offers_moved+'.');
 } finally {button.disabled=false;}
});
$('#shop-form').onsubmit=e=>{e.preventDefault();run(async()=>{const d=formData(e.target);d.enabled=e.target.elements.enabled.checked;d.admin_only=e.target.elements.admin_only.checked;d.room_key=d.room_key||null;d.points=[...e.target.elements.points.selectedOptions].map(o=>o.value);await request(shopApi+'/'+encodeURIComponent(d.key),'PUT',d);await selectShop(d.key);message('Магазин сохранён. Открытие: /shop '+d.key);});};
$('#item-form').onsubmit=e=>{e.preventDefault();run(async()=>{const d=formData(e.target);for(const k of ['id','main_type','inventory_category'])d[k]=Number(d[k]);d.enabled=e.target.elements.enabled.checked;await request(api+'/items/'+d.id,'PUT',d);await reloadItems();message('Предмет сохранён');});};
$('#category-form').onsubmit=e=>{e.preventDefault();run(async()=>{if(!selected)throw Error('Выберите магазин');const d=formData(e.target),id=d.id;delete d.id;d.icon_id=Number(d.icon_id);d.sort=Number(d.sort);d.inventory_category=d.inventory_category===''?null:Number(d.inventory_category);await request(shopApi+'/'+selected+'/categories'+(id?'/'+id:''),id?'PUT':'POST',d);e.target.reset();await selectShop(selected);message('Категория сохранена');});};
$('#offer-form').onsubmit=e=>{e.preventDefault();run(async()=>{const d=formData(e.target);for(const k of ['item_id','category_id','price','experience','sort'])d[k]=Number(d[k]);d.stock=d.stock===''?null:Number(d.stock);d.enabled=e.target.elements.enabled.checked;await request(shopApi+'/'+selected+'/offers/'+d.item_id,'PUT',d);await selectShop(selected);message('Ассортимент обновлён');});};
$('#wallet-form').onsubmit=e=>{e.preventDefault();run(async()=>{const d=formData(e.target);const r=await request(api+'/accounts/'+encodeURIComponent(d.username)+'/balance','POST',{coins:Number(d.coins)});message(r.username+': '+r.coins+' монет');});};
function categoryPreview(){$('#category-preview').src='/api/shop-assets/category-icons/'+$('#category-form').elements.icon_id.value+'.png';}
$('#category-form').elements.icon_id.onchange=categoryPreview;
$('#asset-search').oninput=renderAssets;
$('#asset-family').onchange=renderAssets;
$('#asset-list').onchange=()=>{const id=Number($('#asset-list').value),existing=items.find(i=>i.id===id);fill($('#item-form'),existing??{id,name:'Предмет '+id,main_type:'',inventory_category:1,enabled:true});run(()=>preview(id));};
start().catch(()=>message('Войдите аккаунтом администратора.'));

$('#category-form').addEventListener('reset',()=>setTimeout(()=>{$('#category-form').elements.id.value='';categoryPreview();},0));

let mogobesOffset=0;
async function reloadMogobes(){
 const q=$('#mogobes-search').elements.q.value;
 const data=await request(api+'/accounts?q='+encodeURIComponent(q)+'&offset='+mogobesOffset);
 $('#mogobes-total').textContent='Всего: '+data.total;
 $('#mogobes-prev').disabled=mogobesOffset===0;
 $('#mogobes-next').disabled=mogobesOffset+data.accounts.length>=data.total;
 $('#mogobes-list').replaceChildren();
 for(const a of data.accounts){row($('#mogobes-list'),a.username+' · ID '+a.id+' · уровень '+a.level+' · опыт '+a.score+' · '+a.coins+' монет'+(a.online?' · в игре':'')+(a.is_admin?' · администратор':''),[[a.is_admin?'Снять права':'Назначить администратором',async()=>{await request(api+'/accounts/'+a.id+'/admin','PUT',{is_admin:!a.is_admin});await reloadMogobes();message('Права обновлены: '+a.username);}]]);}
}
$('#mogobes-search').onsubmit=e=>{e.preventDefault();mogobesOffset=0;run(()=>reloadMogobes());};
$('#mogobes-prev').onclick=()=>{mogobesOffset=Math.max(0,mogobesOffset-50);run(()=>reloadMogobes());};
$('#mogobes-next').onclick=()=>{mogobesOffset+=50;run(()=>reloadMogobes());};

$('#fill-world-shops').onclick=()=>run(async()=>{const result=await request(api+'/shop-defaults','POST');await reloadShops();message('Созданы магазины: '+(result.shops_created.join(', ')||'все уже существуют'));});
