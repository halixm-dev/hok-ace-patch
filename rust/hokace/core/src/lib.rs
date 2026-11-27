//! The patchers' shared core (`rust/DECISIONS.md`, ADR-012).
//!
//! Units land here wave by wave as `rust/MAP.md` lists them; until the lift each one is also reached
//! from Python through its rust-anything crate, with Python as the fallback (ADR-019).

/// The workspace's version, as Cargo records it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

pub mod catalog;
pub mod package_metadata;
pub mod protobuf;
pub mod qts;
pub mod scan;
pub mod translation;

#[cfg(test)]
mod tests {
    #[test]
    fn version_is_set() {
        assert!(!super::VERSION.is_empty());
    }
}
