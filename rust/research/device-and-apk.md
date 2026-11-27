# Device and APK plumbing in pure Rust

Research for the Rust migration (`rust/DECISIONS.md` ADR-005 pure Rust, ADR-016 thin Kotlin plugin,
ADR-017 Windows platform code in the core; `rust/MAP.md` open question on `adb.exe`). Researched
2026-11-27. Repo facts cite the file. External facts cite a primary source: AOSP, BoringSSL, docs.rs,
crates.io or a crate's own source. "Unmeasured" means nobody has run it against a phone yet.

`resources/key/` holds `cert.der`, `key.pk8` (a PKCS#8 DER private key, going by the extension and
`apk_tools.sign_v2`'s `load_der_private_key`) and `hok-ace-english.jks` (a Java keystore). I did not
read their contents.

---

## 1. Wireless-debugging pairing

### What the app does today

- `android/app/src/main/cpp/adb_pairing.cpp` (73 lines) is only the SPAKE2 step. It is ported from
  Shizuku and linked against `boringssl::crypto_static` (`CMakeLists.txt`). It creates
  `SPAKE2_CTX_new(spake2_role_alice, "adb pair client\0", "adb pair server\0")`. The names include
  their NUL because they are passed with `sizeof`. It then calls `SPAKE2_generate_msg` and
  `SPAKE2_process_msg`, and the key comes back as up to `SPAKE2_MAX_KEY_SIZE` bytes.
- Everything else is Kotlin in `android/app/src/main/java/dev/halixm/hokacepatcher/AdbPairing.kt`:
  TLS 1.3 through Conscrypt, the exporter, HKDF, AES-GCM and framing. `AdbKey.kt` holds the RSA-2048
  key as PKCS#8 and builds a self-signed X.509 certificate by hand-written DER. It also writes the
  524-byte ADB public key blob and signs AUTH tokens as raw RSA over SHA-1 DigestInfo padding.
  `AdbClient.kt` and `AdbProtocol.kt` hold the ADB wire client: CNXN, STLS, OPEN/WRTE/OKAY/CLSE and
  `shell:`. `AdbMdns.kt` handles discovery.

### The protocol, from primary sources

**TLS.** adbd's TLS layer pins the protocol to TLS 1.3 at both ends
(`SSL_CTX_set_min_proto_version`/`max_proto_version(TLS1_3_VERSION)`). It also requires a peer
certificate (`SSL_VERIFY_PEER | SSL_VERIFY_FAIL_IF_NO_PEER_CERT`). Source: AOSP
`packages/modules/adb/tls/tls_connection.cpp` lines 221-222 and 264
(https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/tls/tls_connection.cpp).
Both sides use self-signed certificates, so the client trusts any server certificate (`AdbKey.kt`,
`trustAll`).

**Exported keying material.** `SSL_export_keying_material(ssl, out, 64, "adb-label", sizeof("adb-label"), nullptr, 0, false)`
is called with a 10-byte label (the NUL is included) and no context (`tls_connection.cpp` lines 36
and 185-186). `kExportedKeySize = 64`
(`pairing_connection/pairing_connection.cpp` line 150). In TLS 1.3 an absent context and an empty
context produce the same exporter output (RFC 8446 §7.5, https://www.rfc-editor.org/rfc/rfc8446#section-7.5).

**SPAKE2 password.** `pswd = pairing code bytes ‖ 64 exported bytes`. The exported bytes are
appended to the password (`pairing_connection.cpp` lines 191-199; Kotlin `code.toByteArray() + exported`).

**SPAKE2 roles.** The client is alice and the server is bob. The names are `"adb pair client"` and
`"adb pair server"`, each passed with `sizeof`, which includes the NUL
(`pairing_auth/pairing_auth.cpp` lines 34-38 and 103-116).

**SPAKE2 itself, as BoringSSL implements it** (`crypto/curve25519/spake25519.cc`,
https://github.com/google/boringssl/blob/master/crypto/curve25519/spake25519.cc):

1. `password_hash = SHA-512(password)`, all 64 bytes, is kept for the transcript.
2. The password scalar `w` is `SHA-512(password)` reduced mod ℓ (`x25519_sc_reduce`). The code then
   applies the **password scalar hack**: it adds ℓ, 2ℓ and 4ℓ conditionally, in constant time, until
   the low 3 bits are zero. The result is ≤ 8ℓ−1 and `w ≡ 0 (mod 8)`. The flag
   `disable_password_scalar_hack` is off by default, and adbd never sets it.
3. M and N are hashed to the curve from seeds. The seeds are `"edwards25519 point generation seed (M)"`
   and `"edwards25519 point generation seed (N)"`; SHA-256 is repeated until a decode succeeds. The
   encodings are M = `5ada7e4bf6ddd9adb6626d32131c6b5c51a1e347a3478f53cfcf441b88eed12e` and N =
   `10e3df0ae37d8e7a99b5fe74b44672103dbddcbd06af680d71329a11693bc778`. Alice masks with M and
   unmasks with N; bob does the reverse.
4. The private scalar `x` is 64 random bytes reduced mod ℓ, then `left_shift_3` (×8, which clears
   the cofactor).
5. The message is `X* = x·B + w·M`, encoded as **exactly 32 bytes**, with no side byte. A peer
   message must also be 32 bytes and must decode to a point.
6. `K = x·(Y* − w·N)`, encoded as 32 bytes.
7. `key = SHA-512(len‖alice_name, len‖bob_name, len‖alice_msg, len‖bob_msg, len‖K, len‖password_hash)`,
   where each `len` is a **u64 little-endian** length prefix. The key is 64 bytes (truncated to the
   caller's buffer).

**Message framing.** The header is `{u8 version = 1, u8 type, u32 payload}`, packed, with the
payload size big-endian (`htonl`). The payload must satisfy `0 < size ≤ 16384`
(`kMaxPayloadSize = kMaxPeerInfoSize * 2`). The types are `SPAKE2_MSG = 0` and `PEER_INFO = 1`
(`pairing_connection.cpp` lines 41-51, 204-243). Each side writes its SPAKE2 message before reading
the peer's (`DoExchangeMsgs`, lines 300-330).

**Peer info.** `PeerInfo {u8 type; u8 data[8191]}` is exactly 8192 bytes. Type
`ADB_RSA_PUB_KEY = 0` carries the base64 ADB public key and its name; `ADB_DEVICE_GUID = 1`
(`pairing_connection/include/adb/pairing/pairing_connection.h` lines 40-50).

**Cipher.** AES-128-GCM. The key is `HKDF-SHA256(ikm = SPAKE2 key, salt = none, info = "adb pairing_auth aes-128-gcm key")`
with no NUL, because `sizeof(info) - 1` is passed. The key is 16 bytes and the tag is the default 16
bytes. The nonce is 12 bytes holding a per-direction u64 counter in host byte order (little-endian
on every target), starting at 0 (`pairing_auth/aes_128_gcm.cpp` lines 33-78). A wrong pairing code
surfaces as the peer info failing to authenticate. The Kotlin port matches all of this.

### Pure-Rust candidates

| Crate | BoringSSL-compatible? | Pure Rust? | Notes |
|---|---|---|---|
| `spake2` 0.4.0 / 0.5.0-pre.0 (RustCrypto PAKEs) | **No** | yes | The password goes through HKDF-SHA256 (info `"SPAKE2 pw"`, 48 bytes) instead of SHA-512 plus reduction. M and N are fixed constants from python-spake2 (M = `15cfd18e…`). Messages are **33 bytes**, with a side byte 0x41/0x42 that `finish` checks. The transcript is SHA-256 over six fixed 32-byte fields with SHA-256'd identities, so the key is **32 bytes**. No hook swaps the group constants or the hash. The docs say it is compatible with python-spake2, unaudited, and "probably not constant-time". Sources: https://docs.rs/spake2/latest/spake2/, https://github.com/RustCrypto/PAKEs/blob/master/spake2/src/ed25519.rs, `spake2/src/lib.rs` |
| `libadb` 0.9.0 (github.com/tarigo/libadb, MIT, first published 2026-08-11, 1088 downloads) | **Claims yes** | its SPAKE2 is; its TLS is **not** | `src/pairing/spake2.rs` says it implements "SPAKE2 as BoringSSL runs it on edwards25519, which is what adbd speaks". It includes the password scalar hack, `left_shift_3`, the u64-LE length-prefixed SHA-512 transcript and a 64-byte key, and states that it is "not RFC 9382, and not what the `spake2` crate implements". It is built on `curve25519-dalek` 4. The `pairing` feature pulls in `tls`, which is rustls 0.23 with the **`ring`** provider, and ring builds C and assembly. Pre-1.0. Sources: https://docs.rs/crate/libadb/latest/source/src/pairing/spake2.rs, `Cargo.toml.orig` on docs.rs, crates.io API |
| `adb_client` 4.0.0 (cocool97) | no pairing SPAKE2 in its manifest | **no** | Its USB support is `rusb` with `vendored` (libusb C), and its TLS is rustls with `ring`. Source: https://docs.rs/crate/adb_client/latest/source/Cargo.toml.orig |
| `adb-utils` 0.6.0 | has an `ADBPair` example | not checked | Its crypto stack is not documented. https://docs.rs/crate/adb-utils/0.6.0/source/examples/networking/pair.rs |

Non-Rust ports of the BoringSSL variant exist and can serve as cross-check references:
[spake2-java](https://github.com/flyfish233/spake2-java) and
[flutter_adb's Dart Spake2Context](https://pub.dev/documentation/flutter_adb/1.0.0/spake2/Spake2Context-class.html).
An Elixir `spake2` package on hex.pm notes that the BoringSSL variant does not interoperate with RFC 9382.

### TLS in pure Rust

- rustls has the RFC 5705 / TLS 1.3 exporter:
  `ConnectionCommon::export_keying_material(output, label: &[u8], context: Option<&[u8]>)`. It
  fails before the handshake completes and never uses the early exporter
  (https://docs.rs/rustls/latest/rustls/struct.ConnectionCommon.html, rustls 0.23.46). Call it with
  `label = b"adb-label\0"` and `context = None`.
- rustls's two built-in providers are `aws-lc-rs` (the default) and `ring`. Both build C and
  assembly, so neither is allowed under ADR-005. rustls supports a custom `CryptoProvider` and
  points to `provider-example/`, "a full client and server example that uses cryptography from the
  RustCrypto and dalek-cryptography projects"
  (https://docs.rs/rustls/latest/rustls/crypto/struct.CryptoProvider.html).
- `rustls-rustcrypto` 0.1.0-pre.0 is a ready-made pure-Rust provider with the TLS 1.3 AES-GCM and
  ChaCha suites. Its README says "USE THIS AT YOUR OWN RISK! DO NOT USE THIS IN PRODUCTION", and
  docs.rs failed to build that version (https://github.com/RustCrypto/rustls-rustcrypto,
  https://docs.rs/crate/rustls-rustcrypto/latest).
- TLS 1.3 client authentication with an RSA key signs CertificateVerify with **RSA-PSS**
  (`rsa_pss_rsae_sha256`), because TLS 1.3 forbids PKCS#1 v1.5 there (RFC 8446 §4.2.3). The provider
  therefore needs RSA-PSS signing through `rsa` 0.10. A custom `ServerCertVerifier` must accept
  adbd's self-signed certificate, the Rust counterpart of `trustAll`.

### What a port needs

1. **SPAKE2 (BoringSSL variant)** on `curve25519-dalek` 4 plus `sha2`, about 200 lines. Either port
   `spake25519.cc` directly or vendor `libadb`'s `src/pairing/spake2.rs` (MIT), recording the
   source in `android/native/THIRD_PARTY.md`. One trap: dalek 4's `Scalar` is always reduced mod ℓ,
   so it cannot hold the hacked `w` (up to 8ℓ). M and N are hashed points that may carry a torsion
   component, so `w·M ≠ (w mod ℓ)·M` in general. The fix is `w = 8t` with `t < ℓ`, giving
   `w·M = t·(8M)`. Likewise `x·Q = r·(8Q)` via `mul_by_cofactor`. Check M and N by re-deriving them
   from the seed strings in a test.
2. **TLS 1.3** through rustls with a pure-Rust provider. Write a small custom one following
   `provider-example`: x25519-dalek, aes-gcm, sha2, hkdf, and rsa 0.10 for PSS signing and
   PKCS#1/PSS verification. Alternatively adopt `rustls-rustcrypto` once it is out of pre-release.
   The same TLS stack serves the ADB connection after `STLS`.
3. **HKDF-SHA256 + AES-128-GCM** from the RustCrypto `hkdf` and `aes-gcm` crates, with the nonce
   counter described above.
4. **Key and certificate.** `rsa` 0.10 (PKCS#8 load and generate), a self-signed certificate built
   with `x509-cert` or hand-written DER as `AdbKey.kt` does, and the 524-byte ADB public-key blob
   (`len`, `n0inv`, modulus LE, `rr` LE, exponent) base64-encoded with a ` name` suffix.
5. **Verification before ADR-016's condition counts as met.** No crate's interoperability with adbd
   is proven by anything I could read. `libadb` claims it but shows no BoringSSL test vectors. Build
   a deterministic-RNG vector test comparing Rust alice and bob with the current
   `libhokace_adb.so`, or with spake2-java, then run a device cycle that pairs with a real phone's
   Wireless debugging. Only then delete the C++.

---

## 2. ADB on Windows

### Every `adb.exe` use

The host commands are in `app/adb_device.py`, which whitelists them in `_argv`. The callers are in
`patcher_core.py`, `apk_preparation.py`, `game_data_pull.py`, `device_transaction.py` and
`hok_patcher.py`.

| Host command | Used for |
|---|---|
| `start-server`, `devices` | Discovering phones (`patcher_core.py` lines 345 and 1030-1033; `hok_patcher.py` line 817) |
| `kill-server` | `Adb.kill_server` |
| `-s <serial> shell <cmd>` | Every device command below |
| `-s <serial> exec-out <cmd>` | Raw stdout. Streamed for the ~2 GB tar of the override layer with a 180 s stall watchdog (`exec_out_stream`); written to a file for the Watchdog tar (`exec_out_to_file`); read whole for the sha256 list |
| `-s <serial> pull <remote> <local>` | The installed APK, ~2 GB (`installed_identity`, `prepare_normal_apk`) |
| `-s <serial> push <local> <remote>` | Uploads to `/data/local/tmp/hokace/<session>/…` (`device_transaction.py` line 179) |
| `-s <serial> install -r <apk>` | `Adb.install`, verified afterwards by re-reading the identity |
| `-s <serial> uninstall <pkg>` | The signer conversion (`apk_preparation.py` line 158) |
| `reconnect`, `get-state`, `get-serialno`, `wait-for-device` | Whitelisted, but no caller uses them |

The device shell commands are:

- `am get-current-user` and `am force-stop com.tencent.tmgp.osgame`
- `pm list packages --user 0 <pkg>` and `pm path <pkg>`
- `sha256sum '<apk>'`
- `getprop ro.product.brand`, `ro.product.model` and `ro.build.version.release`
- `run-as <pkg> cat files/QtsVFSCache/packages/1/1.info`
- `run-as <pkg> tar -cf - -C files/QtsVFSCache packages Watchdog` (and per-batch and Watchdog-only variants)
- `run-as <pkg> sh -c 'cd files/QtsVFSCache/packages && find . -type f -exec sha256sum {} +'`
- the transaction scripts (`run-as <pkg> sh -c <script>`)
- `mkdir -p`, `chmod` and `rm -f` under `/data/local/tmp/hokace`

### Speaking ADB directly

**Wire protocol** (AOSP `docs/dev/protocol.md`,
https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/docs/dev/protocol.md;
`adb.h`):

- The header is 6 little-endian u32s: `command, arg0, arg1, data_length, data_crc32, magic = command ^ 0xffffffff`.
- `A_VERSION = 0x01000001` is `A_VERSION_SKIP_CHECKSUM`: from that version on, the checksum (a byte
  sum, despite the field name) is not checked.
- `MAX_PAYLOAD` is 1 MiB, or 4 KiB for v1. CNXN and AUTH sent to a device must stay within 4096 bytes.
- Authentication: AUTH TOKEN(1) carries a 20-byte token. The client answers SIGNATURE(2), which is
  RSA PKCS#1 v1.5 over the token treated as a SHA-1 digest, or RSAPUBLICKEY(3), which triggers the
  phone's "Allow USB debugging?" prompt.
- Data then flows as OPEN/OKAY/WRTE/CLSE streams. Wireless debugging answers CNXN with STLS.

**Services a port needs:**

- `shell:` or `exec:` for shell and exec-out. `exec:` is raw and has no PTY, which the tar stream
  needs.
- `sync:` for push and pull, using `STAT`/`STA2`, `SEND`/`SND2`, `RECV`/`RCV2`, `DATA` and `DONE`,
  with `SYNC_DATA_MAX` = 64 KiB (`file_sync_protocol.h`).
- Install. Modern `adb install` streams `exec:cmd package install -S <size> -r` (or `package` over
  `abb_exec`) instead of pushing first (`client/adb_install.cpp` lines 161-224). Uninstall uses
  `cmd package uninstall`.
- The `devices` list, which is the USB enumeration itself.

**USB in pure Rust.** `rusb` and libusb are C and so excluded, and `adb_client`'s USB support goes
through them. **`nusb` 0.2.9** is pure Rust. On Windows it uses WinUSB, and "your device or
interface must be associated with the `WinUSB` driver" (https://docs.rs/nusb/latest/nusb/). For a
composite device it finds the usbccgp child, checks that `DEVPKEY_Device_Service` equals `winusb`
(case-insensitive), and reads the interface GUID from the `DeviceInterfaceGUIDs` /
`DeviceInterfaceGUID` registry value
(https://github.com/kevinmehall/nusb/blob/main/src/platform/windows_winusb/enumeration.rs).

adbd advertises a Microsoft OS descriptor with compatible ID `WINUSB` and
`DeviceInterfaceGUID = {F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}`
(`daemon/usb_ffs.cpp` lines 86-89 and 205-210,
https://android.googlesource.com/platform/packages/modules/adb/+/refs/heads/main/daemon/usb_ffs.cpp).
Windows therefore binds WinUSB to the ADB interface on its own, and nusb can open it.

**Where adb.exe still wins.** `adb.exe` goes through `AdbWinApi.dll` (`client/usb_windows.cpp`),
which also speaks to legacy, non-WinUSB ADB drivers. An OEM driver bound in place of WinUSB, or the
Universal ADB Driver if it installs a non-WinUSB service, would be invisible to nusb. I could not
confirm from a primary source whether the Universal ADB Driver binds WinUSB (unmeasured). The
Windows ADB client also sends a zero-length packet when a write is a multiple of the max packet size
(`usb_windows.cpp` lines 366-370), and a port must do the same.

`libadb` 0.9.0 has an `nusb` feature (nusb 0.1), plus `keys` and the shell, exec, sync and cmd
services, with no TLS needed for USB, so that feature set may avoid `ring`. Its `keys` feature uses
`rsa` 0.9, which is affected by RUSTSEC-2023-0071 (see §3). It is a candidate to evaluate or
vendor, not a proven one.

### Trade-off

| | Keep `adb.exe` | Native Rust protocol over nusb |
|---|---|---|
| Driver coverage | Every driver AdbWinApi supports | WinUSB-bound interfaces only, which covers adbd's default via MS OS descriptors |
| Phone trust | Uses `%USERPROFILE%\.android\adbkey`, which phones already trust | Needs its own key, so one new "Allow USB debugging?" prompt per phone (reading the user's adbkey is a privacy line not worth crossing) |
| Conflicts | Shares the adb server with Android Studio and other tools | WinUSB opens are exclusive, so it fails while any adb server holds the device; must `kill-server` or tell the user |
| Shipping | Ships `adb.exe` + `AdbWinApi.dll` + `AdbWinUsbApi.dll` (`resources/adb`, copied into `<work>\adb` so the server never locks the PyInstaller temp folder) | No binaries, no background server, no subprocess output parsing |
| Code reuse | Separate from Android | The same ADB client the Android core needs anyway after ADR-016 (TCP + STLS); only the transport differs |
| Risk | Proven over every past device cycle | New: throughput on 2 GB pulls, ZLP, flow control and install streaming each need a device cycle |

---

## 3. APK handling

### What the Python does

- **`app/apk_tools.rewrite_apk`**
  - Copies every entry **in source order**.
  - **Drops v1 signature files**: `META-INF/*.RSA|.DSA|.EC|.SF|.MF`, so `MANIFEST.MF` goes too.
  - Replaces `AndroidManifest.xml`. `apk_preparation.build_signed` refuses any other replacement.
  - **Decompresses and re-deflates every entry** through CPython's `zipfile`, because
    `src.open(item)` and then `out.open(info, "w")` is not a raw copy. The level is zlib's default.
  - Clears every entry's extra field.
  - Gives each stored entry a `0xD935` extra of `4 + pad` bytes (pad 0-3) so its data starts
    4-aligned. The extra is present even when pad is 0.
  - Raises `zipfile.ZIP64_LIMIT` to `0xFFFFFFFE` so that no ZIP64 records are written for the ~2 GiB
    APK.
- **`apk_tools.sign_v2`**
  - Writes an APK Signing Block with a **v2 block only** (ID `0x7109871A`), one signer, one
    certificate, **no additional attributes**, and algorithm `0x0103` (RSASSA-PKCS1-v1_5 SHA-256).
  - Digests 1 MiB chunks with `0xa5` prefixes and a `0x5a` top-level digest, substituting the
    central directory offset in the EOCD.
  - Adds **no verity padding**.
  - Replaces an existing signing block if present and rewrites the EOCD's central directory offset.
  - The RSA step is injectable (`rsa_signer`). Android passes Java's `Signature` through Chaquopy
    (`android/app/src/main/python/android_bridge.py` `sign_with_java`); Windows uses `cryptography`
    with `key.pk8`.
- **`apk_tools.apk_identity`** reads the following:
  - size and SHA-256;
  - `package` and `versionCode` from the manifest's `<manifest>` attributes;
  - the debuggable flag;
  - the signers: SHA-256 of the v2 certificates, which are authoritative, or else of the
    certificates in the v1 PKCS#7 `META-INF/*.RSA|DSA|EC` files, parsed with `cryptography`'s
    `load_der_pkcs7_certificates`.

  It refuses duplicate entries, a manifest outside 8 B to 8 MiB, and a signing block over 16 MiB.
  `signed_with` searches for the certificate bytes.
- **`tools/axml_set_debuggable.patch`**
  - Parses and rebuilds the string pool (UTF-8 or UTF-16; a pool with styles is refused).
  - Inserts `"debuggable"` at the end of the resource-map prefix with id `0x0101000F` when it is
    missing, and shifts **every** string index ≥ the insert point in every node: comment, namespace
    prefix and uri, element ns and name, attribute ns, name and raw value, typed string data, and
    CDATA.
  - Sets each attribute that carries the debuggable id to `TYPE_INT_BOOLEAN` `0xFFFFFFFF` or `0`
    with no raw value.
  - Sorts `<application>`'s attributes by resource id and recomputes the 1-based
    `idIndex`/`classIndex`/`styleIndex`.
  - It is idempotent, and `is_debuggable(m)` is `patch(m, True) == m`.
- **`tools/axml_label.set_label`** appends `"Honor of Kings: ACE"` to the string pool, so no indices
  shift. It rewrites `android:label` (id `0x01010001`) on `<application>`, and on any component
  sharing the same `TYPE_REFERENCE`, to `TYPE_STRING`. It leaves `resources.arsc` untouched and is
  idempotent.
- **`app/apk_preparation.py`** pulls the installed APK and checks identity before and after. It then
  builds the *normal* APK (debug flag cleared, label set, re-signed) and the *access* APK (debug flag
  set, from the normal APK), installs and verifies each by identity, and uninstalls once for the
  signer conversion.
- **No v3 or lineage for the game APK.** The v3 lineage (`android/signing/patcher.lineage`, `apksigner
  rotate`, `tools/ci/sign_android.ps1`, v3 only) applies to the **patcher app's own** release
  signing in CI (`docs/lab-notebook.md`, 2026-10-18). It stays an `apksigner` CI step and is out of
  scope for the core.

### Crates

| Need | Crate | Verdict |
|---|---|---|
| Zip read | `zip` 9.8.2 | Fine with `default-features = false`. The defaults pull **zstd 0.14 (C, `zstd-sys`)** and bzip2. For deflate, pick `deflate-flate2-zlib-rs` (zlib-rs, Rust) or `flate2/rust_backend` (miniz_oxide). Source: https://docs.rs/crate/zip/latest/features and the crate's `Cargo.toml`. It has `raw_copy_file` (copies compressed bytes without re-deflating) and `with_alignment` |
| Zip write with Python's exact layout | **write it ourselves** (~200 lines) | `zip`'s alignment pads to at least 6 bytes in its own `0xD935`/`0xA11E` format (`src/write.rs` lines 3277-3320; `extra_fields/data_stream_alignment.rs`), which differs from `_align`'s 4+pad bytes. It also switches to ZIP64 at `u32::MAX` (`format/mod.rs` line 81). A hand-written local header + CD + EOCD writer controls every byte |
| v2 signing | **write it ourselves** (~150 lines, as `sign_v2` is) | `apksig` 0.4.0 (https://docs.rs/crate/apksig/latest/source/src/apk.rs) has `sign_v2(algo, cert, rsa::RsaPrivateKey)`. It writes a block via `SigningBlock::new_with_padding` (a different layout), has 16k downloads, and rejects v3. Use it only as an independent test-time cross-check alongside SDK `apksigner verify` |
| RSA PKCS#1 v1.5 SHA-256, PKCS#8 | `rsa` **0.10.0** (2026-11-08) + `sha2` + `pkcs8` | RUSTSEC-2023-0071 / CVE-2023-49092 (Marvin, non-constant-time) is patched in `>=0.10.0` by the move to `crypto-bigint` (https://rustsec.org/advisories/RUSTSEC-2023-0071.html). Pin 0.10. The signing here is local and offline, but `cargo audit` would flag 0.9, and the pairing and ADB auth use the same crate |
| PKCS#7 certificates from v1 `.RSA` | `cms` + `x509-cert` (RustCrypto) | Only `apk_identity` needs it, to read the game's own v1 signers when it has no v2 block |
| AXML | **port the 350 Python lines** | `axmldecoder` 0.5.0 (2023) and `rusty-axml` decode only. `abxml` is a full decoder. `resand` 0.3.0 reads and writes ARSC/AXML but is young. The edits here need byte-exact rebuilds, so a direct port is the right tool. Sources: https://docs.rs/crate/axmldecoder/latest, https://docs.rs/crate/resand/0.3.0, https://github.com/gnieto/abxml-rs |
| SHA-256 / SHA-1 | `sha2`, `sha1` (RustCrypto) | — |

---

## 4. Traps

**Zip and APK**

1. **Re-deflation.** Python re-deflates every compressed entry through CPython's zlib. A Rust port
   matches its bytes only if its deflate is byte-identical to that zlib at level 6. zlib-rs claims
   API compatibility, not identical output (https://github.com/trifectatechfoundation/zlib-rs). This
   is unmeasured. ADR-010 ("everything else stays byte for byte") then bites: either match it, or
   raw-copy the compressed bytes (`raw_copy_file`-style). Raw copying skips 2 GiB of inflate and
   deflate and makes unchanged entries byte-identical to the game's own APK, but its output differs
   from Python's.
2. **Entry order and metadata.** Keep source order. Mirror what `copy.copy(ZipInfo)` plus
   `zipfile._open_to_write` emit: date/time, create_system/version, external attributes,
   `flag_bits` reset (no data descriptor on a seekable file), the UTF-8 flag for non-ASCII names,
   and the same extra in the local header and the CD. Duplicate names must stay refused.
3. **Alignment.**
   - Today stored entries are aligned to 4 bytes with Python's own `0xD935` shape, not zipalign's.
     Keep 4 and the exact shape for parity.
   - Uncompressed `.so` files need page alignment (4 KiB, or 16 KiB for 16 KB-page devices) when
     `extractNativeLibs="false"`. The Python never does this. It works today, so the game evidently
     extracts its libraries, but a Rust port should *check* the manifest flag and refuse rather than
     silently misalign.
   - `resources.arsc` must stay stored and 4-aligned for targetSdk ≥ 30.
4. **No ZIP64.** The platform verifier throws "ZIP64 APK not supported" when a ZIP64 EOCD locator is
   present (`ApkUtilsLite.java` lines 75-76,
   https://android.googlesource.com/platform/tools/apksig/+/refs/heads/main/src/main/java/com/android/apksig/apk/ApkUtilsLite.java).
   Use 32-bit fields up to `0xFFFFFFFE` and refuse anything larger.
5. **Signing block layout.** It must sit immediately before the CD: u64 size, then the pairs, then
   the same u64 size and `"APK Sig Block 42"`. The EOCD's CD offset is substituted while hashing and
   rewritten after (https://source.android.com/docs/security/features/apksigning/v2).
   - Verity padding (block id `0x42726577`, which page-aligns the block) is something apksigner adds
     and `apksig`'s `new_with_padding` likely does. Python does not, so adding it changes the bytes.
   - Strip an existing block before hashing. The Python finds it from the 24-byte footer before the
     CD.
6. **v1 off.** Dropping all of `META-INF/*.SF/.MF/.RSA` is deliberate: minSdk ≥ 24 makes v2
   sufficient. If v1 were kept alongside v2, its `.SF` would need `X-Android-APK-Signed: 2` (the v2
   spec's stripping protection). Don't half-keep v1. `apk_identity` still reads v1 certificates from
   the *source* APK.
7. **Identity is computed, not trusted.** `installed_identity` re-hashes the pulled file against the
   phone's `sha256sum` before and after. Keep that end to end: an install reply alone is never proof
   (`Adb.install` docstring).

**AXML**

8. **String pool lengths.**
   - In a UTF-8 pool the first length is the **UTF-16 code-unit count** and the second is the UTF-8
     byte count (`ResourceTypes.cpp`'s `decodeLength` / `u16len`,
     https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/libs/androidfw/ResourceTypes.cpp).
     In a UTF-16 pool the length is in code units.
   - Python writes `len(text)`, which counts code points, so it is wrong for non-BMP characters.
     王者万象棋 and the English label are BMP, so it is harmless today.
   - The Rust port must choose between matching Python (parity) and `encode_utf16().count()`
     (correct), and record the choice.
   - Lengths over `0x7F` and `0x7FFF` use the two-byte or two-word forms. `encode_length8` does not
     guard against values over `0x7FFF`.
9. **Rebuilding the pool rewrites all of it.** The pool is rebuilt from the decoded strings: no
   dedup, the flags copied (including a possibly stale `SORTED_FLAG`), and padding to 4 bytes. Port
   this behaviour exactly; don't "improve" it in the same change.
10. **Resource-id map.** Attribute names are matched by **resource id**, not by string: the map
    covers the first N pool indices. Insert `debuggable` at index N, the end of the map prefix, then
    shift every string reference ≥ N. Missing one corrupts the manifest silently. The ids are
    `0x0101000F` for `debuggable` and `0x01010001` for `label`.
11. **Attribute order.** Android walks `<application>`'s attributes in ascending resource-id order,
    so a flag placed out of order is never read. The 1-based id/class/style indices must be
    recomputed after sorting.
12. **Idempotence is the test.** `is_debuggable` and "already named" are both defined as
    `patch(m) == m`. Any byte drift in the Rust rebuild breaks them.

**ADB and pairing**

13. The NULs: `"adb-label\0"` (exporter label), `"adb pair client\0"` and `"adb pair server\0"`
    (SPAKE2 names), but **no** NUL in the HKDF info.
14. Pairing header sizes are big-endian. ADB message headers are little-endian.
15. RSA-PSS is needed for the TLS 1.3 CertificateVerify. PKCS#1 v1.5 over SHA-1 is needed for ADB
    AUTH tokens, signing the token as if it were the digest
    (`rsa::Pkcs1v15Sign::new::<Sha1>()` over the 20 raw bytes).
16. WinUSB is exclusive: a running `adb.exe` server, or Android Studio's, blocks a native USB client.

---

## 5. Recommendations

1. **Pairing (ADR-016).** No crate meets ADR-005 as-is. The RustCrypto `spake2` crate does **not**
   interoperate with adbd and cannot be made to. Port BoringSSL's SPAKE2, or vendor `libadb`'s MIT
   `spake2.rs`, onto `curve25519-dalek` 4. Use the `w = 8t` trick for the scalar hack. Put rustls on
   a small custom RustCrypto provider (x25519, AES-GCM, rsa 0.10 PSS) and call
   `export_keying_material(…, b"adb-label\0", None)`.
   - Treat ADR-016's condition as **not yet met**. It is met once a deterministic-RNG vector test
     against the current `libhokace_adb.so` (alice and bob) passes, followed by a device-cycle
     pairing with a real phone. Then delete `android/app/src/main/cpp/` and its BoringSSL
     dependency.
   - Writing the provider ourselves keeps the "DO NOT USE IN PRODUCTION" `rustls-rustcrypto` out of
     the app.
2. **Windows ADB (MAP open question). Keep calling `adb.exe` from Rust for the lift**, behind an
   `AdbTransport` trait that mirrors `Adb`'s whitelisted calls: shell, exec-out stream/file, pull,
   push, install, uninstall, devices and kill-server.
   - The Android core needs a native ADB client over TCP/STLS anyway. Write it once in Rust, then
     add an `nusb` USB transport as an *opt-in* second implementation.
   - Make it the default only after device cycles show WinUSB binding, 2 GB pull throughput, ZLP
     handling and streamed install working on several phones.
   - Keep `adb.exe` as the fallback whenever nusb finds no WinUSB interface, such as a legacy or OEM
     driver.
   - `adb.exe` is an external platform tool, like the driver installer ADR-017 keeps, not C bound
     into the core, so it does not breach ADR-005.
3. **APK.**
   - Port `rewrite_apk`, `sign_v2`, `apk_identity` and the two AXML editors by hand. Read with
     `zip` (`default-features = false`, a pure-Rust deflate backend).
   - Write the archive with our own zip writer and sign v2 with `rsa` **0.10**, `sha2` and `pkcs8`.
     Read v1 signers with `cms`.
   - Prove the result with `apksigner verify --min-sdk-version 29 --print-certs`, the `apksig` crate
     as a second reader, AXML round-trip and idempotence tests against the game's real manifest, and
     a device install.
4. **Decide the re-deflate question before porting `rewrite_apk`.** Either show that the chosen
   deflate matches CPython's zlib byte for byte on a real game APK, or record an ADR-010 amendment:
   APK output is checked by entry-content equality plus `apksigner` plus a device cycle, and
   unchanged entries are raw-copied. I recommend the amendment, because it is faster and removes
   2 GiB of recompression from every preparation. Android's Java-RSA signing alone took 42.9 s on
   the 2 GB APK (`docs/lab-notebook.md`).
5. **Keep v3 lineage in CI.** `apksigner` and `tools/ci/sign_android.ps1` sign the patcher app; the
   core never needs v3.
