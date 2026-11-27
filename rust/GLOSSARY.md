# Glossary: domain terms and their Rust names

The meanings live in the repo's `GLOSSARY.md`; this file only maps each term to its name in Rust, so
every unit names the same thing the same way. Add a row when a unit brings a new term.

| Term (`GLOSSARY.md`) | Python | Rust |
|---|---|---|
| Mobile edition | `patcher_core`, `android_bridge` | `core::mobile` |
| PC edition | `pc_edition` | `core::pc` |
| Data layer | (prose) | `core::layer::Layer` |
| Prime layer | `package_rebuild.extract_prime` | `core::layer::Layer::Prime` |
| Override layer | (prose) | `core::layer::Layer::Override` |
| Pristine layer | `app/pristine_layer.py` | `core::pristine::PristineLayer` |
| Pristine delta | `tools/pristine_delta.py` | `core::pristine::Delta` |
| Catalog | `engine_hooks.load_catalog` | `core::catalog::Catalog` |
| Staging summary | `build_device_patch.build_patch` docstring | `core::staging::Summary` |
| Atlas block scan | `block_scan.stale_blocks` | `stale_blocks_rs::port::stale_blocks` |

Rust names are planned; a row is checked against the code when its unit is ported.
