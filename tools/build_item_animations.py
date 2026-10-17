"""Combine unchanged standing/walking timelines using JPEXS-remapped character IDs.

First run MergeItemAnimations.java on original/Swf/Items into a scratch directory,
then pass that directory as the sole argument. Java is an offline build tool only.
"""
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
from src.shops.swf_stub import build, tag

def records(raw):
    body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
    offset=(5+(body[0]>>3)*4+7)//8+4
    pos=offset
    while pos+2<=len(body):
        head=int.from_bytes(body[pos:pos+2],'little');pos+=2
        kind,size=head>>6,head&63
        if size==63:size=int.from_bytes(body[pos:pos+4],'little');pos+=4
        chunk=body[pos:pos+size];pos+=size
        yield kind,chunk
        if kind==0:break

def main():
    scratch=Path(sys.argv[1]);original=ROOT/'assets/original/Swf/Items'
    output=ROOT/'assets/compat/item-animations';output.mkdir(parents=True,exist_ok=True)
    metadata=json.loads((ROOT/'assets/catalogs/shop-graphics.json').read_text())
    manifest={}
    # Definition tags only: no root transforms or original scripts/root exports.
    kinds={2,22,32,83,39,46,34,6,21,35,36,20,90,87}
    for path in scratch.glob('*.swf'):
        ident=int(path.stem);info=metadata[str(ident)]
        a=(original/'InUse'/path.name).read_bytes();b=path.read_bytes()
        offset=int(path.with_suffix('.swf.offset').read_text())
        exports=[(info['InUse']['sprite_id'],f'mlIconSItem{ident}'),(info['Walking']['sprite_id']+offset,f'mlIconWItem{ident}')]
        body=b'\x08\x00'+struct.pack('<HH',15<<8,1)+tag(69,struct.pack('<I',8))
        body+=b''.join(tag(k,c) for raw in (a,b) for k,c in records(raw) if k in kinds)
        for _,name in exports:body+=b''.join(tag(k,c) for k,c in records(build(name)) if k==82)
        body+=tag(76,struct.pack('<H',2)+b''.join(struct.pack('<H',i)+n.encode()+b'\0' for i,n in exports))+tag(1)+tag(0)
        raw=b'CWS'+bytes([max(10,a[3],b[3])])+struct.pack('<I',len(body)+8)+zlib.compress(body)
        (output/path.name).write_bytes(raw)
        manifest[str(ident)]={'standing_sha256':hashlib.sha256(a).hexdigest(),'walking_sha256':hashlib.sha256((original/'Walking'/path.name).read_bytes()).hexdigest(),'sha256':hashlib.sha256(raw).hexdigest()}
    (output/'sources.json').write_text(json.dumps({'method':'Original timelines; JPEXS character remapping; AS3 export stubs','items':manifest},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Combined',len(manifest),'items')

if __name__=='__main__':main()
