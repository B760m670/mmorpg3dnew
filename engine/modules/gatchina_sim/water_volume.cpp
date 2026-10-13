#include "water_volume.h"

// ПРОВЕРЕНО ПО ЗАГОЛОВКАМ 4.5.2, а не по памяти:
//   class_db.h — без него нет ни ClassDB::bind_method, ни D_METHOD;
//   math_funcs.h — make_half_float лежит в NAMESPACE Math (не в классе);
//   time.h — get_singleton()->get_ticks_usec().
#include "core/math/math_funcs.h"
#include "core/object/class_db.h"
#include "core/os/time.h"

void WaterVolume::setup(int side, float cell_m) {
	ERR_FAIL_COND_MSG(side < 8 || side > 1024, "сторона сетки вне 8..1024");
	ERR_FAIL_COND_MSG(cell_m <= 0.0f, "размер ячейки должен быть больше нуля");
	field.resize(side, cell_m);
	tex_img = Image::create_empty(side, side, false, Image::FORMAT_RGBAH);
	tex = ImageTexture::create_from_image(tex_img);
}

void WaterVolume::set_origin(const Vector2 &world_min) {
	field.set_origin(world_min.x, world_min.y);
}

void WaterVolume::set_manning(float m) {
	field.manning = CLAMP(m, 0.0f, 0.2f);
}

void WaterVolume::set_open_boundary(bool on, float level) {
	field.open_boundary = on;
	field.open_level = level;
}

void WaterVolume::set_bed(const PackedFloat32Array &b) {
	const int need = field.n * field.n;
	ERR_FAIL_COND_MSG(b.size() != need,
			vformat("отметок дна %d, а нужно %d (сторона %d)", b.size(), need, field.n));
	const float *src = b.ptr();
	for (int k = 0; k < need; k++) {
		field.bed[k] = src[k];
	}
}

void WaterVolume::fill_to_level(float y) {
	field.fill_to_level(y);
}

void WaterVolume::fill_region(float y, float bed_max) {
	field.fill_region(y, bed_max);
}

int WaterVolume::step(double dt) {
	const uint64_t t0 = Time::get_singleton()->get_ticks_usec();
	const int sub = field.step((float)dt);
	last_step_usec = (double)(Time::get_singleton()->get_ticks_usec() - t0);
	return sub;
}

void WaterVolume::add_volume(const Vector3 &world_pos, float radius_m, float volume_m3) {
	field.add_volume(world_pos.x, world_pos.z, radius_m, volume_m3);
}

float WaterVolume::depth_at(const Vector3 &world_pos) const {
	return field.depth_at(world_pos.x, world_pos.z);
}

float WaterVolume::surface_at(const Vector3 &world_pos) const {
	return field.surface_at(world_pos.x, world_pos.z);
}

Vector2 WaterVolume::velocity_at(const Vector3 &world_pos) const {
	float u = 0.0f, v = 0.0f;
	field.velocity_at(world_pos.x, world_pos.z, u, v);
	return Vector2(u, v);
}

Vector2 WaterVolume::slope_at(const Vector3 &world_pos) const {
	float sx = 0.0f, sz = 0.0f;
	field.slope_at(world_pos.x, world_pos.z, sx, sz);
	return Vector2(sx, sz);
}

Ref<ImageTexture> WaterVolume::get_texture() {
	if (tex_img.is_null() || tex.is_null()) {
		return Ref<ImageTexture>();
	}
	const int n = field.n;
	// Пишем сразу в буфер образа: покомпонентная запись через set_pixel на
	// 65 тысячах ячеек стоила бы дороже самого решателя.
	Vector<uint8_t> data;
	data.resize((int64_t)n * n * 8);   // RGBAH = 4 канала по 2 байта
	uint16_t *dst = (uint16_t *)data.ptrw();
	const float inv2 = 0.5f / field.dx;
	for (int j = 0; j < n; j++) {
		for (int i = 0; i < n; i++) {
			const size_t k = field.idx(i, j);
			const float d = field.h[k];
			const float eta = field.bed[k] + d;
			// УКЛОН СЧИТАЕТСЯ ПО СОСЕДЯМ ПОЛЯ, а не выборкой surface_at: так это
			// один проход по массиву вместо четырёх интерполяций на ячейку.
			// На сухой ячейке уклона нет — иначе берег бликовал бы как гладь.
			float sx = 0.0f, sz = 0.0f;
			if (d > field.dry_depth) {
				const int im = i > 0 ? i - 1 : i;
				const int ip = i < n - 1 ? i + 1 : i;
				const int jm = j > 0 ? j - 1 : j;
				const int jp = j < n - 1 ? j + 1 : j;
				const size_t kim = field.idx(im, j), kip = field.idx(ip, j);
				const size_t kjm = field.idx(i, jm), kjp = field.idx(i, jp);
				// у сухого соседа берём свою же отметку: уклон не должен
				// «утекать» в берег
				const float em = field.h[kim] > field.dry_depth ? field.bed[kim] + field.h[kim] : eta;
				const float ep = field.h[kip] > field.dry_depth ? field.bed[kip] + field.h[kip] : eta;
				const float fm = field.h[kjm] > field.dry_depth ? field.bed[kjm] + field.h[kjm] : eta;
				const float fp = field.h[kjp] > field.dry_depth ? field.bed[kjp] + field.h[kjp] : eta;
				sx = (ep - em) * inv2;
				sz = (fp - fm) * inv2;
			}
			const size_t o = k * 4;
			dst[o + 0] = Math::make_half_float(eta);
			dst[o + 1] = Math::make_half_float(sx);
			dst[o + 2] = Math::make_half_float(sz);
			dst[o + 3] = Math::make_half_float(d);
		}
	}
	tex_img->set_data(n, n, false, Image::FORMAT_RGBAH, data);
	tex->update(tex_img);
	return tex;
}

Dictionary WaterVolume::report() const {
	Dictionary d;
	d["side"] = field.n;
	d["cell_m"] = field.dx;
	d["window_m"] = field.n * field.dx;
	d["origin"] = Vector2(field.ox, field.oz);
	d["substeps"] = field.last_substeps;
	d["step_usec"] = last_step_usec;
	d["max_dt"] = field.max_dt();
	d["volume_m3"] = field.total_volume();
	d["wet_area_m2"] = field.wetted_area();
	d["max_speed"] = field.max_wave_speed();
	d["manning"] = field.manning;
	d["dry_depth"] = field.dry_depth;
	return d;
}

void WaterVolume::_bind_methods() {
	ClassDB::bind_method(D_METHOD("setup", "side", "cell_m"), &WaterVolume::setup);
	ClassDB::bind_method(D_METHOD("set_origin", "world_min"), &WaterVolume::set_origin);
	ClassDB::bind_method(D_METHOD("set_manning", "m"), &WaterVolume::set_manning);
	ClassDB::bind_method(D_METHOD("set_open_boundary", "on", "level"), &WaterVolume::set_open_boundary);
	ClassDB::bind_method(D_METHOD("set_bed", "bed"), &WaterVolume::set_bed);
	ClassDB::bind_method(D_METHOD("fill_to_level", "y"), &WaterVolume::fill_to_level);
	ClassDB::bind_method(D_METHOD("fill_region", "y", "bed_max"), &WaterVolume::fill_region);
	ClassDB::bind_method(D_METHOD("step", "dt"), &WaterVolume::step);
	ClassDB::bind_method(D_METHOD("add_volume", "world_pos", "radius_m", "volume_m3"),
			&WaterVolume::add_volume);
	ClassDB::bind_method(D_METHOD("depth_at", "world_pos"), &WaterVolume::depth_at);
	ClassDB::bind_method(D_METHOD("surface_at", "world_pos"), &WaterVolume::surface_at);
	ClassDB::bind_method(D_METHOD("velocity_at", "world_pos"), &WaterVolume::velocity_at);
	ClassDB::bind_method(D_METHOD("slope_at", "world_pos"), &WaterVolume::slope_at);
	ClassDB::bind_method(D_METHOD("get_texture"), &WaterVolume::get_texture);
	ClassDB::bind_method(D_METHOD("report"), &WaterVolume::report);
}
