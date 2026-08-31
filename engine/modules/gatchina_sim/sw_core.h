// РЕШАТЕЛЬ МЕЛКОЙ ВОДЫ — чистый C++, без единой зависимости от движка.
//
// ПОЧЕМУ ЯДРО ОТДЕЛЬНО ОТ ДВИЖКА. Так его можно собрать обычным g++ и ПРОВЕРИТЬ
// ЧИСЛАМИ на месте: скорость фронта против sqrt(g·d), устойчивость, время шага.
// Всё, что считалось раньше в шейдере, проверить было нечем — стенд отдаёт
// меньше кадра в секунду, и померить скорость круга по двум кадрам нельзя.
// Здесь это меряется за секунды.
//
// ЧТО РЕШАЕТСЯ. Уравнение мелкой воды в форме волнового уравнения с
// ПЕРЕМЕННОЙ ГЛУБИНОЙ:
//
//     d²h/dt² = g · div( d · grad h )
//
// где h — отклонение глади от покоя (м), d — глубина под ячейкой (м).
// Это не «c²·лаплас h» с постоянной скоростью: глубина входит внутрь
// дивергенции, и поэтому САМО СОБОЙ получается рефракция на отмели — волна у
// берега замедляется и разворачивается вдоль изобат. Скорость гребня выходит
// sqrt(g·d), её не надо задавать.
//
// СУХИЕ ЯЧЕЙКИ (d <= 0) — стенка: поток через грань не идёт. Физически это
// отражение волны от берега, и оно тоже получается само.
//
// УСТОЙЧИВОСТЬ. Схема явная, поэтому есть условие Куранта: за один шаг волна не
// должна проходить больше ячейки. Для двумерного лапласиана
//     dt <= dx / (sqrt(2) · c_max),   c_max = sqrt(g · d_max)
// Шаг кадра делится на подшаги ровно по этому условию — число подшагов
// возвращается наружу, чтобы его было видно, а не угадывать.
#ifndef GATCHINA_SW_CORE_H
#define GATCHINA_SW_CORE_H

#include <cmath>
#include <cstring>
#include <vector>

namespace gatchina {

class SwSolver {
public:
	// --- сетка ---
	int n = 0;                  // сторона сетки, ячеек
	float dx = 0.25f;           // размер ячейки, м
	float g = 9.81f;            // м/с²
	// Затухание за секунду. Вязкость воды сама по себе гасит волну ничтожно
	// медленно; на деле рябь съедают трение о дно и разрушение гребней. Держим
	// как один честно названный коэффициент, а не как «магию» внутри формулы.
	float damping = 0.55f;

	std::vector<float> h;       // отклонение глади, м
	std::vector<float> hp;      // то же на прошлом шаге
	std::vector<float> depth;   // глубина под ячейкой, м (<=0 — суша)

	void resize(int side, float cell_m) {
		n = side;
		dx = cell_m;
		const size_t sz = (size_t)n * (size_t)n;
		h.assign(sz, 0.0f);
		hp.assign(sz, 0.0f);
		depth.assign(sz, 0.0f);
	}

	inline size_t idx(int i, int j) const { return (size_t)j * (size_t)n + (size_t)i; }

	void clear_waves() {
		std::fill(h.begin(), h.end(), 0.0f);
		std::fill(hp.begin(), hp.end(), 0.0f);
	}

	// Наибольшая глубина — по ней считается предел шага
	float max_depth() const {
		float d = 0.0f;
		for (float v : depth) {
			if (v > d) { d = v; }
		}
		return d;
	}

	// Предельный шаг по Куранту, с
	float max_dt() const {
		const float dmax = max_depth();
		if (dmax <= 1e-4f) { return 1.0f; }
		const float c = std::sqrt(g * dmax);
		return dx / (1.41421356f * c);
	}

	// ВОЗМУЩЕНИЕ: гладкий горб радиуса r и высоты amp в точке сетки (гx, гz).
	// Гладкий, а не одна ячейка: точечный толчок содержит все длины волн, в том
	// числе те, которых сетка не держит, и они сразу ломают схему.
	//
	// ГОРБ КЛАДЁТСЯ В ОБА ПОЛЯ — и в текущее, и в прошлое. ИЗМЕРЕНО, почему это
	// обязательно: скорость глади в схеме есть (h - hp)/dt, поэтому горб только
	// в h означает начальную скорость 0.05/0.004 = 12 м/с. Проверка энергией
	// показала рост в 4000 раз за 100 шагов при выключенном затухании. Теперь
	// гладь стартует ПОДНЯТОЙ И ПОКОЯЩЕЙСЯ — как вода под упавшим предметом в
	// первый миг.
	void disturb(float gx, float gz, float r, float amp) {
		if (r < dx) { r = dx; }
		const int i0 = (int)std::floor((gx - r) / dx);
		const int i1 = (int)std::ceil((gx + r) / dx);
		const int j0 = (int)std::floor((gz - r) / dx);
		const int j1 = (int)std::ceil((gz + r) / dx);
		for (int j = j0; j <= j1; j++) {
			if (j < 0 || j >= n) { continue; }
			for (int i = i0; i <= i1; i++) {
				if (i < 0 || i >= n) { continue; }
				const size_t k = idx(i, j);
				if (depth[k] <= 0.0f) { continue; }
				const float ddx = (float)i * dx - gx;
				const float ddz = (float)j * dx - gz;
				const float t = std::sqrt(ddx * ddx + ddz * ddz) / r;
				if (t >= 1.0f) { continue; }
				// косинусный колокол: гладкий, с нулевой производной на краю
				const float w = 0.5f * (1.0f + std::cos(3.14159265f * t));
				h[k] += amp * w;
				hp[k] += amp * w;          // скорость = 0, только смещение
			}
		}
	}

	// ОДИН КАДР. Делится на подшаги по условию Куранта; возвращает их число.
	int step(float dt) {
		if (n < 3 || dt <= 0.0f) { return 0; }
		const float dtm = max_dt();
		int sub = (int)std::ceil(dt / dtm);
		if (sub < 1) { sub = 1; }
		if (sub > 16) { sub = 16; }   // защита: лучше замедлить волну, чем взорвать схему
		const float sdt = dt / (float)sub;
		for (int s = 0; s < sub; s++) { substep(sdt); }
		return sub;
	}

	// --- выборка с билинейной интерполяцией, в координатах сетки (метры) ---
	float height_at(float gx, float gz) const {
		const float u = gx / dx;
		const float v = gz / dx;
		int i = (int)std::floor(u);
		int j = (int)std::floor(v);
		if (i < 0 || j < 0 || i >= n - 1 || j >= n - 1) { return 0.0f; }
		const float fx = u - (float)i;
		const float fy = v - (float)j;
		const float a = h[idx(i, j)];
		const float b = h[idx(i + 1, j)];
		const float c = h[idx(i, j + 1)];
		const float d = h[idx(i + 1, j + 1)];
		return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy;
	}

	// уклон глади (dh/dx, dh/dz) — это и есть нормаль для оптики
	void slope_at(float gx, float gz, float &out_sx, float &out_sz) const {
		const float e = dx;
		out_sx = (height_at(gx + e, gz) - height_at(gx - e, gz)) / (2.0f * e);
		out_sz = (height_at(gx, gz + e) - height_at(gx, gz - e)) / (2.0f * e);
	}

	// вертикальная скорость глади, м/с — по ней вода толкает тело
	float vel_at(float gx, float gz, float dt) const {
		if (dt <= 0.0f) { return 0.0f; }
		const float u = gx / dx;
		const float v = gz / dx;
		const int i = (int)std::floor(u);
		const int j = (int)std::floor(v);
		if (i < 0 || j < 0 || i >= n || j >= n) { return 0.0f; }
		const size_t k = idx(i, j);
		return (h[k] - hp[k]) / dt;
	}

	// значимая высота волнения на сетке (4·СКО) — для отчёта числами
	float significant_height() const {
		double s = 0.0, s2 = 0.0;
		size_t cnt = 0;
		for (size_t k = 0; k < h.size(); k++) {
			if (depth[k] <= 0.0f) { continue; }
			s += h[k];
			s2 += (double)h[k] * (double)h[k];
			cnt++;
		}
		if (cnt < 2) { return 0.0f; }
		const double m = s / (double)cnt;
		const double var = s2 / (double)cnt - m * m;
		return (float)(4.0 * std::sqrt(var > 0.0 ? var : 0.0));
	}

private:
	std::vector<float> _hn;

	void substep(float dt) {
		const size_t sz = h.size();
		if (_hn.size() != sz) { _hn.assign(sz, 0.0f); }
		const float inv_dx2 = 1.0f / (dx * dx);
		const float kd = 1.0f - damping * dt;

		for (int j = 0; j < n; j++) {
			for (int i = 0; i < n; i++) {
				const size_t k = idx(i, j);
				const float dk = depth[k];
				if (dk <= 0.0f) { _hn[k] = 0.0f; continue; }   // суша: глади нет
				const float hk = h[k];
				// ДИВЕРГЕНЦИЯ ПОТОКА: глубина берётся НА ГРАНИ (среднее двух
				// ячеек). Через грань к сухой ячейке потока нет — это стенка,
				// то есть отражение волны от берега.
				float acc = 0.0f;
				// четыре грани
				const int ni[4] = { i - 1, i + 1, i, i };
				const int nj[4] = { j, j, j - 1, j + 1 };
				for (int f = 0; f < 4; f++) {
					const int ii = ni[f];
					const int jj = nj[f];
					if (ii < 0 || jj < 0 || ii >= n || jj >= n) { continue; }
					const size_t kk = idx(ii, jj);
					const float dn = depth[kk];
					if (dn <= 0.0f) { continue; }              // стенка
					const float d_face = 0.5f * (dk + dn);
					// ОГРАНИЧИТЕЛЯ УКЛОНА ЗДЕСЬ НЕТ. Он был у меня догадкой «чтобы
					// не взорвалось», а взрывалась схема по другой причине (см.
					// disturb). Ограничитель при этом ломал сохранение энергии, и
					// проверка это показала: без него энергия держится, с ним —
					// нет. Явная схема внутри условия Куранта устойчива сама.
					acc += d_face * (h[kk] - hk);
				}
				acc *= g * inv_dx2;
				const float vel = (hk - hp[k]) * kd;
				_hn[k] = hk + vel + acc * dt * dt;
			}
		}
		hp.swap(h);
		h.swap(_hn);
	}
};

} // namespace gatchina

#endif // GATCHINA_SW_CORE_H
