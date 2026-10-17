"""Preserve original profile counter vectors in an independently instantiable SWF."""
import hashlib
import json
import struct
import zlib
from pathlib import Path

from build_loading_stub import build
from swf_room_data import SWF, records, rect

ROOT=Path(__file__).resolve().parents[1]


def tag(kind,block=b''):
    return struct.pack('<HI',(kind<<6)|63,len(block))+block


def main():
    source=ROOT/'assets/original/Swf/Assets/Popups/MyProfile.swf'
    swf=SWF(source)
    assert swf.defs[144][0]==83
    ident=max(swf.defs)+1
    name='MogobeProfileCounterArtwork'
    body=swf.header[:-2]+struct.pack('<H',1)+tag(69,struct.pack('<I',8))
    for kind,block,encoded in swf.tags:
        if kind in (2,6,7,10,11,14,20,21,22,32,33,34,35,36,37,39,46,48,60,61,62,73,75,83,84,87,88,90,91):
            body+=encoded
    # Keep shape 144 itself unchanged. The host masks each instantiation to
    # one original pictogram; no Graphics.copyFrom or rasterization is used.
    placement=bytes([6])+struct.pack('<HH',1,144)+b'\0'
    body+=tag(39,struct.pack('<HH',ident,1)+tag(26,placement)+tag(1)+tag(0))
    exports=[(ident,name),(138,'MogobeScoreIndicator')]
    for _,class_name in exports:
        stub=build(class_name)
        _,offset=rect(stub[8:])
        body+=b''.join(encoded for kind,_,encoded in records(stub[8+offset+4:]) if kind==82)
    body+=tag(76,struct.pack('<H',len(exports))+b''.join(struct.pack('<H',i)+n.encode()+b'\0' for i,n in exports))+tag(1)+tag(0)
    out=ROOT/'assets/compat/ProfileCounterIcons.swf'
    out.write_bytes(b'CWS'+bytes([swf.version])+struct.pack('<I',len(body)+8)+zlib.compress(body))
    out.with_suffix('.source.json').write_text(json.dumps({'original_game_asset':False,'original_graphics':True,'source':source.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'shape':144,'class':name,'generator':'tools/build_profile_counter_icons.py','sha256':hashlib.sha256(out.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Extracted original vector profile counter artwork.')


if __name__=='__main__':main()
