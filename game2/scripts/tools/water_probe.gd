extends Node3D
## ЛЁГКИЙ СТЕНД ВОДЫ — только рельеф + вода + солнце + простое небо.
##
## ЗАЧЕМ. Проверять воду полным стендом было расточительно: он поднимает 190k △
## рельефа + 127k дорог + 397k города + 130k фона + 8404 звезды + объёмные
## облака + SDFGI, и всё это на ПРОГРАММНОМ растеризаторе llvmpipe. Один ответ
## «видно ли воду» стоил минут. Здесь выброшено всё, что к воде не относится.
##
## И ГЛАВНОЕ: стенд отвечает ЧИСЛАМИ, а не картинкой. Он печатает урез, дно и
## толщу воды под камерой, а с ключом --nowater строит ту же сцену БЕЗ воды —
## два снимка сравниваются попиксельно (tools/img_diff.py), и «вода видна» из
## впечатления становится замером: сколько процентов кадра изменилось и на
## сколько. Не входит в игру — инструмент проверки.
##
## Аргументы: --out=путь --campos=x,y,z --camlook=x,y,z --utc=HH:MM
##            --nowater (не строить воду — эталон для сравнения)
##            --res=ШxВ (по умолчанию 640x360) --wait=кадров (по умолчанию 2)

func _val(a: PackedStringArray, k: String, d: String) -> String:
	for s in a:
		if s.begins_with(k + "="):
			return s.substr(k.length() + 1)
	return d

func _v3(s: String) -> Vector3:
	var p := s.split(",")
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

func _ready() -> void:
	var a := OS.get_cmdline_user_args()
	var nowater := "--nowater" in a
	var campos := _v3(_val(a, "--campos", "-762,25,-1750"))
	var camlook := _v3(_val(a, "--camlook", "-762,0,-2100"))

	# --- небо и свет: самое простое, что даёт верное освещение воды ---
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	var sky := Sky.new()
	var sm := PhysicalSkyMaterial.new()
	sky.sky_material = sm
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	sky.radiance_size = Sky.RADIANCE_SIZE_128
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)

	var sun := DirectionalLight3D.new()
	sun.light_angular_distance = 0.53
	add_child(sun)
	var clock := WorldClock.new()
	clock.sun = sun
	var t := _val(a, "--utc", "09:00").split(":")
	clock.set_datetime_utc(2025, 6, 21, int(t[0]), int(t[1]) if t.size() > 1 else 0, 0)
	clock.time_scale = 0.0
	add_child(clock)
	clock._compute_and_apply()

	# --- рельеф (в нём чаша водоёма — без него мерить нечего) ---
	var terrain := Terrain.new()
	add_child(terrain)
	terrain.build()

	# --- вода ---
	var water: WaterReal = null
	if not nowater:
		water = WaterReal.new()
		water.terrain = terrain
		add_child(water)
		water.build()

	# --- камера ---
	var cam := Camera3D.new()
	cam.far = 6000.0
	add_child(cam)
	cam.global_position = campos
	cam.look_at(camlook, Vector3.UP)
	cam.current = true

	# --- ЗАМЕР под камерой: есть ли тут вообще вода и какая толща ---
	var gh := terrain.height(campos.x, campos.z)
	if water != null:
		var lv := water.level_at(campos.x, campos.z)
		if is_nan(lv):
			print("[probe] под камерой (%.0f, %.0f): ВОДЫ НЕТ (растр уровня пуст)"
				% [campos.x, campos.z])
		else:
			print("[probe] под камерой (%.0f, %.0f): урез %.2f м, дно %.2f м, ТОЛЩА %.2f м"
				% [campos.x, campos.z, lv, gh, lv - gh])
	else:
		print("[probe] эталон БЕЗ воды; земля под камерой %.2f м" % gh)

	var frames := int(_val(a, "--wait", "2"))
	for i in range(maxi(frames, 1)):
		await get_tree().process_frame
	var out := _val(a, "--out", "")
	if out != "":
		get_viewport().get_texture().get_image().save_png(out)
		print("[probe] снимок -> ", out)
	get_tree().quit()
