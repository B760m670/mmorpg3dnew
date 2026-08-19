// МОСТ ПОЛЯ ВОДЫ В БРАУЗЕР.
//
// ГЛАВНОЕ ЗДЕСЬ — ЧТО ЭТОТ ФАЙЛ НИЧЕГО НЕ СЧИТАЕТ. Он включает ровно тот же
// engine/modules/gatchina_sim/water_field.h, который идёт в сборку для телефона.
// Один исходник на две платформы: если завтра поправить схему, поправятся обе,
// и разойтись они не могут по устройству.
//
// Наружу отдаются УКАЗАТЕЛИ на массивы поля, а не значения по одному. Вызов из
// JS в WASM стоит порядка сотни наносекунд; на 65 тысячах ячеек это были бы
// миллисекунды на пустом месте. JS пишет дно и читает поле прямо в памяти WASM.
#include "../../engine/modules/gatchina_sim/water_field.h"

#include <emscripten/emscripten.h>
#include <vector>

using gatchina::WaterField;

static WaterField g_field;
// Поле для отрисовки: RGBA float на ячейку — отметка поверхности, уклон x,
// уклон z, глубина. Держим свой буфер, чтобы JS забирал одним куском.
static std::vector<float> g_tex;

extern "C" {

EMSCRIPTEN_KEEPALIVE void wf_setup(int n, float cell, float ox, float oz) {
	g_field.resize(n, cell);
	g_field.set_origin(ox, oz);
	g_tex.assign((size_t)n * n * 4, 0.0f);
}

EMSCRIPTEN_KEEPALIVE float *wf_bed_ptr() { return g_field.bed.data(); }
EMSCRIPTEN_KEEPALIVE float *wf_h_ptr() { return g_field.h.data(); }
EMSCRIPTEN_KEEPALIVE float *wf_tex_ptr() { return g_tex.data(); }
EMSCRIPTEN_KEEPALIVE int wf_side() { return g_field.n; }

EMSCRIPTEN_KEEPALIVE void wf_set_manning(float m) { g_field.manning = m; }
EMSCRIPTEN_KEEPALIVE void wf_set_open(int on, float level) {
	g_field.open_boundary = on != 0;
	g_field.open_level = level;
}
EMSCRIPTEN_KEEPALIVE void wf_fill_region(float y, float bed_max) {
	g_field.fill_region(y, bed_max);
}
EMSCRIPTEN_KEEPALIVE void wf_add_volume(float x, float z, float r, float v) {
	g_field.add_volume(x, z, r, v);
}
EMSCRIPTEN_KEEPALIVE int wf_step(float dt) { return g_field.step(dt); }

EMSCRIPTEN_KEEPALIVE float wf_depth_at(float x, float z) {
	return g_field.depth_at(x, z);
}
EMSCRIPTEN_KEEPALIVE float wf_surface_at(float x, float z) {
	return g_field.surface_at(x, z);
}
EMSCRIPTEN_KEEPALIVE double wf_volume() { return g_field.total_volume(); }
EMSCRIPTEN_KEEPALIVE double wf_wet_area() { return g_field.wetted_area(); }
EMSCRIPTEN_KEEPALIVE int wf_substeps() { return g_field.last_substeps; }

// Собрать поле для шейдера. Уклон считается по соседям одним проходом, а на
// сухой ячейке он обнуляется: иначе берег бликовал бы как гладь.
EMSCRIPTEN_KEEPALIVE void wf_pack() {
	const int n = g_field.n;
	const float inv2 = 0.5f / g_field.dx;
	for (int j = 0; j < n; j++) {
		for (int i = 0; i < n; i++) {
			const size_t k = g_field.idx(i, j);
			const float d = g_field.h[k];
			const float eta = g_field.bed[k] + d;
			float sx = 0.0f, sz = 0.0f;
			if (d > g_field.dry_depth) {
				const int im = i > 0 ? i - 1 : i, ip = i < n - 1 ? i + 1 : i;
				const int jm = j > 0 ? j - 1 : j, jp = j < n - 1 ? j + 1 : j;
				const size_t a = g_field.idx(im, j), b = g_field.idx(ip, j);
				const size_t c = g_field.idx(i, jm), e = g_field.idx(i, jp);
				// у сухого соседа берём свою отметку: уклон не «утекает» в берег
				const float ea = g_field.h[a] > g_field.dry_depth ? g_field.bed[a] + g_field.h[a] : eta;
				const float eb = g_field.h[b] > g_field.dry_depth ? g_field.bed[b] + g_field.h[b] : eta;
				const float ec = g_field.h[c] > g_field.dry_depth ? g_field.bed[c] + g_field.h[c] : eta;
				const float ee = g_field.h[e] > g_field.dry_depth ? g_field.bed[e] + g_field.h[e] : eta;
				sx = (eb - ea) * inv2;
				sz = (ee - ec) * inv2;
			}
			float *o = &g_tex[k * 4];
			o[0] = eta;
			o[1] = sx;
			o[2] = sz;
			o[3] = d;
		}
	}
}

} // extern "C"
