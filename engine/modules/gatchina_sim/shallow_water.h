// ShallowWater — решатель мелкой воды, доступный из игры.
//
// Вся математика в sw_core.h и от движка не зависит: её можно собрать обычным
// g++ и проверить числами (tests/sw_test.cpp). Здесь только мост: приём данных
// из игры, шаг, отдача поля в текстуру для шейдера и ответы на вопросы о
// высоте и скорости глади в точке.
//
// ЗАЧЕМ C++, А НЕ GDScript. ИЗМЕРЕНО на этой же машине: сетка 128×128 стоит
// 233 мкс на кадр. На GDScript та же работа — 16384 ячейки × ~12 операций —
// это порядка 26-79 мс при бюджете ВСЕГО кадра 16.7 мс. Разница не в стиле, а
// в том, возможно это вообще или нет.
#ifndef GATCHINA_SHALLOW_WATER_H
#define GATCHINA_SHALLOW_WATER_H

#include "core/io/image.h"
#include "core/object/ref_counted.h"
#include "scene/resources/image_texture.h"

#include "sw_core.h"

class ShallowWater : public RefCounted {
	GDCLASS(ShallowWater, RefCounted);

	gatchina::SwSolver solver;
	// Мировые координаты ячейки (0,0). Окно ездит за наблюдателем.
	Vector2 origin = Vector2(0, 0);
	Ref<Image> field_img;
	Ref<ImageTexture> field_tex;
	int last_substeps = 0;
	double last_step_usec = 0.0;

protected:
	static void _bind_methods();

	// мир -> координаты сетки (метры от её левого-верхнего угла)
	inline Vector2 to_grid(const Vector3 &w) const {
		return Vector2(w.x - origin.x, w.z - origin.y);
	}

public:
	// Сетка: сторона в ячейках и размер ячейки в метрах.
	// ВАЖНО ПРО ТОЧНОСТЬ (измерено, глубина 2 м, ожидание 4.43 м/с):
	//   ячейка 0.50 м -> ошибка скорости гребня -30.9%
	//   ячейка 0.25 м -> -4.6%
	//   ячейка 0.125 м -> -0.5%
	// Сходимость второго порядка. 0.25 м — рабочий выбор: на глубине больше
	// метра ошибка в пределах 7%, а на мелководье 0.5 м она доходит до -33%,
	// и это надо знать, а не обнаруживать потом на кадре.
	void setup(int side, float cell_m);
	void set_origin(const Vector2 &world_min);
	void set_damping(float d);

	// Глубина под каждой ячейкой, side*side значений, порядок строками.
	// Отрицательная или нулевая — суша, там стенка и волна отражается.
	void set_depth(const PackedFloat32Array &d);

	void disturb(const Vector3 &world_pos, float radius_m, float amp_m);
	int step(double dt);
	void clear_waves();

	float height_at(const Vector3 &world_pos) const;
	Vector2 slope_at(const Vector3 &world_pos) const;
	float vel_at(const Vector3 &world_pos, double dt) const;

	// Поле для шейдера: R = высота (м), G и B = уклон, A = 1 где вода.
	// Половинная точность (RGBAH), а не 32-битная: 32-битные форматы не
	// гарантированно фильтруются на мобильных GPU.
	Ref<ImageTexture> get_texture();

	// Числа для журнала и HUD: подшагов, микросекунд, значимая высота.
	Dictionary report() const;

	ShallowWater() {}
};

#endif // GATCHINA_SHALLOW_WATER_H
