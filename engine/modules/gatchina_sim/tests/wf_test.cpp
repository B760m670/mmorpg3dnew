// ЧИСЛЕННАЯ ПРОВЕРКА ПОЛЯ ВОДЫ. Собирается обычным g++, движка не требует.
//
// Первый тест здесь — не про волны. Он про то, чего у прежней воды не было
// вовсе: ОЗЕРО В ПОКОЕ ОБЯЗАНО СТОЯТЬ. Наивная схема на наклонном дне сама
// разгоняет течение, и это выглядело бы как вечная зыбь ниоткуда.
#include "../water_field.h"

#include <chrono>
#include <cstdio>
#include <cmath>

using gatchina::WaterField;

// Поле отсчитывает мир от ячейки (0,0). Тесты строят чашу вокруг мирового нуля,
// значит начало координат поля надо сдвинуть в центр сетки — иначе всплеск
// уходит в угол, а замер ищет его в середине (на этом первый прогон и сломался).
static void center_origin(WaterField &w) {
	w.set_origin(-0.5f * (float)w.n * w.dx, -0.5f * (float)w.n * w.dx);
}

static void bowl(WaterField &w, float depth_at_center, float radius) {
	// Чаша-парабола: дно = -depth*(1 - (r/R)^2), выше края — суша.
	for (int j = 0; j < w.n; j++) {
		for (int i = 0; i < w.n; i++) {
			const float x = ((float)i - 0.5f * w.n) * w.dx;
			const float z = ((float)j - 0.5f * w.n) * w.dx;
			const float r = std::sqrt(x * x + z * z);
			const float t = r / radius;
			w.bed[w.idx(i, j)] = t < 1.0f ? -depth_at_center * (1.0f - t * t)
										  : depth_at_center * (t - 1.0f) * 0.5f;
		}
	}
}

int main() {
	printf("=== ПОЛЕ ВОДЫ: проверка числами ===\n\n");

	// ---------------------------------------------------------------- 1
	printf("1. ОЗЕРО В ПОКОЕ НА НАКЛОННОМ ДНЕ обязано стоять.\n");
	printf("   Это главный тест: без него стоячий пруд сам начинает течь.\n");
	{
		WaterField w;
		w.resize(128, 1.0f);
		// дно с уклоном 1:20 плюс бугры — заведомо не плоское
		for (int j = 0; j < w.n; j++) {
			for (int i = 0; i < w.n; i++) {
				const float x = (float)i, z = (float)j;
				w.bed[w.idx(i, j)] = -6.0f + 0.05f * x
					+ 0.6f * std::sin(0.11f * x) * std::cos(0.09f * z);
			}
		}
		w.fill_to_level(0.0f);
		const double v0 = w.total_volume();
		float eta_min0 = 1e9f, eta_max0 = -1e9f;
		for (size_t k = 0; k < w.h.size(); k++) {
			if (w.h[k] > w.dry_depth) {
				eta_min0 = std::min(eta_min0, w.surface((int)k));
				eta_max0 = std::max(eta_max0, w.surface((int)k));
			}
		}
		for (int s = 0; s < 3000; s++) { w.step(1.0f / 60.0f); }
		float qmax = 0.0f, umax = 0.0f;
		float eta_min = 1e9f, eta_max = -1e9f;
		for (size_t k = 0; k < w.h.size(); k++) {
			if (w.h[k] <= w.dry_depth) { continue; }
			const float q = std::sqrt(w.qx[k] * w.qx[k] + w.qz[k] * w.qz[k]);
			qmax = std::max(qmax, q);
			umax = std::max(umax, q / w.h[k]);
			eta_min = std::min(eta_min, w.surface((int)k));
			eta_max = std::max(eta_max, w.surface((int)k));
		}
		const double v1 = w.total_volume();
		printf("   после 3000 шагов (50 с модельного времени):\n");
		printf("     наибольший расход      %.3e м²/с (ждём 0)\n", qmax);
		printf("     наибольшая скорость    %.3e м/с   (ждём 0)\n", umax);
		printf("     разброс поверхности    %.3e м     (было %.3e)\n",
				eta_max - eta_min, eta_max0 - eta_min0);
		printf("     объём %.4f -> %.4f м³, изменение %.2e%%\n",
				v0, v1, 100.0 * (v1 - v0) / v0);
	}

	// ---------------------------------------------------------------- 2
	printf("\n2. ПРОРЫВ ПЛОТИНЫ (Риттер, плоское сухое дно).\n");
	printf("   Аналитика: фронт идёт 2·sqrt(g·h0), уровень в створе 4/9·h0.\n");
	{
		const float h0 = 1.0f;
		WaterField w;
		w.resize(400, 0.25f);
		w.manning = 0.0f;               // Риттер — без трения
		for (auto &b : w.bed) { b = 0.0f; }
		for (int j = 0; j < w.n; j++) {
			for (int i = 0; i < w.n; i++) {
				w.h[w.idx(i, j)] = (i < w.n / 2) ? h0 : 0.0f;
			}
		}
		const float T = 3.0f;
		float t = 0.0f;
		while (t < T) { w.step(1.0f / 240.0f); t += 1.0f / 240.0f; }
		// фронт: самая правая мокрая ячейка на средней строке
		const int j = w.n / 2;
		int front = w.n / 2;
		for (int i = w.n / 2; i < w.n; i++) {
			if (w.h[w.idx(i, j)] > 1e-3f) { front = i; }
		}
		const float x_front = ((float)front - (float)(w.n / 2)) * w.dx;
		const float v_meas = x_front / t;
		const float v_true = 2.0f * std::sqrt(WaterField::G * h0);
		const float h_gate = w.h[w.idx(w.n / 2, j)];
		const float h_true = 4.0f / 9.0f * h0;
		printf("   фронт за %.2f с ушёл на %.2f м -> %.2f м/с против %.2f м/с (%+.1f%%)\n",
				t, x_front, v_meas, v_true, 100.0f * (v_meas - v_true) / v_true);
		printf("   уровень в створе %.3f м против 4/9·h0 = %.3f м (%+.1f%%)\n",
				h_gate, h_true, 100.0f * (h_gate - h_true) / h_true);
	}

	// ---------------------------------------------------------------- 3
	printf("\n3. СКОРОСТЬ МАЛОЙ ВОЛНЫ против sqrt(g·h) на разных глубинах.\n");
	printf("   Ищем ГРЕБЕНЬ с уточнением параболой и считаем скорость по разности\n");
	printf("   двух моментов — начальный радиус пятна в разности сокращается.\n");
	for (float depth : {0.5f, 1.0f, 2.0f, 3.0f}) {
		WaterField w;
		w.resize(256, 0.25f);
		center_origin(w);
		w.manning = 0.0f;
		for (auto &b : w.bed) { b = -depth; }
		w.fill_to_level(0.0f);
		// возмущение 5% глубины на пятне 1.5 м
		const float amp = 0.05f * depth;
		w.add_volume(0.0f, 0.0f, 1.5f, amp * 3.14159f * 1.5f * 1.5f * 0.5f);
		// МОМЕНТЫ ЗАМЕРА ПОДБИРАЮТСЯ ПОД ГЛУБИНУ: гребень должен УЖЕ выйти из
		// пятна возмущения. При жёстких 0.30/0.90 с на глубине 1 м яма от
		// источника оказывалась «главным отклонением», и замер дал −113%.
		const float vt0 = std::sqrt(WaterField::G * depth);
		const float ta = 3.0f / vt0, tb = ta + 0.6f;
		float t = 0.0f;
		// ГРЕБЕНЬ, уточнённый параболой по трём соседям. Порог «5% от пика»
		// оказался негодным: пик падает с расстоянием, порог падает вместе с
		// ним, и найденный «фронт» убегает вперёд — отсюда были +50%.
		auto front = [&]() {
			const int jc = w.n / 2;
			const int i0 = jc + (int)(2.0f / w.dx);
			int best = i0;
			float bh = 0.0f;
			for (int i = i0; i < w.n - 2; i++) {
				const float d = std::fabs(w.h[w.idx(i, jc)] - depth);
				if (d > bh) { bh = d; best = i; }
			}
			float r = (float)(best - jc) * w.dx;
			if (best > i0 && best < w.n - 3) {
				const float y0 = std::fabs(w.h[w.idx(best - 1, jc)] - depth);
				const float y1 = bh;
				const float y2 = std::fabs(w.h[w.idx(best + 1, jc)] - depth);
				const float den = y0 - 2.0f * y1 + y2;
				if (std::fabs(den) > 1e-12f) { r += w.dx * 0.5f * (y0 - y2) / den; }
			}
			return r;
		};
		while (t < ta) { w.step(1.0f / 480.0f); t += 1.0f / 480.0f; }
		const float ra = front();
		while (t < tb) { w.step(1.0f / 480.0f); t += 1.0f / 480.0f; }
		const float rb = front();
		const float v = (rb - ra) / (tb - ta);
		const float vt = std::sqrt(WaterField::G * depth);
		printf("   глубина %.2f м: гребень %.2f -> %.2f м, %.2f м/с против %.2f м/с (%+.1f%%)\n",
				depth, ra, rb, v, vt, 100.0f * (v - vt) / vt);
	}

	// ---------------------------------------------------------------- 4
	printf("\n4. НАПОЛНЕНИЕ ЧАШИ: вода обязана найти ОДИН уровень,\n");
	printf("   а мокрая площадь — совпасть с геометрией чаши.\n");
	{
		WaterField w;
		w.resize(200, 0.5f);       // 100 x 100 м
		center_origin(w);
		bowl(w, 4.0f, 30.0f);      // чаша глубиной 4 м, радиус 30 м
		// наливаем объём, отвечающий уровню -2 м: V = pi*R²*d²/(2*D)
		const float target = -2.0f;
		const float d = 4.0f + target;                 // 2 м над дном центра
		const float R = 30.0f, D = 4.0f;
		const double v_want = 3.14159265 * R * R * d * d / (2.0 * D);
		w.add_volume(0.0f, 0.0f, 12.0f, (float)v_want);
		for (int s = 0; s < 4000; s++) { w.step(1.0f / 60.0f); }
		float eta_min = 1e9f, eta_max = -1e9f;
		for (size_t k = 0; k < w.h.size(); k++) {
			if (w.h[k] > 0.02f) {
				eta_min = std::min(eta_min, w.surface((int)k));
				eta_max = std::max(eta_max, w.surface((int)k));
			}
		}
		const double area = w.wetted_area();
		double area_2cm = 0.0, area_10cm = 0.0;
		for (size_t k = 0; k < w.h.size(); k++) {
			if (w.h[k] > 0.02f) { area_2cm += 1.0; }
			if (w.h[k] > 0.10f) { area_10cm += 1.0; }
		}
		area_2cm *= w.dx * w.dx;
		area_10cm *= w.dx * w.dx;
		const double area_true = 3.14159265 * R * R * d / D;   // r² = R²·d/D
		printf("   налито %.0f м³, объём в поле %.0f м³\n", v_want, w.total_volume());
		printf("   уровень установился %.3f .. %.3f м (ждём %.2f), разброс %.4f м\n",
				eta_min, eta_max, target, eta_max - eta_min);
		printf("   мокро при пороге 1 мм: %.0f м²  |  2 см: %.0f м²  |  10 см: %.0f м²\n",
				area, area_2cm, area_10cm);
		printf("   по геометрии чаши на этом уровне: %.0f м² (%+.1f%% к порогу 2 см)\n",
				area_true, 100.0 * (area_2cm - area_true) / area_true);
		printf("   БЕРЕГ ЗДЕСЬ — ИЗОЛИНИЯ, а не многоугольник: он круглый, потому\n");
		printf("   что круглая чаша, и никто его не рисовал.\n");
	}

	// ---------------------------------------------------------------- 5
	printf("\n5. СОХРАНЕНИЕ ОБЪЁМА при бурном движении (замкнутая чаша).\n");
	{
		WaterField w;
		w.resize(200, 0.5f);
		center_origin(w);
		bowl(w, 4.0f, 30.0f);
		w.fill_region(-2.0f, 0.0f);
		const double v0 = w.total_volume();
		// сильный всплеск сбоку: волна ходит по чаше и накатывает на берег
		w.add_volume(-12.0f, 0.0f, 4.0f, 120.0f);
		for (int s = 0; s < 2000; s++) { w.step(1.0f / 60.0f); }
		const double v1 = w.total_volume();
		printf("   объём %.2f -> %.2f м³ (добавили 120), ошибка %.3e%%\n",
				v0 + 120.0, v1, 100.0 * (v1 - (v0 + 120.0)) / (v0 + 120.0));
	}

	// ---------------------------------------------------------------- 6
	printf("\n6. ЦЕНА КАДРА.\n");
	for (int side : {128, 256, 512}) {
		WaterField w;
		w.resize(side, 1.0f);
		center_origin(w);
		for (auto &b : w.bed) { b = -3.0f; }
		w.fill_to_level(0.0f);
		w.add_volume(0.0f, 0.0f, 3.0f, 5.0f);
		const int N = 60;
		auto t0 = std::chrono::high_resolution_clock::now();
		for (int s = 0; s < N; s++) { w.step(1.0f / 60.0f); }
		auto t1 = std::chrono::high_resolution_clock::now();
		const double us = std::chrono::duration<double, std::micro>(t1 - t0).count() / N;
		printf("   %3dx%-3d (%4.0f x %4.0f м): %8.1f мкс/кадр при %d подшагах, %d ячеек\n",
				side, side, side * w.dx, side * w.dx, us, w.last_substeps, side * side);
	}

	printf("\n");
	return 0;
}
