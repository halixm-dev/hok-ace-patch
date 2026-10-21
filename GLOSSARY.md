# HOK ACE Mobile English Patcher

Installs a translation of 王者万象棋 onto an Android phone by rewriting the game's own data packages, without root.

## Language

### Game data

**Data layer**:
One of the two places the game reads its packages from; the override layer is read first, the prime layer only for what the override lacks.
_Avoid_: data set, tier

**Prime layer**:
The packages baked into the game's APK.
_Avoid_: builtin, APK layer

**Override layer**:
The packages the game downloads into its data directory, which this patcher rewrites.
_Avoid_: downloaded layer, game data (when the layer is meant)

**Pristine layer**:
The override layer as the game downloaded it, before any patch.
_Avoid_: original, clean, unpatched data

**Pristine delta**:
The pristine bytes an install overwrote, kept so a later run can rebuild the pristine layer from the files the install left unchanged.
_Avoid_: restore delta, backup, undo

**Replaced file**:
A file the pristine delta names that a game update rewrote, so it matches neither side of its entry. It becomes the new pristine only when the delta's asset record shows none of this patcher's assets left in its package.
_Avoid_: updated file, stale file

**Prime-only**:
Said of an asset the prime layer carries and the override layer does not.

**Package**:
A numbered container of assets in a data layer, identified by its package id.
_Avoid_: bundle, archive

**Asset**:
One addressable item in a package, named by a 16-hex-digit hash.
_Avoid_: entry, file, resource

**Text table**:
An asset holding localization strings, keyed by row.
_Avoid_: dictionary (unless a card dictionary is meant), string table

**Card dictionary**:
A text table mapping a game mode's card refs to card names; every game mode carries its own copy.

**Texture**:
An asset holding an image the game draws.
_Avoid_: graphic, picture, sprite (a sprite is one region of a texture)

**Config bin**:
An asset holding game configuration rows whose stored checksum the client enforces.
_Avoid_: ResData, config asset

**Reseal**:
Recomputing a rewritten config bin's two stored digests (fields 1 and 4) so the client loads it.

**Lineup bin**:
One of the three package-`1` config bins whose rows each carry a share code.

**Share code**:
A lineup encoded as base64 of raw deflate of an `OSProto.OneLineup` protobuf, which the client decodes on the phone.
_Avoid_: lineup code, formation code

**Regioned atlas**:
A texture packing many sprites, whose translation is applied sprite by sprite.

**Sprite table**:
The game's own record of where each sprite sits inside a regioned atlas.

### Translation

**Catalog**:
The reviewed translation for one patch language: its text tables and its catalog edits.

**Catalog edit**:
One reviewed texture change in a catalog.
_Avoid_: texture payload, patch image

**Terminology table**:
The fixed mapping from each game keyword to the one name it reads as in every patch language (`夺取` is always *Steal*).
_Avoid_: glossary (that word means `GLOSSARY.md`), keyword glossary

### Delivery

**Staging**:
Writing translated packages into an output directory, ready to push to the phone.
_Avoid_: building, patching (for this step alone)

**Append**:
Adding a prime-only asset to the override layer's copy of its package, leaving everything else in that package as it was.
_Avoid_: insert, prime injection

**Rebuild**:
Laying out a whole package again with Tencent's own builder.
_Avoid_: repack

**Relocation**:
Moving a text table that no longer fits its place to the end of its package.

**Normal APK**:
The game's own APK, re-signed, which stays installed on the phone.
_Avoid_: patched APK, game APK (when the re-signed copy is meant)

**Access APK**:
A debuggable copy of the normal APK, installed only long enough to write the override layer.
_Avoid_: debug APK, data-access copy

**Windows patcher**:
The Windows app that installs the translation onto a phone connected over USB.
_Avoid_: PC patcher, Windows GUI, Windows app, desktop patcher

**Android patcher**:
The app that installs the translation onto the phone it runs on.
_Avoid_: Android app, mobile patcher

**PC patcher**:
The upstream patcher for the PC edition of the game, which produces the catalog and the translation runtime this project ships.
_Avoid_: using it for the Windows patcher

### Verification

**Device cycle**:
One watched run on a real phone that tests a single change and ends in a verdict.
_Avoid_: test run, watched cycle

**Allowlist**:
The config bins a device cycle has cleared for translation; empty today.
_Avoid_: safe list, whitelist

**Candidate queue**:
The config bins not yet tried, each awaiting its own device cycle.

**Withdrawn**:
Said of an asset a device cycle failed, so it stays untranslated, with the failing screen recorded.
_Avoid_: disabled, removed
