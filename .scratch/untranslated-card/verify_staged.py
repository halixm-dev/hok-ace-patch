"""Read the two reported cards back from the staged English package."""
from pathlib import Path
import json,sys
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
import qts_relocate,terminology,catalog_supplement
from wxq_patch.qtsvfs import QtsPackage
from wxq_patch import adaptive
qts_relocate.install_btree_slot_map();terminology.install()
c=adaptive.load_catalog(Path('resources/catalog'))
root=Path('artifacts/chano-yao-fix/out')
s=json.loads((root/'device_patch_summary.json').read_text())
p=QtsPackage(root/'1');slots=p.build_slot_map()
source=QtsPackage(Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1')); ss=source.build_slot_map()
hits=json.loads(Path('.scratch/untranslated-card/hits.json').read_text(encoding='utf-8'))
occurrences=0;yao=0
ys='你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。'
for hit in hits:
 if hit['layer']!='override' or not hit['catalog_table']:continue
 h=int(hit['hash'],16);raw=qts_relocate.read_raw(source,ss,h);out=qts_relocate.read_raw(p,slots,h)
 assert out is not None,hit['hash']
 for zh in list(catalog_supplement.TEXTS)[:2]:
  if zh.encode() in raw:
   occurrences+=raw.count(zh.encode());assert c.unique[zh].encode() in out,hit['hash']; assert zh.encode() not in out
 if ys.encode() in raw:
  yao+=1;assert c.unique[ys].encode() in out,hit['hash']
assert occurrences==55 and yao>0
report={'Chano_occurrences_read_back':occurrences,'Yao_tables_read_back':yao,'counts':s['counts'],'text_skipped':s['text_skipped'],'append_skipped':s['append_skipped']}
print(json.dumps(report,indent=2))
Path('.scratch/untranslated-card/staged-verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
