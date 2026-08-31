#include "shallow_water.h"

// ПРОВЕРЕНО ПО ЗАГОЛОВКАМ 4.5.2, а не по памяти:
//   class_db.h — без него нет ни ClassDB::bind_method, ни D_METHOD;
//   math_funcs.h — make_half_float лежит в NAMESPACE Math (не в классе);
//   time.h — get_singleton()->get_ticks_usec().
#include "core/math/math_funcs.h"
#include "core/object/class_db.h"
#include "core/os/time.h"

void ShallowWater::setup(int side, float cell_m) {
	ERR_FAIL_COND_MSG(side < 8 || side > 1024, "сторона сетки вне 8..1024");
	ERR_FAIL_COND_MSG(cell_m <= 0.0f, "размер ячейки должен быть больше нуля");
	solver.resize(side, cell_m);
	field_img = Image::create_empty(side, side, false, Image::FORMAT_RGBAH);
	field_tex = ImageTexture::create_from_image(field_img);
}

void ShallowWater::set_origin(const Vector2 &world_min) {
	// ОКНО ПЕРЕЕХАЛО — волны сбрасываются. Переносить поле со сдвигом можно, но
	// это отдельная работа: при переносе надо докладывать глубину новых ячеек и
	// не порвать волну на стыке. Пока честнее сбросить, чем сдвинуть неверно.
	if (!origin.is_equal_approx(world_min)) {
		solver.clear_waves();
	}
	origin = world_min;
}

void ShallowWater::set_damping(float d) {
	solver.damping = CLAMP(d, 0.0f, 8.0f);
}

void ShallowWater::set_depth(const PackedFloat32Array &d) {
	const int need = solver.n * solver.n;
	ERR_FAIL_COND_MSG(d.size() != need,
			vformat("глубин %d, а нужно %d (сторона %d)", d.size(), need, solver.n));
	const float *src = d.ptr();
	for (int k = 0; k < need; k++) {
		solver.depth[k] = src[k];
	}
}

void ShallowWater::disturb(const Vector3 &world_pos, float radius_m, float amp_m) {
	const Vector2 g = to_grid(world_pos);
	solver.disturb(g.x, g.y, radius_m, amp_m);
}

int ShallowWater::step(double dt) {
	const uint64_t t0 = Time::get_singleton()->get_ticks_usec();
	last_substeps = solver.step((float)dt);
	last_step_usec = (double)(Time::get_singleton()->get_ticks_usec() - t0);
	return last_substeps;
}

void ShallowWater::clear_waves() {
	solver.clear_waves();
}

float ShallowWater::height_at(const Vector3 &world_pos) const {
	const Vector2 g = to_grid(world_pos);
	return solver.height_at(g.x, g.y);
}

Vector2 ShallowWater::slope_at(const Vector3 &world_pos) const {
	const Vector2 g = to_grid(world_pos);
	float sx = 0.0f, sz = 0.0f;
	solver.slope_at(g.x, g.y, sx, sz);
	return Vector2(sx, sz);
}

float ShallowWater::vel_at(const Vector3 &world_pos, double dt) const {
	const Vector2 g = to_grid(world_pos);
	return solver.vel_at(g.x, g.y, (float)dt);
}

Ref<ImageTexture> ShallowWater::get_texture() {
	if (field_img.is_null() || field_tex.is_null()) {
		return Ref<ImageTexture>();
	}
	const int n = solver.n;
	// Пишем сразу в буфер образа: покомпонентная запись через set_pixel на
	// 16 тысячах ячеек стоила бы дороже самого решателя.
	Vector<uint8_t> data;
	data.resize((int64_t)n * n * 8);   // RGBAH = 4 канала по 2 байта
	uint16_t *dst = (uint16_t *)data.ptrw();
	for (int j = 0; j < n; j++) {
		for (int i = 0; i < n; i++) {
			const size_t k = solver.idx(i, j);
			float sx = 0.0f, sz = 0.0f;
			solver.slope_at((float)i * solver.dx, (float)j * solver.dx, sx, sz);
			const size_t o = k * 4;
			dst[o + 0] = Math::make_half_float(solver.h[k]);
			dst[o + 1] = Math::make_half_float(sx);
			dst[o + 2] = Math::make_half_float(sz);
			dst[o + 3] = Math::make_half_float(solver.depth[k] > 0.0f ? 1.0f : 0.0f);
		}
	}
	field_img->set_data(n, n, false, Image::FORMAT_RGBAH, data);
	field_tex->update(field_img);
	return field_tex;
}

Dictionary ShallowWater::report() const {
	Dictionary d;
	d["side"] = solver.n;
	d["cell_m"] = solver.dx;
	d["window_m"] = solver.n * solver.dx;
	d["origin"] = origin;
	d["substeps"] = last_substeps;
	d["step_usec"] = last_step_usec;
	d["max_dt"] = solver.max_dt();
	d["max_depth"] = solver.max_depth();
	d["significant_height"] = solver.significant_height();
	d["damping"] = solver.damping;
	return d;
}

void ShallowWater::_bind_methods() {
	ClassDB::bind_method(D_METHOD("setup", "side", "cell_m"), &ShallowWater::setup);
	ClassDB::bind_method(D_METHOD("set_origin", "world_min"), &ShallowWater::set_origin);
	ClassDB::bind_method(D_METHOD("set_damping", "d"), &ShallowWater::set_damping);
	ClassDB::bind_method(D_METHOD("set_depth", "depths"), &ShallowWater::set_depth);
	ClassDB::bind_method(D_METHOD("disturb", "world_pos", "radius_m", "amp_m"),
			&ShallowWater::disturb);
	ClassDB::bind_method(D_METHOD("step", "dt"), &ShallowWater::step);
	ClassDB::bind_method(D_METHOD("clear_waves"), &ShallowWater::clear_waves);
	ClassDB::bind_method(D_METHOD("height_at", "world_pos"), &ShallowWater::height_at);
	ClassDB::bind_method(D_METHOD("slope_at", "world_pos"), &ShallowWater::slope_at);
	ClassDB::bind_method(D_METHOD("vel_at", "world_pos", "dt"), &ShallowWater::vel_at);
	ClassDB::bind_method(D_METHOD("get_texture"), &ShallowWater::get_texture);
	ClassDB::bind_method(D_METHOD("report"), &ShallowWater::report);
}
