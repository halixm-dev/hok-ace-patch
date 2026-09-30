# Panduan untuk AI agent: memperbaiki string yang belum terjemah (nama Chessplayer, tab faksi di menu Card, dll.)

Panduan ini ditulis dari pengalaman project `hok-ace-mobile-en-v1` (patcher bahasa Inggris untuk
王者万象棋 / HOK ACE, `com.tencent.tmgp.osgame`, Android, tanpa root). Pakai untuk project serupa:
game Unity + QtsVFS (Tencent) dengan patcher yang menulis terjemahan ke data game di HP.

Baca dulu `README.md` project. Semua klaim "tested" di bawah berasal dari uji di HP (Infinix X6853),
game versi 1.3.0.4 dan 1.4.0.1.

---

## 1. Model mental: kenapa string masih Mandarin

Data game Android punya **dua lapis**:

| Lapis | Lokasi | Isi |
|---|---|---|
| Prime (bawaan APK) | `assets/bin/Data/Package/builtin/<id>/` di dalam APK | Semua asset saat APK dibuild |
| Override (download) | `files/QtsVFSCache/packages/<id>/` (akses via `run-as`) | Hanya asset yang **berubah** sejak APK dibuild |

Game membaca override dulu, lalu fallback ke prime. Patcher lama hanya mengubah override, jadi
**asset yang hanya ada di APK tidak pernah tersentuh**. Di 1.3.0.4, 413 dari 497 tabel teks catalog
(loading tips, nama chessplayer, sebagian besar UI) dan semua 72 tekstur arena/map hanya ada di APK.

Penyebab lain string tetap Mandarin:
1. String ada di asset yang **tidak dicakup catalog PC** (bukan tabel bahasa) → pass `extra_text`.
2. String ada di **Unity prefab** (package 19) atau tabel definisi → sering *tidak aman* diubah (lihat §5).
3. String berasal dari **launcher**, bukan data game (mis. "正在初始化游戏", judul login) → tidak bisa dipatch lewat data.
4. Terjemahannya ada, tapi **terlalu panjang** untuk layout mobile (mis. tab "Chessplayer" menimpa
   "Combat Power") → itu masalah panjang teks, bukan string yang hilang.

---

## 2. Alur diagnosis (lakukan berurutan)

1. **Screenshot + catat string Mandarin persis** (minta user, atau `adb exec-out screencap -p > s.png`).
   Salin karakter aslinya, mis. `瑶妹`, `棋手`.
2. **Cari di catalog**: `resources/catalog/catalog.json.gz` → key `unique` adalah map Mandarin → Inggris resmi
   dari patcher PC. `table_hashes`/`schema` menunjukkan tabel mana yang dicakup.
   ```python
   import gzip, json
   cat = json.load(gzip.open("resources/catalog/catalog.json.gz"))
   print(cat["unique"].get("瑶妹"))   # -> "Yaria"
   ```
   Di Windows, set `PYTHONIOENCODING=utf-8` sebelum print CJK (cp1252 akan crash).
3. **Cari asset yang memuat string itu**, di kedua lapis:
   - override: dump dari HP (`run-as <pkg> tar -cf - -C files/QtsVFSCache packages`)
   - prime: ekstrak dari APK (`package_rebuild.extract_prime`)
   Baca tiap asset dengan `QtsPackage(...).build_slot_map()` + `extra_text.read_raw`, lalu cari
   bytes UTF-8 string tsb. Catat **package id** dan **file hash** (16 hex).
4. **Klasifikasikan** hasilnya:

| Temuan | Tindakan |
|---|---|
| Hash ada di `catalog.known`, asset hanya di prime | Tambahkan package ke `REBUILD_PACKAGES` (§3) |
| Hash ada di `catalog.known`, asset di override | Seharusnya sudah jalan; cek log stager (asset di-drop karena tidak muat slot?) |
| Bukan tabel catalog, protobuf teks tampilan | Tambahkan hash ke `DISPLAY_ASSETS` di `extra_text.py` setelah diuji (§4) |
| Unity prefab package 19 / tabel definisi | Lihat §5 — sudah terbukti crash/hang |
| Tidak ditemukan di data sama sekali | Kemungkinan launcher/native; laporkan tidak bisa dipatch |

---

## 3. Perbaikan utama: rebuild package penuh (ini yang memperbaiki nama Chessplayer)

Nama chessplayer di halaman Chessplayer (`瑶妹`→Yaria, `镜`→Jing, `乔汐`→Qiao Xi, `白歌`→Bai Ge, dst.)
ada di tabel teks package **1** yang hanya ada di APK. Solusinya: bangun ulang override package utuh.

Kode: `tools/package_rebuild.py`, `tools/qts_builder.py`, dipanggil dari
`build_device_patch.rebuild_prime_packages`.

Cara kerja:
1. `extract_prime(apk, REBUILD_PACKAGES, work/"prime")` — salin `.db` package dari APK.
2. Untuk tiap asset override: baca raw (dari override, atau dari prime jika entry override tanpa data),
   jalankan `transform` (tabel catalog → `adaptive.translate_table`, grafik → `mobile_graphics`,
   `SAFE_ASSETS` → `pb_text.rewrite`).
3. Tambahkan asset **prime-only yang berubah setelah diterjemahkan**. Prime-only yang tidak berubah
   jangan dimasukkan — game tetap membacanya dari APK.
4. Build dengan builder resmi Tencent: `QtsVFS.dll` + `QtskDB.dll` dari game PC
   (`WXQ_Data/Plugins/x86_64`, dibundel di `resources/qtsvfs/`). Format PC = Android (key entry & chunk
   hash diturunkan dari file hash + isi).
5. `qts_builder.finalize`: hapus record khusus builder (global-index node, export-setting/remain-dir),
   salin node `QTSF_PACKAGE` dan flag entry dari override asli.
6. **Read-back**: setiap asset dibaca ulang dan dibandingkan byte-per-byte; node package harus identik.
   Jangan pernah push ke HP jika read-back gagal.

Jebakan yang sudah ditemukan:
- `MaxStorageSize` **wajib** di-set (1 GiB). Kalau tidak, builder membaca memori sampah dan menulis
  satu file storage per asset.
- Flag kompresi packed = `level << 16 | type` (level default 5).
- Hanya rebuild package yang memang perlu (`REBUILD_PACKAGES = ("1", "1050016095")`). Package lain
  cukup in-place; rebuild berarti rekompresi ratusan MB.
- Package yang di-rebuild dilewati oleh stager in-place dan pass `extend` (`skip=rebuilt`).

Hasil di 1.3.0.4: package 1 = 684 asset (97 override diterjemahkan + 303 tabel baru dari APK);
package 1050016095 = 66 tekstur arena/map.

---

## 4. Asset non-catalog: `extra_text.py`

Untuk string yang tidak ada di tabel bahasa catalog tapi ada di asset protobuf tampilan:
- `pb_text.rewrite` mengganti string yang **persis** cocok dengan `catalog.unique` (+ `OFFICIAL_FIXES`).
- Nama lawan AI (`BOT_NAME_ASSETS`, ~11k nama) diromanisasi dengan `pypinyin` karena tidak ada terjemahan resmi.
- Hanya hash di `SAFE_ASSETS` yang diubah. **Allowlist, bukan blocklist**: mengganti semua string
  yang cocok di config lain merusak layar login karena sebagian string Mandarin adalah *lookup key*.
- Package `10` (label skill editor) dan `14` (script gameplay) dikecualikan: Mandarin di sana adalah logika.

Menambah asset baru ke `DISPLAY_ASSETS`: tambahkan **satu per satu** (atau set kecil), uji di HP
(loading sampai "Click to Enter Game", buka menu Card, lobby), lalu catat hasilnya di komentar —
termasuk yang gagal. Daftar yang sudah terbukti merusak ada di komentar `extra_text.py`:
- Loading macet 40–80%: newbie unlock rewards `41974B12`, salah satu tabel label kecil
  `8B5C2394/A07BC11B/4CEF98BE/63922EF4/7E3F57D7/3914DBBF/14DEEB2E`.
- Menu Card rusak (kartu abu-abu placeholder): hero role guide `DD11D75B/CA340C43/BBFD4BE9/CAC6E38D`.

---

## 5. Yang sudah dicoba dan GAGAL (jangan ulangi tanpa ide baru)

| Percobaan | Hasil |
|---|---|
| Ubah nama di definisi chessplayer `A8BC70BB87700709` field 37 | Lobby macet saat loading, bahkan setelah semua referensi di package 1 & 14 ikut diganti. Nama di halaman Chessplayer diperbaiki lewat tabel teks package 1 (§3), bukan lewat definisi ini. |
| Rewrite semua label prefab Unity package 19 (`UNITY_TEXT_PACKAGES = {"19"}`) | Lobby macet. |
| Rewrite **hanya nama faksi** di 15 prefab package 19 yang menampilkannya (tab faksi menu Card) | Crash saat start: `stack corruption detected`. Package 19 prefab sekarang dibiarkan. |
| Code injection ke APK | Dibunuh anti-cheat. |
| APK "prebaked" dengan asset terjemahan | `IsPrebuild errorCode:151`. |
| Memodifikasi paket bahasa di APK sebelum update | Updater Tencent memakai binary diff; diff rusak. |

### Tab faksi di menu Card
Status: **belum terselesaikan secara aman** lewat prefab. Langkah yang disarankan untuk agent berikutnya:
1. Cek dulu apakah nama faksi juga ada di **tabel teks catalog yang prime-only** di package 1. Kalau ya,
   rebuild §3 mungkin sudah menerjemahkannya — verifikasi di HP sebelum menyentuh prefab.
2. Kalau label hanya ada di prefab package 19, jangan rewrite serialized string-nya (panjang berubah →
   crash). Opsi yang belum dicoba: ganti dengan string **berpanjang byte sama/lebih pendek dengan padding**
   sehingga layout serialized tidak bergeser, atau cari apakah prefab mengambil teks dari key tabel
   (lalu terjemahkan tabelnya). Uji satu prefab dulu.
3. Kalau tidak ada cara aman, dokumentasikan sebagai known limit.

---

## 6. Alur uji di HP

1. Pastikan data game sudah update penuh sampai layar login (setelah update game: clear data,
   download ulang, lalu patch lagi).
2. Build patch offline dulu terhadap dump data (`python tools/build_device_patch.py --runtime resources/runtime
   --game <dump> --catalog resources/catalog --work <w> --output <o> --apk <apk> --builder resources/qtsvfs`).
   Butuh Python **3.12** (bytecode runtime `wxq_patch`).
3. Push ke `files/QtsVFSCache/packages/<id>/`, hapus `files/QtsVFSCache/Watchdog/*` (lihat `app/patcher_core.py`).
4. Buka game, cek `adb logcat` untuk error QtsVFS, screenshot layar login.
5. Setelah login (user harus pakai *Scan to login*; login WeChat/QQ langsung tidak jalan di APK re-sign):
   cek loading tips, halaman Chessplayer, lobby, menu Card, gambar arena.
6. Simpan backup `packages` + `Watchdog` sebelum push agar bisa rollback.

## 7. Aturan kerja

- Satu perubahan per uji; catat hasil (berhasil/gagal + gejala + tanggal) di komentar kode dekat hash-nya.
- Gunakan terjemahan resmi dari catalog PC; jangan menerjemahkan bebas kecuali tidak ada padanan
  (lalu masukkan ke `OFFICIAL_FIXES` dengan alasan).
- Jangan ubah panjang/struktur asset biner yang tidak dipahami; selalu read-back sebelum push.
- Jangan klaim "sudah terjemah" sebelum user melihatnya di HP setelah login.
