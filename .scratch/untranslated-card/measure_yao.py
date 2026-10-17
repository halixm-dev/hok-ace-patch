from pathlib import Path
import sys,json
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage
import qts_relocate
qts_relocate.install_btree_slot_map()
needle='你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。'
roots={'override':Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1'),'prime':Path('D:/scratch/hok-cycle/control/work/prime/1')}
rows=set()
for layer,root in roots.items():
 p=QtsPackage(root);slots=p.build_slot_map()
 for h in slots:
  raw=qts_relocate.read_raw(p,slots,h)
  if not raw or needle.encode() not in raw:continue
  for _,value,_ in adaptive.fields(raw):
   if not isinstance(value,bytes):continue
   fields=list(adaptive.fields(value));texts=[v.decode('utf-8') for _,v,_ in fields if isinstance(v,bytes)]
   if needle in texts:
    row=(f'{h:016X}',texts[0]);rows.add(row);print(layer,row)
Path('.scratch/untranslated-card/yao-identities.json').write_text(json.dumps(sorted(rows),indent=2),encoding='utf-8')
