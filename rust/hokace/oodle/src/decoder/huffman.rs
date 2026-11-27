// Adapted from oozextract 0.5.7, a Rust port of ooz.
// Ooz copyright (C) 2016 Powzix. See ../../NOTICE.md for provenance and licenses.

use crate::decoder::Core;
use crate::decoder::pointer::Pointer;
use crate::error::End::Len;
use crate::error::{ErrorContext, Res, ResultBuilder, SliceErrors, WithContext};

pub const BASE_PREFIX: [usize; 12] = [
    0x0, 0x0, 0x2, 0x6, 0xE, 0x1E, 0x3E, 0x7E, 0xFE, 0x1FE, 0x2FE, 0x3FE,
];

#[derive(Default)]
pub struct HuffReader<const SRC: u8, const DST: u8> {
    // Array to hold the output of the huffman read array operation
    pub output: Pointer<DST>,
    pub output_end: Pointer<DST>,
    // We decode three parallel streams, two forwards, |src| and |src_mid|
    // while |src_end| is decoded backwards.
    pub src: Pointer<SRC>,
    pub src_mid: Pointer<SRC>,
    pub src_end: Pointer<SRC>,
    pub src_mid_org: Pointer<SRC>,
    pub src_bitpos: i32,
    pub src_mid_bitpos: i32,
    pub src_end_bitpos: i32,
    pub src_bits: u32,
    pub src_mid_bits: u32,
    pub src_end_bits: u32,
}

impl<const SRC: u8, const DST: u8> ErrorContext for HuffReader<SRC, DST> {}

impl<const SRC: u8, const DST: u8> HuffReader<SRC, DST> {
    pub fn decode_bytes(&mut self, core: &mut Core, lut: &HuffRevLut) -> Res<()> {
        let mut src = self.src;
        let mut src_bits = self.src_bits;
        let mut src_bitpos = self.src_bitpos;

        let mut src_mid = self.src_mid;
        let mut src_mid_bits = self.src_mid_bits;
        let mut src_mid_bitpos = self.src_mid_bitpos;

        let mut src_end = self.src_end;
        let mut src_end_bits = self.src_end_bits;
        let mut src_end_bitpos = self.src_end_bitpos;

        let mut k: usize;
        let mut n;

        let mut dst = self.output;
        let mut dst_end = self.output_end;

        self.assert_le(src, src_mid)?;

        if (self.src_end - src_mid) >= 4 && (dst_end - dst) >= 6 {
            dst_end -= 5;
            src_end -= 4;

            let mut tmp = [0; 8];
            while dst < dst_end && src <= src_mid && src_mid <= src_end {
                src_bits |= (core.get_le_bytes(src, 4).at(core)? as u32) << src_bitpos;
                src += (31 - src_bitpos) >> 3;

                src_end_bits |= (core.get_be_bytes(src_end, 4).at(core)? as u32) << src_end_bitpos;
                src_end -= (31 - src_end_bitpos) >> 3;

                src_mid_bits |= (core.get_le_bytes(src_mid, 4).at(core)? as u32) << src_mid_bitpos;
                src_mid += (31 - src_mid_bitpos) >> 3;

                src_bitpos |= 0x18;
                src_end_bitpos |= 0x18;
                src_mid_bitpos |= 0x18;

                k = (src_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_bits >>= n as u32;
                src_bitpos -= n as i32;
                tmp[0] = lut.bits2sym.get_copy(k)?;

                k = (src_end_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_end_bits >>= n as u32;
                src_end_bitpos -= n as i32;
                tmp[1] = lut.bits2sym.get_copy(k)?;

                k = (src_mid_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_mid_bits >>= n as u32;
                src_mid_bitpos -= n as i32;
                tmp[2] = lut.bits2sym.get_copy(k)?;

                k = (src_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_bits >>= n as u32;
                src_bitpos -= n as i32;
                tmp[3] = lut.bits2sym.get_copy(k)?;

                k = (src_end_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_end_bits >>= n as u32;
                src_end_bitpos -= n as i32;
                tmp[4] = lut.bits2sym.get_copy(k)?;

                k = (src_mid_bits & 0x7FF) as _;
                n = lut.bits2len.get_copy(k)?;
                src_mid_bits >>= n as u32;
                src_mid_bitpos -= n as i32;
                tmp[5] = lut.bits2sym.get_copy(k)?;

                core.set_arr(dst, tmp).at(self)?;
                dst += 6;
            }
            dst_end += 5;

            src -= src_bitpos >> 3;
            src_bitpos &= 7;

            src_end += 4 + (src_end_bitpos >> 3);
            src_end_bitpos &= 7;

            src_mid -= src_mid_bitpos >> 3;
            src_mid_bitpos &= 7;
        }
        while dst < dst_end {
            if (src_mid - src) <= 1 {
                if (src_mid - src) == 1 {
                    // no test coverage
                    src_bits |= (core.get_byte(src).at(self)? as u32) << src_bitpos;
                }
            } else {
                src_bits |= (core.get_le_bytes(src, 2).at(core)? as u32) << src_bitpos;
            }
            k = (src_bits & 0x7FF) as _;
            n = lut.bits2len.get_copy(k)?;
            src_bitpos -= n as i32;
            src_bits >>= n as u32;
            core.set(dst, lut.bits2sym.get_copy(k)?).at(self)?;
            dst += 1;
            src += (7 - src_bitpos) >> 3;
            src_bitpos &= 7;

            if dst < dst_end {
                if (src_end - src_mid) <= 1 {
                    if (src_end - src_mid) == 1 {
                        let mid = core.get_byte(src_mid).at(self)? as u32;
                        src_end_bits |= mid << src_end_bitpos;
                        src_mid_bits |= mid << src_mid_bitpos;
                    }
                } else {
                    let v = core.get_le_bytes(src_end - 2, 2).at(self)? as u32;
                    src_end_bits |= (((v >> 8) | (v << 8)) & 0xffff) << src_end_bitpos;
                    src_mid_bits |=
                        (core.get_le_bytes(src_mid, 2).at(self)? as u32) << src_mid_bitpos;
                }
                core.set(dst, lut.bits2sym.get_copy((src_end_bits & 0x7FF) as usize)?)
                    .at(self)?;
                dst += 1;
                n = lut.bits2len.get_copy((src_end_bits & 0x7FF) as usize)?;
                src_end_bitpos -= n as i32;
                src_end_bits >>= n as u32;
                src_end -= (7 - src_end_bitpos) >> 3;
                src_end_bitpos &= 7;
                if dst < dst_end {
                    core.set(dst, lut.bits2sym.get_copy((src_mid_bits & 0x7FF) as usize)?)
                        .at(self)?;
                    dst += 1;
                    n = lut.bits2len.get_copy((src_mid_bits & 0x7FF) as usize)?;
                    src_mid_bitpos -= n as i32;
                    src_mid_bits >>= n as u32;
                    src_mid += (7 - src_mid_bitpos) >> 3;
                    src_mid_bitpos &= 7;
                }
            }
            self.assert_le(src, src_mid)?;
            self.assert_le(src_mid, src_end)?;
        }
        self.assert_eq(src, self.src_mid_org)?;
        self.assert_eq(src_end, src_mid)?;
        Ok(())
    }
}

pub struct HuffRange {
    pub symbol: u16,
    pub num: u16,
}

pub struct HuffRevLut {
    // Mapping that maps a bit pattern to a code length.
    pub bits2len: [u8; 2048],
    // Mapping that maps a bit pattern to a symbol.
    pub bits2sym: [u8; 2048],
}

impl Core<'_> {
    pub fn make_lut(&mut self, prefix_cur: &[usize; 12], syms: &[u8; 1280]) -> Res<HuffRevLut> {
        let mut bits2len = [0; 2048];
        let mut bits2sym = [0; 2048];
        let mut currslot = 0;
        for i in 1..11u8 {
            #[allow(clippy::indexing_slicing)]
            let (start, cur) = (BASE_PREFIX[usize::from(i)], prefix_cur[usize::from(i)]);
            let count = cur - start;
            if count != 0 {
                let stepsize = 1 << (11 - i);
                let num_to_set = count << (11 - i);
                self.assert_le(currslot + num_to_set, 2048)?;
                bits2len.slice_mut(currslot, Len(num_to_set))?.fill(i);

                for j in 0..count {
                    let dst = currslot + stepsize * j;
                    bits2sym
                        .slice_mut(dst, Len(stepsize))?
                        .fill(syms.get_copy(start + j)?)
                }
                currslot += num_to_set;
            }
        }
        if prefix_cur[11] - BASE_PREFIX[11] != 0 {
            let num_to_set = prefix_cur[11] - BASE_PREFIX[11];
            bits2len.slice_mut(currslot, Len(num_to_set))?.fill(11);
            let sym = syms
                .get(BASE_PREFIX[11]..BASE_PREFIX[11] + num_to_set)
                .msg_of(&(BASE_PREFIX[11], num_to_set))?;
            bits2sym
                .slice_mut(currslot, Len(num_to_set))?
                .copy_from_slice(sym);
            currslot += num_to_set;
        }

        self.assert_eq(currslot, 2048)?;
        Ok(HuffRevLut {
            bits2len: reverse_lut(&bits2len),
            bits2sym: reverse_lut(&bits2sym),
        })
    }
}

fn reverse_lut(input: &[u8; 2048]) -> [u8; 2048] {
    std::array::from_fn(|index| input[usize::from((index as u16).reverse_bits() >> 5)])
}
