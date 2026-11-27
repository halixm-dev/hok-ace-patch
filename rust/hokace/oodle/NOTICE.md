# Decoder provenance

The Leviathan and shared entropy routines in `src/leviathan.rs`, `src/decoder/`
and `src/error.rs` were adapted on 2026-11-27 from [oozextract 0.5.7](https://crates.io/crates/oozextract/0.5.7)
(commit `8acaeb2bc375dd56c413a83aae4e87156136fdac`). The published package marks its
contributions as MIT. Oozextract ports [ooz](https://github.com/powzix/ooz),
copyright © 2016 Powzix, licensed GPL-3.0-or-later. The combined decoder is
distributed under GPL-3.0-or-later. [GPL text](../../../android/native/licenses/GPL-3.0.txt)

This adaptation keeps only the Leviathan paths, uses this crate's QTS framing
and exact-size checks, and replaces the SIMD helpers with safe Rust.

The patcher's source repository is https://github.com/halixm-dev/hok-ace-patch.
The corresponding decoder is under `rust/hokace/oodle`, with Python bindings
and their Cargo lockfile under `crates/hok_codecs`. Run `build.bat` for the
Windows extension or `android/native/build_rust_wheels.py --help` for the
Chaquopy wheel recipe.

## MIT terms for the oozextract contributions

Copyright © the oozextract contributors.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
