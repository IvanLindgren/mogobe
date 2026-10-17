"""Create a localization adaptation with numeric original experience levels."""
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=ROOT/'assets/original/servises/lang.xml'
    tree=ET.parse(source)
    section=tree.find('.//Section[@name="UserExperience"]')
    assert section is not None and len(section)==12
    for message in section:
        ident=int(message.get('id'))
        message.set('msg','Уровень: '+str(ident if ident else 12))
    out=ROOT/'assets/compat/lang-numeric-levels.xml'
    tree.write(out,encoding='utf-8',xml_declaration=True)
    out.with_suffix('.source.json').write_text(json.dumps({'original_game_asset':False,'source':source.relative_to(ROOT).as_posix(),'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'change':'Only UserExperience names become Уровень: 1–12','generator':'tools/build_numeric_levels.py','sha256':hashlib.sha256(out.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Created numeric level names; original localization unchanged.')

if __name__=='__main__':main()
