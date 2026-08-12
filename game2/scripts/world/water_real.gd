class_name WaterReal
extends Node3D
## ВОДА — два РАЗНЫХ вещества, а не одна «вода».
##
## Разделение, до которого дошли числами:
##   ПОЛОЖЕНИЕ — из настоящих данных (Overture, water.json): это измеренная
##     реальность, реки Парица и Колпанка там, где они есть на самом деле.
##     ИЗМЕРЕНО, почему не из расчёта: наш DEM даёт русла лишь вдвое лучше
##     случайного (11% против 5.4%) — долины (1.24 м) мельче ошибки данных
##     (5-10 м), река (5-15 м) уже одной ячейки (32 м). Точное положение из
##     такого рельефа вычислить НЕЛЬЗЯ в принципе.
##   ПОВЕДЕНИЕ — из физики: течение по flow_map (из настоящего уклона),
##     глубина из впадин, дно из подводных почв, оптика по измеренным
##     коэффициентам поглощения.
##
## ОЗЕРО и РЕКА отличаются ВЕЩЕСТВОМ (испытано в soil_profile/water_physics):
##   озеро — стоячее, цветёт планктоном (зелёная муть), дно САПРОПЕЛЬ (ил,
##     180 кг/м3, нога проваливается);
##   река — проточная 0.36 м/с, прозрачнее, но несёт глину (бурый оттенок),
##     дно ПРОМЫТЫЙ ПЕСОК (1750 кг/м3, твёрдое).

const WATER_JSON := "res://data/real/water.json"
const FLOW_BIN := "res://assets/dem/flow_map.bin"
const LEVEL_BIN := "res://assets/dem/water_level_cm.bin"
const GRID_N := 513
const STEP_M := 32.0
const HALF_M := (GRID_N - 1) * STEP_M * 0.5
const NO_WATER := -32768        # маркер растра уровня: здесь воды нет

var terrain: Terrain
## сколько шагов трассировки отражений — из оси качества (Core.gfx)
var ssr_steps := 16
var lakes_built := 0
var rivers_built := 0

var _flow_tex: ImageTexture
var _level: PackedByteArray     # растр уреза воды (int16, см), из carve_water_beds.py
var _biggest_w := 0.0
var _biggest := ""

## ПОВЕРХНОСТЬ ВОДЫ БЕРЁТСЯ ГОТОВОЙ (tools/build_water_mesh.py).
##
## ЧТО БЫЛО. Вода строилась ЗДЕСЬ по 166 контурам и 330 линиям из внешних
## данных, а рельеф у нас свой, и никто их не сверял. Смотр всей карты
## (tools/audit_water.py) показал цену:
##   настоящая вода 1 450 416 м² (94.1%), ГЛАДЬ НА СУШЕ 48 208 м² (3.1%),
##   под землёй 39 520 м² (2.6%); у рек 88.8% ленты закопано, 11.2% торчит
##   краем до 1.06 м.
## Правки шли по одному месту за раз, по снимку с телефона. Правило теперь ОДНО
## и применено сразу ко всей карте: вода есть там, где у НАС есть чаша ниже
## уреза. Отброшено 237 416 м² (14% контуров).
##
## РЕК НЕТ. Русел в рельефе не вырезано, и лента на «земле минус 10 см» может
## быть только закопанной или плавающей. Честнее не рисовать, чем рисовать
## плёнку. Вернутся, когда будут вырезаны русла.
const SURFACE_BIN := "res://assets/dem/water_surface.bin"

func build() -> void:
	_load_flow()
	_load_level()
	_load_park_water()
	var f := FileAccess.open(SURFACE_BIN, FileAccess.READ)
	if f == null:
		push_warning("[water] нет испечённой поверхности — запусти tools/build_water_mesh.py")
		return
	var n := int(f.get_32())
	if n <= 0 or n > 2000000:
		push_warning("[water] поверхность воды не читается")
		return
	var href: float = terrain.h_ref if terrain != null else 0.0
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var y_min := INF
	var y_max := -INF
	var area := 0.0
	for i in range(n):
		var x0 := f.get_float()
		var z0 := f.get_float()
		var x1 := f.get_float()
		var z1 := f.get_float()
		var y := f.get_float()
		y_min = minf(y_min, y)
		y_max = maxf(y_max, y)
		area += absf((x1 - x0) * (z1 - z0))
		# НАМОТКА. cull_back отсекает грань по обходу, а не по нормали.
		# ИЗМЕРЕНО: грань смотрит ВВЕРХ при обходе по (x,z) ПО часовой стрелке
		# (знаковая площадь < 0). Для прямоугольника это A→D→C→B.
		var a := Vector3(x0, y, z0)
		var b := Vector3(x1, y, z0)
		var c := Vector3(x1, y, z1)
		var d := Vector3(x0, y, z1)
		for v in [a, d, c, a, c, b]:
			st.set_normal(Vector3.UP)
			st.add_vertex(v)
	var mi := MeshInstance3D.new()
	mi.mesh = st.commit()
	mi.material_override = _material(false)
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	lakes_built = 1
	_sim_init()
	print("[water] поверхность: %d плит (△ %d), площадь %.0f м², урез %.2f..%.2f м — ОДНА сетка вместо 483"
		% [n, n * 2, area, y_min, y_max])

func _load_flow() -> void:
	var f := FileAccess.open(FLOW_BIN, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(GRID_N * GRID_N * 3)
	if b.size() != GRID_N * GRID_N * 3:
		return
	var img := Image.create_from_data(GRID_N, GRID_N, false, Image.FORMAT_RGB8, b)
	_flow_tex = ImageTexture.create_from_image(img)

func _load_level() -> void:
	var f := FileAccess.open(LEVEL_BIN, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(GRID_N * GRID_N * 2)
	if b.size() == GRID_N * GRID_N * 2:
		_level = b

# Урез в парке — из МЕТРОВОГО растра (tools/build_park_dem.py). Общая сетка
# 32 м не описывает пруд в 60-200 м: урез из неё выходил выше берега, и гладь
# висела плитой над землёй. В парке спрашиваем сначала метровую карту.
const PARK_WATER := "res://assets/dem/park_water_cm.bin"
var _park_w: PackedByteArray

# МАСКА ВОДЫ ДЛЯ ШЕЙДЕРА УБРАНА. Вчера она обрезала воду по метровому растру —
# но только в окне парка ±950 м, а плёнка была по ВСЕЙ карте (48 208 м²), и
# построение маски гоняло в GDScript цикл на 3.6 млн ячеек при каждом запуске.
# Теперь границу водоёма задаёт САМА ГЕОМЕТРИЯ, испечённая по нашей батиметрии:
# одно правило на всю карту и ноль работы на старте.
func _load_park_water() -> void:
	if terrain == null or terrain.park_n == 0:
		return
	var f := FileAccess.open(PARK_WATER, FileAccess.READ)
	if f == null:
		return
	var b := f.get_buffer(terrain.park_n * terrain.park_n * 2)
	if b.size() == terrain.park_n * terrain.park_n * 2:
		_park_w = b

func _park_level_at(x: float, z: float) -> float:
	if _park_w.is_empty():
		return NAN
	var n: int = terrain.park_n
	var i := int(roundf(x - terrain.park_cx + terrain.park_half))
	var j := int(roundf(terrain.park_cy + terrain.park_half - (-z)))
	if i < 0 or j < 0 or i >= n or j >= n:
		return NAN
	var v := _park_w.decode_s16((j * n + i) * 2)
	if v == NO_WATER:
		return NAN
	return float(v) / 100.0 - terrain.h_ref

## Урез воды из растра (см → м). Возвращает NAN, если в этой клетке воды нет.
func level_at(x: float, z: float) -> float:
	# В ОКНЕ ПАРКА действует ТОЛЬКО метровый растр. Грубый (32 м) там нельзя
	# спрашивать даже как запасной: его уровни в парке заведомо неверны, и
	# именно они давали воду на 10 м ниже земли рядом с прудом.
	if terrain != null and terrain.park_weight(x, z) > 0.0:
		return _park_level_at(x, z)
	if _level.is_empty() or terrain == null:
		return NAN
	var i := int(roundf((x + HALF_M) / STEP_M))
	var j := int(roundf((z + HALF_M) / STEP_M))
	if i < 0 or j < 0 or i >= GRID_N or j >= GRID_N:
		return NAN
	var v := _level.decode_s16((j * GRID_N + i) * 2)
	if v == NO_WATER:
		return NAN
	# растр в АБСОЛЮТНЫХ метрах; мир отсчитывается от нуля-дворца
	return float(v) / 100.0 - terrain.h_ref

## ВЕЩЕСТВО водоёма: озеро и река — разные, по испытанным свойствам.
## МАТЕРИАЛ ОДИН НА ВСЕ ОЗЁРА и один на все реки. Раньше их создавалось по
## одному на водоём — 153 озера и 330 рек, то есть 483 материала. Кроме лишних
## переключений в рендере это делало невозможным главное: каждый кадр сообщать
## воде, где её потревожили. Теперь это две записи в кадр.
var _mat_lake: ShaderMaterial
var _mat_river: ShaderMaterial

func _material(is_river: bool) -> ShaderMaterial:
	if is_river and _mat_river != null:
		return _mat_river
	if not is_river and _mat_lake != null:
		return _mat_lake
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/water_real.gdshader")
	# ДНО БОЛЬШЕ НЕ ЗАДАЁТСЯ ЦВЕТОМ. Раньше тут стояли bottom_color и картинка
	# дна — то есть вода несла СВОЁ представление о том, что под ней. Теперь
	# сквозь воду видно НАСТОЯЩИЙ рельеф из кадра (преломление по экрану), и
	# цвет воды возникает из поглощения на измеренной толще. Остаётся задать
	# только ВЕЩЕСТВО: сколько в воде взвеси и какого она цвета.
	if is_river:
		# РЕКА: проточная, прозрачнее, но несёт глину -> буроватая взвесь
		m.set_shader_parameter("turbidity", 0.28)
		m.set_shader_parameter("scatter_color", Vector3(0.18, 0.20, 0.15))
		m.set_shader_parameter("flow_scale", 1.0)
		# над руслом ветер сбит берегами и деревьями
		m.set_shader_parameter("wind_ms", 2.0)
	else:
		# ОЗЕРО: стоячее, цветёт планктоном -> зелёная муть
		m.set_shader_parameter("turbidity", 0.55)
		m.set_shader_parameter("scatter_color", Vector3(0.10, 0.26, 0.21))
		m.set_shader_parameter("flow_scale", 0.0)
		# средний летний ветер Ленинградской области; отсюда по Cox & Munk
		# берётся уклон ряби в шейдере
		m.set_shader_parameter("wind_ms", 4.0)
	m.set_shader_parameter("dem_half", HALF_M)
	m.set_shader_parameter("ssr_steps", ssr_steps)
	if _flow_tex != null:
		m.set_shader_parameter("flow_tex", _flow_tex)
	if is_river:
		_mat_river = m
	else:
		_mat_lake = m
	return m

# ============================================================================
# ВОДА КАК ТЕЛО: глубина, поверхность, круги от возмущений
# ============================================================================

## Высота глади в точке (мировые метры) или NAN, если воды тут нет.
func surface_y(x: float, z: float) -> float:
	return level_at(x, z)

## ТОЛЩА ВОДЫ в точке, м. Ноль — воды нет или она сошла на нет.
## Это то же число, которым шейдер красит воду, только взятое из данных, а не
## из буфера глубины: физика и картинка обязаны говорить об одной воде.
func depth_at(x: float, z: float) -> float:
	var lv := level_at(x, z)
	if is_nan(lv) or terrain == null:
		return 0.0
	return maxf(0.0, lv - terrain.height(x, z))

## КРУГИ ПО ВОДЕ. Каждое возмущение — точка, время рождения и амплитуда.
## Шейдер сам разносит от неё волну со скоростью sqrt(g·d) по своей толще.
## Держим 6 последних: больше на кадре всё равно не различить, а каждое стоит
## шести операций на пиксель воды.
const RIPPLE_MAX := 6
const RIPPLE_LIFE := 4.0            # с, дольше круг уже не виден
var _rip := PackedVector4Array()    # x, z, возраст (с), амплитуда (м)
var _rip_next := 0

func _ready() -> void:
	_rip.resize(RIPPLE_MAX)
	for i in range(RIPPLE_MAX):
		_rip[i] = Vector4(0.0, 0.0, RIPPLE_LIFE * 2.0, 0.0)   # заведомо мёртвые

## ВЕТЕР НАД ВОДОЙ, м/с. Отсюда шейдер берёт уклон ряби по Cox & Munk.
## Позже это поведёт погода; сейчас это ещё и единственный способ сделать гладь
## стеклом, чтобы измерить круг от всплеска отдельно от ряби.
func set_wind(ms: float) -> void:
	if _mat_lake != null:
		_mat_lake.set_shader_parameter("wind_ms", ms)
	if _mat_river != null:
		_mat_river.set_shader_parameter("wind_ms", maxf(ms * 0.5, 0.0))

## ЗАПАСНОЕ НЕБО для отражения — только на случай, когда неба нет и в кадре.
func set_sky(horizon: Vector3, zenith: Vector3) -> void:
	if _mat_lake != null:
		_mat_lake.set_shader_parameter("sky_horizon", horizon)
		_mat_lake.set_shader_parameter("sky_zenith", zenith)
	if _mat_river != null:
		_mat_river.set_shader_parameter("sky_horizon", horizon)
		_mat_river.set_shader_parameter("sky_zenith", zenith)

## Потревожить воду: нога вошла, камень упал, весло гребнуло.
## amp — высота горба у самого места, м. Для шага человека это сантиметры.
func disturb(pos: Vector3, amp: float) -> void:
	if amp <= 0.0:
		return
	if sim != null:
		# радиус пятна — размер ступни; амплитуда та же, в метрах
		sim.disturb(pos, 0.22, -amp)
		return
	_rip[_rip_next] = Vector4(pos.x, pos.z, 0.0, amp)
	_rip_next = (_rip_next + 1) % RIPPLE_MAX

func _process(delta: float) -> void:
	if _mat_lake == null and _mat_river == null:
		return
	var alive := false
	for i in range(RIPPLE_MAX):
		var r: Vector4 = _rip[i]
		if r.z < RIPPLE_LIFE:
			r.z += delta
			_rip[i] = r
			alive = true
	# Пока ничего не тревожили, уравнения не гоняем: у стоячего пруда решение
	# известно и равно плоской глади.
	if not alive and not _rip_dirty:
		return
	_rip_dirty = alive
	if _mat_lake != null:
		_mat_lake.set_shader_parameter("ripples", _rip)
	if _mat_river != null:
		_mat_river.set_shader_parameter("ripples", _rip)

var _rip_dirty := false

# ============================================================================
# РЕШАТЕЛЬ МЕЛКОЙ ВОДЫ НА C++ (engine/modules/gatchina_sim)
# ============================================================================
# Здесь кончается «аналитический круг» и начинается настоящее решение уравнения
# мелкой воды на сетке. Разница не косметическая:
#   круг в шейдере — одна формула на расходящееся кольцо, он не знает ни берега,
#     ни другой волны, ни отражения, и складывать их можно только штуками;
#   решатель — поле на сетке, где волны сами складываются, отражаются от берега,
#     замедляются на отмели и разворачиваются вдоль изобат.
# ПРОВЕРЕНО ЧИСЛАМИ (engine/modules/gatchina_sim/tests/run.sh):
#   скорость гребня против sqrt(g·d): -2.3% на 3 м, -4.6% на 2 м, -7% на 1 м;
#   сходимость второго порядка по шагу сетки (0.50 м -30.9%, 0.25 м -4.6%,
#     0.125 м -0.5%) — значит дискретизация верна, остаток это разрешение;
#   энергия при выключенном затухании держится ровно на 50% (половина ушла в
#     кинетическую, как и должно быть при старте из покоя);
#   вода за сухие ячейки не выходит (максимум на суше 0.000000 м);
#   цена кадра 196 мкс на сетке 128×128 против 26-79 мс на GDScript.
#
# ПОЧЕМУ ЧЕРЕЗ ПРОВЕРКУ НАЛИЧИЯ КЛАССА. Модуль живёт в шаблоне движка, а шаблон
# собирается отдельно. Пока на устройстве стоит старый шаблон, класса нет — и
# игра обязана работать по-прежнему, а не падать.
const SIM_SIDE := 128           # ячеек
const SIM_CELL := 0.25          # м; из замера сходимости — рабочая точность
const SIM_RECENTER := 6.0       # м смещения наблюдателя до переезда окна

var sim: RefCounted             # ShallowWater, если модуль есть
var _sim_origin := Vector2(1e9, 1e9)
var _sim_logged := false
var _refill_logged := false
var sim_refill_ms := 0.0        # цена последнего переезда окна расчёта

func sim_available() -> bool:
	return sim != null

func _sim_init() -> void:
	if not ClassDB.class_exists("ShallowWater"):
		print("[вода] решателя мелкой воды нет: шаблон движка без модуля gatchina_sim — идут аналитические круги")
		return
	sim = ClassDB.instantiate("ShallowWater")
	sim.setup(SIM_SIDE, SIM_CELL)
	# затухание: рябь от шага должна жить секунды, а не минуты
	sim.set_damping(0.55)
	print("[вода] решатель мелкой воды: сетка %d×%d по %.2f м (окно %.0f м)"
		% [SIM_SIDE, SIM_SIDE, SIM_CELL, SIM_SIDE * SIM_CELL])

## Переставить окно расчёта под наблюдателя и залить глубины из НАШЕЙ батиметрии.
## Глубина — то же число, которым вода нарисована: урез минус земля.
func sim_center_on(pos: Vector3, force: bool = false) -> void:
	if sim == null:
		return
	var half := SIM_SIDE * SIM_CELL * 0.5
	var org := Vector2(pos.x - half, pos.z - half)
	if not force and _sim_origin.distance_to(org) < SIM_RECENTER:
		return
	_sim_origin = org
	sim.set_origin(org)
	# ЦЕНА ПЕРЕЕЗДА ЗАМЕРЯЕТСЯ, а не предполагается: это 16 384 обращения к
	# батиметрии на GDScript, и происходят они разом, в одном кадре. Если тут
	# окажутся миллисекунды, ходьба будет дёргаться каждые шесть метров — и
	# узнать об этом надо числом, а не по ощущению «что-то подтормаживает».
	var t0 := Time.get_ticks_usec()
	var d := PackedFloat32Array()
	d.resize(SIM_SIDE * SIM_SIDE)
	for j in range(SIM_SIDE):
		var wz := org.y + float(j) * SIM_CELL
		for i in range(SIM_SIDE):
			var wx := org.x + float(i) * SIM_CELL
			d[j * SIM_SIDE + i] = depth_at(wx, wz)
	sim.set_depth(d)
	sim_refill_ms = float(Time.get_ticks_usec() - t0) / 1000.0
	if not _refill_logged:
		_refill_logged = true
		print("[вода] переезд окна: %d глубин за %.1f мс (бюджет кадра при 90 к/с — 11.1 мс)"
			% [SIM_SIDE * SIM_SIDE, sim_refill_ms])

## ПРОВЕРКА РЕШАТЕЛЯ НА НАСТОЯЩЕЙ ВОДЕ ИГРЫ, а не на выдуманном бассейне.
## Бросаем возмущение и СЧИТАЕМ, где через заданное время оказался гребень.
## Мелкая вода обязана разносить его со скоростью sqrt(g·d) — это единственный
## способ отличить решённую жидкость от нарисованных кругов, и он не про кадр,
## а про числа: тут не важно, что видно, важно, что происходит.
##
## Шагаем ЗДЕСЬ ЖЕ, а не ждём кадров: решатель стоит сотни микросекунд, и
## секунда модельного времени считается за десятки миллисекунд.
func sim_selftest(center: Vector3, t_probe: float = 0.8) -> Dictionary:
	if sim == null:
		return {"ok": false, "why": "решателя нет"}
	# ОКНО СТАВИМ ПРИНУДИТЕЛЬНО: обычная постановка ленива (переезжает раз в 6 м),
	# и проверка бросала бы возмущение мимо расчётной области.
	sim_center_on(center, true)
	sim.clear_waves()
	var d := depth_at(center.x, center.z)
	if d < 0.05:
		return {"ok": false, "why": "в этой точке воды нет (толща %.2f м)" % d}
	sim.disturb(center, 0.5, 0.05)
	var dt := 1.0 / 120.0
	var steps := int(t_probe / dt)
	var t0 := Time.get_ticks_usec()
	for i in range(steps):
		sim.step(dt)
	var usec := float(Time.get_ticks_usec() - t0) / float(steps)
	# ГРЕБЕНЬ ищем по лучу, исключая ближнюю зону: в самом центре |h| тоже велик,
	# и «максимум по всему полю» показал бы ноль-радиус. На этом я уже попадался.
	var best_r := 0.0
	var best_h := 0.0
	var half := SIM_SIDE * SIM_CELL * 0.5 - 1.0
	var r := 1.0
	while r < half:
		var s := 0.0
		for a in range(16):
			var ang := TAU * float(a) / 16.0
			s += absf(sim.height_at(center + Vector3(cos(ang) * r, 0.0, sin(ang) * r)))
		s /= 16.0
		if s > best_h:
			best_h = s
			best_r = r
		r += SIM_CELL
	var v_meas := best_r / t_probe
	var v_true := sqrt(9.81 * d)
	return {
		"ok": true, "depth_m": d, "t_s": t_probe,
		"crest_r_m": best_r, "crest_h_m": best_h,
		"v_measured": v_meas, "v_theory": v_true,
		"err_pct": 100.0 * (v_meas - v_true) / v_true,
		"step_usec": usec, "cells": SIM_SIDE * SIM_SIDE,
	}

## Шаг решателя и передача поля в шейдер. Возвращает отчёт числами или пусто.
func sim_step(delta: float) -> Dictionary:
	if sim == null:
		return {}
	sim.step(delta)
	var tex: Texture2D = sim.get_texture()
	if tex != null and _mat_lake != null:
		_mat_lake.set_shader_parameter("sim_tex", tex)
		_mat_lake.set_shader_parameter("sim_origin", _sim_origin)
		_mat_lake.set_shader_parameter("sim_size", SIM_SIDE * SIM_CELL)
	var r: Dictionary = sim.report()
	if not _sim_logged:
		_sim_logged = true
		print("[вода] шаг решателя: %.0f мкс, подшагов %d, предел шага %.4f с, глубина до %.2f м"
			% [r.get("step_usec", 0.0), r.get("substeps", 0),
			r.get("max_dt", 0.0), r.get("max_depth", 0.0)])
	return r
