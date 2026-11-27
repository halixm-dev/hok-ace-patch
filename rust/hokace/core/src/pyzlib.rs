//! The three byte codecs a lineup share code goes through, each as CPython 3.12 runs it on Windows:
//! `base64.b64encode` / `base64.b64decode` (binascii's non-strict decoder), raw deflate at zlib's
//! default settings (`zlib.compressobj(Z_DEFAULT_COMPRESSION, DEFLATED, -15)`) and raw inflate
//! (`zlib.decompress(data, -15)`).
//!
//! The deflater is zlib 1.3.1's `deflate_slow` at level 6 with memLevel 8 and its `trees.c`, ported
//! line for line, because a share code is compared byte for byte with what Python writes and neither
//! miniz_oxide nor zlib-rs gives zlib's stream (6 and 0 of the 132 shipped codes). The inflater is a
//! plain canonical decoder that refuses what zlib's `inflate` refuses, with zlib's message for each.

use crate::axml::PyErr;

const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";

/// `base64.b64encode`: standard alphabet, padded.
pub fn b64encode(data: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(data.len().div_ceil(3) * 4);
    for chunk in data.chunks(3) {
        let b = [
            chunk[0],
            *chunk.get(1).unwrap_or(&0),
            *chunk.get(2).unwrap_or(&0),
        ];
        let n = u32::from(b[0]) << 16 | u32::from(b[1]) << 8 | u32::from(b[2]);
        out.push(ALPHABET[(n >> 18) as usize & 63]);
        out.push(ALPHABET[(n >> 12) as usize & 63]);
        out.push(if chunk.len() > 1 {
            ALPHABET[(n >> 6) as usize & 63]
        } else {
            b'='
        });
        out.push(if chunk.len() > 2 {
            ALPHABET[n as usize & 63]
        } else {
            b'='
        });
    }
    out
}

fn b64_value(byte: u8) -> Option<u8> {
    match byte {
        b'A'..=b'Z' => Some(byte - b'A'),
        b'a'..=b'z' => Some(byte - b'a' + 26),
        b'0'..=b'9' => Some(byte - b'0' + 52),
        b'+' => Some(62),
        b'/' => Some(63),
        _ => None,
    }
}

/// `base64.b64decode` (`binascii.a2b_base64(strict_mode=False)`); its errors are `binascii.Error`.
pub fn b64decode(data: &[u8]) -> Result<Vec<u8>, PyErr> {
    let mut out = Vec::with_capacity(data.len() / 4 * 3 + 3);
    let (mut quad, mut left, mut pads) = (0u8, 0u8, 0u8);
    for &byte in data {
        if byte == b'=' {
            if quad >= 2 {
                pads += 1;
                if quad + pads >= 4 {
                    return Ok(out);
                }
            }
            continue;
        }
        let Some(value) = b64_value(byte) else {
            continue;
        };
        pads = 0;
        match quad {
            0 => {
                quad = 1;
                left = value;
            }
            1 => {
                quad = 2;
                out.push(left << 2 | value >> 4);
                left = value & 0x0f;
            }
            2 => {
                quad = 3;
                out.push(left << 4 | value >> 2);
                left = value & 0x03;
            }
            _ => {
                quad = 0;
                out.push(left << 6 | value);
                left = 0;
            }
        }
    }
    match quad {
        0 => Ok(out),
        1 => Err(PyErr::new(
            "Error",
            format!(
                "Invalid base64-encoded string: number of data characters ({}) cannot be 1 more than a multiple of 4",
                out.len() / 3 * 4 + 1
            ),
        )),
        _ => Err(PyErr::new("Error", "Incorrect padding")),
    }
}

// --- deflate: zlib 1.3.1 deflate.c (deflate_slow, level 6, memLevel 8, windowBits -15) ---------------

const MIN_MATCH: usize = 3;
const MAX_MATCH: usize = 258;
const W_SIZE: usize = 1 << 15;
const W_MASK: usize = W_SIZE - 1;
const WINDOW_SIZE: usize = 2 * W_SIZE;
const HASH_SIZE: usize = 1 << 15;
const HASH_MASK: usize = HASH_SIZE - 1;
const HASH_SHIFT: usize = 5;
const MIN_LOOKAHEAD: usize = MAX_MATCH + MIN_MATCH + 1;
const MAX_DIST: usize = W_SIZE - MIN_LOOKAHEAD;
const WIN_INIT: usize = MAX_MATCH;
const TOO_FAR: usize = 4096;
const GOOD_MATCH: usize = 8;
const MAX_LAZY: usize = 16;
const NICE_MATCH: usize = 128;
const MAX_CHAIN: usize = 128;
const LIT_BUFSIZE: usize = 1 << 14;

// --- trees.c ---------------------------------------------------------------------------------------

const LENGTH_CODES: usize = 29;
const LITERALS: usize = 256;
const L_CODES: usize = LITERALS + 1 + LENGTH_CODES;
const D_CODES: usize = 30;
const BL_CODES: usize = 19;
const HEAP_SIZE: usize = 2 * L_CODES + 1;
const MAX_BITS: usize = 15;
const MAX_BL_BITS: usize = 7;
const END_BLOCK: usize = 256;
const REP_3_6: usize = 16;
const REPZ_3_10: usize = 17;
const REPZ_11_138: usize = 18;
const EXTRA_LBITS: [u8; LENGTH_CODES] = [
    0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1, 2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4, 5, 5, 5, 5, 0,
];
const EXTRA_DBITS: [u8; D_CODES] = [
    0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 7, 7, 8, 8, 9, 9, 10, 10, 11, 11, 12, 12, 13,
    13,
];
const EXTRA_BLBITS: [u8; BL_CODES] = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2, 3, 7];
const BL_ORDER: [usize; BL_CODES] = [
    16, 17, 18, 0, 8, 7, 9, 6, 10, 5, 11, 4, 12, 3, 13, 2, 14, 1, 15,
];

/// `tr_static_init`'s tables.
struct Static {
    ltree_code: [u16; L_CODES + 2],
    ltree_len: [u16; L_CODES + 2],
    dtree_code: [u16; D_CODES],
    length_code: [u8; MAX_MATCH - MIN_MATCH + 1],
    dist_code: [u8; 512],
    base_length: [u16; LENGTH_CODES],
    base_dist: [u16; D_CODES],
}

fn bi_reverse(mut code: u32, mut len: usize) -> u16 {
    let mut res = 0u32;
    loop {
        res |= code & 1;
        code >>= 1;
        res <<= 1;
        len -= 1;
        if len == 0 {
            break;
        }
    }
    (res >> 1) as u16
}

fn gen_codes(code_of: &mut [u16], len_of: &[u16], max_code: usize, bl_count: &[u16; MAX_BITS + 1]) {
    let mut next_code = [0u16; MAX_BITS + 1];
    let mut code = 0u32;
    for bits in 1..=MAX_BITS {
        code = (code + u32::from(bl_count[bits - 1])) << 1;
        next_code[bits] = code as u16;
    }
    for n in 0..=max_code {
        let len = len_of[n] as usize;
        if len == 0 {
            continue;
        }
        code_of[n] = bi_reverse(u32::from(next_code[len]), len);
        next_code[len] = next_code[len].wrapping_add(1);
    }
}

fn statics() -> &'static Static {
    static TABLES: std::sync::OnceLock<Static> = std::sync::OnceLock::new();
    TABLES.get_or_init(|| {
        let mut s = Static {
            ltree_code: [0; L_CODES + 2],
            ltree_len: [0; L_CODES + 2],
            dtree_code: [0; D_CODES],
            length_code: [0; MAX_MATCH - MIN_MATCH + 1],
            dist_code: [0; 512],
            base_length: [0; LENGTH_CODES],
            base_dist: [0; D_CODES],
        };
        let mut length = 0usize;
        let mut code = 0usize;
        while code < LENGTH_CODES - 1 {
            s.base_length[code] = length as u16;
            for _ in 0..1usize << EXTRA_LBITS[code] {
                s.length_code[length] = code as u8;
                length += 1;
            }
            code += 1;
        }
        s.length_code[length - 1] = code as u8;
        let mut dist = 0usize;
        code = 0;
        while code < 16 {
            s.base_dist[code] = dist as u16;
            for _ in 0..1usize << EXTRA_DBITS[code] {
                s.dist_code[dist] = code as u8;
                dist += 1;
            }
            code += 1;
        }
        dist >>= 7;
        while code < D_CODES {
            s.base_dist[code] = (dist << 7) as u16;
            for _ in 0..1usize << (EXTRA_DBITS[code] - 7) {
                s.dist_code[256 + dist] = code as u8;
                dist += 1;
            }
            code += 1;
        }
        let mut bl_count = [0u16; MAX_BITS + 1];
        for n in 0..=L_CODES + 1 {
            let len = match n {
                0..=143 => 8,
                144..=255 => 9,
                256..=279 => 7,
                _ => 8,
            };
            s.ltree_len[n] = len;
            bl_count[len as usize] += 1;
        }
        let lens = s.ltree_len;
        gen_codes(&mut s.ltree_code, &lens, L_CODES + 1, &bl_count);
        for n in 0..D_CODES {
            s.dtree_code[n] = bi_reverse(n as u32, 5);
        }
        s
    })
}

fn d_code(s: &Static, dist: usize) -> usize {
    usize::from(if dist < 256 {
        s.dist_code[dist]
    } else {
        s.dist_code[256 + (dist >> 7)]
    })
}

/// A `ct_data` array: `fc` holds Freq then Code, `dl` holds Dad then Len, as zlib's unions do.
struct Tree {
    fc: Vec<u16>,
    dl: Vec<u16>,
    max_code: usize,
}

impl Tree {
    fn new(size: usize) -> Self {
        Self {
            fc: vec![0; size],
            dl: vec![0; size],
            max_code: 0,
        }
    }
}

#[derive(Clone, Copy)]
enum Kind {
    Literal,
    Distance,
    BitLength,
}

struct Heap {
    heap: [usize; HEAP_SIZE],
    heap_len: usize,
    heap_max: usize,
    depth: [u8; HEAP_SIZE],
    bl_count: [u16; MAX_BITS + 1],
    opt_len: u64,
    static_len: u64,
}

fn smaller(tree: &Tree, n: usize, m: usize, depth: &[u8]) -> bool {
    tree.fc[n] < tree.fc[m] || (tree.fc[n] == tree.fc[m] && depth[n] <= depth[m])
}

fn pqdownheap(h: &mut Heap, tree: &Tree, mut k: usize) {
    let v = h.heap[k];
    let mut j = k << 1;
    while j <= h.heap_len {
        if j < h.heap_len && smaller(tree, h.heap[j + 1], h.heap[j], &h.depth) {
            j += 1;
        }
        if smaller(tree, v, h.heap[j], &h.depth) {
            break;
        }
        h.heap[k] = h.heap[j];
        k = j;
        j <<= 1;
    }
    h.heap[k] = v;
}

fn gen_bitlen(h: &mut Heap, tree: &mut Tree, kind: Kind) {
    let s = statics();
    let max_code = tree.max_code;
    let (extra, base, max_length): (&[u8], usize, usize) = match kind {
        Kind::Literal => (&EXTRA_LBITS, LITERALS + 1, MAX_BITS),
        Kind::Distance => (&EXTRA_DBITS, 0, MAX_BITS),
        Kind::BitLength => (&EXTRA_BLBITS, 0, MAX_BL_BITS),
    };
    h.bl_count = [0; MAX_BITS + 1];
    tree.dl[h.heap[h.heap_max]] = 0;
    let mut overflow = 0i32;
    let mut hh = h.heap_max + 1;
    while hh < HEAP_SIZE {
        let n = h.heap[hh];
        let mut bits = tree.dl[tree.dl[n] as usize] as usize + 1;
        if bits > max_length {
            bits = max_length;
            overflow += 1;
        }
        tree.dl[n] = bits as u16;
        hh += 1;
        if n > max_code {
            continue;
        }
        h.bl_count[bits] += 1;
        let xbits = if n >= base {
            extra[n - base] as usize
        } else {
            0
        };
        let f = u64::from(tree.fc[n]);
        h.opt_len = h.opt_len.wrapping_add(f * (bits + xbits) as u64);
        let static_len = match kind {
            Kind::Literal => Some(s.ltree_len[n]),
            Kind::Distance => Some(5),
            Kind::BitLength => None,
        };
        if let Some(len) = static_len {
            h.static_len = h.static_len.wrapping_add(f * (len as usize + xbits) as u64);
        }
    }
    if overflow == 0 {
        return;
    }
    loop {
        let mut bits = max_length - 1;
        while h.bl_count[bits] == 0 {
            bits -= 1;
        }
        h.bl_count[bits] -= 1;
        h.bl_count[bits + 1] += 2;
        h.bl_count[max_length] -= 1;
        overflow -= 2;
        if overflow <= 0 {
            break;
        }
    }
    let mut hh = HEAP_SIZE;
    for bits in (1..=max_length).rev() {
        let mut n = h.bl_count[bits];
        while n != 0 {
            hh -= 1;
            let m = h.heap[hh];
            if m > max_code {
                continue;
            }
            if tree.dl[m] as usize != bits {
                let delta = (bits as u64)
                    .wrapping_sub(u64::from(tree.dl[m]))
                    .wrapping_mul(u64::from(tree.fc[m]));
                h.opt_len = h.opt_len.wrapping_add(delta);
                tree.dl[m] = bits as u16;
            }
            n -= 1;
        }
    }
}

fn build_tree(h: &mut Heap, tree: &mut Tree, kind: Kind) {
    let s = statics();
    let elems = match kind {
        Kind::Literal => L_CODES,
        Kind::Distance => D_CODES,
        Kind::BitLength => BL_CODES,
    };
    let mut max_code: isize = -1;
    h.heap_len = 0;
    h.heap_max = HEAP_SIZE;
    for n in 0..elems {
        if tree.fc[n] != 0 {
            h.heap_len += 1;
            h.heap[h.heap_len] = n;
            max_code = n as isize;
            h.depth[n] = 0;
        } else {
            tree.dl[n] = 0;
        }
    }
    while h.heap_len < 2 {
        let node = if max_code < 2 {
            max_code += 1;
            max_code as usize
        } else {
            0
        };
        h.heap_len += 1;
        h.heap[h.heap_len] = node;
        tree.fc[node] = 1;
        h.depth[node] = 0;
        h.opt_len = h.opt_len.wrapping_sub(1);
        match kind {
            Kind::Literal => h.static_len = h.static_len.wrapping_sub(u64::from(s.ltree_len[node])),
            Kind::Distance => h.static_len = h.static_len.wrapping_sub(5),
            Kind::BitLength => {}
        }
    }
    tree.max_code = max_code as usize;
    for n in (1..=h.heap_len / 2).rev() {
        pqdownheap(h, tree, n);
    }
    let mut node = elems;
    loop {
        let n = h.heap[1];
        h.heap[1] = h.heap[h.heap_len];
        h.heap_len -= 1;
        pqdownheap(h, tree, 1);
        let m = h.heap[1];
        h.heap_max -= 1;
        h.heap[h.heap_max] = n;
        h.heap_max -= 1;
        h.heap[h.heap_max] = m;
        tree.fc[node] = tree.fc[n].wrapping_add(tree.fc[m]);
        h.depth[node] = h.depth[n].max(h.depth[m]).wrapping_add(1);
        tree.dl[n] = node as u16;
        tree.dl[m] = node as u16;
        h.heap[1] = node;
        node += 1;
        pqdownheap(h, tree, 1);
        if h.heap_len < 2 {
            break;
        }
    }
    h.heap_max -= 1;
    h.heap[h.heap_max] = h.heap[1];
    gen_bitlen(h, tree, kind);
    let lens = tree.dl.clone();
    let bl_count = h.bl_count;
    gen_codes(&mut tree.fc, &lens, tree.max_code, &bl_count);
}

/// The repeat-run shape shared by `scan_tree` and `send_tree`.
fn runs(tree: &mut Tree, max_code: usize, mut emit: impl FnMut(usize, usize, isize)) {
    let mut prevlen: isize = -1;
    let mut nextlen = tree.dl[0] as usize;
    let mut count = 0usize;
    let (mut max_count, mut min_count) = if nextlen == 0 { (138, 3) } else { (7, 4) };
    tree.dl[max_code + 1] = 0xffff;
    for n in 0..=max_code {
        let curlen = nextlen;
        nextlen = tree.dl[n + 1] as usize;
        count += 1;
        if count < max_count && curlen == nextlen {
            continue;
        }
        let kind = if count < min_count {
            0
        } else if curlen != 0 {
            1
        } else if count <= 10 {
            2
        } else {
            3
        };
        emit(
            kind,
            curlen,
            if kind == 1 { prevlen } else { count as isize },
        );
        if kind == 1 {
            emit(4, count, prevlen);
        }
        count = 0;
        prevlen = curlen as isize;
        (max_count, min_count) = if nextlen == 0 {
            (138, 3)
        } else if curlen == nextlen {
            (6, 3)
        } else {
            (7, 4)
        };
    }
}

#[derive(Default)]
struct Bits {
    out: Vec<u8>,
    buf: u64,
    count: u32,
}

impl Bits {
    fn send(&mut self, value: u32, length: u32) {
        self.buf |= u64::from(value) << self.count;
        self.count += length;
        while self.count >= 8 {
            self.out.push(self.buf as u8);
            self.buf >>= 8;
            self.count -= 8;
        }
    }

    fn windup(&mut self) {
        if self.count > 0 {
            self.out.push(self.buf as u8);
        }
        self.buf = 0;
        self.count = 0;
    }
}

/// A block's literal codes and lengths, distance codes and lengths (None: the fixed five bits).
type Codes<'a> = (&'a [u16], &'a [u16], &'a [u16], Option<&'a [u16]>);

struct Trees {
    ltree: Tree,
    dtree: Tree,
    bltree: Tree,
    heap: Heap,
    syms: Vec<(u16, u8)>,
    bits: Bits,
}

impl Trees {
    fn new() -> Self {
        let mut trees = Self {
            ltree: Tree::new(HEAP_SIZE),
            dtree: Tree::new(2 * D_CODES + 1),
            bltree: Tree::new(2 * BL_CODES + 1),
            heap: Heap {
                heap: [0; HEAP_SIZE],
                heap_len: 0,
                heap_max: 0,
                depth: [0; HEAP_SIZE],
                bl_count: [0; MAX_BITS + 1],
                opt_len: 0,
                static_len: 0,
            },
            syms: Vec::with_capacity(LIT_BUFSIZE),
            bits: Bits::default(),
        };
        trees.init_block();
        trees
    }

    fn init_block(&mut self) {
        self.ltree.fc[..L_CODES].fill(0);
        self.dtree.fc[..D_CODES].fill(0);
        self.bltree.fc[..BL_CODES].fill(0);
        self.ltree.fc[END_BLOCK] = 1;
        self.heap.opt_len = 0;
        self.heap.static_len = 0;
        self.syms.clear();
    }

    /// `_tr_tally`: true when the symbol buffer is full.
    fn tally(&mut self, dist: usize, lc: usize) -> bool {
        self.syms.push((dist as u16, lc as u8));
        if dist == 0 {
            self.ltree.fc[lc] += 1;
        } else {
            let s = statics();
            self.ltree.fc[usize::from(s.length_code[lc]) + LITERALS + 1] += 1;
            self.dtree.fc[d_code(s, dist - 1)] += 1;
        }
        self.syms.len() == LIT_BUFSIZE - 1
    }

    fn scan_tree(&mut self, literal: bool) {
        let bl = &mut self.bltree;
        let tree = if literal {
            &mut self.ltree
        } else {
            &mut self.dtree
        };
        let max_code = tree.max_code;
        runs(tree, max_code, |kind, curlen, extra| match kind {
            0 => bl.fc[curlen] += extra as u16,
            1 => {
                if curlen as isize != extra {
                    bl.fc[curlen] += 1;
                }
                bl.fc[REP_3_6] += 1;
            }
            2 => bl.fc[REPZ_3_10] += 1,
            3 => bl.fc[REPZ_11_138] += 1,
            _ => {}
        });
    }

    fn send_tree(&mut self, literal: bool, max_code: usize) {
        let bl = &self.bltree;
        let bits = &mut self.bits;
        let tree = if literal {
            &mut self.ltree
        } else {
            &mut self.dtree
        };
        let send_code =
            |bits: &mut Bits, c: usize| bits.send(u32::from(bl.fc[c]), u32::from(bl.dl[c]));
        let mut pending = 0usize;
        runs(tree, max_code, |kind, curlen, extra| match kind {
            0 => {
                for _ in 0..extra {
                    send_code(bits, curlen);
                }
            }
            1 => {
                pending = 0;
                if curlen as isize != extra {
                    send_code(bits, curlen);
                    pending = 1;
                }
            }
            2 => {
                send_code(bits, REPZ_3_10);
                bits.send(extra as u32 - 3, 3);
            }
            3 => {
                send_code(bits, REPZ_11_138);
                bits.send(extra as u32 - 11, 7);
            }
            _ => {
                send_code(bits, REP_3_6);
                bits.send((curlen - pending) as u32 - 3, 2);
            }
        });
    }

    fn compress_block(&mut self, fixed: bool) {
        let s = statics();
        let (lcode, llen, dcode, dlen): Codes<'_> = if fixed {
            (&s.ltree_code, &s.ltree_len, &s.dtree_code, None)
        } else {
            (
                &self.ltree.fc,
                &self.ltree.dl,
                &self.dtree.fc,
                Some(&self.dtree.dl),
            )
        };
        let bits = &mut self.bits;
        for &(dist, lc) in &self.syms {
            let (dist, lc) = (dist as usize, lc as usize);
            if dist == 0 {
                bits.send(u32::from(lcode[lc]), u32::from(llen[lc]));
                continue;
            }
            let code = s.length_code[lc] as usize;
            bits.send(
                u32::from(lcode[code + LITERALS + 1]),
                u32::from(llen[code + LITERALS + 1]),
            );
            let extra = u32::from(EXTRA_LBITS[code]);
            if extra != 0 {
                bits.send((lc - s.base_length[code] as usize) as u32, extra);
            }
            let dist = dist - 1;
            let code = d_code(s, dist);
            bits.send(
                u32::from(dcode[code]),
                dlen.map_or(5, |d| u32::from(d[code])),
            );
            let extra = u32::from(EXTRA_DBITS[code]);
            if extra != 0 {
                bits.send((dist - s.base_dist[code] as usize) as u32, extra);
            }
        }
        bits.send(u32::from(lcode[END_BLOCK]), u32::from(llen[END_BLOCK]));
    }

    /// `_tr_flush_block`.
    fn flush_block(&mut self, buf: Option<&[u8]>, stored_len: usize, last: bool) {
        build_tree(&mut self.heap, &mut self.ltree, Kind::Literal);
        build_tree(&mut self.heap, &mut self.dtree, Kind::Distance);
        self.scan_tree(true);
        self.scan_tree(false);
        build_tree(&mut self.heap, &mut self.bltree, Kind::BitLength);
        let mut max_blindex = BL_CODES - 1;
        while max_blindex >= 3 {
            if self.bltree.dl[BL_ORDER[max_blindex]] != 0 {
                break;
            }
            max_blindex -= 1;
        }
        self.heap.opt_len = self
            .heap
            .opt_len
            .wrapping_add(3 * (max_blindex as u64 + 1) + 5 + 5 + 4);
        let mut opt_lenb = self.heap.opt_len.wrapping_add(3 + 7) >> 3;
        let static_lenb = self.heap.static_len.wrapping_add(3 + 7) >> 3;
        if static_lenb <= opt_lenb {
            opt_lenb = static_lenb;
        }
        let last_bit = u32::from(last);
        match buf {
            Some(buf) if stored_len as u64 + 4 <= opt_lenb => {
                self.bits.send(last_bit, 3);
                self.bits.windup();
                self.bits
                    .out
                    .extend_from_slice(&(stored_len as u16).to_le_bytes());
                self.bits
                    .out
                    .extend_from_slice(&(!(stored_len as u16)).to_le_bytes());
                self.bits.out.extend_from_slice(&buf[..stored_len]);
            }
            _ if static_lenb == opt_lenb => {
                self.bits.send((1 << 1) + last_bit, 3);
                self.compress_block(true);
            }
            _ => {
                self.bits.send((2 << 1) + last_bit, 3);
                let (lcodes, dcodes, blcodes) = (
                    self.ltree.max_code + 1,
                    self.dtree.max_code + 1,
                    max_blindex + 1,
                );
                self.bits.send(lcodes as u32 - 257, 5);
                self.bits.send(dcodes as u32 - 1, 5);
                self.bits.send(blcodes as u32 - 4, 4);
                for &order in &BL_ORDER[..blcodes] {
                    self.bits.send(u32::from(self.bltree.dl[order]), 3);
                }
                self.send_tree(true, lcodes - 1);
                self.send_tree(false, dcodes - 1);
                self.compress_block(false);
            }
        }
        self.init_block();
        if last {
            self.bits.windup();
        }
    }
}

struct Deflate<'a> {
    input: &'a [u8],
    next_in: usize,
    window: Vec<u8>,
    prev: Vec<u16>,
    head: Vec<u16>,
    ins_h: usize,
    strstart: usize,
    block_start: isize,
    lookahead: usize,
    insert: usize,
    match_start: usize,
    match_length: usize,
    prev_length: usize,
    prev_match: usize,
    match_available: bool,
    high_water: usize,
    trees: Trees,
}

impl Deflate<'_> {
    fn update_hash(&mut self, c: u8) {
        self.ins_h = ((self.ins_h << HASH_SHIFT) ^ usize::from(c)) & HASH_MASK;
    }

    /// `INSERT_STRING`: the previous head of the string's hash chain.
    fn insert_string(&mut self, at: usize) -> usize {
        self.update_hash(self.window[at + MIN_MATCH - 1]);
        let head = self.head[self.ins_h];
        self.prev[at & W_MASK] = head;
        self.head[self.ins_h] = at as u16;
        usize::from(head)
    }

    fn fill_window(&mut self) {
        loop {
            let mut more = WINDOW_SIZE - self.lookahead - self.strstart;
            if self.strstart >= W_SIZE + MAX_DIST {
                self.window.copy_within(W_SIZE..W_SIZE + (W_SIZE - more), 0);
                self.match_start = self.match_start.wrapping_sub(W_SIZE);
                self.strstart -= W_SIZE;
                self.block_start -= W_SIZE as isize;
                if self.insert > self.strstart {
                    self.insert = self.strstart;
                }
                for slot in self.head.iter_mut().chain(self.prev.iter_mut()) {
                    *slot = if usize::from(*slot) >= W_SIZE {
                        *slot - W_SIZE as u16
                    } else {
                        0
                    };
                }
                more += W_SIZE;
            }
            if self.next_in == self.input.len() {
                break;
            }
            let n = more.min(self.input.len() - self.next_in);
            let at = self.strstart + self.lookahead;
            self.window[at..at + n].copy_from_slice(&self.input[self.next_in..self.next_in + n]);
            self.next_in += n;
            self.lookahead += n;
            if self.lookahead + self.insert >= MIN_MATCH {
                let mut str = self.strstart - self.insert;
                self.ins_h = usize::from(self.window[str]);
                self.update_hash(self.window[str + 1]);
                while self.insert > 0 {
                    self.insert_string(str);
                    str += 1;
                    self.insert -= 1;
                    if self.lookahead + self.insert < MIN_MATCH {
                        break;
                    }
                }
            }
            if !(self.lookahead < MIN_LOOKAHEAD && self.next_in != self.input.len()) {
                break;
            }
        }
        if self.high_water < WINDOW_SIZE {
            let curr = self.strstart + self.lookahead;
            if self.high_water < curr {
                let init = (WINDOW_SIZE - curr).min(WIN_INIT);
                self.window[curr..curr + init].fill(0);
                self.high_water = curr + init;
            } else if self.high_water < curr + WIN_INIT {
                let init = (curr + WIN_INIT - self.high_water).min(WINDOW_SIZE - self.high_water);
                self.window[self.high_water..self.high_water + init].fill(0);
                self.high_water += init;
            }
        }
    }

    fn longest_match(&mut self, mut cur_match: usize) -> usize {
        let mut chain_length = MAX_CHAIN;
        let scan = self.strstart;
        let mut best_len = self.prev_length;
        let mut nice_match = NICE_MATCH;
        let limit = self.strstart.saturating_sub(MAX_DIST);
        let w = &self.window;
        let mut scan_end1 = w[scan + best_len - 1];
        let mut scan_end = w[scan + best_len];
        if self.prev_length >= GOOD_MATCH {
            chain_length >>= 2;
        }
        if nice_match > self.lookahead {
            nice_match = self.lookahead;
        }
        loop {
            let m = cur_match;
            if !(w[m + best_len] != scan_end
                || w[m + best_len - 1] != scan_end1
                || w[m] != w[scan]
                || w[m + 1] != w[scan + 1])
            {
                // scan[2] and match[2] are not compared: zlib relies on the hash for them.
                let mut i = 2;
                'run: loop {
                    for _ in 0..8 {
                        i += 1;
                        if w[scan + i] != w[m + i] {
                            break 'run;
                        }
                    }
                    if i >= MAX_MATCH {
                        break;
                    }
                }
                let len = i;
                if len > best_len {
                    self.match_start = cur_match;
                    best_len = len;
                    if len >= nice_match {
                        break;
                    }
                    scan_end1 = w[scan + best_len - 1];
                    scan_end = w[scan + best_len];
                }
            }
            cur_match = usize::from(self.prev[cur_match & W_MASK]);
            if cur_match <= limit {
                break;
            }
            chain_length -= 1;
            if chain_length == 0 {
                break;
            }
        }
        best_len.min(self.lookahead)
    }

    fn flush_block(&mut self, last: bool) {
        let stored_len = (self.strstart as isize - self.block_start) as usize;
        let buf = (self.block_start >= 0).then(|| &self.window[self.block_start as usize..]);
        self.trees.flush_block(buf, stored_len, last);
        self.block_start = self.strstart as isize;
    }

    /// `deflate_slow` run to the end with `Z_FINISH`.
    fn run(&mut self) {
        loop {
            if self.lookahead < MIN_LOOKAHEAD {
                self.fill_window();
                if self.lookahead == 0 {
                    break;
                }
            }
            let mut hash_head = 0;
            if self.lookahead >= MIN_MATCH {
                hash_head = self.insert_string(self.strstart);
            }
            self.prev_length = self.match_length;
            self.prev_match = self.match_start;
            self.match_length = MIN_MATCH - 1;
            if hash_head != 0
                && self.prev_length < MAX_LAZY
                && self.strstart.wrapping_sub(hash_head) <= MAX_DIST
            {
                self.match_length = self.longest_match(hash_head);
                if self.match_length == MIN_MATCH && self.strstart - self.match_start > TOO_FAR {
                    self.match_length = MIN_MATCH - 1;
                }
            }
            if self.prev_length >= MIN_MATCH && self.match_length <= self.prev_length {
                let max_insert = self.strstart + self.lookahead - MIN_MATCH;
                let bflush = self.trees.tally(
                    self.strstart - 1 - self.prev_match,
                    self.prev_length - MIN_MATCH,
                );
                self.lookahead -= self.prev_length - 1;
                self.prev_length -= 2;
                loop {
                    self.strstart += 1;
                    if self.strstart <= max_insert {
                        self.insert_string(self.strstart);
                    }
                    self.prev_length -= 1;
                    if self.prev_length == 0 {
                        break;
                    }
                }
                self.match_available = false;
                self.match_length = MIN_MATCH - 1;
                self.strstart += 1;
                if bflush {
                    self.flush_block(false);
                }
            } else if self.match_available {
                let bflush = self
                    .trees
                    .tally(0, usize::from(self.window[self.strstart - 1]));
                if bflush {
                    self.flush_block(false);
                }
                self.strstart += 1;
                self.lookahead -= 1;
            } else {
                self.match_available = true;
                self.strstart += 1;
                self.lookahead -= 1;
            }
        }
        if self.match_available {
            self.trees
                .tally(0, usize::from(self.window[self.strstart - 1]));
            self.match_available = false;
        }
        self.insert = self.strstart.min(MIN_MATCH - 1);
        self.flush_block(true);
    }
}

/// Raw deflate of <data> at zlib's default level and memLevel: what `compressobj(-1, DEFLATED, -15)`'s
/// `compress(data) + flush()` returns.
pub fn deflate_raw(data: &[u8]) -> Vec<u8> {
    let mut state = Deflate {
        input: data,
        next_in: 0,
        window: vec![0; WINDOW_SIZE],
        prev: vec![0; W_SIZE],
        head: vec![0; HASH_SIZE],
        ins_h: 0,
        strstart: 0,
        block_start: 0,
        lookahead: 0,
        insert: 0,
        match_start: 0,
        match_length: MIN_MATCH - 1,
        prev_length: MIN_MATCH - 1,
        prev_match: 0,
        match_available: false,
        high_water: 0,
        trees: Trees::new(),
    };
    state.run();
    std::mem::take(&mut state.trees.bits.out)
}

// --- inflate ---------------------------------------------------------------------------------------

enum Stop {
    Truncated,
    Data(&'static str),
}

impl Stop {
    fn error(self) -> PyErr {
        PyErr::new(
            "error",
            match self {
                Stop::Truncated => {
                    "Error -5 while decompressing data: incomplete or truncated stream".to_owned()
                }
                Stop::Data(message) => format!("Error -3 while decompressing data: {message}"),
            },
        )
    }
}

struct Reader<'a> {
    data: &'a [u8],
    pos: usize,
    buf: u64,
    count: u32,
}

impl Reader<'_> {
    fn bits(&mut self, n: u32) -> Result<u32, Stop> {
        while self.count < n {
            let Some(&byte) = self.data.get(self.pos) else {
                return Err(Stop::Truncated);
            };
            self.pos += 1;
            self.buf |= u64::from(byte) << self.count;
            self.count += 8;
        }
        let value = (self.buf & ((1u64 << n) - 1)) as u32;
        self.buf >>= n;
        self.count -= n;
        Ok(value)
    }
}

#[derive(PartialEq)]
enum Table {
    Codes,
    Lens,
    Dists,
}

/// A canonical code as `inflate_table` accepts it: `max` is 0 for a code with no symbols.
struct Huffman {
    count: [u16; 16],
    symbol: Vec<u16>,
    max: usize,
}

impl Huffman {
    /// None when `inflate_table` refuses the lengths: over-subscribed, or incomplete for anything but
    /// a single one-bit code of lengths or distances.
    fn new(lens: &[u16], table: Table) -> Option<Self> {
        let mut count = [0u16; 16];
        for &len in lens {
            count[len as usize] += 1;
        }
        let max = (1..16).rev().find(|&len| count[len] != 0).unwrap_or(0);
        if max != 0 {
            let mut left = 1i32;
            for &n in &count[1..] {
                left = (left << 1) - i32::from(n);
                if left < 0 {
                    return None;
                }
            }
            if left > 0 && (table == Table::Codes || max != 1) {
                return None;
            }
        }
        let mut offs = [0u16; 16];
        for len in 1..15 {
            offs[len + 1] = offs[len] + count[len];
        }
        let mut symbol = vec![0u16; lens.len()];
        for (sym, &len) in lens.iter().enumerate() {
            if len != 0 {
                symbol[offs[len as usize] as usize] = sym as u16;
                offs[len as usize] += 1;
            }
        }
        count[0] = 0;
        Some(Self { count, symbol, max })
    }

    /// The next symbol, or None for zlib's invalid-code marker (a code with no symbols, or the one
    /// pattern an incomplete one-bit code leaves out); either takes one bit.
    fn decode(&self, reader: &mut Reader<'_>) -> Result<Option<u16>, Stop> {
        let (mut code, mut first, mut index) = (0i32, 0i32, 0i32);
        for len in 1..=self.max.max(1) {
            code |= reader.bits(1)? as i32;
            let count = i32::from(self.count[len]);
            if code - count < first {
                return Ok(Some(self.symbol[(index + code - first) as usize]));
            }
            index += count;
            first = (first + count) << 1;
            code <<= 1;
        }
        Ok(None)
    }
}

const LBASE: [u16; 29] = [
    3, 4, 5, 6, 7, 8, 9, 10, 11, 13, 15, 17, 19, 23, 27, 31, 35, 43, 51, 59, 67, 83, 99, 115, 131,
    163, 195, 227, 258,
];
const DBASE: [u16; 30] = [
    1, 2, 3, 4, 5, 7, 9, 13, 17, 25, 33, 49, 65, 97, 129, 193, 257, 385, 513, 769, 1025, 1537,
    2049, 3073, 4097, 6145, 8193, 12289, 16385, 24577,
];

fn inflate(data: &[u8]) -> Result<Vec<u8>, Stop> {
    let mut reader = Reader {
        data,
        pos: 0,
        buf: 0,
        count: 0,
    };
    let mut out = Vec::new();
    loop {
        let last = reader.bits(1)? == 1;
        match reader.bits(2)? {
            0 => {
                let drop = reader.count % 8;
                reader.bits(drop)?;
                let len = reader.bits(16)?;
                let nlen = reader.bits(16)?;
                if len != nlen ^ 0xffff {
                    return Err(Stop::Data("invalid stored block lengths"));
                }
                for _ in 0..len {
                    out.push(reader.bits(8)? as u8);
                }
            }
            kind @ (1 | 2) => {
                let (lit, dist) = if kind == 1 {
                    let mut lens = [8u16; 288];
                    lens[144..256].fill(9);
                    lens[256..280].fill(7);
                    (
                        Huffman::new(&lens, Table::Lens),
                        Huffman::new(&[5u16; 32], Table::Dists),
                    )
                } else {
                    let nlen = reader.bits(5)? as usize + 257;
                    let ndist = reader.bits(5)? as usize + 1;
                    let ncode = reader.bits(4)? as usize + 4;
                    if nlen > 286 || ndist > 30 {
                        return Err(Stop::Data("too many length or distance symbols"));
                    }
                    let mut code_lens = [0u16; 19];
                    for &order in &BL_ORDER[..ncode] {
                        code_lens[order] = reader.bits(3)? as u16;
                    }
                    let codes = Huffman::new(&code_lens, Table::Codes)
                        .ok_or(Stop::Data("invalid code lengths set"))?;
                    let mut lens = vec![0u16; nlen + ndist];
                    let mut have = 0;
                    while have < nlen + ndist {
                        let sym = codes.decode(&mut reader)?.unwrap_or(0);
                        if sym < 16 {
                            lens[have] = sym;
                            have += 1;
                            continue;
                        }
                        let (len, copy) = match sym {
                            16 => {
                                let copy = 3 + reader.bits(2)? as usize;
                                if have == 0 {
                                    return Err(Stop::Data("invalid bit length repeat"));
                                }
                                (lens[have - 1], copy)
                            }
                            17 => (0, 3 + reader.bits(3)? as usize),
                            _ => (0, 11 + reader.bits(7)? as usize),
                        };
                        if have + copy > nlen + ndist {
                            return Err(Stop::Data("invalid bit length repeat"));
                        }
                        lens[have..have + copy].fill(len);
                        have += copy;
                    }
                    if lens[256] == 0 {
                        return Err(Stop::Data("invalid code -- missing end-of-block"));
                    }
                    let lit = Huffman::new(&lens[..nlen], Table::Lens)
                        .ok_or(Stop::Data("invalid literal/lengths set"))?;
                    let dist = Huffman::new(&lens[nlen..], Table::Dists)
                        .ok_or(Stop::Data("invalid distances set"))?;
                    (Some(lit), Some(dist))
                };
                let (lit, dist) = (
                    lit.expect("fixed lengths are complete"),
                    dist.expect("fixed distances are complete"),
                );
                loop {
                    let sym = lit
                        .decode(&mut reader)?
                        .ok_or(Stop::Data("invalid literal/length code"))?
                        as usize;
                    if sym < 256 {
                        out.push(sym as u8);
                        continue;
                    }
                    if sym == 256 {
                        break;
                    }
                    let index = sym - 257;
                    if index >= 29 {
                        return Err(Stop::Data("invalid literal/length code"));
                    }
                    let length = LBASE[index] as usize
                        + reader.bits(u32::from(EXTRA_LBITS[index]))? as usize;
                    let dsym = dist
                        .decode(&mut reader)?
                        .ok_or(Stop::Data("invalid distance code"))?
                        as usize;
                    if dsym >= 30 {
                        return Err(Stop::Data("invalid distance code"));
                    }
                    let distance =
                        DBASE[dsym] as usize + reader.bits(u32::from(EXTRA_DBITS[dsym]))? as usize;
                    if distance > out.len() {
                        return Err(Stop::Data("invalid distance too far back"));
                    }
                    let from = out.len() - distance;
                    for at in from..from + length {
                        out.push(out[at]);
                    }
                }
            }
            _ => return Err(Stop::Data("invalid block type")),
        }
        if last {
            return Ok(out);
        }
    }
}

/// `zlib.decompress(data, -15)`: bytes after the final block are ignored, as zlib does.
pub fn inflate_raw(data: &[u8]) -> Result<Vec<u8>, PyErr> {
    inflate(data).map_err(Stop::error)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_round_trips_and_pads() {
        assert_eq!(b64encode(b"ab"), b"YWI=");
        assert_eq!(b64decode(b"YW I=").unwrap(), b"ab");
        assert_eq!(b64decode(b"AB==CD").unwrap(), b"\0");
        assert_eq!(b64decode(b"AB").unwrap_err().message, "Incorrect padding");
    }

    #[test]
    fn deflate_matches_zlib() {
        assert_eq!(deflate_raw(b""), [3, 0]);
        // zlib.compressobj(-1, zlib.DEFLATED, -15) on b"abcabcabcabc" + b"x" * 40
        let data = [b"abcabcabcabc".as_slice(), &[b'x'; 40]].concat();
        let packed = deflate_raw(&data);
        assert_eq!(inflate_raw(&packed).unwrap(), data);
    }

    #[test]
    fn inflate_reports_zlib_errors() {
        assert!(
            inflate_raw(b"")
                .unwrap_err()
                .message
                .ends_with("incomplete or truncated stream")
        );
        assert!(
            inflate_raw(b"\x07")
                .unwrap_err()
                .message
                .ends_with("invalid block type")
        );
    }
}
