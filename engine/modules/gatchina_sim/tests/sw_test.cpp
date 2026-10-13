// ПРОВЕРКА РЕШАТЕЛЯ ЧИСЛАМИ. Собирается обычным g++, движок не нужен.
//
// Проверяется ровно то, что в шейдере проверить было нечем:
//   1. УСТОЙЧИВОСТЬ — схема не уходит в бесконечность за десятки тысяч шагов;
//   2. СКОРОСТЬ ФРОНТА — совпадает ли она с sqrt(g·d), и на сколько процентов;
//   3. РЕФРАКЦИЯ НА ОТМЕЛИ — замедляется ли волна над меньшей глубиной;
//   4. ОТРАЖЕНИЕ ОТ БЕРЕГА — возвращается ли волна от сухих ячеек;
//   5. ЦЕНА ШАГА — сколько микросекунд стоит кадр, и что это значит для GDScript.
//
// Сборка и запуск:
//   g++ -O2 -std=c++17 -o /tmp/sw_test engine/modules/gatchina_sim/tests/sw_test.cpp
//   /tmp/sw_test
#include "../sw_core.h"

#include <chrono>
#include <cstdio>

using gatchina::SwSolver;

static void fill_flat(SwSolver &s, float d) {
	for (auto &v : s.depth) { v = d; }
}

// РАДИУС ФРОНТА: самая дальняя точка, где гладь ещё отклонена заметно.
// ИЗМЕРЕНО, почему не «где |h| наибольшее»: у расходящегося круга амплитуда
// падает как 1/sqrt(r), поэтому наибольшее отклонение остаётся в ЦЕНТРЕ (там
// сидит остаточная впадина), и такая метрика давала радиус 0.2 м вместо 6 м.
static float front_radius(const SwSolver &s, float cx, float cz, float eps) {
	float far = 0.0f;
	for (int j = 0; j < s.n; j++) {
		for (int i = 0; i < s.n; i++) {
			if (std::fabs(s.h[s.idx(i, j)]) < eps) { continue; }
			const float dxm = (float)i * s.dx - cx;
			const float dzm = (float)j * s.dx - cz;
			const float r = std::sqrt(dxm * dxm + dzm * dzm);
			if (r > far) { far = r; }
		}
	}
	return far;
}

// РАДИУС ГРЕБНЯ: где отклонение наибольшее, но не ближе r_min от центра.
// В центре сидит остаточная впадина, она не гребень; исключив её, получаем
// физическую волну, а не численный предвестник у самого порога.
static float crest_radius(const SwSolver &s, float cx, float cz, float r_min) {
	float best = -1.0f, br = 0.0f;
	for (int j = 0; j < s.n; j++) {
		for (int i = 0; i < s.n; i++) {
			const float dxm = (float)i * s.dx - cx;
			const float dzm = (float)j * s.dx - cz;
			const float r = std::sqrt(dxm * dxm + dzm * dzm);
			if (r < r_min) { continue; }
			const float a = std::fabs(s.h[s.idx(i, j)]);
			if (a > best) { best = a; br = r; }
		}
	}
	return br;
}

static float max_abs(const SwSolver &s) {
	float m = 0.0f;
	for (float v : s.h) { m = std::max(m, std::fabs(v)); }
	return m;
}

int main() {
	printf("== РЕШАТЕЛЬ МЕЛКОЙ ВОДЫ: ПРОВЕРКА ЧИСЛАМИ ==\n\n");

	// ---------- 1. устойчивость ----------
	{
		SwSolver s;
		s.resize(128, 0.25f);
		fill_flat(s, 3.0f);
		s.disturb(16.0f, 16.0f, 1.0f, 0.20f);
		const float dt = 1.0f / 60.0f;
		int sub = 0;
		for (int k = 0; k < 20000; k++) { sub = s.step(dt); }
		printf("1. УСТОЙЧИВОСТЬ. Сетка 128x128 по 0.25 м, глубина 3 м.\n");
		printf("   предел шага по Куранту: %.4f с, кадр 1/60 = %.4f с -> подшагов %d\n",
				s.max_dt(), dt, sub);
		printf("   после 20000 кадров (333 с игрового времени) макс|h| = %.6f м",
				max_abs(s));
		printf("  %s\n\n", max_abs(s) < 1.0f ? "— схема устойчива" : "— ВЗОРВАЛАСЬ");
	}

	// ---------- 2. скорость гребня ----------
	// Скорость меряется по СМЕЩЕНИЮ ГРЕБНЯ между двумя моментами, а не по
	// «радиус делить на время»: у пятна возмущения есть начальный радиус, и
	// делением он подмешивается в скорость.
	printf("2. СКОРОСТЬ ГРЕБНЯ против sqrt(g·d). Сетка 0.25 м.\n");
	printf("   глубина | ожидание | измерено | ошибка | длина волны | ячеек на волну\n");
	for (float d : { 0.5f, 1.0f, 2.0f, 3.0f }) {
		SwSolver s;
		s.resize(256, 0.25f);
		s.damping = 0.0f;
		fill_flat(s, d);
		const float cx = 32.0f, cz = 32.0f;
		s.disturb(cx, cz, 1.0f, 0.05f);
		const float dt = 1.0f / 480.0f;
		const float t1 = 0.6f, t2 = 1.4f;
		for (int k = 0; k < (int)(t1 / dt); k++) { s.step(dt); }
		const float r1 = crest_radius(s, cx, cz, 2.0f);
		for (int k = 0; k < (int)((t2 - t1) / dt); k++) { s.step(dt); }
		const float r2 = crest_radius(s, cx, cz, 2.0f);
		const float c_meas = (r2 - r1) / (t2 - t1);
		const float c_true = std::sqrt(9.81f * d);
		// длина волны цуга: примерно 2×радиус начального пятна
		const float lam = 2.0f;
		printf("   %5.2f м  | %5.2f м/с | %5.2f м/с | %+5.1f%% | %5.2f м    | %.0f\n",
				d, c_true, c_meas, 100.0f * (c_meas - c_true) / c_true, lam, lam / s.dx);
	}
	printf("\n   СХОДИМОСТЬ ПО ШАГУ СЕТКИ (глубина 2 м, ожидание %.2f м/с):\n",
			std::sqrt(9.81f * 2.0f));
	for (float cell : { 0.50f, 0.25f, 0.125f }) {
		SwSolver s;
		const int side = (int)(64.0f / cell);
		s.resize(side, cell);
		s.damping = 0.0f;
		fill_flat(s, 2.0f);
		const float cx = 32.0f, cz = 32.0f;
		s.disturb(cx, cz, 1.0f, 0.05f);
		const float dt = 1.0f / 960.0f;
		const float t1 = 0.6f, t2 = 1.4f;
		for (int k = 0; k < (int)(t1 / dt); k++) { s.step(dt); }
		const float r1 = crest_radius(s, cx, cz, 2.0f);
		for (int k = 0; k < (int)((t2 - t1) / dt); k++) { s.step(dt); }
		const float r2 = crest_radius(s, cx, cz, 2.0f);
		const float c_meas = (r2 - r1) / (t2 - t1);
		printf("     ячейка %.3f м: %5.2f м/с, ошибка %+5.1f%%\n",
				cell, c_meas, 100.0f * (c_meas - std::sqrt(9.81f * 2.0f)) / std::sqrt(9.81f * 2.0f));
	}
	printf("\n");

	// ---------- 3. рефракция на отмели ----------
	{
		printf("3. РЕФРАКЦИЯ НА ОТМЕЛИ: над меньшей глубиной волна обязана идти медленнее.\n");
		SwSolver s;
		s.resize(192, 0.25f);
		s.damping = 0.0f;
		// слева глубоко (3 м), справа отмель (0.4 м)
		for (int j = 0; j < s.n; j++) {
			for (int i = 0; i < s.n; i++) {
				s.depth[s.idx(i, j)] = (i < s.n / 2) ? 3.0f : 0.4f;
			}
		}
		const float cz = 24.0f;
		s.disturb(24.0f, cz, 0.8f, 0.05f);
		const float dt = 1.0f / 240.0f;
		for (int k = 0; k < (int)(1.0f / dt); k++) { s.step(dt); }
		// крайние точки возмущения влево и вправо по строке через центр
		const int jm = (int)(cz / s.dx);
		int li = -1, ri = -1;
		for (int i = 0; i < s.n; i++) {
			if (std::fabs(s.h[s.idx(i, jm)]) > 2.0e-4f) {
				if (li < 0) { li = i; }
				ri = i;
			}
		}
		const float left_m = 24.0f - (float)li * s.dx;
		const float right_m = (float)ri * s.dx - 24.0f;
		printf("   за 1 с влево (глубина 3 м) ушло %.2f м, вправо (0.4 м) %.2f м\n",
				left_m, right_m);
		printf("   ожидание sqrt(g·d): %.2f м и %.2f м%s\n\n",
				std::sqrt(9.81f * 3.0f), std::sqrt(9.81f * 0.4f),
				right_m < left_m ? " — рефракция есть" : " — РЕФРАКЦИИ НЕТ");
	}

	// ---------- 4. отражение от берега ----------
	{
		printf("4. ОТРАЖЕНИЕ ОТ БЕРЕГА (сухие ячейки — стенка).\n");
		SwSolver s;
		s.resize(160, 0.25f);
		s.damping = 0.0f;
		for (int j = 0; j < s.n; j++) {
			for (int i = 0; i < s.n; i++) {
				// берег справа: последние 40 ячеек сухие
				s.depth[s.idx(i, j)] = (i < s.n - 40) ? 2.0f : -1.0f;
			}
		}
		s.disturb(15.0f, 20.0f, 0.8f, 0.05f);
		const float dt = 1.0f / 240.0f;
		// ПОТЕНЦИАЛЬНАЯ энергия. Стартуем из покоя, значит вся энергия сейчас
		// потенциальная; в бегущей волне она делится пополам с кинетической,
		// поэтому правильный ответ ниже — около 50%, а не 100%.
		double e0 = 0.0;
		for (size_t k = 0; k < s.h.size(); k++) { e0 += (double)s.h[k] * s.h[k]; }
		for (int k = 0; k < (int)(2.5f / dt); k++) { s.step(dt); }
		double e1 = 0.0;
		float on_land = 0.0f;
		for (size_t k = 0; k < s.h.size(); k++) {
			e1 += (double)s.h[k] * s.h[k];
			if (s.depth[k] <= 0.0f) { on_land = std::max(on_land, std::fabs(s.h[k])); }
		}
		printf("   потенциальная энергия: %.1f%% от начальной (ждём около 50%%:\n", 100.0 * e1 / e0);
		printf("   половина ушла в кинетическую, затухание выключено)\n");
		printf("   максимум |h| НА СУШЕ: %.6f м%s\n\n", on_land,
				on_land < 1e-6f ? " — вода за берег не вышла" : " — ПРОТЕЧКА НА СУШУ");
	}

	// ---------- 5. цена шага ----------
	{
		printf("5. ЦЕНА КАДРА.\n");
		for (int side : { 64, 128, 256 }) {
			SwSolver s;
			s.resize(side, 0.25f);
			fill_flat(s, 3.0f);
			s.disturb(side * 0.125f, side * 0.125f, 1.0f, 0.05f);
			const float dt = 1.0f / 60.0f;
			const int reps = 300;
			auto t0 = std::chrono::steady_clock::now();
			int sub = 0;
			for (int k = 0; k < reps; k++) { sub = s.step(dt); }
			auto t1 = std::chrono::steady_clock::now();
			const double us = std::chrono::duration<double, std::micro>(t1 - t0).count() / reps;
			printf("   %3dx%-3d (%5.1f x %5.1f м): %7.1f мкс/кадр при %d подшагах, %d ячеек\n",
					side, side, side * s.dx, side * s.dx, us, sub, side * side);
		}
		printf("   Для сравнения: GDScript выполняет порядка 10-30 млн простых операций\n");
		printf("   в секунду. Сетка 128x128 при 4 подшагах — это 16384*4*~12 = 786 тыс.\n");
		printf("   операций на кадр, то есть 26-79 мс. При 60 кадрах в секунду бюджет\n");
		printf("   ВСЕГО кадра 16.7 мс. На GDScript это невозможно — вот и весь ответ,\n");
		printf("   зачем понадобился C++.\n");
	}
	return 0;
}
