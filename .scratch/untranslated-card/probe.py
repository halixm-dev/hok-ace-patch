from pathlib import Path
import sys,json
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
import qts_relocate, pb_text, terminology
from wxq_patch.qtsvfs import QtsPackage
from wxq_patch import adaptive
qts_relocate.install_btree_slot_map(); terminology.install()
cat=adaptive.load_catalog(Path('resources/catalog'))
roots={'override':Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1'),'prime':Path('D:/scratch/hok-cycle/control/work/prime/1')}
results=[]
needle='你的召唤单位阵亡'.encode()
for layer,root in roots.items():
 p=QtsPackage(root); slots=p.build_slot_map()
 for h in slots:
  raw=qts_relocate.read_raw(p,slots,h)
  if not raw or needle not in raw: continue
  text=raw.decode('utf-8','replace'); at=0
  snippets=[]
  while (at:=text.find('你的召唤单位阵亡',at))>=0:
   snippets.append(text[at:at+180]); at+=1
  record={'layer':layer,'package':'1','hash':f'{h:016X}','catalog_table':h in cat.known,'snippets':snippets}
  print(json.dumps(record,ensure_ascii=False),flush=True);results.append(record)
Path('.scratch/untranslated-card/hits.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
