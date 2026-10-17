"""Extract original inventory pictograms into independently masked SWF sprites.

Optional --png-strip is a JPEXS PNG export of MyProfile.swf shape 52; Pillow
creates the admin thumbnails and measures alpha bounds. Runtime uses vectors.
"""
import argparse
import hashlib
import json
import struct
import zlib
from pathlib import Path

from swf_room_data import SWF

ROOT=Path(__file__).resolve().parents[1]

def tag(kind,block=b''):
    return struct.pack('<HI',(kind<<6)|63,len(block))+block

def packed(bits):
    bits+='0'*(-len(bits)%8)
    return int(bits,2).to_bytes(len(bits)//8,'big')

def signed(value,n):
    return f'{value&((1<<n)-1):0{n}b}'

def rectangle(ident,area):
    x1,x2,y1,y2=[round(v*20) for v in area]
    n=max(abs(v).bit_length()+1 for v in (x1,x2,y1,y2))
    rect=packed(f'{n:05b}'+''.join(signed(v,n) for v in (x1,x2,y1,y2)))
    n=max(x1.bit_length()+1,y1.bit_length()+1,2)
    bits='000011'+f'{n:05b}'+signed(x1,n)+signed(y1,n)+'1'
    for delta,vertical in [(x2-x1,False),(y2-y1,True),(x1-x2,False),(y1-y2,True)]:
        n=max(2,abs(delta).bit_length()+1)
        bits+='11'+f'{n-2:04b}'+'0'+str(int(vertical))+signed(delta,n)
    bits+='000000'
    return tag(32,struct.pack('<H',ident)+rect+b'\x01\x00\x00\x00\x00\xff\x00\x10'+packed(bits))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--png-strip',type=Path);args=parser.parse_args()
    source=ROOT/'assets/original/Swf/Assets/Popups/MyProfile.swf';swf=SWF(source)
    body=swf.header[:-2]+struct.pack('<H',1)+tag(69,struct.pack('<I',8))
    for kind,block,encoded in swf.tags:
        if kind in (2,6,7,10,11,14,20,21,22,32,33,34,35,36,37,39,46,48,60,61,62,73,75,83,84,87,88,90,91):body+=encoded
    mapping=[(4,'Верх',1),(5,'Низ',2),(6,'Очки',5),(7,'Обувь',3),(8,'Головные уборы',0),(9,'Аксессуары',4),(10,'Украшения',4)]
    cuts=[0,32,67,102,137,172,205];icons=[]
    strip=None
    if args.png_strip:
        from PIL import Image
        strip=Image.open(args.png_strip).convert('RGBA')
    for ident,name,index in mapping:
        left,right=cuts[index:index+2];mask_id=500+ident;sprite_id=600+ident
        area=[left,right,0,28]
        body+=rectangle(mask_id,area)
        mask=bytes([70])+struct.pack('<HH',1,mask_id)+b'\0'+struct.pack('<H',2)
        art=bytes([6])+struct.pack('<HH',2,52)+b'\0'
        body+=tag(39,struct.pack('<HH',sprite_id,1)+tag(26,mask)+tag(26,art)+tag(1)+tag(0))
        bounds=[left,right,5.9,21.1]
        if strip:
            px1=max(0,round(left-6.05));px2=min(strip.width,round(right-6.05));crop=strip.crop((px1,0,px2,strip.height));box=crop.getbbox()
            bounds=[6.05+px1+box[0],6.05+px1+box[2],5.9+box[1],5.9+box[3]]
            crop=crop.crop(box);crop.thumbnail((32,28));png=Image.new('RGBA',(40,40));png.alpha_composite(crop,((40-crop.width)//2,(40-crop.height)//2))
            path=ROOT/f'assets/compat/shop-categories/{ident}.png';path.parent.mkdir(parents=True,exist_ok=True);png.save(path)
        icons.append({'id':ident,'name':name,'sprite_id':sprite_id,'bounds':bounds,'inventory_index':index,'clip':area})
    body+=tag(1)+tag(0)
    out=ROOT/'assets/compat/InventoryCategoryIcons.swf';out.write_bytes(b'CWS'+bytes([swf.version])+struct.pack('<I',len(body)+8)+zlib.compress(body))
    catalog={'source':'assets/compat/InventoryCategoryIcons.swf','source_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'original_source':source.relative_to(ROOT).as_posix(),'original_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'note':'Original mlClothBtns pictograms from MyProfile.swf shape 52, separated only by SWF masks.','generator':'tools/build_inventory_category_icons.py','icons':icons}
    (ROOT/'assets/catalogs/shop-categories.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    out.with_suffix('.source.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (ROOT/'assets/compat/shop-categories/source.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Extracted original inventory category icons with vector masks.')

if __name__=='__main__':main()
