//! Phase timers for speed work, compiled only with the `prof` feature.

#[cfg(feature = "prof")]
mod imp {
    use std::cell::RefCell;
    use std::time::{Duration, Instant};

    pub const NAMES: [&str; 16] = [
        "ideal_colors",
        "ideal_weights_dec",
        "angular",
        "quant_weights",
        "weight_error",
        "endpoint_formats",
        "recompute_colors",
        "pack_colors",
        "difference",
        "realign",
        "partition_search",
        "block_stats",
        "load",
        "physical",
        "p1_total",
        "p2_total",
    ];
    thread_local! {
        static T: RefCell<[(Duration, u64); 16]> = const { RefCell::new([(Duration::ZERO, 0); 16]) };
    }
    pub struct Span(usize, Instant);
    impl Drop for Span {
        fn drop(&mut self) {
            let d = self.1.elapsed();
            T.with(|t| {
                let mut t = t.borrow_mut();
                t[self.0].0 += d;
                t[self.0].1 += 1;
            });
        }
    }
    pub fn span(i: usize) -> Span {
        Span(i, Instant::now())
    }
    pub fn report() {
        T.with(|t| {
            for (i, (d, n)) in t.borrow().iter().enumerate() {
                println!(
                    "{:>18} {:>9.3} s {:>11} calls",
                    NAMES[i],
                    d.as_secs_f64(),
                    n
                );
            }
        });
    }
}

#[cfg(feature = "prof")]
pub use imp::{report, span};

#[cfg(not(feature = "prof"))]
pub struct Span;
#[cfg(not(feature = "prof"))]
#[inline(always)]
pub fn span(_: usize) -> Span {
    Span
}
#[cfg(not(feature = "prof"))]
pub fn report() {}
