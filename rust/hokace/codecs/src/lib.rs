//! The pipeline's codecs in pure Rust (`rust/MAP.md`, wave 1; ADR-005, ADR-010).
//!
//! Each module mirrors the one Python call the pipeline makes, with its edge behavior
//! (`rust/research/compression-codecs.md`, `rust/research/texture-codecs.md`); the corpus check in
//! `examples/corpus.rs` holds them to the Python libraries on the game's own data.

mod astc;
pub mod astc_encode;
pub mod bc7;
pub mod lz4;
pub mod png;
pub mod texture;
pub mod zstd;
