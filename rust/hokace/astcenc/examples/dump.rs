//! Write `dump::dump_context` for a footprint (LDR, quality 85), to compare with `oracle --dump`.
//!     cargo run --release -p hokace-astcenc --example dump -- <bx> <by> <out.bin>

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().skip(1).collect();
    let (bx, by) = (args[0].parse()?, args[1].parse()?);
    let config = hokace_astcenc::config_init(hokace_astcenc::PRF_LDR, bx, by, 85.0, 0)
        .map_err(|e| format!("{e:?}"))?;
    let context = hokace_astcenc::Context::new(&config).map_err(|e| format!("{e:?}"))?;
    std::fs::write(&args[2], hokace_astcenc::dump::dump_context(&context))?;
    Ok(())
}
