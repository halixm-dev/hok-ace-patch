//! Single-block encoder from rustbcx 0.8.0, revision
//! e58a6dde6ade655bbba8357615cd48a59d6fdb39.
//!
//! Source: <https://github.com/OctoKeights/rustbcx>. The single-block subset
//! builds with the pinned workspace toolchain. See the licenses and NOTICE
//! beside this file for the port and the original bc7enc_rdo code.

mod bc7decomp;
mod bc7enc;
mod fmath;

pub(super) use bc7enc::{Bc7Enc, CompressBlockParams};
