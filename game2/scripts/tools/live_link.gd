# class_name не объявляем: подключаемся через preload (см. light_stage.gd)
extends Node
## ЖИВОЙ КАНАЛ В ЗАПУЩЕННУЮ ИГРУ.
##
## ЗАЧЕМ. Раньше каждый мой взгляд на мир стоил полного перезапуска: поднять
## 190k △ рельефа, 127k дорог, 397k города, 130k фона, звёзды, объёмные облака
## и SDFGI на ПРОГРАММНОМ растеризаторе — минуты ради одного кадра. И кадр
## отвечал только на то, что я догадался спросить заранее (камеру-то задавал
## аргументом запуска).
##
## ЗДЕСЬ игра поднимается ОДИН раз и остаётся жить, а я разговариваю с ней по
## сокету: перевести камеру, обернуться, снять кадр, спросить что под ногами,
## сменить время суток, включить каркас. Цена взгляда падает с минут до секунд,
## и главное — можно ИСКАТЬ, а не проверять заранее придуманную гипотезу.
##
## Слушает 127.0.0.1 (только петля, наружу не смотрит). Клиент — tools/live.py.
## Команды (по одной в строке, ответ — строка):
##   pos X,Y,Z            поставить камеру
##   look X,Y,Z           направить камеру в точку
##   turn ЯЗИМУТ[,УГОЛ]   повернуть на месте (градусы; 0=север, +восток)
##   move ВПЕРЁД[,ВБОК,ВВЕРХ]   сдвиг относительно взгляда, м
##   shot ПУТЬ [ШИРИНА]   снять кадр (кадр отдаётся, когда он готов)
##   state                где я, что подо мной, какое время, сколько кадров/с
##   probe X,Z            рельеф/вода/почва в точке
##   time ЧЧ:ММ           поставить время
##   walk X,Z | walk off  поставить ТЕЛО в точку / вернуть свободную камеру
##   go ВПЕРЁД[,ВБОК]     задать телу намерение движения (как стик, 0..1)
##   body                 что тело чувствует: погружение, брод, плавание
##   splash X,Z[,АМПЛ]    бросить в воду — от точки пойдёт круг
##   wave X,Z             ПРОВЕРКА решателя: гребень против sqrt(g·d)
##   wind М/С             ветер над водой (0 — гладь как стекло)
##   weather 0..1         зафиксировать облачность (для сравнения кадров)
##   post on|off|ПАРАМ N  кино-пост целиком или по параметру
##   hud on|off           убрать надпись, которая закрывает вид
##   dbg РЕЖИМ            wire|overdraw|unshaded|normals|lighting|off
##   quit                 закрыть игру

const PORT := 8787
const WP := preload("res://scripts/world/water_physics.gd")

var camera: Camera3D
var terrain: Terrain
var water: WaterReal
var walker: Walker
var stage: Node
var clock: WorldClock
var hud: CanvasItem

var _srv := TCPServer.new()
var _peer: StreamPeerTCP
var _buf := ""
var _shot_path := ""
var _shot_wait := 0
var _fps := 0.0

func _ready() -> void:
	var err := _srv.listen(PORT, "127.0.0.1")
	if err != OK:
		push_warning("[live] порт %d занят (код %d) — живой канал не поднят" % [PORT, err])
		return
	print("[live] канал открыт: 127.0.0.1:%d — игра ждёт команд" % PORT)

func _process(_dt: float) -> void:
	# СЧЁТЧИК КАДРОВ ВРАЛ, И ВРАЛ КРУПНО. Здесь стояло накопление dt из
	# _process — а Godot ЗАЖИМАЕТ этот dt (physics/common/max_physics_steps),
	# и при настоящем 1 кадре в секунду он приходит как 0.125 с. Счётчик
	# показывал 15.0 при истинном 1: ошибка в пятнадцать раз, ровно в ту
	# сторону, в которую приятно ошибаться. Это тот же дефект, что я уже
	# поймал в веб-версии, — и он снова прошёл незамеченным, потому что число
	# выглядело правдоподобно. Engine.get_frames_per_second() считает движок,
	# и подделать его нечем.
	_fps = Engine.get_frames_per_second()

	# кадр просили — отдаём, когда он ТОЧНО отрисован (иначе поймаем прошлый)
	if _shot_wait > 0:
		# ДИЗЕРИНГ СНИМАЕТСЯ НА ВРЕМЯ СНИМКА, И ВОТ ПОЧЕМУ. use_debanding в
		# проекте включён — он подмешивает в кадр шахматный шум, чтобы прятать
		# ступеньки на плавных переходах. На экране это правильно. В ЗАМЕРЕ это
		# ложь: density.py насчитал 41 «источник света» на чёрном ночном кадре,
		# где нет ни одного — это были одиночные яркие пиксели дизеринга,
		# вытянутые ночной экспозицией. Устройства это не касается: снимаем шум
		# только на кадр замера и тут же возвращаем.
		get_viewport().use_debanding = false
		_shot_wait -= 1
		if _shot_wait == 0:
			var img := get_viewport().get_texture().get_image()
			img.save_png(_shot_path)
			get_viewport().use_debanding = true
			_reply("ok кадр %dx%d -> %s (дизеринг снят на время замера)"
				% [img.get_width(), img.get_height(), _shot_path])

	if _srv.is_listening() and _srv.is_connection_available():
		_peer = _srv.take_connection()
	if _peer == null:
		return
	_peer.poll()
	if _peer.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		_peer = null
		return
	var n := _peer.get_available_bytes()
	if n > 0:
		_buf += _peer.get_utf8_string(n)
	while "\n" in _buf:
		var i := _buf.find("\n")
		var line := _buf.substr(0, i).strip_edges()
		_buf = _buf.substr(i + 1)
		if line != "":
			_exec(line)

func _reply(s: String) -> void:
	# ответ всегда ОДНА строка: перевод строки экранируем, клиент вернёт обратно
	if _peer != null and _peer.get_status() == StreamPeerTCP.STATUS_CONNECTED:
		_peer.put_data((s.replace("\n", "\\n") + "\n").to_utf8_buffer())

func _v3(s: String) -> Vector3:
	var p := s.split(",")
	if p.size() < 3:
		return Vector3.ZERO
	return Vector3(float(p[0]), float(p[1]), float(p[2]))

func _exec(line: String) -> void:
	var sp := line.split(" ", false)
	var cmd := sp[0].to_lower()
	var arg := " ".join(Array(sp).slice(1)) if sp.size() > 1 else ""
	match cmd:
		"pos":
			if camera == null:
				_reply("нет камеры"); return
			camera.global_position = _v3(arg)
			_reply("ok позиция %s" % camera.global_position)
		"look":
			if camera == null:
				_reply("нет камеры"); return
			var t := _v3(arg)
			# ЧЕРЕЗ setup(), А НЕ look_at(). Свободная камера держит СВОИ углы и
			# каждый кадр собирает из них базис заново — look_at она затирала уже
			# на следующем кадре, и снимок приходил не оттуда, куда я смотрел.
			# Ловил это трижды, пока не сверил компас в кадре с командой.
			if camera.global_position.distance_to(t) > 0.01:
				camera.setup(camera.global_position, t)
			_reply("ok смотрю на %s" % t)
		"turn":
			# азимут в градусах: 0=север(-Z), +по часовой на восток; второй — наклон
			var p := arg.split(",")
			var az := deg_to_rad(float(p[0]))
			var el := deg_to_rad(float(p[1])) if p.size() > 1 else 0.0
			var d := Vector3(sin(az) * cos(el), sin(el), -cos(az) * cos(el))
			camera.setup(camera.global_position, camera.global_position + d)
			_reply("ok азимут %s наклон %s" % [p[0], p[1] if p.size() > 1 else "0"])
		"move":
			var p2 := arg.split(",")
			var fwd := float(p2[0])
			var side := float(p2[1]) if p2.size() > 1 else 0.0
			var up := float(p2[2]) if p2.size() > 2 else 0.0
			var b := camera.global_transform.basis
			camera.global_position += -b.z * fwd + b.x * side + Vector3.UP * up
			_reply("ok позиция %s" % camera.global_position)
		"shot":
			var q := arg.split(" ", false)
			_shot_path = q[0] if q.size() > 0 else "/tmp/live.png"
			_shot_wait = 3                        # дать кадру дорисоваться
		"see":
			var g := arg.split("x")
			_reply(_see(int(g[0]) if g.size() > 0 and g[0] != "" else 9,
				int(g[1]) if g.size() > 1 else 5))
		"phys":
			# ЛУЧ ВНИЗ ПО НАСТОЯЩЕЙ ФИЗИКЕ: есть ли под точкой твёрдая земля и
			# на какой она высоте. Так «проваливаюсь сквозь поверхность»
			# перестаёт быть ощущением и становится замером.
			var pp := arg.split(",")
			var qx := float(pp[0])
			var qz := float(pp[1]) if pp.size() > 1 else 0.0
			_reply(_phys(qx, qz))
		"walk":
			# ТЕЛО В ТОЧКУ. Без этого воду нельзя проверить: смотреть на неё
			# камерой — не то же самое, что войти в неё телом.
			if walker == null or terrain == null or stage == null:
				_reply("нет тела"); return
			if arg.begins_with("off"):
				# ВЕРНУТЬ СВОБОДНУЮ КАМЕРУ, оставив следы на земле. Без этого
				# на след нельзя посмотреть: в режиме пешехода камера привязана
				# к телу и стоит там же, где след.
				if stage._walk_active:
					stage._toggle_walk()
				_reply("ok полёт"); return
			var wp := arg.split(",")
			var wx := float(wp[0])
			var wz := float(wp[1]) if wp.size() > 1 else 0.0
			var gy := terrain.height(wx, wz)
			terrain.update_collision(Vector3(wx, 0.0, wz))
			if not stage._walk_active:
				stage._walk_active = true
				camera.set_process_input(false)
			walker.activate(Vector3(wx, gy + 0.6, wz), 0.0)
			_reply("ok тело в (%.1f, %.2f, %.1f)" % [wx, gy + 0.6, wz])
		"go":
			if walker == null:
				_reply("нет тела"); return
			var gp := arg.split(",")
			walker.set_intent(Vector2(float(gp[1]) if gp.size() > 1 else 0.0,
				-float(gp[0])))
			_reply("ok намерение %s" % arg)
		"post":
			# КИНО-ПОСТ: on|off целиком, либо glare/grain со значением
			# («post glare 0», «post grain 2»). Нужно ровно за тем же — чтобы
			# сравнить два кадра, а не спорить о вкусах.
			if stage == null or stage._post_mat == null:
				_reply("нет поста"); return
			var pa := arg.split(" ")
			var pk := pa[0]
			if pk == "off" or pk == "on":
				var v := 1.0 if pk == "on" else 0.0
				stage._post_mat.set_shader_parameter("glare", v)
				stage._post_mat.set_shader_parameter("grain", v)
				stage._post_mat.set_shader_parameter("vignette", 0.28 * v)
				stage._post_mat.set_shader_parameter("ca", 0.0016 * v)
				_reply("ok пост %s" % pk)
			elif pa.size() > 1 and (pk == "glare" or pk == "grain" or pk == "vignette" or pk == "ca"):
				stage._post_mat.set_shader_parameter(pk, float(pa[1]))
				_reply("ok %s = %s" % [pk, pa[1]])
			else:
				_reply("post on|off | post glare|grain|vignette|ca ЧИСЛО")
		"tonemap":
			# СМЕНИТЬ ТОНМАППЕР НА ХОДУ: aces|filmic|agx|reinhard|linear.
			# Нужно, чтобы отличить «цвет пришёл из сцены» от «цвет сделал
			# тонмаппер»: на почти чёрном кадре кривая тона решает всё.
			if stage == null or stage._env == null:
				_reply("нет окружения"); return
			match arg:
				"aces": stage._env.tonemap_mode = Environment.TONE_MAPPER_ACES
				"filmic": stage._env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
				"agx": stage._env.tonemap_mode = Environment.TONE_MAPPER_AGX
				"reinhard": stage._env.tonemap_mode = Environment.TONE_MAPPER_REINHARDT
				"linear": stage._env.tonemap_mode = Environment.TONE_MAPPER_LINEAR
				_: _reply("tonemap aces|filmic|agx|reinhard|linear"); return
			_reply("ok тонмаппер %s" % arg)
		"weather":
			# ОБЛАЧНОСТЬ ФИКСИРУЕТСЯ (0 ясно .. 1 сплошь). Без этого «дыхание»
			# погоды меняет свет между двумя снимками, и сравнивать их нельзя:
			# разница окажется не от правки, а от туч.
			if stage == null or stage._clouds == null:
				_reply("нет облаков"); return
			var cv := clampf(float(arg), 0.0, 1.0)
			stage._clouds.weather_enabled = false
			stage._clouds.coverage = cv
			stage._clouds.current_coverage = cv
			_reply("ok облачность %.2f (дыхание погоды выключено)" % cv)
		"wind":
			if water == null:
				_reply("нет воды"); return
			water.set_wind(float(arg))
			_reply("ok ветер %s м/с" % arg)
		"splash":
			# БРОСИТЬ В ВОДУ. Нужно, чтобы круги можно было проверить не «на
			# глаз», а замером: снять два кадра и померить, на сколько ушёл
			# фронт. Он обязан идти со скоростью sqrt(g·d).
			if water == null:
				_reply("нет воды"); return
			var sp2 := arg.split(",")
			var sx := float(sp2[0])
			var sz := float(sp2[1]) if sp2.size() > 1 else 0.0
			var sa := float(sp2[2]) if sp2.size() > 2 else 0.06
			water.disturb(Vector3(sx, 0.0, sz), sa)
			var dd := water.depth_at(sx, sz)
			_reply("ok всплеск %.2f м в (%.1f, %.1f), толща %.2f м, круг пойдёт %.2f м/с"
				% [sa, sx, sz, dd, WP.wave_speed(dd)])
		"wave":
			# ПРОВЕРКА РЕШЁННОЙ ЖИДКОСТИ ЧИСЛАМИ: гребень обязан идти со
			# скоростью sqrt(g·d) по НАШЕЙ батиметрии, а не по выдуманной.
			if water == null:
				_reply("нет воды"); return
			var wv := arg.split(",")
			var wcx := float(wv[0]) if wv.size() > 0 and wv[0] != "" else 0.0
			var wcz := float(wv[1]) if wv.size() > 1 else 0.0
			var rep: Dictionary = water.sim_selftest(Vector3(wcx, 0.0, wcz))
			if not rep.get("ok", false):
				_reply("проверка не вышла: %s" % rep.get("why", "?")); return
			_reply(("толща %.2f м · гребень: %.2f м за %.2f с -> %.2f м за %.2f с\n"
				+ "скорость по разности %.2f м/с против sqrt(g·d)=%.2f м/с — ошибка %+.1f%%\n"
				+ "без затухания %.2f м/с (%+.1f%%): затухание %.2f гасит ВЫСОТУ, а не скорость\n"
				+ "шаг решателя %.0f мкс на %d ячеек")
				% [rep["depth_m"], rep["r_a"], rep["t_a"], rep["crest_r_m"], rep["t_s"],
				rep["v_measured"], rep["v_theory"], rep["err_pct"],
				rep["v_nodamp"], rep["err_pct_nodamp"], rep["damping"],
				rep["step_usec"], rep["cells"]])
		"moon":
			# ГДЕ ЛУНА И ВИДНА ЛИ ОНА. «Луны не видно» — это три разных случая:
			# её нет над горизонтом, она есть но не нарисована, или её закрыли
			# облака. Различать их на глаз нельзя, поэтому спрашиваем числами.
			_reply(_moon())
		"body":
			_reply(_body())
		"state":
			_reply(_state())
		"probe":
			var p3 := arg.split(",")
			_reply(_probe(float(p3[0]), float(p3[1]) if p3.size() > 1 else 0.0))
		"time":
			# ДАТА БЫЛА НАМЕРТВО 21 ИЮНЯ, и это скрывало половину освещения: на
			# широте Гатчины (59.6°) в июне ночи нет вовсе — Солнце не опускается
			# ниже -7°, белые ночи. Проверить ночное свечение неба на июньском
			# кадре нельзя в принципе. Теперь дату можно задать:
			#   time 21:30            — часы:минуты по UTC (местное = +3)
			#   time 12-15 21:30      — месяц-день и время
			var da := arg.split(" ", false)
			var mon := 6
			var day := 21
			if da.size() > 1:
				var md := da[0].split("-")
				mon = int(md[0])
				day = int(md[1]) if md.size() > 1 else 21
				da.remove_at(0)
			var t2: PackedStringArray = da[0].split(":") if da.size() > 0 else PackedStringArray(["12"])
			clock.set_datetime_utc(2025, mon, day, int(t2[0]),
				int(t2[1]) if t2.size() > 1 else 0, 0)
			clock.time_scale = 0.0
			clock._compute_and_apply()
			_reply("ok %02d-%02d %s UTC (местное +3), солнце %.1f°"
				% [mon, day, da[0] if da.size() > 0 else "12:00", clock.sun_elevation_deg])
		"hud":
			if hud != null:
				hud.visible = arg.begins_with("on")
			_reply("ok надпись %s" % arg)
		"lamp":
			# ПОСТАВИТЬ ИСТОЧНИК СВЕТА ЭПОХИ И ПОСМОТРЕТЬ, ЧТО ОН ДЕЛАЕТ.
			#   lamp                 — каталог: что есть и с какой силой
			#   lamp свеча           — поставить перед камерой, в 1.2 м
			#   lamp лампа10 x,y,z   — поставить в точку мира
			#   lamp off             — убрать все
			_reply(_lamp(arg))
		"dbg":
			RenderingServer.set_debug_generate_wireframes(true)
			var vp := get_viewport()
			match arg:
				"wire": vp.debug_draw = Viewport.DEBUG_DRAW_WIREFRAME
				"overdraw": vp.debug_draw = Viewport.DEBUG_DRAW_OVERDRAW
				"unshaded": vp.debug_draw = Viewport.DEBUG_DRAW_UNSHADED
				"normals": vp.debug_draw = Viewport.DEBUG_DRAW_NORMAL_BUFFER
				"lighting": vp.debug_draw = Viewport.DEBUG_DRAW_LIGHTING
				_: vp.debug_draw = Viewport.DEBUG_DRAW_DISABLED
			_reply("ok режим %s" % arg)
		"quit":
			_reply("ok выхожу")
			get_tree().quit()
		_:
			_reply("не знаю команды «%s»" % cmd)

## ИСТОЧНИКИ СВЕТА ЭПОХИ — поставить, убрать, спросить каталог.
##
## Нужно ровно затем, чтобы «локальный свет меняет кадр» перестало быть моим
## рассуждением и стало замером: поставил лампу, снял кадр, прогнал density.py,
## сравнил числа с теми же числами до неё.
var _lamps: Array[Lantern] = []

func _lamp(arg: String) -> String:
	if arg == "" or arg == "?":
		var out := "[каталог] источники Гатчины 1894 (улица — керосин, дуга — только у дворца)\n"
		for k in Lantern.KINDS:
			var v: Array = Lantern.KINDS[k]
			out += "  %-14s %6.1f кд  %5.0f K  дальность %5.1f м\n" % [
				k, float(v[0]), float(v[1]), sqrt(float(v[0]) / Lantern.CUTOFF_LUX)]
		return out.strip_edges()
	if arg.begins_with("off"):
		var n := _lamps.size()
		for l in _lamps:
			if is_instance_valid(l):
				l.queue_free()
		_lamps.clear()
		return "ok убрано источников: %d" % n

	var parts := arg.split(" ", false)
	var what := parts[0]
	if not Lantern.KINDS.has(what):
		return "нет такого источника: «%s» (спроси «lamp» без аргумента)" % what
	var lamp := Lantern.make(what)
	get_tree().current_scene.add_child(lamp)
	if parts.size() > 1:
		lamp.global_position = _v3(parts[1])
	elif camera != null:
		# перед камерой и чуть ниже линии взгляда — как лампу держат в руке
		var b := camera.global_transform.basis
		lamp.global_position = camera.global_position - b.z * 1.2 - b.y * 0.35
	_lamps.append(lamp)
	return ("ok %s: %.1f кд, %.0f K, энергия %.5f, обратный квадрат, дальность %.1f м\n"
		+ "   на 1 м %.1f лк, на 3 м %.1f лк, на 10 м %.2f лк\n"
		+ "   для сравнения: ночное свечение неба заложено как %.1f лк\n"
		+ "   поставлено в %s, всего источников %d") % [
			lamp.kind, lamp.cd, float(Lantern.KINDS[what][1]), lamp.light_energy,
			lamp.omni_range, lamp.lux_at(1.0), lamp.lux_at(3.0), lamp.lux_at(10.0),
			WeatherSky.NIGHT_GLOW / WeatherSky.AMB_PER_KLX * 1000.0,
			lamp.global_position, _lamps.size()]


## ЧТО В КАДРЕ — разбор картинки ЧИСЛАМИ, а не глазами.
##
## Это главное, чего не давали ни снимки, ни отдельные замеры. Снимок
## показывает вид, но не говорит, ЧТО и НА КАКОМ расстоянии; замер точки
## говорит точно, но только про одну точку. Здесь через кадр пускается сетка
## лучей, каждый шагает по полю высот и по урезу воды — и кадр возвращается
## подписанным: где земля, где вода, где небо и как далеко.
##
## Лучи считаются по тем же данным, что и рисунок (высота рельефа, растр
## уреза), поэтому подпись — не догадка по цвету пикселя, а разбор сцены.
func _see(cols: int, rows: int) -> String:
	if camera == null or terrain == null:
		return "нечего разбирать"
	cols = clampi(cols, 3, 15)
	rows = clampi(rows, 3, 11)
	var b := camera.global_transform.basis
	var origin := camera.global_position
	var fov_v := deg_to_rad(camera.fov)
	var aspect := float(get_viewport().get_visible_rect().size.x) \
		/ maxf(get_viewport().get_visible_rect().size.y, 1.0)
	var out := "что в кадре (%dx%d лучей, %.0f° по вертикали):" % [cols, rows, camera.fov]
	var seen := {"вода": 0, "земля": 0, "небо": 0}
	for r in range(rows):
		var fy := 1.0 - 2.0 * (float(r) + 0.5) / float(rows)     # +верх .. -низ
		var line := "\n  "
		for c in range(cols):
			var fx := 2.0 * (float(c) + 0.5) / float(cols) - 1.0
			var d := (b.x * (fx * tan(fov_v * 0.5) * aspect)
				+ b.y * (fy * tan(fov_v * 0.5)) - b.z).normalized()
			var hit := _cast(origin, d)
			seen[hit[0]] = int(seen.get(hit[0], 0)) + 1
			if hit[0] == "небо":
				line += "%9s" % "небо"
			else:
				line += "%6s%3d" % [hit[0], int(hit[1] / 10.0)]   # десятки метров
			line += " "
		out += line
	out += "\nвсего лучей: вода %d, земля %d, небо %d (расстояние — в десятках метров)" \
		% [seen["вода"], seen["земля"], seen["небо"]]
	return out

## шаг луча по полю высот и урезу воды: что встретим первым
func _cast(o: Vector3, d: Vector3) -> Array:
	var t := 1.0
	var far := 5000.0
	while t < far:
		var p := o + d * t
		var gh := terrain.height(p.x, p.z)
		if water != null:
			var lv := water.level_at(p.x, p.z)
			if not is_nan(lv) and lv > gh and p.y <= lv:
				return ["вода", t]
		if p.y <= gh:
			return ["земля", t]
		# шаг растёт с дальностью: вблизи точно, вдали дёшево
		t += maxf(2.0, t * 0.02)
	return ["небо", far]

func _phys(x: float, z: float) -> String:
	var vis := terrain.height(x, z) if terrain != null else 0.0
	var space := get_viewport().world_3d.direct_space_state
	var q := PhysicsRayQueryParameters3D.create(
		Vector3(x, vis + 200.0, z), Vector3(x, vis - 200.0, z))
	var hit := space.intersect_ray(q)
	var cen := "нет"
	if terrain != null:
		cen = "центр заплатки X %.0f Z %.0f, край ±%.0f м, до края %.0f м" % [
			terrain._col_center.x, terrain._col_center.z, terrain.COL_HALF,
			terrain.COL_HALF - maxf(absf(x - terrain._col_center.x),
				absf(z - terrain._col_center.z))]
	if hit.is_empty():
		return "точка X %.0f Z %.0f: ТВЁРДОЙ ЗЕМЛИ НЕТ (луч 400 м пуст), видно %.2f м | %s" \
			% [x, z, vis, cen]
	var hy: float = hit["position"].y
	var who := "?"
	var col: Object = hit.get("collider")
	if col != null and col is Node:
		who = (col as Node).name + " (" + col.get_class() + ")"
	var cc := "нет"
	if terrain != null:
		cc = "центр заплатки X %.0f Z %.0f" % [terrain._col_center.x, terrain._col_center.z]
	return "точка X %.0f Z %.0f: упор в %s на %.2f м | видно %.2f м | расхождение %+.2f м | %s" \
		% [x, z, who, hy, vis, hy - vis, cc]

func _state() -> String:
	var p := camera.global_position if camera != null else Vector3.ZERO
	var b := camera.global_transform.basis if camera != null else Basis.IDENTITY
	var f := -b.z
	var az := rad_to_deg(atan2(f.x, -f.z))
	var el := rad_to_deg(asin(clampf(f.y, -1.0, 1.0)))
	var s := "камера X %.1f Y %.1f Z %.1f | азимут %.0f° наклон %.0f° | %.1f кадр/с" \
		% [p.x, p.y, p.z, fposmod(az, 360.0), el, _fps]
	s += "\n" + _probe(p.x, p.z)
	if clock != null:
		s += "\nвремя %s, солнце %.1f°/аз %.1f°" \
			% [clock.local_time_string(), clock.sun_elevation_deg, clock.sun_azimuth_deg]
	# СВЕТ ЧИСЛАМИ. Без этого «темно» остаётся впечатлением: непонятно, мало
	# света у солнца, мало у неба или экспозиция не подхватила сумерки.
	if stage != null and stage._sun != null and stage._env != null:
		s += "\nсвет: солнце %.2f (%d клк, %dК), неб.свет %.2f, экспозиция %.3f, пасмурность %.2f" \
			% [stage._sun.light_energy, int(clock.sun_direct_klx),
			int(clock.sun_color_temp_k), stage._env.ambient_light_energy,
			stage._env.tonemap_exposure, stage._weather_oc]
	return s

func _moon() -> String:
	if stage == null or stage._night_sky == null or clock == null:
		return "ночного неба нет"
	var ns = stage._night_sky
	var m: Dictionary = clock.moon_state(clock.utc_unix)
	var d: Vector3 = ns.moon_dir_world
	var el := rad_to_deg(asin(clampf(d.y, -1.0, 1.0)))
	var az := fposmod(rad_to_deg(atan2(d.x, -d.z)), 360.0)
	var drawn: bool = ns._moon != null and ns._moon.visible
	var ml: Color = ns.moon_light
	var s := "Луна: высота %+.1f° азимут %.0f° · фаза %.0f%% (элонгация %.0f°)\n" \
		% [el, az, float(m["illum"]) * 100.0, float(m["elong_deg"])]
	s += "расстояние %.0f км, видимый размер %.3f° · диск нарисован: %s\n" \
		% [float(m["dist_km"]), float(m["ang_diam_deg"]), "да" if drawn else "НЕТ"]
	s += "свет Луны для облаков: %.4f, %.4f, %.4f (солнце %.1f°)" \
		% [ml.r, ml.g, ml.b, clock.sun_elevation_deg]
	if el <= 0.0:
		s += "\nЛуны НЕ ВИДНО потому, что она под горизонтом — это не дефект"
	return s

## ЧТО ЧУВСТВУЕТ ТЕЛО. Раньше такого вопроса нельзя было задать вовсе: вода
## была плёнкой, и «войти в неё» ничего не значило.
func _body() -> String:
	if walker == null:
		return "тела нет"
	var p := walker.global_position
	var sub: float = walker.submersion
	var v := Vector2(walker.velocity.x, walker.velocity.z).length()
	var s := "тело X %.1f Y %.2f Z %.1f | скорость %.2f м/с" % [p.x, p.y, p.z, v]
	if sub <= 0.02:
		return s + " | посуху"
	s += "\n  вверх %.3f м/с, опора: %s" % [walker.velocity.y,
		"есть" if walker.is_on_floor() else "нет"]
	s += "\n  погружение %.2f м (%s)" % [sub, "ПЛЫВЁТ" if walker.swimming else "брод"]
	s += "\n  на ногах %.0f%% веса, архимедова сила %.0f Н из %.0f Н веса" \
		% [WP.foot_load(sub) * 100.0, WP.buoyancy(sub),
		WP.BODY_M * WP.G]
	s += "\n  предел брода тут %.2f м/с, площадь под водой %.3f м²" \
		% [WP.wade_speed(sub), WP.frontal_area(sub)]
	if water != null:
		var d := water.depth_at(p.x, p.z)
		s += "\n  толща воды %.2f м, круги идут %.2f м/с" \
			% [d, WP.wave_speed(d)]
	return s

func _probe(x: float, z: float) -> String:
	var s := "точка X %.0f Z %.0f:" % [x, z]
	if terrain != null:
		s += " земля %.2f м" % terrain.height(x, z)
		var g := WorldGeo.world_to_geo(x, z)
		s += " | %.6f, %.6f" % [g.x, g.y]
	if water != null:
		var lv := water.level_at(x, z)
		if is_nan(lv):
			s += " | воды нет"
		else:
			var th := lv - (terrain.height(x, z) if terrain != null else 0.0)
			s += " | ВОДА: урез %.2f, толща %.2f м" % [lv, th]
	return s
