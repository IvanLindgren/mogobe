"""Measure original display graphics for centered, proportional SWF thumbnails.

Uses only the SWFs already in the repository. Does not modify original files.
"""
import json
from functools import lru_cache
from pathlib import Path

from swf_room_data import SWF, rect

ROOT = Path(__file__).resolve().parents[1]


def transformed(bounds, values):
    x1, x2, y1, y2 = bounds
    a, b, c, d, tx, ty = values
    points = [(a*x+c*y+tx, b*x+d*y+ty) for x in (x1,x2) for y in (y1,y2)]
    return [min(p[0] for p in points),max(p[0] for p in points),min(p[1] for p in points),max(p[1] for p in points)]


def measure(swf, ident):
    @lru_cache
    def bounds(ident):
        definition = swf.defs.get(ident)
        if definition is None:
            return None
        kind, block, _ = definition
        if kind in (2,22,32,83):
            return rect(block,2)[0]
        if kind != 39:
            return None
        children=[]
        for child in swf.children(ident):
            if child['id'] is not None:
                area=bounds(child['id'])
                if area is not None:
                    children.append(transformed(area,child['matrix']))
        if not children:
            return None
        return [min(b[0] for b in children),max(b[1] for b in children),min(b[2] for b in children),max(b[3] for b in children)]
    return bounds(ident)


def main():
    path=ROOT/'assets/catalogs/shop-graphics.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    missing=[]
    count=0
    for ident, roles in data.items():
        if 'Display' not in roles:
            continue
        info=roles['Display']
        swf=SWF(ROOT/f'assets/original/Swf/Items/Display/{ident}.swf')
        bounds=measure(swf,info['sprite_id'])
        if bounds is None:
            missing.append(ident)
            continue
        info['bounds']=[round(n,5) for n in transformed(bounds,info['matrix'])]
        count+=1
    path.write_text(json.dumps(data,indent=2)+'\n',encoding='utf-8')
    print(f'Measured {count} display graphics; unmeasured: {missing}')


if __name__=='__main__':main()
