"""Verify measured supplement pairs and read their actual staged package bytes."""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "tools"), str(ROOT / "resources/runtime")]
import catalog_supplement
from languages import for_catalog
from qts_relocate import install_btree_slot_map, read_raw
from resource_tokens import expand_resource_tokens
from terminology import install
from wxq_patch import adaptive
from wxq_patch.qtsvfs import QtsPackage


def rows(raw: bytes) -> dict[str, str]:
    """Decode the runtime's text-table rows without translating them again."""
    result = {}
    for _, nested, _ in adaptive.fields(raw):
        fields = {tag: value.decode("utf-8") for tag, value, _ in adaptive.fields(nested)}
        result[fields[10]] = fields[18]
    return result


install_btree_slot_map()
install()
record = Path(__file__).parent
before = json.loads((record / "leftovers.json").read_text(encoding="utf-8"))
pairs = json.loads((record / "translations.json").read_text(encoding="utf-8"))
source = Path(before["source"]) / "WXQ_Data/Package/builtin/1"
original = QtsPackage(source)
slots = original.build_slot_map()
report = {}
for code, folder, staged in (("en", "catalog", Path(sys.argv[1])), ("id", "catalog_id", Path(sys.argv[2]))):
    index = int(code == "id")
    # Validate every supplement entry, not just this update.
    for text, targets in catalog_supplement.TEXTS.items():
        valid, reason = adaptive.validate_translation(text, targets[index])
        assert valid, (code, text, reason)
    assert not catalog_supplement.check({s: p[index] for s, p in catalog_supplement.TEXTS.items()})
    for text, targets in pairs.items():
        assert catalog_supplement.TEXTS[text] == tuple(targets)
        # Formula expressions cannot lose numbers when wording changes.
        assert Counter(re.findall(r"\[[^\]]*\d[^\]]*\]", text)) == Counter(re.findall(r"\[[^\]]*\d[^\]]*\]", targets[index]))
    catalog = adaptive.load_catalog(ROOT / "resources" / folder)
    terms = for_catalog(ROOT / "resources" / folder).resource_terms
    output = QtsPackage(staged / "1")
    output_slots = output.build_slot_map()
    assets = sorted({int(asset, 16) for row in before["languages"][code]["strings"].values() for asset in row["tables"]})
    checked = Counter()
    for asset in assets:
        old = rows(read_raw(original, slots, asset))
        new = rows(read_raw(output, output_slots, asset))
        assert old.keys() == new.keys(), f"Row keys changed: {asset:016X}"
        for key, text in old.items():
            if text not in pairs:
                continue
            expected = expand_resource_tokens(catalog.lookup(asset, key, text), terms)
            assert new[key] == expected, (code, f"{asset:016X}", key, text, expected, new[key])
            assert not adaptive.CJK_RE.search(new[key]), (code, text)
            checked[text] += 1
    assert set(checked) == set(pairs)
    assert sum(checked.values()) == before["languages"][code]["rows"]
    report[code] = {"sources_read_back": len(checked), "rows_read_back": sum(checked.values()),
                    "tables_read_back": len(assets), "supplement_entries_validated": len(catalog_supplement.TEXTS),
                    "new_rows_remaining_chinese": 0}
    print(code, report[code], flush=True)
(record / "verification.json").write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
