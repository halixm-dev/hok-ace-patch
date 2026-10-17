from pathlib import Path
import sys
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
import qts_relocate,terminology
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage
qts_relocate.install_btree_slot_map();terminology.install()
p=QtsPackage(Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1'));s=p.build_slot_map(); h=0xA07B2B9F994FB0ED
raw=qts_relocate.read_raw(p,s,h)
for lang in ('catalog','catalog_id'):
 c=adaptive.load_catalog(Path('resources')/lang)
 out,counts=adaptive.translate_table(raw,h,c)
 print(lang, type(out).__name__,counts)
 if out is not None:
  b=bytes(out)
  for value in (30,60):
   t=f'你的召唤单位阵亡时，会对周围敌人造成{{ResCardInfoDataBin_1771_17711_{0 if value==30 else 1}: {value}}}点物理伤害。每次召唤还会额外提升该伤害。'
   print(value,'source_in_catalog',t in c.unique,'remains_Chinese',t.encode() in b)
