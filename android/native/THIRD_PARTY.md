# Experimental Android codec builds

The local build script downloads original source distributions, checks these SHA-256 hashes,
and compiles the existing CPython wrappers with NDK **28.2.13676358**, Android API **24**,
ARM64, Chaquopy CPython **3.12.12** headers, and 16 KiB ELF segment alignment. It builds
scalar and NEON ASTC variants and statically links the NDK C++ runtime. These are development
builds; 16 KiB device acceptance and a release redistribution review remain required.

| Distribution | Version | Source archive SHA-256 | Notices and source requirements |
|---|---|---|---|
| [pyooz](https://pypi.org/project/pyooz/0.0.8/) | 0.0.8 | `98916331773493764483bc6448c9c6166bf2440939abe77cd140509038cc3adf` | GPL-3.0-or-later wrapper/decoder; preserve copyright and GPL text, provide corresponding source and build instructions for distributed binaries. Its vendored SIMDe has MIT notices. The source distribution does not include a standalone GPL text. |
| [astc-encoder-py](https://pypi.org/project/astc-encoder-py/0.1.12/) | 0.1.12 | `03759ac32804cae32bc238e72f94c5ba27e228507df00816b741f7961f1184f9` | MIT wrapper; vendored Arm encoder source carries Apache-2.0 notices. Preserve both license texts and applicable notices. |
| [texture2ddecoder](https://pypi.org/project/texture2ddecoder/1.0.6/) | 1.0.6 | `88f04d8951018ac13b8dacd07e57e8adad4a6f1cfe5509646e8a1020346a81ca` | MIT wrapper/decoder; preserve vendored Crunch/Unity Crunch notices as well as the top-level license. |

Source archive URLs and metadata are available from the versioned PyPI JSON APIs. The script
does not run their setup scripts and does not modify their source. All license/notice files
present in an archive are copied into the generated wheel's `dist-info/licenses/` directory.
Source-header notices and missing license texts must also accompany a release. Generated
wheels and their hash report live in ignored `android/wheels/`; downloaded source and object
files belong in a selected scratch directory, not committed source.

The static [LLVM libc++ runtime](https://llvm.org/docs/DeveloperPolicy.html#license)
uses Apache-2.0 with LLVM exceptions; retain the NDK's applicable notices. Shizuku API/provider
13.1.5 use MIT. Chaquopy and its embedded Python/native wheel dependencies need their own
license inventory before release. Core spike wheels are LZ4 4.3.2, Zstandard 0.22.0,
Archspec 0.2.6, pypinyin 0.55.0 and (for the development graphics oracle) Pillow 11.0.0.
These differ from Windows pins where the Android wheel repository requires it; successful
imports alone do not establish output parity or current-release suitability.

Static APK inventory on 2026-10-04 checks 84 ELF64 libraries, including nested Chaquopy `.imy`
archives. Six lack 16 KiB load alignment: LZ4 `_version`, `_block` and `_frame`, Zstandard
`_cffi` and `backend_c`, and the Pillow dependency `chaquopy/lib/libfreetype.so`. The three
custom codec builds pass this ELF check, but their alignment does not fix these dependencies.
Report: ignored `artifacts/android-native-alignment.json`. Run the source-only checker with:

```bat
.venv\Scripts\python.exe tools\research\check_android_native.py android\app\build\outputs\apk\debug\app-debug.apk --report artifacts\android-native-alignment.json
```

This is a static inventory, separate from APK ZIP alignment and actual 16 KiB loader acceptance.
Keep 16 KiB support unclaimed until the dependency binaries and a suitable device are verified.

### Source-built compression and FreeType variant

The default (full-codec) build selects local source-built LZ4 4.3.2,
Zstandard 0.22.0 (both C and CFFI bindings), and FreeType 2.9.1. It does not change their
versions or patch upstream source. Use the same NDK/API/ARM64 headers as the codec builds.
The compression recipe uses the upstream CFFI generator with an explicitly selected Android
preprocessor; CFFI 2.1.1 generated the measured build. CFFI backend runtime acceptance is
separate from the CPython C backend used by the pipeline.

| Component | Original source SHA-256 | Notices |
|---|---|---|
| LZ4 4.3.2 | `e1431d84a9cfb23e6773e72078ce8e65cad6745816d4cbf9ae67da5ea419acda` | Preserve Python wrapper and bundled LZ4/xxHash license/header notices |
| Zstandard 0.22.0 | `8226a33c542bcb54cd6bd0a366067b610b41713b64c9abec1bc4533d69f51e70` | Preserve wrapper and bundled Zstandard BSD notices and upstream license choices |
| FreeType 2.9.1 | `ec391504e55498adceb30baceebd147a6e963f636eb617424bcfc47a169898ce` | FreeType License selected; retain `docs/FTL.TXT`, copyright and distribution attribution |

FreeType's archive comes from the [GNU release server](https://download.savannah.gnu.org/releases/freetype/).
Its build matches the [Chaquopy recipe](https://github.com/chaquo/chaquopy/blob/master/server/pypi/packages/chaquopy-freetype/build.sh):
system zlib, no HarfBuzz/PNG, and SONAME `libfreetype.so`. The inspected original wheel also
has no BZip2 dependency. The CMake build uses a position-independent static archive and links
that archive into the shared library with explicit 16 KiB segment alignment.

```bat
.venv\Scripts\python.exe android\native\build_compression_wheels.py --ndk <ndk> ^
    --python-headers <extracted-python-target>\include\python3.12 ^
    --python-libs <extracted-python-target>\jniLibs\arm64-v8a ^
    --work <dependency-scratch> --output android\wheels
.venv\Scripts\python.exe android\native\build_freetype_wheel.py --ndk <ndk> ^
    --cmake <sdk>\cmake\3.22.1 --work <dependency-scratch> --output android\wheels
.venv\Scripts\python.exe android\native\package_sources.py --sources <codec-scratch> ^
    --compression-sources <dependency-scratch> --freetype-sources <dependency-scratch> ^
    --output <six-component-source-companion.zip>
```

The source companion contains all six pinned original archives and recipes, with hash/CRC
read-back. It is a component inventory; complete application/runtime redistribution acceptance
remains open. The earlier six failures describe the original repository-wheel variant, and
must not be confused with the separately checked source-built APK.

The first compiler attempt applied `-fms-extensions` to every codec, which made Clang reject
Ooz's `_rotl` definition as a builtin collision. The script applies that upstream flag only
to the texture decoder, which requests it. No upstream source edit was needed.

`licenses/GPL-3.0.txt` is the unmodified GNU text retrieved from
`https://www.gnu.org/licenses/gpl-3.0.txt` (35149 bytes, SHA-256
`3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986`).
It is included in verified engine notice assets. Generate a source companion for the three
custom codec components, retaining every original archive/header and the exact build recipe:

```bat
.venv\Scripts\python.exe android\native\package_sources.py --sources artifacts\android-native-build --output artifacts\android-custom-codec-sources.zip
```

The packager refuses an archive whose hash does not match `build_wheels.py`, emits a hash manifest,
and reads the archive back. The other wheel/runtime dependencies and application source/notice
inventory remain release work; this component companion does not close those tasks.

### Packaged notice audit

The current development APK carries unmodified CPython 3.12.12 and Chaquopy 17.0.0 license
texts, Apache-2.0, GPL-3.0, Shizuku's MIT text and NDK 28.2.13676358 toolchain notices.
`licenses/sources.json` records upstream origins, content hashes and scope. The Shizuku text
comes from an immutable upstream commit at the URL referenced by the 13.1.5 Maven POM;
matching the version-specific library source remains open. The whole NDK toolchain notice also
includes components which this APK does not use.

`collect_source_notices.py` verifies the three original codec archive hashes and preserves
copyright/license comment blocks from the first 16 KiB of C/C++ files, including Ooz/SIMDe,
Arm ASTC and the texture decoder's vendored code. Its output is an inventory to review, not
proof that every applicable source notice was found. The unchanged original sources also
remain in the component companion.

```bat
.venv\Scripts\python.exe android\native\collect_source_notices.py --sources artifacts\android-native-build --output android\native\licenses\Codec-source-header-NOTICES.txt
.venv\Scripts\python.exe android\native\audit_notices.py android\app\build\outputs\apk\debug\app-debug.apk --report artifacts\android-dependency-notices-final-inventory.json
```

| Verification | Result |
|---|---|
| Actual packaged Python metadata | 12 distributions, including bootstrap pyelftools/setuptools |
| Notice/provenance files | 29; engine notice assets match their resource-manifest hashes |
| Native payload hashes | All 84 unchanged by the notice additions |
| Final APK ZIP alignment | SDK `zipalign -c -P 16 -v 4` passes; physical 16 KiB loading remains unverified |
| Android verified extraction/runtime | One full-codec check passes in 1.764 s |
| Six-component source companion | Original archive hashes, notice provenance hashes, ZIP CRC and exact read-back pass |

The APK audit retains original metadata labels/classifiers, which can disagree; it does not
choose a license based on one field. Ooz's generic GPL text and source-header notices are in
engine assets even though its own dist-info contains no notice file. `release_ready` stays
false: exact Maven runtime dependencies, native dependencies embedded in Python, application
and precompiled runtime/catalog distribution permissions, and combined redistribution
requirements remain to be resolved. This inventory does not close the release gate.

### Resolved Maven runtime inventory

The Gradle task resolves `releaseRuntimeClasspath` and hashes each artifact. The auditor
rechecks the cached binaries against that record. The downloader uses Google Maven or Maven
Central for the exact coordinates, records POM/source hashes, and reuses only verified originals.
It records expected identities before publishing new files, so an interrupted write can be
retried without adopting an unknown partial file.

```bat
android\gradlew.bat -p android :app:writeRuntimeDependencyInventory
.venv\Scripts\python.exe android\native\download_maven_sources.py android\app\build\reports\release-runtime-dependencies.json --output artifacts\android-maven-sources
.venv\Scripts\python.exe android\native\audit_maven.py android\app\build\reports\release-runtime-dependencies.json --published artifacts\android-maven-sources --notice-output android\native\licenses\Maven-source-header-NOTICES.txt --report artifacts\android-maven-published-source-inventory.json
.venv\Scripts\python.exe android\native\package_sources.py --sources artifacts\android-native-build --compression-sources artifacts\android-dependency-build --freetype-sources artifacts\android-dependency-build --maven-sources artifacts\android-maven-sources --output artifacts\android-codec-maven-source-companion.zip
```

| Resolved candidate | Version | Published POM declaration |
|---|---|---|
| AndroidX annotation | 1.3.0 | Apache-2.0 |
| Shizuku API, provider, AIDL, shared | 13.1.5 | MIT, all four POMs |
| Kotlin stdlib | 2.0.0 | Apache-2.0 |
| JetBrains annotations | 13.0 | Apache-2.0 |

On 2026-10-04, the cached-only audit verified all seven binaries but lacked JetBrains' POM.
The matching source/POM download was not executed because automatic approval review failed
on workspace credits. Following the user's continuation on 2026-10-05, downloads succeeded.
All seven published source JAR hashes and CRCs verify; the six previously cached POMs match
the published files exactly, and the seventh fills the metadata gap. A modified source JAR
is refused. These are published artifact identities, not a binary/source reproducibility proof.

None of the seven binary artifacts embeds a license/notice, including AAR `classes.jar`.
The source-header collector retains original Java/Kotlin copyright/license comments in
`licenses/Maven-source-header-NOTICES.txt`; the four Shizuku source JARs have no such scanned
header, so their POM declarations and separately retained upstream MIT text remain relevant.
The expanded companion preserves six native source archives, seven Maven source JARs, their
POMs, origins/hashes and recipes. Notice provenance, CRC and exact outer-ZIP read-back verify.

The final APK contains twelve Python distribution metadata records, thirty notice/provenance
files and eighty-four unchanged native payloads. Verified extraction and full-codec imports
pass on Android in 2.150 s; final SDK ZIP alignment passes. This adds no game content change.

Runtime resolution inventories candidates; annotation-only classes may not survive APK
packaging. Chaquopy plugin-injected runtime, Python native dependencies, notice completeness,
application/runtime/catalog distribution and combined redistribution review remain open.
`release_ready` stays false.
