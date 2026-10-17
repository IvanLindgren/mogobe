"""Measure the first visible frame of item animations lacking a Display SWF."""
import json
from pathlib import Path
from index_shop_graphics import measure, transformed
from swf_room_data import SWF, records, place

ROOT = Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'assets/catalogs/shop-graphics.json'
    data=json.loads(path.read_text())
    count=0
    for ident,roles in data.items():
        if 'Display' in roles:continue
        info=roles['Walking'];swf=SWF(ROOT/f'assets/original/Swf/Items/Walking/{ident}.swf')
        frames={};frame=1
        for kind,block,_ in records(swf.defs[info['sprite_id']][1][4:]):
            if kind==1:frame+=1
            if kind not in (26,70):continue
            item=place(kind,block)
            bounds=measure(swf,item['id']) if item and item['id'] else None
            if bounds:frames.setdefault(frame,[]).append(transformed(bounds,item['matrix']))
        if not frames:raise ValueError('No visible frame: '+ident)
        frame=min(frames);parts=frames[frame]
        bounds=[min(a[0] for a in parts),max(a[1] for a in parts),min(a[2] for a in parts),max(a[3] for a in parts)]
        info['preview_frame']=frame
        info['bounds']=[round(n,5) for n in transformed(bounds,info['matrix'])]
        count+=1
    path.write_text(json.dumps(data,indent=2)+'\n')
    print('Indexed',count,'walking previews')

if __name__=='__main__':main()
