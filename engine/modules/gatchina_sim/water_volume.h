// WaterVolume — поле воды, доступное из игры.
//
// ГРАНИЦА ПРОВЕДЕНА ЗДЕСЬ И ТОЛЬКО ЗДЕСЬ. Вся вода — состояние h(x,z), дно,
// расходы — живёт в water_field.h простыми массивами и о движке не знает
// ничего: её можно собрать обычным g++ и проверить числами (tests/wf_test.cpp).
// В этом файле нет ни одной формулы, только приём данных, шаг и отдача поля.
//
// ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ ПРЕЖНЕГО ShallowWater. Тот считал ОТКЛОНЕНИЕ глади от
// плоскости в окне 32 м, которое ездило за наблюдателем и сбрасывалось при
// каждом переезде, а результат уходил только в нормаль фрагмента. Здесь поле
// СТОИТ НА МЕСТЕ над игровым срезом и хранит саму воду: её объём, её уровень и
// её берег. Поверхность в кадре строится из этого поля, а не рядом с ним.
#ifndef GATCHINA_WATER_VOLUME_H
#define GATCHINA_WATER_VOLUME_H

#include "core/io/image.h"
#include "core/object/ref_counted.h"
#include "scene/resources/image_texture.h"

#include "water_field.h"

class WaterVolume : public RefCounted {
	GDCLASS(WaterVolume, RefCounted);

	gatchina::WaterField field;
	Ref<Image> tex_img;
	Ref<ImageTexture> tex;
	double last_step_usec = 0.0;

protected:
	static void _bind_methods();

public:
	// Сторона в ячейках и размер ячейки в метрах. ИЗМЕРЕНО (tests/wf_test.cpp,
	// один подшаг): 128² — 0.7 мс, 256² — 2.5 мс, 512² — 9.7 мс на кадр.
	// Рабочая точка — 256 ячеек по 1 м: срез 256 м и 2.5 мс.
	void setup(int side, float cell_m);
	// Мировые координаты ячейки (0,0). Поле СТОИТ, за наблюдателем не ездит.
	void set_origin(const Vector2 &world_min);
	void set_manning(float m);
	// Открытая граница: окно вырезано из большего водоёма, снаружи вода стоит
	// на этой отметке. Волна уходит и не отражается от берега, которого нет.
	void set_open_boundary(bool on, float level);

	// Отметка дна под каждой ячейкой, side*side значений, порядок строками.
	void set_bed(const PackedFloat32Array &b);

	void fill_to_level(float y);
	void fill_region(float y, float bed_max);

	int step(double dt);
	// Добавить (или забрать, если со знаком минус) ОБЪЁМ в круге: всплеск,
	// дождь, вытеснение вошедшим телом.
	void add_volume(const Vector3 &world_pos, float radius_m, float volume_m3);

	float depth_at(const Vector3 &world_pos) const;
	float surface_at(const Vector3 &world_pos) const;
	Vector2 velocity_at(const Vector3 &world_pos) const;
	Vector2 slope_at(const Vector3 &world_pos) const;

	// Поле для шейдера: R = отметка поверхности (м), G и B = уклон, A = глубина.
	// Половинная точность (RGBAH), а не 32-битная: 32-битные форматы не
	// гарантированно фильтруются на мобильных GPU.
	//
	// ОТМЕТКА ПОВЕРХНОСТИ, А НЕ ОТКЛОНЕНИЕ — потому что вершинный шейдер ставит
	// по ней вершину. Именно этого не мог прежний решатель: он отдавал наклон,
	// и двигать было нечего.
	Ref<ImageTexture> get_texture();

	Dictionary report() const;

	WaterVolume() {}
};

#endif // GATCHINA_WATER_VOLUME_H
