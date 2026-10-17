"""Exercise reruns on old English output from real catalog text tables."""
from pathlib import Path
import gzip,json,sys
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage
import terminology,qts_relocate
qts_relocate.install_btree_slot_map();terminology.install()
base=json.load(gzip.open('resources/catalog/catalog.json.gz'))
old=adaptive.Catalog(base)
new=adaptive.load_catalog(Path('resources/catalog'))
ids=json.loads(Path('.scratch/untranslated-card/yao-identities.json').read_text())
p=QtsPackage(Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1'));slots=p.build_slot_map()
previous='Your Heroes gain +1 Level when <a href=13><color=#ffffff>╦<b>upgraded</b></color></a>.'
source='你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。'
current=new.unique[source]
checked=0
for asset in sorted({a for a,k in ids}):
 h=int(asset,16);raw=qts_relocate.read_raw(p,slots,h)
 patched,_=adaptive.translate_table(raw,h,old)
 assert patched.count(previous.encode())==2
 rerun,counts=adaptive.translate_table(patched,h,new)
 assert previous.encode() not in rerun, f'{asset}: rerun kept upgraded'
 assert rerun.count(current.encode())==2
 again,_=adaptive.translate_table(rerun,h,new);assert again==rerun
 # Exact table/key/value scope: a different key, asset or previous sentence must survive.
 for wrong_asset,wrong_key,value in [(h,'#OTHER#',previous),(0,'#'+dict(ids)[asset].strip('#')+'#',previous),(h,dict(ids)[asset],previous+' Extra')]:
  kb=wrong_key.encode();vb=value.encode();row=b'\x0a'+adaptive.encode_varint(len(kb))+kb+b'\x12'+adaptive.encode_varint(len(vb))+vb
  message=b'\x0a'+adaptive.encode_varint(len(row))+row
  result,_=adaptive.translate_table(message,wrong_asset,new);assert result==message
 checked+=1
print(f'PASS: {checked} old-English tables, {checked*2} exact Yao updates, rerun idempotence and wrong asset/key/text guards')
