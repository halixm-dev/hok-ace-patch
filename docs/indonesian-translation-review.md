# Indonesian Translation Review & Remediation Specification

**Document Version:** 1.0  
**Target File:** `resources/catalog_id/catalog.json.gz` (and runtime pipeline in `tools/languages.py`)  
**Scope:** Review of Indonesian patch translation consistency, gaming terminology, syntactic correctness, and actionable remediation guidelines for automated agent implementation.

---

## 1. Executive Summary & Core Directives

The Indonesian localization catalog (`resources/catalog_id/catalog.json.gz`) contains 39,011 string mappings. An evaluation of the catalog and the live staged game data (`dist/HOK ACE Patcher Data/final-catalog_id/out/1/1_0.db`) reveals that while ~1,069 reviewed strings are high quality, the remainder (~33,500 strings) suffered from unvetted machine translation (MT) with severe issues:
1. **Religious Scripture Hallucinations (P0):** 33+ skill and rule descriptions contain injected Quranic verses and Tafsir commentary.
2. **Context-Blind False Friends (P1):** Blatant literal translations such as `hibah` (grants), `pemutar` (player), `kulit` (skin), `kolam renang` (card pool), `wajik` (diamond), and `pembawa berita` (item wearer).
3. **Symbol Encoding Corruptions (P1):** Relational operators $\ge$ and $\le$ corrupted into `£`.
4. **Terminology Inconsistencies (P2):** `Damage` vs `Kerusakan`, `Chessplayer` vs `Chesplains` (typo), `Lineup Championship` vs `Lineup Juara`.

### Core Directives on Game Terminology
- **Keep in English (DO NOT translate):**
  - **`Deploy` / `Deployment`**: Standard auto-chess terminology for fielding chess pieces.
  - **`Combine` / `Combine Skill`**: Core game mechanic for fusing hero skills.
  - **`Level` / `Level Up` / `Lv.`**: Universal progression terms.
  - **`Hero`**, **`Skin`**, **`Skill`**, **`Passive`**, **`Ultimate`**.
  - **`Damage`**, **`Physical Attack`**, **`Magic Attack`**, **`Defense`**, **`Shield`**, **`Lifesteal`**, **`Spell Vamp`**, **`Crit`**.
  - **`Buff`**, **`Debuff`**, **`Stack`**, **`Stun`**, **`Knockup`**, **`Knockback`**, **`Stealth`**, **`True Damage`**.
  - **`Lineup`**, **`Tier`**, **`Reroll`**, **`Refresh`**, **`Shop`**.
  - **`Diamond`**, **`Token`**, **`Coupon`**.
- **Must be in Indonesian:**
  - **`Pemain`** (Never *pemutar*).
  - **`Ronde`** (Standard for game rounds).
  - **`Pengguna` / `Pemakai`** (For item wearer/bearer, never *pembawa berita*).
  - **`Memberikan` / `Memperoleh`** (For grants/gains, never *hibah* or *keuntungan*).

---

## 2. "Usage" vs "Use" Investigation & Resolution

### Chinese Source Analysis
In the original Chinese game data, the corresponding source word is almost exclusively **`使用`** (`shǐyòng`).
- In Chinese grammar, verbs do not inflect for tense or part-of-speech. `使用` functions as both the verb **"to use"** and the noun **"use / usage"**.
- In the upstream PC patcher pipeline, the English translator applied a rigid lemma mapping that translated `使用` systematically into capitalized **`Usage`** across 666 entries, even where it was clearly an imperative or infinitive verb:
  - `使用探宝秘钥` $\to$ Translated as `Usage Treasure Keys` (Grammatically should be *Use Treasure Keys*).
  - `对自身使用1张古币` $\to$ Translated as `Usage 1 Ancient Coin on yourself` (Grammatically should be *Use 1 Ancient Coin...*).
  - `可以使用换帅` $\to$ Translated as `you can Usage Change of Commander` (*you can use...*).
  - `不要忘记使用哦` $\to$ Translated as `Don't forget to Usage them!` (*Don't forget to use them!*).

### Indonesian Translation Rule for "Usage / Use"
When translating `使用` / `Usage` into Indonesian, the following grammatical rules **must be applied**:

1. **Imperative Verb / Action Instruction $\to$ `Gunakan`**
   - Chinese: `使用探宝秘钥开启宝藏`
   - Bad MT: `Usage Treasure Key...` / `Penggunaan Treasure Key...`
   - **Correct Indonesian:** `Gunakan Treasure Key untuk membuka treasure...`
   - Chinese: `对自身使用1张古币`
   - Bad MT: `Usage 1 Ancient Coin pada diri sendiri`
   - **Correct Indonesian:** `Gunakan 1 Ancient Coin pada diri sendiri`

2. **Active Verb with Auxiliary (`bisa`, `dapat`, `untuk`) $\to$ `menggunakan` / `memakai`**
   - Chinese: `可以使用这套阵容`
   - Bad MT: `kamu bisa Usage Lineup ini` / `kamu bisa Penggunaan Lineup ini`
   - **Correct Indonesian:** `Kamu bisa menggunakan Lineup ini...`

3. **Genuine Noun (`每次使用`, `使用次数`) $\to$ `penggunaan`**
   - Chinese: `每次使用此牌都会提升效果`
   - English: `Each Usage of this Card increases the Effect`
   - **Correct Indonesian:** `Setiap penggunaan Kartu ini meningkatkan efeknya...`

4. **Prohibition:**
   - **NEVER** leave raw English `Usage` inside an Indonesian sentence (e.g. `Tukar Kulit dan Penggunaan efek ini?` $\to$ `Ganti Skin dan gunakan efek ini?`).
   - **NEVER** use the noun `Penggunaan` as a verb (e.g. `Penggunaan Energy awal untuk dicapai Level 3` $\to$ `Gunakan Energy di awal untuk mencapai Level 3`).

---

## 3. Priority Remediation Categories

### Category P0: Religious Hallucinations (Critical Purge)
The upstream MT model hallucinated religious scripture (Tafsir Jalalayn / Indonesian Quran translations) when encountering complex formatting. These must be purged and replaced with proper game translations.

#### Key Hallucination Entries & Corrections:

1. **Sage's Sanctuary (Revive Item Passive)**
   - **CN:** `获得1张特殊装备贤者的庇护。可穿戴给【河洛】英雄，穿戴者会在首次被击败的2秒后复生，仅恢复30%生命值。`
   - **Current ID (Corrupted):** `Dapatkan 1 Special Equipment Sage's Sanctuary. Dapat dilengkapi dengan [Central Plains] Hero. Sesungguhnya neraka itu api murni yang bergejolak dan akan melepas kedua tangan, kaki dan seluruh sendimu dengan keras... Dibangkitkan 2 detik setelah sedang Dikalahkan...`
   - **Corrected ID:** `Dapatkan 1 Special Equipment <color=#ffffff><b>Sage's Sanctuary</b></color>. Bisa dipakaikan ke Hero [Central Plains]. Pengguna akan <a href=16><color=#ffffff>╧<b>Hidup Kembali</b></color></a> 2 detik setelah Dikalahkan untuk pertama kalinya, memulihkan 30% HP.`

2. **Energy Tower (Mage Skill)**
   - **CN:** `开局生成一个元气塔，初始攻击为<color=#00FF00>260</color>，法师每释放一个技能将会为元气塔充能...`
   - **Current ID (Corrupted):** `...menara kebakaran Energy Blast di kelompok musuh, pengedar Magic Damage (Kemudian apabila sangkakala ditiup sekali tiup) yaitu, untuk tiupan yang kedua kalinya, sebagai pemula untuk dijalankannya peradilan di antara semua makhluk. Attack dan terus pengisian.`
   - **Corrected ID:** `Di awal pertempuran, munculkan sebuah Energy Tower dengan <color=#00FF00>260</color> Initial Attack. Setiap kali Mage menggunakan Skill, menara terisi daya, meningkatkan Attack sebesar 15%. Setiap 5 detik, menara menembakkan Energy Blast ke kerumunan musuh terpadat, memberikan Magic Damage saat meledak, lalu mereset Attack-nya dan terus mengisi daya.`

3. **Fox Fire Ability**
   - **CN:** `施放5团狐火随机攻击范围内的敌人...`
   - **Current ID (Corrupted):** `Menyebabkan 5 kebakaran rubah secara acak Attack musuh dalam jangkauan... (Dan demi yang turun dari langit dengan cepat) yakni demi malaikat-malaikat yang melayang turun dari langit dengan membawa perintah-Nya. pertahanan magis oleh 3 sampai akhir ronde`
   - **Corrected ID:** `Menembakkan 5 Fox Fire secara acak ke musuh dalam jangkauan, memberikan Magic Damage sebesar <color=#d487e4>[109010p1q1]+[109010p1q2/100]% Magic Attack</color> dan mengurangi <color=#d487e4>Magic Defense sebesar 3</color> hingga akhir Ronde.`

4. **Transmute (Tier Transform)**
   - **CN:** `化铁为金：指定1名1-3阶的英雄随机变为不在场的5阶英雄，觉醒并保留其当前等级`
   - **Current ID (Corrupted):** `Transmutasi: Target 1 Tier 1-3 Hero untuk secara acak berubah menjadi off- field Tier 5 HeroMaka Allah swt. berfirman, Level`
   - **Corrected ID:** `Transmute: Pilih 1 Hero Tier 1-3 untuk secara acak berubah menjadi Hero Tier 5 di luar arena, meng-Awaken mereka dan mempertahankan Level mereka saat ini.`

5. **King of Kings Team Rules**
   - **CN:** `1、当王中王玩家选择了组队作战时，会出现王中王队伍；...`
   - **Current ID (Corrupted):** `1. Ketika King of Kings Player memilih untuk Team Up, a King of Kings Team (Maka dengan serta-merta mereka) yakni semua makhluk (bangun) berada di permukaan bumi dalam keadaan hidup, yang sebelumnya mereka berada di perut bumi dalam keadaan mati.`
   - **Corrected ID:** `1. Saat pemain King of Kings memilih untuk Team Up, Tim King of Kings akan muncul.`

6. **Defensive Armor Passive**
   - **CN:** `战斗开始后每5秒，穿戴者临时等级+30。`
   - **Current ID (Corrupted):** `...setiap 5 detik setelah Pertempuran dimulai(Dan orang-orang yang paling dahulu) dalam kebaikan, mereka adalah para nabi; ayat ini berkedudukan menjadi Mubtada (yaitu orang-orang yang paling dahulu) lafal ayat ini mengukuhkan makna ayat pertama... ═Temporary Level + 30.`
   - **Corrected ID:** `Setiap 5 detik setelah Battle dimulai, Temporary Level pengguna <color=#99DEB0>+30</color>.`

---

### Category P1: Context-Blind False Friends

| Bad Term | Count | Context | Correct Term | Example Fix |
| :--- | :---: | :--- | :--- | :--- |
| **`hibah`** | 40 | `grants` (rewards, intimacy, stats) | `memberikan` / `mendapatkan` | `"Setiap pertandingan ranked memberikan 6 Intimacy"` |
| **`pemutar`** | 24 | `player` | `pemain` | `"skor Penyelesaian untuk setiap Pemain"` |
| **`kulit`** | 22 | `skin` (hero/board cosmetics) | `Skin` | `"Gunakan Skin mereka dan papan pertandingan ini!"` |
| **`kolam renang`** | 12 | `pool` (card/hero/prize pool) | `Pool` / `kumpulan kartu` / `total hadiah` | `"<color=#90abddb2>telah kembali ke card pool</color>"` |
| **`wajik`** | 6 | `diamond` (currency in Diamond Rush) | `Diamond` | `"Tak cukup Diamond untuk ditambahkan"` |
| **`pembawa berita`** | 2 | `wearer` / `bearer` (item bearer) | `Pengguna` / `Pemakai` | `"Pengguna hidup kembali 2 detik setelah Dikalahkan"` |
| **`kebakaran rubah`** | 1 | `fox fire` (kitsunebi) | `Fox Fire` | `"Menembakkan 5 Fox Fire..."` |
| **`cairan darah mantra`** | 1 | `spell blood drain` (spell vamp) | `Spell Vamp` / `Magic Lifesteal` | `"20% Spell Vamp"` |
| **`ruang suai`** | 1 | `Custom Room` | `Custom Room` | `"Custom Room dikecualikan"` |
| **`mencangkul yang kuat`** | 1 | `hoeing the strong...` (锄强扶弱) | `menumpas yang lalim dan membela yang lemah` | Lore description idiom fix. |

---

### Category P2: Symbol Encoding & Terminology Normalization

1. **Character Encoding Restorations:**
   - In currency, rank, and intimacy conditions, replace corrupted `£` with `≥` or `≤`:
     - `£10 Coupons` $\to$ `≥10 Coupons`
     - `£500 Intimacy` $\to$ `≥500 Intimacy`
     - `£3000 Intimacy` $\to$ `≥3000 Intimacy`
     - `£1` (in `<= 1`) $\to$ `≤1`
   - Restore corrupted circled digits (`$1000` $\to$ `② 1000 Intimacy`).

2. **Normalize Combat Stats & Terms:**
   - **`Kerusakan` (168x in catalog, 1,027x in staged package):** Replace with **`Damage`** to unify with the 14,372 existing instances of `Damage`.
   - **`Serangan Fisik` (28x):** Standardize to **`Physical Attack`**.
   - **`Pertahanan Fisik / Magis`:** Standardize to **`Physical Defense`** / **`Magic Defense`**.
   - **Typo `Chesplains` / `Chessplains`:** Correct to **`Chessplayer`**.
   - **`Lineup Championship` vs `Lineup Juara`:** Standardize to **`Lineup Juara`** or **`Championship Lineup`**.
   - **Inverted Syntax:**
     - `General Seri` $\to$ `Seri General`
     - `Effect Card Seri` $\to$ `Seri Effect Card`
     - `Seri Grassakar` $\to$ `Seri Grassroots`

---

### Category P3: UI Layout & Length Considerations

Inspecting `artifacts/indonesian-lobby-20261005.png` revealed two layout overflows:
1. **Lobby Bottom-Right Button Wrap:**
   - Current: `"Chessplaye\nr"` (The English word `Chessplayer` wraps the letter 'r').
   - **Solution:** In UI button contexts, shorten the label to `"Pemain"` or `"Catur"`.
2. **Bottom-Left Badge Clipping:**
   - Current: `"Kesejahteraan"` is clipped vertically.
   - **Solution:** Shorten to `"Benefit"` or `"Hadiah"`.

---

## 4. Implementation Blueprint for Remediation Agent

When deploying an agent to perform the fix:

### Constraint Checklist (`AGENTS.md`)
- **Preserve Placeholder Integrity:** Do **NOT** remove or alter `{0}`, `{1}`, `%s`, `%d`, `{Energy}`, `{LordExp}`, `{LordHp}`. The game runtime's `translate_table` checks placeholder equality between source and target; mismatched placeholders cause the record to be rejected (`placeholders_changed`).
- **Token Handling:** Keep `{Energy}`, `{LordExp}`, and `{LordHp}` as literal brace tokens in `catalog.json.gz`. The runtime in `tools/resource_tokens.py` automatically expands them into `Energy`, `EXP Chessplayer`, and `HP Chessplayer`.
- **Target File:** Load `resources/catalog_id/catalog.json.gz`, modify the `unique` dictionary (and `reviewed_updates` / `english_updates` if tracking history), and write back with `gzip.open(..., "wt", encoding="utf-8")`.

### Remediation Script Skeleton
The deployed agent can run a script patterned as follows:

```python
import gzip
import json
import re

CATALOG_PATH = "resources/catalog_id/catalog.json.gz"

with gzip.open(CATALOG_PATH, "rt", encoding="utf-8") as f:
    catalog = json.load(f)

unique = catalog["unique"]

# 1. Apply Terminology Replacements
REPLACEMENTS = [
    (r"\bhibah\b", "memberikan"),
    (r"\bHibah\b", "Memberikan"),
    (r"\bpemutar\b", "pemain"),
    (r"\bPemutar\b", "Pemain"),
    (r"\bkolam renang\b", "card pool"),
    (r"\bwajik\b", "Diamond"),
    (r"\bKerusakan\b", "Damage"),
    (r"\bkerusakan\b", "damage"),
    (r"\bChessplains\b", "Chessplayer"),
    (r"\bChesplains\b", "Chessplayer"),
    (r"£(\d+)", r"≥\1"),
    (r"£\s*(\d+)", r"≥\1"),
]

for cn, tr in unique.items():
    # Only replace cosmetic kulit
    if "kulit" in tr.lower() and "grape" not in tr.lower():
        tr = re.sub(r"\bkulit\b", "Skin", tr)
        tr = re.sub(r"\bKulit\b", "Skin", tr)
    
    # Specific False Friends
    if "pembawa berita" in tr.lower():
        tr = tr.replace("Pembawa berita", "Pengguna").replace("pembawa berita", "pengguna")
    if "kebakaran rubah" in tr.lower():
        tr = tr.replace("kebakaran rubah", "Fox Fire")
    if "cairan darah mantra" in tr.lower():
        tr = tr.replace("cairan darah mantra", "Spell Vamp")

    for pat, rep in REPLACEMENTS:
        tr = re.sub(pat, rep, tr)
        
    unique[cn] = tr

# 2. Overwrite P0 Hallucinations with Curated Entries
# (Load from docs/indonesian-translation-review.md curated tables)

# 3. Save back to gzip
with gzip.open(CATALOG_PATH, "wt", encoding="utf-8") as f:
    json.dump(catalog, f, ensure_ascii=False, indent=2)

print("Indonesian catalog remediation complete.")
```
