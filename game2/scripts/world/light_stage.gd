extends Node3D
## Ф1 «Свет» — первый кино-срез. Не игровой мир, а СТЕНД СВЕТА: золотой час,
## тёплое солнце с мягкой полутенью, физичное небо, реальная GI (SDFGI),
## контактные тени (SSAO), PBR-земля с микрорельефом, объекты для отскока и
## цветового бликования. Проверка — числами (гистограмма яркости, вклад GI),
## а не «на глаз». Кино-пост — тем же надёжным canvas-оверлеем. HUD измеримый.

const ENABLE_POST := true
const ENABLE_METALFX := true
# GI (SDFGI) — ВКЛЮЧЁН, есть переключатель в HUD (кнопка «GI»).
# ПРИЧИНА СТАРЫХ БЕД НАЙДЕНА И ИЗМЕРЕНА (не гипотеза): min_cell_size стоял 0.06 м
# при 4 каскадах, а дальность SDFGI = min_cell_size*64*2^(каскадов-1) = 31 м.
# То есть GI покрывал лишь 31 метр вокруг камеры в мире 16 км — отсюда и
# «яркая полоса на дали» (за 31 м GI обрывался), и полное отсутствие разницы
# при включении (проверено на устройстве). 0.06 м — значение для КОМНАТЫ.
# Исправлено: 1 м при 5 каскадах -> 1024 м покрытия.
# Локально проверить нельзя: SDFGI только в Forward+, а стенд идёт в
# GL Compatibility (Vulkan в окружении нет) — проверка только на устройстве.
const ENABLE_GI := true
const ENABLE_SSAO := true        # контактные тени
const ENABLE_SSIL := true        # непрямой свет от соседних поверхностей (GI экрана)
const ENABLE_GLOW := true        # мягкое свечение в бликах
# ПОГОДА Гатчины теперь КОГЕРЕНТНА и ДИНАМИЧНА: пасмурность рождается из
# плотности облаков (Clouds.current_coverage) и через WeatherSky ведёт небо
# (синее↔серое), рассеянный свет и приглушение Солнца — см. _update_weather.

var _post_mat: ShaderMaterial
var _hud: Label
var _env: Environment
var _sun: DirectionalLight3D
var _clock: WorldClock
var _terrain: Terrain
var _cam: FreeCamera

func _ready() -> void:
	# --- аргументы стенда (для оффлайн-аудита на CI) ---
	var args := OS.get_cmdline_user_args()
	var gi_off := "--gi-off" in args

	# самопроверки числами и выход
	if "--astro-test" in args:
		var wc := WorldClock.new()
		add_child(wc)
		wc.run_self_test()
		get_tree().quit()
		return
	if "--spectral-test" in args:
		var wc2 := WorldClock.new()
		add_child(wc2)
		wc2.run_spectral_test()
		get_tree().quit()
		return

	_env = _build_environment(ENABLE_GI and not gi_off)
	var we := WorldEnvironment.new()
	we.environment = _env
	add_child(we)

	_build_sun()
	_build_night_sky()
	_build_clouds()
	_build_ground()
	_build_water_real()
	_build_roads()
	_build_city()
	_build_backdrop()
	# СТАРАЯ трава (MultiMesh, разбросанные былинки) УБРАНА — она была
	# неестественной и «размазанной» по всей карте; траву создадим настоящей
	# (разной, в Blender) позже. Сейчас работаем над ПОЧВОЙ.
	_build_soil_volume()
	_build_props()
	_build_camera()
	_build_deform()

	if ENABLE_POST:
		_build_post_overlay()
	_build_hud(gi_off)

	if ENABLE_METALFX:
		Core.apply_scaling(get_viewport())

	# --- режим ИНСПЕКЦИИ (я «вхожу в мир»): задать время/камеру, выгрузить числа ---
	var inspect := "--inspect" in args
	var utc := _arg_val(args, "--utc")           # "HH:MM"
	if utc != "":
		var pp := utc.split(":")
		_clock.set_datetime_utc(2025, 6, 21, int(pp[0]), int(pp[1]) if pp.size() > 1 else 0, 0)
		_clock.time_scale = 0.0                   # фиксируем момент детерминированно
		_clock._compute_and_apply()
	var cp := _arg_val(args, "--campos")
	var cl := _arg_val(args, "--camlook")
	if cp != "" and cl != "":
		_cam.setup(_vec3(cp), _vec3(cl))

	print("[light] Ф1 свет, gi=", ENABLE_GI and not gi_off,
		" adapter=", RenderingServer.get_video_adapter_name())

	# --- РЕЖИМ ДИАГНОСТИКИ («спец-возможности»): вскрыть геометрию/оверлап/нормали,
	# чтобы ВИДЕТЬ корень багов (Z-fighting дорог, швы колец, «круг»), а не гадать.
	_dbg_arg = _arg_val(args, "--debug")
	if _dbg_arg != "":
		RenderingServer.set_debug_generate_wireframes(true)
		get_viewport().debug_draw = _debug_mode(_dbg_arg)
		print("[light] ДИАГНОСТИКА: ", _dbg_arg)

	# ЖИВОЙ КАНАЛ: игра остаётся работать и слушает команды по сокету.
	# Раньше любой взгляд на мир стоил полного перезапуска (минуты на софтовом
	# растеризаторе) и показывал только заранее заданный ракурс. Теперь мир
	# поднимается один раз, и по нему можно ходить и смотреть.
	if "--live" in args:
		var link := LIVE_LINK.new()
		link.camera = _cam
		link.terrain = _terrain
		link.water = _water_real
		link.clock = _clock
		link.hud = _hud
		add_child(link)

	# офлайн-снимок / инспекция: ждём схождения и выгружаем состояние
	# ПРОБНАЯ ЯМА (стенд): выкопать в точке камеры, чтобы увидеть настоящие слои
	if "--dig" in args:
		await get_tree().process_frame
		var dp := _cam.global_position
		# окно копания ставим ТУДА, где сейчас наблюдатель (камера уже на месте)
		var gy := _terrain.height(dp.x, dp.z) if _terrain != null else 0.0
		_soil.center_on(dp.x, dp.z, _terrain)
		_soil.global_position = Vector3(dp.x, gy, dp.z)
		var vol := dig_soil(dp.x, dp.z, 2.2, 2.4)
		var r: Dictionary = _soil.report()
		print("[soil] ВЫКОПАНО: %.2f м3 (с разрыхлением), глубина %.2f м, окно %.0f м, ячейка %.2f м"
			% [vol, r["deepest_m"], r["window_m"], r["cell_m"]])
		print("[soil] ЗАМЕР GDScript: осыпание %.1f мс, геометрия %.1f мс, ячеек %d"
			% [r["collapse_ms"], r["mesh_ms"], r["cells"]])

	if "--boot-shot" in args or inspect:
		var out_path := _arg_val(args, "--out")
		if out_path == "":
			out_path = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/light_shot.png"
		await get_tree().create_timer(2.5 if inspect else 3.5).timeout
		if inspect:
			_print_state()
		get_viewport().get_texture().get_image().save_png(out_path)
		print("[light] shot saved -> ", out_path)
		get_tree().quit()

func _arg_val(args: PackedStringArray, key: String) -> String:
	for a in args:
		if a.begins_with(key + "="):
			return a.substr(key.length() + 1)
	return ""

# --- РЕЖИМ ДИАГНОСТИКИ: встроенные отладочные буферы Godot ---
var _dbg_arg: String = ""
# preload, а не class_name: имя класса берётся из кэша проекта, а он на свежем
# запуске может ещё не знать про новый файл — тогда сцена вовсе не грузится.
const LIVE_LINK := preload("res://scripts/tools/live_link.gd")
const DBG_CYCLE := ["disabled", "wire", "overdraw", "unshaded", "normals", "lighting"]
var _dbg_idx: int = 0

func _debug_mode(name: String) -> int:
	match name:
		"wire": return Viewport.DEBUG_DRAW_WIREFRAME
		"overdraw": return Viewport.DEBUG_DRAW_OVERDRAW
		"unshaded": return Viewport.DEBUG_DRAW_UNSHADED
		"normals": return Viewport.DEBUG_DRAW_NORMAL_BUFFER
		"lighting": return Viewport.DEBUG_DRAW_LIGHTING
		_: return Viewport.DEBUG_DRAW_DISABLED

## переключить режим диагностики на устройстве (по кнопке HUD/жесту)
func cycle_debug() -> void:
	_dbg_idx = (_dbg_idx + 1) % DBG_CYCLE.size()
	var m: String = DBG_CYCLE[_dbg_idx]
	RenderingServer.set_debug_generate_wireframes(true)
	get_viewport().debug_draw = _debug_mode(m)
	_dbg_arg = "" if m == "disabled" else m

func _vec3(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

## выгрузка состояния мира числами (машинно-читаемо) — «взгляд изнутри»
func _print_state() -> void:
	var r := _terrain.report()
	var d := {
		"local": _clock.local_time_string(),
		"sun_el": snappedf(_clock.sun_elevation_deg, 0.1),
		"sun_az": snappedf(_clock.sun_azimuth_deg, 0.1),
		"daytime": _clock.is_daytime(),
		"sun_energy": snappedf(_sun.light_energy, 0.01),
		"sun_color": [snappedf(_sun.light_color.r, 0.01), snappedf(_sun.light_color.g, 0.01), snappedf(_sun.light_color.b, 0.01)],
		"sun_ct_k": int(_clock.sun_color_temp_k),
		"terrain_relief_m": snappedf(r["relief_m"], 0.1),
		"tris": r["tris"],
		"grass_clumps": _grass.clump_count if _grass != null else 0,
		"roads_km": snappedf(_roads.length_km, 0.1) if _roads != null else 0.0,
		"adapter": RenderingServer.get_video_adapter_name(),
	}
	print("STATE ", JSON.stringify(d))

# --- окружение: небо, тонемап, GI, SSAO, glow ---
func _build_environment(gi: bool) -> Environment:
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	# ФИЗИЧЕСКОЕ небо: рэлеевское+ми рассеяние (не градиент). Золотой час
	# получается сам из низкого солнца — длинный путь через атмосферу краснит.
	# ПАСМУРНОЕ небо Гатчины (не ясный юг): облака = сильное Ми-рассеяние → небо
	# светло-серое, ровное; синева Рэлея приглушена; диск Солнца скрыт за облаком;
	# рассеянный свет неба-купола становится главным источником (мягкие тени).
	# КОГЕРЕНТНАЯ ПОГОДА (WeatherSky): небо НЕ крашеная серая крыша. Ясно →
	# синее физ-небо; пасмурно → ровный серый — но пасмурность РОЖДАЕТСЯ из
	# плотности облаков (обновляется в _update_weather каждый кадр), и этим же
	# сереет/гаснет прямой свет. Никакой фиктивной серой заливки.
	var sm := PhysicalSkyMaterial.new()
	sm.use_debanding = true
	WeatherSky.apply_sky(sm, 0.6)             # старт — умеренная облачность
	_sky_mat = sm
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME   # без чёрного экрана до схождения
	sky.radiance_size = Sky.RADIANCE_SIZE_256       # realtime-небо требует 256
	env.sky = sky

	# рассеянный свет неба-купола — главный источник в пасмурность; сила зависит
	# от погоды (в _update_weather). Небо и отражения — с купола.
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = WeatherSky.ambient_energy(0.6)
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY

	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = WeatherSky.exposure(0.6)
	env.tonemap_white = 6.0

	if gi:
		env.sdfgi_enabled = true
		env.sdfgi_use_occlusion = true
		env.sdfgi_bounce_feedback = 0.85       # больше отскоков → заметнее цвет
		# ИЗМЕРЕНО (расчёт по формуле Godot: дальность = min_cell_size*64*2^(каскадов-1)):
		# было min_cell_size=0.06 при 4 каскадах -> GI покрывал ВСЕГО 31 м вокруг
		# камеры. В мире 16 км это ничто, поэтому включение/выключение GI не давало
		# видимой разницы (проверено на устройстве). 0.06 м — значение для КОМНАТЫ.
		# Стало: 1 м при 5 каскадах -> 1024 м. Это же объясняет старую «яркую полосу
		# на дали»: за 31 м GI обрывался резко.
		env.sdfgi_cascades = 5
		env.sdfgi_min_cell_size = 1.0
		env.sdfgi_energy = 1.6                  # усиленный вклад GI
		env.sdfgi_y_scale = Environment.SDFGI_Y_SCALE_75_PERCENT

	# НЕПРЯМОЙ СВЕТ (SSIL): свет, отражённый соседними поверхностями — стена
	# подкрашивает землю рядом, в переулке темнее, под карнизом сумрак. Именно
	# этого не хватало миру для «объёма». В отличие от SDFGI работает в открытом
	# мире на любой дальности (нет каскадов и нет яркой полосы на горизонте).
	if ENABLE_SSIL:
		env.ssil_enabled = true
		env.ssil_radius = 4.0            # м: масштаб зданий/стен, не комьев
		env.ssil_intensity = 1.1
		env.ssil_sharpness = 0.98
		env.ssil_normal_rejection = 1.0

	if ENABLE_SSAO:
		env.ssao_enabled = true
		env.ssao_radius = 0.6
		env.ssao_intensity = 0.9              # ниже — меньше шумной мороки контактных теней
		env.ssao_power = 1.3
		env.ssao_detail = 0.5

	if ENABLE_GLOW:
		env.glow_enabled = true
		env.glow_intensity = 0.5
		env.glow_bloom = 0.05
		env.glow_hdr_threshold = 1.1
		env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT

	# воздушная перспектива: дальний рельеф растворяется в ЦВЕТЕ НЕБА (aerial=1),
	# контраст тёмная-земля/светлое-небо у горизонта падает → уходит алиасинг гряд
	# воздушная перспектива: мягкая, не «зажигает» дальнюю землю цветом неба
	env.fog_enabled = true
	env.fog_mode = Environment.FOG_MODE_DEPTH
	env.fog_light_color = Color(0.58, 0.64, 0.74)
	env.fog_density = 0.0007
	env.fog_sky_affect = 0.0
	env.fog_aerial_perspective = 0.55
	env.fog_depth_begin = 400.0
	env.fog_depth_end = 9500.0

	# ОБЪЁМНЫЙ туман: даёт световые шахты (god-rays) — тени в солнце режут
	# рассеяние, вперёд-рассеяние (anisotropy) тянет свет к солнцу.
	# ОБЪЁМНЫЙ ТУМАН ВЫКЛЮЧЕН: под пасмурным небом god-rays не нужны, а его
	# фроксель-буфер давал СИЛЬНОЕ зерно (заметно в движении) и ронял FPS до ~16.
	# Дальнюю дымку/горизонт держит дешёвый depth-fog (aerial perspective) выше.
	env.volumetric_fog_enabled = false
	return env

# --- солнце золотого часа с мягкой полутенью ---
func _build_sun() -> void:
	# Солнце: параметры тени задаём тут, а НАПРАВЛЕНИЕ/ЦВЕТ/ЭНЕРГИЮ ведёт
	# WorldClock из настоящей астрономии.
	_sun = DirectionalLight3D.new()
	_sun.shadow_enabled = true
	# НАСТОЯЩИЙ угловой размер Солнца — 0.53° (диск в небе не должен быть огромным;
	# было 5° → диск ~10× больше реального). Мягкость теней в пасмурность даёт
	# размытие тени, а не гигантский диск.
	_sun.light_angular_distance = 0.53
	_sun.shadow_blur = 2.5
	_sun.directional_shadow_max_distance = 90.0
	_sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	add_child(_sun)

	_clock = WorldClock.new()
	_clock.sun = _sun
	# overcast теперь ДИНАМИЧЕСКИЙ — из плотности облаков (см. _update_weather)
	# старт: летнее утро над Гатчиной, ясный фронтальный свет (местное 09:00 → UTC 06:00)
	_clock.set_datetime_utc(2025, 6, 21, 6, 0, 0)
	add_child(_clock)

# --- ОБЛАКА: объёмный слой (raymarch), движется ветром; покрытие ∝ пасмурности ---
var _clouds: Clouds
var _sky_mat: PhysicalSkyMaterial          # небо, ведомое погодой (WeatherSky)
var _weather_oc: float = -1.0
var _soil_wet: float = 0.25          # влага земли (идёт за погодой, медленно)

## --- НОЧНОЕ НЕБО: настоящие звёзды (каталог) + Луна (орбита+фаза) ---
var _night_sky: NightSky

func _build_night_sky() -> void:
	_night_sky = NightSky.new()
	_night_sky.sun = _sun
	_night_sky.clock = _clock
	add_child(_night_sky)
	_night_sky.build()

func _build_clouds() -> void:
	_clouds = Clouds.new()
	_clouds.sun = _sun
	_clouds.clock = _clock                        # день/ночь → свет облаков
	_clouds.night_sky = _night_sky                # свет Луны ночью
	# КЛИМАТ Гатчины — облачно; погода «дышит» вокруг среднего (Clouds.weather_enabled),
	# и это среднее ведёт всю пасмурность неба/света через _update_weather.
	_clouds.coverage = 0.55                       # среднее покрытие (климат)
	add_child(_clouds)
	_clouds.build()

# --- КОГЕРЕНТНАЯ ПОГОДА: плотность облаков ведёт небо И свет каждый кадр ---
func _update_weather() -> void:
	if _clouds == null or _clock == null or _env == null:
		return
	var oc := WeatherSky.overcast_from_coverage(_clouds.current_coverage)
	_clock.overcast = oc                          # пасмурность гасит/сереет прямой свет
	# ВЛАГА ЗЕМЛИ идёт за погодой: под плотной облачностью (дожди) земля сырая,
	# в ясную — сохнет. Меняется медленно: почва не сохнет мгновенно.
	var target_wet := clampf((oc - 0.35) / 0.5, 0.0, 1.0)
	_soil_wet = lerpf(_soil_wet, target_wet, 0.02)
	if _terrain != null and _terrain.ground_mat != null:
		_terrain.ground_mat.set_shader_parameter("soil_wetness", _soil_wet)
	if absf(oc - _weather_oc) > 0.01:             # небо/экспозицию — при заметном изменении
		_weather_oc = oc
		if _sky_mat != null:
			WeatherSky.apply_sky(_sky_mat, oc)
		_env.ambient_light_energy = WeatherSky.ambient_energy(oc)
		_env.tonemap_exposure = WeatherSky.exposure(oc)

# --- НАСТОЯЩАЯ земля: рельеф Гатчины в реальном масштабе (метры) ---
func _build_ground() -> void:
	_terrain = Terrain.new()
	add_child(_terrain)
	_terrain.build()
	_terrain.build_collision()          # рельеф — твёрдое тело (физика)

# --- вода по реальным контурам (шаг 1 генплана) ---
var _water: WaterBodies

func _build_water() -> void:
	_water = WaterBodies.new()
	_water.terrain = _terrain
	add_child(_water)
	_water.build()

## ВОДА ВЕРНУЛАСЬ — но как ДВА РАЗНЫХ ВЕЩЕСТВА (озеро и река), на настоящих
## местах и с физикой: оптика по измеренным коэффициентам поглощения, течение
## по flow map из настоящего уклона, дно из подводных почв.
var _water_real: WaterReal

func _build_water_real() -> void:
	_water_real = WaterReal.new()
	_water_real.terrain = _terrain
	add_child(_water_real)
	_water_real.build()

# --- дороги по реальной сети (эпоха 1894: макадам/грунт, ж/д насыпь) ---
var _roads: RoadNetwork

func _build_roads() -> void:
	_roads = RoadNetwork.new()
	_roads.terrain = _terrain
	add_child(_roads)
	_roads.build()

# --- город: реальные следы зданий Гатчины, поставленные на рельеф ---
var _city: CityBuildings

func _build_city() -> void:
	_city = CityBuildings.new()
	_city.terrain = _terrain
	add_child(_city)
	_city.build()

# --- ДАЛЬНИЙ ФОН: реальный рельеф региона за детальной территорией (до горизонта) ---
var _backdrop: Backdrop

func _build_backdrop() -> void:
	_backdrop = Backdrop.new()
	_backdrop.terrain = _terrain
	add_child(_backdrop)
	_backdrop.build()

# --- травяной ярус: посев по реальным зонам вокруг наблюдателя ---
var _grass: GrassField

func _build_grass() -> void:
	_grass = GrassField.new()
	_grass.terrain = _terrain
	_grass.zone_size_m = _terrain.world_size_m
	add_child(_grass)

# --- объекты-эталоны масштаба: реальные размеры, стоят НА рельефе ---
# деформация почвы под нагрузкой (следы/проседание) — по полю деформируемости
var _deform: GroundDeform

func _build_deform() -> void:
	_deform = GroundDeform.new()
	_deform.terrain = _terrain
	_deform.target = _walker            # тело пешехода — точка нагрузки
	add_child(_deform)

func _build_props() -> void:
	# человекоростовой столб-эталон (1.8 м) — чувство масштаба земли
	var post := MeshInstance3D.new()
	var pb := BoxMesh.new(); pb.size = Vector3(0.4, 1.8, 0.4)
	post.mesh = pb
	post.position = _on_ground(2.0, 0.0, 0.9)
	post.mesh.surface_set_material(0, _lit_mat(Color(0.74, 0.10, 0.08), 0.6))
	add_child(post)

	# нейтральные кубы 1 м — эталон и мягкие тени, сидят на земле
	for p in [Vector2(6, -4), Vector2(-5, 5), Vector2(0, 8)]:
		var b := MeshInstance3D.new()
		var bm := BoxMesh.new(); bm.size = Vector3(1, 1, 1)
		b.mesh = bm
		b.position = _on_ground(p.x, p.y, 0.5)
		b.mesh.surface_set_material(0, _lit_mat(Color(0.68, 0.66, 0.62), 0.6))
		add_child(b)

	# сфера-эталон — ПЕРВЫЙ ФИЗИЧЕСКИЙ ОБЪЕКТ: настоящее тело (масса, гравитация,
	# столкновения) — падает, катится по склону, её можно толкнуть телом
	var ball := RigidBody3D.new()
	ball.mass = 12.0
	var bcol := CollisionShape3D.new()
	var bsh := SphereShape3D.new(); bsh.radius = 0.5
	bcol.shape = bsh
	ball.add_child(bcol)
	var bmesh := MeshInstance3D.new()
	var sph := SphereMesh.new(); sph.radius = 0.5; sph.height = 1.0
	bmesh.mesh = sph
	bmesh.mesh.surface_set_material(0, _lit_mat(Color(0.80, 0.78, 0.74), 0.35))
	ball.add_child(bmesh)
	ball.position = _on_ground(0.0, 0.0, 1.5)   # уронится и уляжется сам — физика
	add_child(ball)

## позиция на поверхности рельефа + смещение вверх (полувысота объекта)
func _on_ground(x: float, z: float, y_off: float) -> Vector3:
	var h := _terrain.height(x, z) if _terrain != null else 0.0
	return Vector3(x, h + y_off, z)

var _walker: Walker
var _walk_active := false

func _build_camera() -> void:
	_cam = FreeCamera.new()
	_cam.fov = 50.0
	_cam.terrain = _terrain
	add_child(_cam)
	_cam.far = 22000.0                            # видеть всю территорию 12.3 км
	# старт: над землёй у объектов-эталонов, смотрим на них — сразу можно крутить/летать
	var eye := _on_ground(18.0, 22.0, 6.0)
	_cam.setup(eye, _on_ground(0.0, 0.0, 0.8))
	_cam.current = true
	_cam.toggle_requested.connect(_toggle_walk)

	_walker = Walker.new()
	add_child(_walker)
	_walker.deactivate()
	_walker.toggle_requested.connect(_toggle_walk)

func _toggle_walk() -> void:
	_walk_active = not _walk_active
	if _walk_active:
		# спуститься телом на землю под камерой
		var gp := _cam.position
		var gy := _terrain.height(gp.x, gp.z)
		_cam.set_process_input(false)
		_walker.activate(Vector3(gp.x, gy + 0.3, gp.z), _cam.yaw())
	else:
		_walker.deactivate()
		_cam.position = _walker.global_position + Vector3(0, 25.0, 0)
		_cam.current = true
		_cam.set_process_input(true)

func _build_post_overlay() -> void:
	var layer := CanvasLayer.new(); layer.layer = 100
	add_child(layer)
	var rect := ColorRect.new()
	rect.anchor_right = 1.0; rect.anchor_bottom = 1.0
	rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_post_mat = ShaderMaterial.new()
	_post_mat.shader = load("res://shaders/post/cinema_overlay.gdshader")
	rect.material = _post_mat
	layer.add_child(rect)

func _build_hud(gi_off: bool) -> void:
	var ui := CanvasLayer.new(); ui.layer = 101
	add_child(ui)
	_hud = Label.new()
	_hud.add_theme_font_size_override("font_size", 32)
	_hud.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.85))
	_hud.add_theme_constant_override("shadow_offset_x", 2)
	_hud.add_theme_constant_override("shadow_offset_y", 2)
	_hud.position = Vector2(60, 64)
	_hud.set_meta("gi_off", gi_off)
	ui.add_child(_hud)

	# КОМПАС: сверху по центру, буквы + азимут; един для полёта и пешехода.
	# Север мира = −Z (выверено по Солнцу: в полдень оно строго на юге).
	_compass = Label.new()
	_compass.add_theme_font_size_override("font_size", 44)
	_compass.add_theme_color_override("font_shadow_color", Color(0, 0, 0, 0.9))
	_compass.add_theme_constant_override("shadow_offset_x", 2)
	_compass.add_theme_constant_override("shadow_offset_y", 2)
	ui.add_child(_compass)

	# КНОПКА ДИАГНОСТИКИ («спец-возможности»): цикл каркас/overdraw/нормали/свет —
	# чтобы ВСКРЫТЬ болячки мира (Z-fighting дорог, швы, оверлап «круга») и показать.
	_dbg_btn = Button.new()
	_dbg_btn.text = "DBG: выкл"
	_dbg_btn.add_theme_font_size_override("font_size", 30)
	_dbg_btn.anchor_left = 1.0; _dbg_btn.anchor_right = 1.0
	_dbg_btn.position = Vector2(-260, 64)
	_dbg_btn.size = Vector2(200, 56)
	_dbg_btn.pressed.connect(_on_debug_pressed)
	ui.add_child(_dbg_btn)

	# ПЕРЕКЛЮЧАТЕЛЬ GI на устройстве: проверять гипотезу вживую, а не верить
	# комментарию. Локально (GL Compatibility) SDFGI недоступен — только здесь.
	_gi_btn = Button.new()
	_gi_btn.text = "GI: %s" % ("вкл" if _env.sdfgi_enabled else "выкл")
	_gi_btn.add_theme_font_size_override("font_size", 30)
	_gi_btn.anchor_left = 1.0; _gi_btn.anchor_right = 1.0
	_gi_btn.position = Vector2(-260, 130)
	_gi_btn.size = Vector2(200, 56)
	_gi_btn.pressed.connect(_on_gi_pressed)
	ui.add_child(_gi_btn)
	_update_hud()

func _on_debug_pressed() -> void:
	cycle_debug()
	var m: String = DBG_CYCLE[_dbg_idx]
	_dbg_btn.text = "DBG: %s" % m

var _gi_btn: Button

func _on_gi_pressed() -> void:
	if _env == null:
		return
	_env.sdfgi_enabled = not _env.sdfgi_enabled
	_gi_btn.text = "GI: %s" % ("вкл" if _env.sdfgi_enabled else "выкл")

var _dbg_btn: Button
var _compass: Label
const _WINDS := ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]

func _update_compass() -> void:
	if _compass == null:
		return
	var yaw := _walker.yaw() if _walk_active else _cam.yaw()
	var heading := fposmod(-rad_to_deg(yaw), 360.0)
	var wind: String = _WINDS[int(round(heading / 45.0)) % 8]
	_compass.text = "%s · %d°" % [wind, int(round(heading)) % 360]
	var w := get_viewport().get_visible_rect().size.x
	_compass.position = Vector2(w * 0.5 - _compass.size.x * 0.5, 22.0)

# --- материалы/текстуры ---
func _lit_mat(col: Color, rough: float) -> StandardMaterial3D:
	var m := StandardMaterial3D.new()
	m.albedo_color = col
	m.roughness = rough
	return m

func _noise_tex(size: int, freq: float, as_normal: bool, bump: float) -> NoiseTexture2D:
	var n := FastNoiseLite.new()
	n.noise_type = FastNoiseLite.TYPE_SIMPLEX_SMOOTH
	n.frequency = freq
	n.fractal_octaves = 4
	var t := NoiseTexture2D.new()
	t.width = size; t.height = size
	t.seamless = true
	t.noise = n
	if as_normal:
		t.as_normal_map = true
		t.bump_strength = bump
	return t

func _scaling_mode_name(vp: Viewport) -> String:
	match vp.scaling_3d_mode:
		Viewport.SCALING_3D_MODE_BILINEAR: return "bilinear"
		Viewport.SCALING_3D_MODE_FSR: return "FSR1"
		Viewport.SCALING_3D_MODE_FSR2: return "FSR2"
		_:
			if "SCALING_3D_MODE_METALFX_TEMPORAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_TEMPORAL:
				return "MetalFX temporal"
			if "SCALING_3D_MODE_METALFX_SPATIAL" in Viewport \
					and vp.scaling_3d_mode == Viewport.SCALING_3D_MODE_METALFX_SPATIAL:
				return "MetalFX spatial"
			return "mode#%d" % vp.scaling_3d_mode

func _update_hud() -> void:
	if _hud == null:
		return
	var vp := get_viewport()
	var out := vp.get_visible_rect().size
	var scale := vp.scaling_3d_scale
	var inr := Vector2i(int(round(out.x * scale)), int(round(out.y * scale)))
	var mode := _scaling_mode_name(vp)
	var mfx := "ВКЛ" if mode.begins_with("MetalFX") else "нет"
	var gi_on := ENABLE_GI and not bool(_hud.get_meta("gi_off", false)) and _env.sdfgi_enabled
	_hud.text = "Ф3 · ЗЕМЛЯ+СВЕТ · Godot 4.5.2 (форк) · Metal\n" \
		+ "GPU: %s\n" % RenderingServer.get_video_adapter_name() \
		+ _terrain_line() \
		+ "Небо: физ.атмосфера · погода: %s · облака 1.2–3.2 км (ветер)\n" % (
			_clouds.weather_label() if _clouds != null else "—") \
		+ "GI(SDFGI): %s   SSAO: %s   Glow: %s   пост: %s\n" % [
			"ВКЛ" if gi_on else "выкл",
			"ВКЛ" if ENABLE_SSAO else "выкл",
			"ВКЛ" if ENABLE_GLOW else "выкл",
			"ВКЛ" if ENABLE_POST else "выкл"] \
		+ "MetalFX: %s (%s)  3D %d×%d → %d×%d\n" % [mfx, mode, inr.x, inr.y, int(out.x), int(out.y)] \
		+ _clock_line() \
		+ _coords_line() \
		+ "FPS: %d / лимит %s · режим: %s (двойной тап — сменить)" % [
			Engine.get_frames_per_second(), Core.frame_rate_label(),
			"ПЕШЕХОД·физика" if _walk_active else "ПОЛЁТ"]

func _terrain_line() -> String:
	if _terrain == null:
		return ""
	var r := _terrain.report()
	if r["real"]:
		return "Земля: %.1f×%.1f км · рельеф РЕАЛЬНЫЙ (Гатчина, DEM) %.0f..%.0f м · △ %d · дороги: %.0f км\n" % [
			r["size_m"] / 1000.0, r["size_m"] / 1000.0, r["abs_min"], r["abs_max"], r["tris"],
			_roads.length_km if _roads != null else 0.0]
	return "Земля: %.0f×%.0f м · рельеф ПРОЦЕДУРНЫЙ (фолбэк!) %.1f м · △ %d\n" % [
		r["size_m"], r["size_m"], r["relief_m"], r["tris"]]

## ПОЧВА КАК ОБЪЁМ: локальное окно, где землю можно КОПАТЬ по-настоящему —
## грунт вынимается, в стенке ямы обнажаются настоящие слои профиля, стенки
## осыпаются по своим углам естественного откоса.
var _soil: SoilVolume

func _build_soil_volume() -> void:
	_soil = SoilVolume.new()
	add_child(_soil)
	# окно ставим туда, где стоит наблюдатель
	var p := _cam.global_position if _cam != null else Vector3.ZERO
	var y := _terrain.height(p.x, p.z) if _terrain != null else 0.0
	_soil.center_on(p.x, p.z, _terrain)
	_soil.global_position = Vector3(p.x, y, p.z)

## КОПАТЬ в точке мира (радиус и глубина — м). Отдаёт объём вынутого грунта.
func dig_soil(world_x: float, world_z: float, r_m: float, depth_m: float) -> float:
	if _soil == null:
		return 0.0
	return _soil.dig(world_x, world_z, r_m, depth_m)

## СЧЁТЧИК КООРДИНАТ: где мы сейчас на НАСТОЯЩЕЙ карте. Широта/долгота WGS84
## (якорь — Большой Гатчинский дворец), плюс мировые метры и высота над нулём
## мира. По этим числам можно точно указать место для работ.
func _coords_line() -> String:
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return ""
	var p := cam.global_position
	if _walk_active and _walker != null:
		p = _walker.global_position
	var g: Vector2 = WorldGeo.world_to_geo(p.x, p.z)
	return "📍 %.6f, %.6f · %s · X%+.0f Z%+.0f м · выс %.0f м\n" % [
		g.x, g.y, WorldGeo.to_dms(g.x, g.y), p.x, p.z, p.y]

func _clock_line() -> String:
	if _clock == null:
		return ""
	return "Гатчина %s · %s · Солнце %.1f°/аз %.0f° · %dK/%dклк · ×%d\n" % [
		_clock.local_time_string(),
		"ДЕНЬ" if _clock.is_daytime() else "НОЧЬ",
		_clock.sun_elevation_deg, _clock.sun_azimuth_deg,
		int(_clock.sun_color_temp_k), int(_clock.sun_direct_klx),
		int(_clock.time_scale)]

func _process(_delta: float) -> void:
	if _post_mat != null:
		_post_mat.set_shader_parameter("t", float(Time.get_ticks_msec()) / 1000.0)
	_update_weather()
	_update_fog_altitude()
	# КОЛЛИЗИЯ ЕДЕТ ЗА НАБЛЮДАТЕЛЕМ. Без этого твёрдая земля остаётся там, где
	# игрок был при запуске, и он проваливается сквозь видимый рельеф.
	if _terrain != null:
		var who := _walker.global_position if _walk_active and _walker != null \
			else (_cam.global_position if _cam != null else Vector3.ZERO)
		_terrain.update_collision(who)
	_update_hud()
	_update_compass()

# воздушная перспектива — ПРИЗЕМНЫЙ эффект (даль тает в дымке). С высоты полёта
# её граница (fog_depth_end) ложилась ДИСКОМ по земле («круг» под облаками).
# Отодвигаем границу пропорционально высоте камеры → с высоты кольца нет,
# у земли — прежняя дымка.
func _update_fog_altitude() -> void:
	if _env == null:
		return
	var cam := get_viewport().get_camera_3d()
	if cam == null:
		return
	var h := maxf(cam.global_position.y, 0.0)
	_env.fog_depth_end = clampf(9500.0 + h * 6.0, 9500.0, 60000.0)
