//! The patchers' shared core (`rust/DECISIONS.md`, ADR-012).
//!
//! Units land here wave by wave as `rust/MAP.md` lists them; until the lift each one is also reached
//! from Python through its rust-anything crate, with Python as the fallback (ADR-019).

/// The workspace's version, as Cargo records it.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

pub mod axml;
pub mod broken_list;
pub mod card_titles;
pub mod catalog;
pub mod catalog_supplement;
pub mod catalog_updates;
pub mod config_bin;
pub mod hand_card_titles;
pub mod languages;
pub mod launcher;
pub mod lineup_codes;
pub mod native_verify;
pub mod package_metadata;
pub mod pb_text;
pub mod protobuf;
pub mod pyjson;
pub mod pyos;
pub mod pystr;
pub mod pyzlib;
pub mod qts;
pub mod resource_tokens;
pub mod run;
pub mod scan;
pub mod sprite_table;
pub mod terminology;
pub mod transaction;
pub mod translation;
pub mod unity_text;

#[cfg(test)]
mod tests {
    #[test]
    fn version_is_set() {
        assert!(!super::VERSION.is_empty());
    }
}
