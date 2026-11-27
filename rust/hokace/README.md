# hokace workspace

The Rust migration's one Cargo workspace (`../DECISIONS.md`, ADR-012). `core/` is the shared core;
the front ends join as members when their wave starts (`../MAP.md`).

```bat
cargo test --manifest-path rust\hokace\Cargo.toml
cargo build --manifest-path rust\hokace\Cargo.toml --target aarch64-linux-android
```

The Android build needs the NDK's linker; see `../../android/native/build_rust_wheels.py`.
