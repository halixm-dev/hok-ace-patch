//! Arm astcenc (commit 631fb04e1c4b, as vendored in astc-encoder-py 0.1.12) translated to Rust: the LDR
//! compressor at one thread, byte for byte with the scalar build the Windows wheel's bytes match
//! (`.scratch/astcenc-port/plan.md`). Each module names the C++ file it translates.

#![expect(
    clippy::needless_range_loop,
    reason = "index loops kept as the C++ writes them, so each reads line by line against upstream"
)]

pub mod averages_and_directions;
pub mod block_sizes;
pub mod color_quantize;
pub mod color_unquantize;
pub mod compress_symbolic;
pub mod decompress_symbolic;
pub mod entry;
pub mod find_best_partitioning;
pub mod ideal_endpoints_and_weights;
pub mod image;
pub mod integer_sequence;
pub mod internal;
mod lanes;
pub mod partition_tables;
pub mod pick_best_endpoint_format;
pub mod symbolic_physical;
pub mod tables;
pub mod vecmath;
pub mod weight_align;

pub mod dump;
pub mod prof;

pub use entry::{Context, Error, config_init};
pub use internal::Config;
pub use internal::{PRF_LDR, PRF_LDR_SRGB};
