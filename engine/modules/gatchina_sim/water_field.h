// ВОДА КАК СОСТОЯНИЕ, А НЕ КАК ИЗДЕЛИЕ.
//
// ЗАЧЕМ ЭТОТ ФАЙЛ СУЩЕСТВУЕТ. Прежняя вода в игре была запечённой поверхностью:
// 7292 прямоугольника по осям, 75 плоских уровней, одна вершина на 33 м², шаг
// запекания 2 м. Берег был лестницей, поверхность не могла двинуться, а глубина
// считалась как «урез минус рельеф» — оба слагаемых постоянны. Такая вода в
// принципе не умеет наполняться, убывать, течь и расступаться под телом.
// Решатель волн при этом был верен и не влиял ни на что: он отдавал только
// наклон в шейдер.
//
// ЗДЕСЬ ВОДА ОПРЕДЕЛЕНА ОДНОЙ ВЕЛИЧИНОЙ — ВЫСОТОЙ СТОЛБА h(x,z). Дно b(x,z)
// берётся из рельефа. Поверхность = b + h. Мокро там, где h > 0. Из этого само
// собой выходит то, чего не было:
//   БЕРЕГ — изолиния h = 0: кривая, подвижная, без ступеней, и бесплатно;
//   НАПОЛНЕНИЕ, СЛИВ, ТЕЧЕНИЕ, ВЫТЕСНЕНИЕ ТЕЛОМ, ВОЛНА — одно уравнение.
//
// СХЕМА. Конечные объёмы по уравнениям мелкой воды в консервативных
// переменных (h, qx, qz), поток Русанова, ГИДРОСТАТИЧЕСКАЯ РЕКОНСТРУКЦИЯ
// (Audusse и др., 2004) на гранях.
//
// ПОЧЕМУ ИМЕННО ГИДРОСТАТИЧЕСКАЯ РЕКОНСТРУКЦИЯ, а не «шаг попроще». Наивная
// схема на наклонном дне НЕ УДЕРЖИВАЕТ ОЗЕРО В ПОКОЕ: разность давлений между
// соседними ячейками не гасится источником, и стоячий пруд сам собой начинает
// течь. На кадре это выглядело бы как вечная зыбь ниоткуда, и искали бы её
// в шейдере. Здесь источник построен так, что при постоянной поверхности он
// ТОЧНО сокращает разность потоков — это и проверяется первым тестом.
#ifndef GATCHINA_WATER_FIELD_H
#define GATCHINA_WATER_FIELD_H

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace gatchina {

struct WaterField {
	static constexpr float G = 9.81f;

	int n = 0;            // сторона сетки в ячейках
	float dx = 1.0f;      // метр на ячейку
	// Мировые координаты ЦЕНТРА ячейки (0,0). Поле НЕ ездит за наблюдателем:
	// оно стоит над игровым срезом. Иначе уровень воды нельзя хранить — он
	// сбрасывался бы при каждом переезде окна, как это и было раньше.
	float ox = 0.0f, oz = 0.0f;

	std::vector<float> bed;   // отметка дна, м (из рельефа)
	std::vector<float> h;     // ВЫСОТА СТОЛБА, м — единственное состояние воды
	std::vector<float> qx;    // расход h·u, м²/с
	std::vector<float> qz;    // расход h·v, м²/с

	// ШЕРОХОВАТОСТЬ ДНА по Маннингу. 0.03 — заиленное дно пруда с растительностью
	// (справочные значения: гладкий бетон 0.012, чистый песок 0.020,
	// заиленное русло с травой 0.030-0.045). Трение нужно не для красоты: без
	// него разогнанная вода не останавливается никогда.
	float manning = 0.03f;
	// Ниже этой глубины ячейка считается сухой. 1 мм: тоньше плёнки на кадре не
	// видно, а численно тонкий слой требует крошечного шага по времени.
	float dry_depth = 1e-3f;
	float cfl = 0.45f;

	// --- служебное ---
	std::vector<float> h2, qx2, qz2;
	int last_substeps = 0;

	inline size_t idx(int i, int j) const { return (size_t)j * (size_t)n + (size_t)i; }
	inline bool inside(int i, int j) const { return i >= 0 && j >= 0 && i < n && j < n; }

	void resize(int side, float cell_m) {
		n = side;
		dx = cell_m;
		const size_t sz = (size_t)n * (size_t)n;
		bed.assign(sz, 0.0f);
		h.assign(sz, 0.0f);
		qx.assign(sz, 0.0f);
		qz.assign(sz, 0.0f);
		h2.assign(sz, 0.0f);
		qx2.assign(sz, 0.0f);
		qz2.assign(sz, 0.0f);
	}

	void set_origin(float world_x, float world_z) { ox = world_x; oz = world_z; }

	// Налить до отметки: h = max(0, y - дно). Так задаётся исходное состояние
	// водоёма — и оно СОСТОЯНИЕ, а не описание: дальше вода живёт сама.
	void fill_to_level(float y) {
		for (size_t k = 0; k < h.size(); k++) {
			const float d = y - bed[k];
			h[k] = d > 0.0f ? d : 0.0f;
			qx[k] = 0.0f;
			qz[k] = 0.0f;
		}
	}

	// Налить до отметки ТОЛЬКО там, где отметка ниже указанного потолка дна:
	// нужно, чтобы не залить всю карту одним уровнем, когда водоёмов несколько.
	void fill_region(float y, float bed_max) {
		for (size_t k = 0; k < h.size(); k++) {
			if (bed[k] <= bed_max) {
				const float d = y - bed[k];
				if (d > 0.0f) { h[k] = d; }
			}
		}
	}

	inline float surface(size_t k) const { return bed[k] + h[k]; }

	double total_volume() const {
		double v = 0.0;
		for (size_t k = 0; k < h.size(); k++) { v += (double)h[k]; }
		return v * (double)dx * (double)dx;
	}

	double wetted_area() const {
		double a = 0.0;
		for (size_t k = 0; k < h.size(); k++) { if (h[k] > dry_depth) { a += 1.0; } }
		return a * (double)dx * (double)dx;
	}

	// Наибольшая скорость возмущения по всему полю: по ней и берётся шаг.
	float max_wave_speed() const {
		float s = 0.0f;
		for (size_t k = 0; k < h.size(); k++) {
			if (h[k] <= dry_depth) { continue; }
			const float u = qx[k] / h[k];
			const float v = qz[k] / h[k];
			const float c = std::sqrt(G * h[k]);
			const float a = std::sqrt(u * u + v * v) + c;
			if (a > s) { s = a; }
		}
		return s;
	}

	float max_dt() const {
		const float s = max_wave_speed();
		if (s <= 1e-6f) { return 1.0f; }
		// делитель sqrt(2) — потому что шагаем по двум направлениям сразу
		return cfl * dx / (s * 1.41421356f);
	}

	// ДОБАВИТЬ ОБЪЁМ в круге: всплеск, дождь, вытеснение вошедшим телом.
	// Знак минус — забрать. Это единственный способ тронуть воду снаружи, и он
	// физический: меняется ОБЪЁМ, а не «высота волны».
	void add_volume(float world_x, float world_z, float radius_m, float volume_m3) {
		const float gx = (world_x - ox) / dx;
		const float gz = (world_z - oz) / dx;
		const float r = radius_m / dx;
		const int i0 = (int)std::floor(gx - r), i1 = (int)std::ceil(gx + r);
		const int j0 = (int)std::floor(gz - r), j1 = (int)std::ceil(gz + r);
		// вес — косинусный колокол, сумма нормируется, чтобы объём был ровно тот
		float wsum = 0.0f;
		for (int j = j0; j <= j1; j++) {
			for (int i = i0; i <= i1; i++) {
				if (!inside(i, j)) { continue; }
				const float d = std::sqrt((i - gx) * (i - gx) + (j - gz) * (j - gz));
				if (d > r) { continue; }
				wsum += 0.5f * (1.0f + std::cos(3.14159265f * d / std::max(r, 1e-6f)));
			}
		}
		if (wsum <= 0.0f) { return; }
		const float cell_area = dx * dx;
		for (int j = j0; j <= j1; j++) {
			for (int i = i0; i <= i1; i++) {
				if (!inside(i, j)) { continue; }
				const float d = std::sqrt((i - gx) * (i - gx) + (j - gz) * (j - gz));
				if (d > r) { continue; }
				const float w = 0.5f * (1.0f + std::cos(3.14159265f * d / std::max(r, 1e-6f)));
				const size_t k = idx(i, j);
				h[k] += volume_m3 * (w / wsum) / cell_area;
				if (h[k] < 0.0f) { h[k] = 0.0f; }
			}
		}
	}

	int step(float dt) {
		if (n <= 0 || dt <= 0.0f) { return 0; }
		const float md = max_dt();
		int sub = (int)std::ceil(dt / md);
		if (sub < 1) { sub = 1; }
		if (sub > 24) { sub = 24; }   // потолок: лучше замедлить воду, чем кадр
		const float sdt = dt / (float)sub;
		for (int s = 0; s < sub; s++) { substep(sdt); }
		last_substeps = sub;
		return sub;
	}

	// --- выборка с билинейной интерполяцией (для игры и шейдера) ---
	float depth_at(float world_x, float world_z) const {
		return sample(h, world_x, world_z);
	}

	float surface_at(float world_x, float world_z) const {
		const float d = sample(h, world_x, world_z);
		return sample(bed, world_x, world_z) + d;
	}

	void velocity_at(float world_x, float world_z, float &u, float &v) const {
		const float d = sample(h, world_x, world_z);
		if (d <= dry_depth) { u = 0.0f; v = 0.0f; return; }
		u = sample(qx, world_x, world_z) / d;
		v = sample(qz, world_x, world_z) / d;
	}

	// Уклон ПОВЕРХНОСТИ (для нормали в шейдере), безразмерный.
	void slope_at(float world_x, float world_z, float &sx, float &sz) const {
		const float e = dx;
		const float c = surface_at(world_x, world_z);
		sx = (surface_at(world_x + e, world_z) - c) / e;
		sz = (surface_at(world_x, world_z + e) - c) / e;
		// на сухом уклон не имеет смысла
		if (depth_at(world_x, world_z) <= dry_depth) { sx = 0.0f; sz = 0.0f; }
	}

private:
	float sample(const std::vector<float> &f, float world_x, float world_z) const {
		if (n <= 0) { return 0.0f; }
		float gx = (world_x - ox) / dx;
		float gz = (world_z - oz) / dx;
		if (gx < 0.0f) { gx = 0.0f; }
		if (gz < 0.0f) { gz = 0.0f; }
		if (gx > (float)(n - 1)) { gx = (float)(n - 1); }
		if (gz > (float)(n - 1)) { gz = (float)(n - 1); }
		const int i0 = (int)gx, j0 = (int)gz;
		const int i1 = std::min(i0 + 1, n - 1), j1 = std::min(j0 + 1, n - 1);
		const float ti = gx - (float)i0, tj = gz - (float)j0;
		const float a = f[idx(i0, j0)] * (1 - ti) + f[idx(i1, j0)] * ti;
		const float b = f[idx(i0, j1)] * (1 - ti) + f[idx(i1, j1)] * ti;
		return a * (1 - tj) + b * tj;
	}

	// Поток Русанова между двумя реконструированными состояниями по одной оси.
	// Возвращает (поток массы, поток импульса вдоль оси, поток импульса поперёк).
	static inline void rusanov(float hL, float quL, float qtL,
			float hR, float quR, float qtR,
			float &fh, float &fqu, float &fqt) {
		const float uL = hL > 1e-6f ? quL / hL : 0.0f;
		const float uR = hR > 1e-6f ? quR / hR : 0.0f;
		const float cL = std::sqrt(G * std::max(hL, 0.0f));
		const float cR = std::sqrt(G * std::max(hR, 0.0f));
		const float a = std::max(std::fabs(uL) + cL, std::fabs(uR) + cR);
		const float FhL = quL;
		const float FhR = quR;
		const float FquL = quL * uL + 0.5f * G * hL * hL;
		const float FquR = quR * uR + 0.5f * G * hR * hR;
		const float FqtL = qtL * uL;
		const float FqtR = qtR * uR;
		fh = 0.5f * (FhL + FhR) - 0.5f * a * (hR - hL);
		fqu = 0.5f * (FquL + FquR) - 0.5f * a * (quR - quL);
		fqt = 0.5f * (FqtL + FqtR) - 0.5f * a * (qtR - qtL);
	}

	// ОДНА ГРАНЬ. Вынесено в функцию, потому что граней четыре вида (две оси и
	// на каждой — внутренние и граничные), а перепутать в них знак проще
	// простого. Так правило записано один раз.
	//
	// СТЕНКА НА КРАЮ ПОЛЯ — не «пропустить грань», а ЗЕРКАЛО. Первый заход я
	// просто не считал крайние грани, и озеро на ПЛОСКОМ дне разгонялось само:
	// крайняя ячейка получала давление только с одной стороны, и расход рос на
	// (dt/dx)·(g/2)h² за подшаг — ровно те 0.184, что показал замер. Зеркальная
	// ячейка (та же глубина, то же дно, обратная нормальная скорость) даёт
	// встречное давление и держит воду.
	inline void face(int iL, int jL, int iR, int jR, bool along_x, float inv) {
		const bool okL = inside(iL, jL);
		const bool okR = inside(iR, jR);
		if (!okL && !okR) { return; }
		const size_t kL = okL ? idx(iL, jL) : idx(iR, jR);
		const size_t kR = okR ? idx(iR, jR) : idx(iL, jL);
		const float hL = h[kL], hR = h[kR];
		if (hL <= dry_depth && hR <= dry_depth) { return; }
		const float zL = bed[kL], zR = bed[kR];
		const float qnL_real = along_x ? qx[kL] : qz[kL];
		const float qnR_real = along_x ? qx[kR] : qz[kR];
		const float qtL = along_x ? qz[kL] : qx[kL];
		const float qtR = along_x ? qz[kR] : qx[kR];
		// зеркало на стенке: нормальная составляющая обратная
		const float qnL = okL ? qnL_real : -qnR_real;
		const float qnR = okR ? qnR_real : -qnL_real;

		const float zf = std::max(zL, zR);
		const float hLs = std::max(0.0f, zL + hL - zf);
		const float hRs = std::max(0.0f, zR + hR - zf);
		const float uL = hL > dry_depth ? qnL / hL : 0.0f;
		const float uR = hR > dry_depth ? qnR / hR : 0.0f;
		const float vL = hL > dry_depth ? qtL / hL : 0.0f;
		const float vR = hR > dry_depth ? qtR / hR : 0.0f;
		float fh, fqn, fqt;
		rusanov(hLs, hLs * uL, hLs * vL, hRs, hRs * uR, hRs * vR, fh, fqn, fqt);
		// источник по дну — тот, что при постоянной поверхности ТОЧНО
		// сокращает разность давлений и держит озеро в покое
		const float SL = 0.5f * G * (hLs * hLs - hL * hL);
		const float SR = 0.5f * G * (hRs * hRs - hR * hR);
		if (okL) {
			h2[kL] -= inv * fh;
			if (along_x) {
				qx2[kL] -= inv * (fqn - SL);
				qz2[kL] -= inv * fqt;
			} else {
				qz2[kL] -= inv * (fqn - SL);
				qx2[kL] -= inv * fqt;
			}
		}
		if (okR) {
			h2[kR] += inv * fh;
			if (along_x) {
				qx2[kR] += inv * (fqn - SR);
				qz2[kR] += inv * fqt;
			} else {
				qz2[kR] += inv * (fqn - SR);
				qx2[kR] += inv * fqt;
			}
		}
	}

	void substep(float dt) {
		const size_t sz = h.size();
		h2 = h;
		qx2 = qx;
		qz2 = qz;
		const float inv = dt / dx;

		// грани по X: их n+1 на строку, крайние — стенки
		for (int j = 0; j < n; j++) {
			for (int i = 0; i <= n; i++) { face(i - 1, j, i, j, true, inv); }
		}
		// грани по Z
		for (int j = 0; j <= n; j++) {
			for (int i = 0; i < n; i++) { face(i, j - 1, i, j, false, inv); }
		}

		// --- сушка, трение, запись ---
		for (size_t k = 0; k < sz; k++) {
			float hh = h2[k];
			if (hh < 0.0f) { hh = 0.0f; }
			if (hh <= dry_depth) {
				h[k] = hh;
				qx[k] = 0.0f;
				qz[k] = 0.0f;
				continue;
			}
			float u = qx2[k] / hh;
			float v = qz2[k] / hh;
			// ТРЕНИЕ ПО МАННИНГУ, полунеявно: явное вычитание может перевернуть
			// знак скорости, и тогда вода дёргается на мелководье.
			const float sp = std::sqrt(u * u + v * v);
			if (sp > 1e-6f && manning > 0.0f) {
				const float cf = G * manning * manning * sp / std::pow(hh, 4.0f / 3.0f);
				const float den = 1.0f + dt * cf;
				u /= den;
				v /= den;
			}
			h[k] = hh;
			qx[k] = u * hh;
			qz[k] = v * hh;
		}
	}
};

} // namespace gatchina

#endif // GATCHINA_WATER_FIELD_H
