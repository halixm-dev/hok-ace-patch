"""Verify the measured Chano variants and Yao keyword through real text tables."""
from pathlib import Path
import gzip,json,sys
sys.path.insert(0,'tools');sys.path.append('resources/runtime')
import catalog_supplement,terminology,qts_relocate
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage
qts_relocate.install_btree_slot_map();terminology.install()
hits=json.loads(Path('.scratch/untranslated-card/hits.json').read_text(encoding='utf-8'))
source='你的英雄<a href=13><color=#ffffff>╦<b>合成</b></color></a>提升的等级+1。'
roots={'override':Path('dist/HOK ACE Patcher Data/pristine/20261016-101124/game/WXQ_Data/Package/builtin/1'),'prime':Path('D:/scratch/hok-cycle/control/work/prime/1')}
report={}
for language in ('catalog','catalog_id'):
 data=json.load(gzip.open(f'resources/{language}/catalog.json.gz'))
 code='id' if language=='catalog_id' else 'en'
 pairs=catalog_supplement.entries(data['unique'],code)
 assert not catalog_supplement.check(pairs)
 for zh in list(catalog_supplement.TEXTS)[:2]:
  assert zh not in data['unique'], 'baseline should lack the changed Chano descriptions'
 if code == 'en':
  assert '<b>upgraded</b>' in data['unique'][source], 'baseline should reproduce Yao'
 for zh in list(catalog_supplement.TEXTS)[:2]:
  assert adaptive.validate_translation(zh,pairs[zh])[0], (zh,adaptive.validate_translation(zh,pairs[zh]))
 terms=terminology.INDONESIAN_TERMS if code=='id' else terminology.ENGLISH_TERMS
 before=dict(data['unique']);changes=terminology.apply(data,terms)
 changed={zh:target for zh,target in data['unique'].items() if before[zh]!=target}
 assert not catalog_supplement.check(changed)
 assert not terminology.apply(data,terms)
 c=adaptive.load_catalog(Path('resources')/language)
 assert '<b>Combine</b>' in c.unique[source] and 'upgraded' not in c.unique[source]
 assert c.unique['同级物品可合成高一级物品']==before['同级物品可合成高一级物品']
 checked=0;occurrences=0;yao_tables=0
 for layer,root in roots.items():
  p=QtsPackage(root);slots=p.build_slot_map()
  for hit in hits:
   if hit['layer']!=layer or not hit['catalog_table']:continue
   h=int(hit['hash'],16);raw=qts_relocate.read_raw(p,slots,h)
   out,counts=adaptive.translate_table(raw,h,c)
   for zh in list(catalog_supplement.TEXTS)[:2]:
    if zh.encode() in raw:
     occurrences+=raw.count(zh.encode());assert zh.encode() not in out,(language,layer,hit['hash'])
   if source.encode() in raw:
    yao_tables+=1
    assert c.unique[source].encode() in out,(language,layer,hit['hash'],'Yao')
   checked+=1
 assert yao_tables > 0
 report[code]={'Yao_tables_checked':yao_tables,'tables_checked':checked,'updated_Chano_occurrences':occurrences,'Combine_targets_changed':changes['Combine'],'supplement_added':c.supplemented}
print(json.dumps(report,indent=2))
Path('.scratch/untranslated-card/verification.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
