// The ASTC oracle: Arm astcenc at the source astc-encoder-py 0.1.12 ships (commit 631fb04e1c4b), built
// the way its Windows wheel is (scalar ISA, MSVC /fp:precise, invariance on), so the Rust port of
// astcenc (rust/hokace/astcenc) has a reference it can be traced against, not only the final bytes.
//
//   oracle <manifest>    each line: <width> <height> <bx> <by> <input.rgba> <output.astc>
//   oracle --dump <bx> <by> <out.bin>    the context's config and block-size descriptor, laid out as
//                                        rust/hokace/astcenc/src/dump.rs writes them
//
// Every image is encoded at LDR, quality 85, no flags, identity swizzle, one thread, with one context
// per footprint, as tools/mobile_graphics.py encodes it.
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <algorithm>
#include <fstream>
#include <map>
#include <sstream>
#include <string>
#include <vector>

#include "astcenc.h"
#include "astcenc_internal_entry.h"

struct Writer {
	std::vector<unsigned char> b;
	void u8(uint8_t v) { b.push_back(v); }
	void u16(uint16_t v) { u8(v & 0xFF); u8(v >> 8); }
	void u32(uint32_t v) { u16(v & 0xFFFF); u16(v >> 16); }
	void f32(float v) { uint32_t u; std::memcpy(&u, &v, 4); u32(u); }
	void u64(uint64_t v) { u32(uint32_t(v)); u32(uint32_t(v >> 32)); }
};

static unsigned simd(unsigned n) { return (n + 3) / 4 * 4; }

static int dump(unsigned bx, unsigned by, const char* out) {
	astcenc_config config;
	astcenc_context* context = nullptr;
	if (astcenc_config_init(ASTCENC_PRF_LDR, bx, by, 1, 85.0f, 0, &config) != ASTCENC_SUCCESS ||
	    astcenc_context_alloc(&config, 1, &context) != ASTCENC_SUCCESS) return 1;
	const astcenc_contexti& ctx = context->context;
	const astcenc_config& c = ctx.config;
	Writer w;
	for (unsigned v : {c.tune_partition_count_limit, c.tune_2partition_index_limit, c.tune_3partition_index_limit,
	                   c.tune_4partition_index_limit, c.tune_block_mode_limit, c.tune_refinement_limit,
	                   c.tune_candidate_limit, c.tune_2partitioning_candidate_limit,
	                   c.tune_3partitioning_candidate_limit, c.tune_4partitioning_candidate_limit}) w.u32(v);
	for (float v : {c.tune_db_limit, c.tune_mse_overshoot, c.tune_2partition_early_out_limit_factor,
	                c.tune_3partition_early_out_limit_factor, c.tune_2plane_early_out_limit_correlation,
	                c.tune_search_mode0_enable, c.cw_r_weight, c.cw_g_weight, c.cw_b_weight, c.cw_a_weight}) w.f32(v);
	const block_size_descriptor& b = *ctx.bsd;
	w.u8(b.xdim); w.u8(b.ydim); w.u8(b.zdim); w.u8(b.texel_count);
	for (unsigned v : {b.decimation_mode_count_always, b.decimation_mode_count_selected, b.decimation_mode_count_all,
	                   b.block_mode_count_1plane_always, b.block_mode_count_1plane_selected,
	                   b.block_mode_count_1plane_2plane_selected, b.block_mode_count_all}) w.u32(v);
	for (int i = 0; i < 4; i++) { w.u32(b.partitioning_count_selected[i]); w.u32(b.partitioning_count_all[i]); }
	for (unsigned i = 0; i < b.decimation_mode_count_all; i++) {
		const decimation_mode& dm = b.decimation_modes[i];
		w.u8(uint8_t(dm.maxprec_1plane)); w.u8(uint8_t(dm.maxprec_2planes)); w.u16(dm.refprec_1plane); w.u16(dm.refprec_2planes);
	}
	for (unsigned d = 0; d < b.decimation_mode_count_all; d++) {
		const decimation_info& di = b.decimation_tables[d];
		w.u8(di.texel_count); w.u8(di.max_texel_weight_count); w.u8(di.weight_count);
		w.u8(di.weight_x); w.u8(di.weight_y); w.u8(di.weight_z);
		unsigned tcs = simd(di.texel_count), wcs = simd(di.weight_count);
		for (unsigned i = 0; i < tcs; i++) w.u8(di.texel_weight_count[i]);
		for (int j = 0; j < 4; j++)
			for (unsigned i = 0; i < tcs; i++) {
				w.u8(di.texel_weights_tr[j][i]); w.u8(di.texel_weight_contribs_int_tr[j][i]);
				w.f32(di.texel_weight_contribs_float_tr[j][i]);
			}
		unsigned max_tcw = 0;
		for (unsigned i = 0; i < di.weight_count; i++) max_tcw = std::max<unsigned>(max_tcw, di.weight_texel_count[i]);
		for (unsigned i = 0; i < wcs; i++) {
			w.u8(di.weight_texel_count[i]);
			for (unsigned j = 0; j < max_tcw; j++) { w.u8(di.weight_texels_tr[j][i]); w.f32(di.weights_texel_contribs_tr[j][i]); }
			unsigned n = i < di.weight_count ? di.weight_texel_count[i] : 0;
			for (unsigned j = 0; j < n; j++) w.f32(di.texel_contrib_for_weight[j][i]);
		}
	}
	for (unsigned i = 0; i < WEIGHTS_MAX_BLOCK_MODES; i++) w.u16(b.block_mode_packed_index[i]);
	for (unsigned i = 0; i < b.block_mode_count_all; i++) {
		const block_mode& bm = b.block_modes[i];
		w.u16(bm.mode_index); w.u8(bm.decimation_mode); w.u8(bm.quant_mode); w.u8(bm.weight_bits); w.u8(bm.is_dual_plane);
	}
	for (unsigned pc = 1; pc <= 4; pc++)
		for (unsigned k = 0; k < b.partitioning_count_all[pc - 1]; k++) {
			const partition_info& pi = b.get_raw_partition_info(pc, k);
			w.u16(pi.partition_count); w.u16(pi.partition_index);
			for (int i = 0; i < 4; i++) w.u8(pi.partition_texel_count[i]);
			for (unsigned i = 0; i < b.texel_count; i++) w.u8(pi.partition_of_texel[i]);
			for (unsigned p = 0; p < pi.partition_count; p++)
				for (unsigned i = 0; i < simd(pi.partition_texel_count[p]); i++) w.u8(pi.texels_of_partition[p][i]);
			if (pc == 2) for (int i = 0; i < 2; i++) w.u64(b.coverage_bitmaps_2[k][i]);
			if (pc == 3) for (int i = 0; i < 3; i++) w.u64(b.coverage_bitmaps_3[k][i]);
			if (pc == 4) for (int i = 0; i < 4; i++) w.u64(b.coverage_bitmaps_4[k][i]);
		}
	for (int r = 0; r < 3; r++) for (unsigned i = 0; i < BLOCK_MAX_PARTITIONINGS; i++) w.u16(b.partitioning_packed_index[r][i]);
	for (unsigned i = 0; i < std::min<unsigned>(b.texel_count, BLOCK_MAX_KMEANS_TEXELS); i++) w.u8(b.kmeans_texels[i]);
	std::ofstream(out, std::ios::binary).write(reinterpret_cast<const char*>(w.b.data()), w.b.size());
	return 0;
}

static std::vector<unsigned char> read_file(const std::string& path) {
	std::ifstream in(path, std::ios::binary);
	return std::vector<unsigned char>((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
}

int main(int argc, char** argv) {
	if (argc == 5 && std::string(argv[1]) == "--dump") return dump(std::atoi(argv[2]), std::atoi(argv[3]), argv[4]);
	if (argc != 2) {
		std::fprintf(stderr, "usage: oracle <manifest>\n");
		return 2;
	}
	std::map<std::pair<unsigned, unsigned>, astcenc_context*> contexts;
	std::ifstream manifest(argv[1]);
	std::string line;
	int count = 0;
	while (std::getline(manifest, line)) {
		std::istringstream fields(line);
		unsigned width, height, bx, by;
		std::string input, output;
		if (!(fields >> width >> height >> bx >> by >> input >> output)) continue;
		astcenc_context*& context = contexts[{bx, by}];
		if (!context) {
			astcenc_config config;
			if (astcenc_config_init(ASTCENC_PRF_LDR, bx, by, 1, 85.0f, 0, &config) != ASTCENC_SUCCESS ||
			    astcenc_context_alloc(&config, 1, &context) != ASTCENC_SUCCESS) {
				std::fprintf(stderr, "context %ux%u failed\n", bx, by);
				return 1;
			}
		}
		std::vector<unsigned char> rgba = read_file(input);
		if (rgba.size() != size_t(width) * height * 4) {
			std::fprintf(stderr, "%s: %zu bytes, expected %u\n", input.c_str(), rgba.size(), width * height * 4);
			return 1;
		}
		void* slices[1] = {rgba.data()};
		astcenc_image image {width, height, 1, ASTCENC_TYPE_U8, slices};
		astcenc_swizzle swizzle {ASTCENC_SWZ_R, ASTCENC_SWZ_G, ASTCENC_SWZ_B, ASTCENC_SWZ_A};
		size_t size = size_t((width + bx - 1) / bx) * ((height + by - 1) / by) * 16;
		std::vector<unsigned char> blocks(size);
		if (astcenc_compress_image(context, &image, &swizzle, blocks.data(), size, 0) != ASTCENC_SUCCESS ||
		    astcenc_compress_reset(context) != ASTCENC_SUCCESS) {
			std::fprintf(stderr, "%s: compress failed\n", input.c_str());
			return 1;
		}
		std::ofstream(output, std::ios::binary).write(reinterpret_cast<const char*>(blocks.data()), size);
		count++;
	}
	std::printf("%d images\n", count);
	return 0;
}
