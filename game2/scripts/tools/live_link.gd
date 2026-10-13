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
##   person on|off        герой виден / выключен (выключен пешком = от 1-го лица)
##   body                 что тело чувствует: погружение, брод, плавание
##   cam                  где камера пешехода и на что она смотрит
##   film ПАПКА [КАДРОВ]  СНЯТЬ ВИДЕО подряд (собрать: tools/film.py)
##   slow К               замедлить мир для съёмки (0.5 -> 30 кадров на с)
##   fast [off]           съёмочный режим: снять дорогие слои с кадра
##   clip ИМЯ | clip off  проиграть ОДИН клип, минуя смешивание
##   gait [КАДРОВ]        ЗАМЕР ПОХОДКИ: скользит ли опорная стопа
##   jitter [КАДРОВ]      ЗАМЕР ДРОЖАНИЯ: ровно ли идут отрисованные кадры
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

# --- СЪЁМКА ВИДЕО ---
# ПО КАДРАМ ПОХОДКУ СУДИТЬ НЕЛЬЗЯ. Это сказал заказчик, и это верно по
# существу: кадр показывает ПОЗУ, а спрос — к движению МЕЖДУ позами. Сколько
# ни снимай одиночных кадров, из них не собрать ответа на вопрос «как он
# идёт». Я этого полгода не замечал и каждый раз судил фигуру по стоп-кадру.
#
# ВРЕМЯ ПИШЕТСЯ ВМЕСТЕ С КАДРАМИ. На программном растеризаторе кадр рисуется
# полторы секунды, и снимать «с частотой 30 кадров в секунду» тут нечем. Но
# движок сам сообщает, сколько ИГРОВОГО времени он прожил за кадр, и ровно на
# это время продвинулась анимация. Пишем это число рядом с каждым кадром, и
# сборка (tools/film.py) даёт каждому кадру его длительность — видео идёт в
# НАСТОЯЩЕМ темпе, хотя снималось в сто раз медленнее.
var _film_left := 0
var _film_dir := ""
var _film_n := 0
var _film_times := ""

# --- ЗАМЕР ПОХОДКИ ---
# Что в походке глаз читает как «манекен» и что при этом можно посчитать без
# глаза: СКОЛЬЖЕНИЕ ОПОРНОЙ СТОПЫ. У живого человека стопа, вставшая на землю,
# стоит на месте — тело едет мимо неё. У плохой походки стопа едет вместе с
# телом, и это ровно то, что читается «конькобежцем».
var _gait_left := 0
var _gait: Array = []
var _gait_л := -1
var _gait_п := -1

# --- ЗАМЕР ДРОЖАНИЯ ---
# «Камера дёргается» — ощущение, спорить о нём бесполезно. Числами проверяется
# однозначно: пишем каждый НАРИСОВАННЫЙ кадр — где камера и где тело внутри
# кадра. Дрожание есть тогда, когда часть кадров картинка стоит, а на
# следующем прыгает вдвое.
var _jit_left := 0
var _jit: Array = []
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

	if _film_left > 0:
		_film_frame(_dt)
	if _gait_left > 0:
		_gait_sample(_dt)
	if _jit_left > 0:
		_jit_sample(_dt)

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

## Один кадр фильма: сохранить картинку и записать, сколько ИГРОВОГО времени
## он занял.
func _film_frame(dt: float) -> void:
	var img := get_viewport().get_texture().get_image()
	img.save_png("%s/к%04d.png" % [_film_dir, _film_n])
	_film_times += "%.5f\n" % dt
	_film_n += 1
	_film_left -= 1
	if _film_left == 0:
		var f := FileAccess.open(_film_dir + "/время.txt", FileAccess.WRITE)
		if f != null:
			f.store_string(_film_times)
			f.close()
		get_viewport().use_debanding = true
		_reply("ok снято %d кадров %dx%d -> %s (время кадров в время.txt)"
			% [_film_n, img.get_width(), img.get_height(), _film_dir])


## СЪЁМОЧНЫЙ РЕЖИМ: снять с кадра всё, что стоит пикселей и не относится к
## фигуре. Рельеф, солнце и тени остаются — без них не видно, как стопа встаёт
## на землю. ЭТО РЕЖИМ СТЕНДА, А НЕ ИГРЫ: на устройстве Metal, там эти слои
## нужны по-прежнему.
func _fast(on: bool) -> String:
	if stage == null or stage._env == null:
		return "нет сцены"
	var e: Environment = stage._env
	e.sdfgi_enabled = false if on else bool(stage.GFX.get("sdfgi", false))
	e.ssao_enabled = false if on else bool(stage.GFX.get("ssao", false))
	e.ssil_enabled = false if on else bool(stage.GFX.get("ssil", false))
	e.glow_enabled = false if on else bool(stage.GFX.get("glow", false))
	var снято := PackedStringArray()
	for имя in ["_clouds", "_backdrop", "_night_sky", "_city", "_water_vol"]:
		var n = stage.get(имя)
		if n != null and n is Node3D:
			(n as Node3D).visible = not on
			снято.append(имя.substr(1))
	if stage._post_mat != null:
		var v := 0.0 if on else 1.0
		stage._post_mat.set_shader_parameter("glare", v)
		stage._post_mat.set_shader_parameter("grain", v)
		stage._post_mat.set_shader_parameter("vignette", 0.28 * v)
		stage._post_mat.set_shader_parameter("ca", 0.0016 * v)
	if stage._sun != null:
		stage._sun.directional_shadow_max_distance = 40.0 if on else \
			float(stage.GFX.get("shadow_far", 120.0))
	return "ok съёмочный режим %s (снято: GI, SSAO, SSIL, свечение, %s)" % [
		"ВКЛ" if on else "выкл", ", ".join(снято)]


## ПРОИГРАТЬ ОДИН КЛИП, минуя пространство смешивания. Без этого нельзя
## понять, чей дефект видно в кадре: самого клипа, переноса движения или
## смешивания. Пустое имя — вернуть смешивание.
func _clip(имя: String) -> String:
	if walker == null or walker.person == null or walker.person.anim == null:
		return "нет проигрывателя"
	var ап: AnimationPlayer = walker.person.anim
	var дер: AnimationTree = walker.get("_tree")
	if имя == "" or имя == "off":
		if дер != null:
			дер.active = true
		return "ok смешивание вернулось"
	var есть := ап.get_animation_list()
	var найдено := ""
	for a in есть:
		if a == имя or a.to_lower().contains(имя.to_lower()):
			найдено = a
			break
	if найдено == "":
		return "нет клипа «%s»; есть: %s" % [имя, ", ".join(есть)]
	# ДЕРЕВО ГЛУШИТСЯ: иначе оно и проигрыватель пишут в одни кости, и в кадре
	# окажется смесь, а не проверяемый клип.
	if дер != null:
		дер.active = false
	ап.play(найдено)
	ап.speed_scale = 1.0
	return "ok играю «%s» (%.2f с)" % [найдено, ап.get_animation(найдено).length]


func _кость(sk: Skeleton3D, имена: Array) -> int:
	for nm in имена:
		var id := sk.find_bone(nm)
		if id >= 0:
			return id
	return -1


func _gait_start(n: int) -> String:
	if walker == null or walker.person == null or walker.person.skel == null:
		return "нет скелета"
	var sk: Skeleton3D = walker.person.skel
	_gait_л = _кость(sk, ["LeftToeBase", "LeftFoot", "toe.L", "foot.L"])
	_gait_п = _кость(sk, ["RightToeBase", "RightFoot", "toe.R", "foot.R"])
	if _gait_л < 0 or _gait_п < 0:
		return "стопы не найдены среди %d костей" % sk.get_bone_count()
	_gait.clear()
	_gait_left = maxi(n, 12)
	return ""


func _gait_sample(dt: float) -> void:
	var sk: Skeleton3D = walker.person.skel
	var T := sk.global_transform
	var л: Vector3 = T * sk.get_bone_global_pose(_gait_л).origin
	var п: Vector3 = T * sk.get_bone_global_pose(_gait_п).origin
	# ВЫСОТА СТОПЫ МЕРИТСЯ ОТ ТЕЛА, А НЕ ОТ МИРА. В мире она включает всё, что
	# делает само тело: падение с высоты постановки, спуск по склону. Первый же
	# замер дал «подъём 688 мм» — это было падение тела, а не мах ногой.
	_gait.append([dt, л, п, walker.global_position,
		л.y - walker.global_position.y, п.y - walker.global_position.y])
	_gait_left -= 1
	if _gait_left == 0:
		_reply(_gait_report())


func _gait_report() -> String:
	if _gait.size() < 12:
		return "мало кадров"
	var путь_тела := 0.0
	var проезд := 0.0          # сколько проехала ОПОРНАЯ стопа
	var время := 0.0
	var смен := 0
	var прошлая := 0
	var вл := [INF, -INF]
	var вп := [INF, -INF]
	for i in range(1, _gait.size()):
		var a: Array = _gait[i - 1]
		var b: Array = _gait[i]
		время += float(b[0])
		var A: Vector3 = a[3]
		var B: Vector3 = b[3]
		путь_тела += Vector2(B.x - A.x, B.z - A.z).length()
		# ОПОРНАЯ — та стопа, что ниже. Прямой признак, не требующий луча.
		var опора := 1 if float(b[4]) <= float(b[5]) else 2
		if i > 1 and опора != прошлая:
			смен += 1
		прошлая = опора
		var с0: Vector3 = a[1] if опора == 1 else a[2]
		var с1: Vector3 = b[1] if опора == 1 else b[2]
		проезд += Vector2(с1.x - с0.x, с1.z - с0.z).length()
		вл[0] = minf(вл[0], float(b[4])); вл[1] = maxf(вл[1], float(b[4]))
		вп[0] = minf(вп[0], float(b[5])); вп[1] = maxf(вп[1], float(b[5]))
	var n := _gait.size()
	_gait.clear()
	var стопы := "\n  подъём стоп над низшей точкой: левая %.0f мм, правая %.0f мм" \
		% [(вл[1] - вл[0]) * 1000.0, (вп[1] - вп[0]) * 1000.0]
	if путь_тела < 0.02:
		return ("походка за %d кадров (%.2f с): ТЕЛО СТОЯЛО (путь %.3f м), "
			+ "скольжение не мерится%s") % [n, время, путь_тела, стопы]
	return ("походка за %d кадров (%.2f с, %.2f м, %.2f м/с)"
		+ "\n  СКОЛЬЖЕНИЕ ОПОРНОЙ СТОПЫ: %.0f%% пути тела (%.2f м из %.2f м)"
		+ "\n    0%% — стопа стоит на земле, 100%% — едет вместе с телом"
		+ "%s\n  смен опорной ноги: %d (шагов в минуту %.0f; у человека 100-130)") % [
		n, время, путь_тела, путь_тела / maxf(время, 1e-6),
		100.0 * проезд / путь_тела, проезд, путь_тела, стопы,
		смен, смен * 60.0 / maxf(время, 1e-6)]


func _jit_sample(dt: float) -> void:
	if walker == null or walker.cam == null:
		_jit_left = 0
		_reply("нет тела")
		return
	var c := walker.cam.global_transform
	var b := walker.global_position
	# Точка груди героя В СИСТЕМЕ КАМЕРЫ: именно она стоит или скачет в кадре.
	# Мировые координаты для этого не годятся — при ровном движении они
	# меняются, а картинка при этом неподвижна.
	_jit.append([dt, c.origin, b, c.affine_inverse() * (b + Vector3(0, 1.4, 0))])
	_jit_left -= 1
	if _jit_left == 0:
		_reply(_jit_report())


func _jit_stat(v: PackedFloat64Array) -> Array:
	if v.is_empty():
		return [0.0, 0.0, 0.0]
	var s := 0.0
	var mn: float = v[0]
	var mx: float = v[0]
	for x in v:
		s += x
		mn = minf(mn, x)
		mx = maxf(mx, x)
	return [s / v.size(), mn, mx]


func _jit_report() -> String:
	if _jit.size() < 8:
		return "мало кадров"
	var шаг_кам := PackedFloat64Array()
	var скольз := PackedFloat64Array()
	var стоячих := 0
	var время := 0.0
	for i in range(1, _jit.size()):
		var a: Array = _jit[i - 1]
		var b: Array = _jit[i]
		время += float(b[0])
		var dк: float = (b[1] as Vector3).distance_to(a[1] as Vector3)
		шаг_кам.append(dк)
		if dк < 1e-5:
			стоячих += 1
		скольз.append((b[3] as Vector3).distance_to(a[3] as Vector3) * 1000.0)
	var к := _jit_stat(шаг_кам)
	var г := _jit_stat(скольз)
	# РЫВОК — вторая разность: ровное движение даёт около нуля, ступенька
	# физического такта даёт всплеск размером с сам шаг.
	var рывок := PackedFloat64Array()
	for i in range(1, шаг_кам.size()):
		рывок.append(absf(шаг_кам[i] - шаг_кам[i - 1]) * 1000.0)
	var р := _jit_stat(рывок)
	var поводок := PackedFloat64Array()
	for s in _jit:
		поводок.append((s[1] as Vector3).distance_to(s[2] as Vector3))
	var п := _jit_stat(поводок)
	var n := _jit.size()
	_jit.clear()
	return ("дрожание за %d кадров (%.2f с игрового времени, физика %d Гц)"
		+ "\n  камера, шаг за кадр: сред %.1f мм, макс %.1f мм; "
		+ "рывок сред %.1f мм, макс %.1f мм"
		+ "\n  КАДРОВ БЕЗ ДВИЖЕНИЯ КАМЕРЫ: %d из %d (%.0f%%)"
		+ "\n  герой ВНУТРИ КАДРА, смещение за кадр: сред %.2f мм, макс %.2f мм"
		+ "\n  поводок: сред %.2f м, размах %.2f м (мин %.2f, макс %.2f)") % [
		n, время, Engine.physics_ticks_per_second,
		к[0] * 1000.0, к[2] * 1000.0, р[0], р[2],
		стоячих, n - 1, 100.0 * стоячих / maxf(n - 1, 1),
		г[0], г[2], п[0], п[2] - п[1], п[1], п[2]]


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
			# ТРЕТИЙ ПАРАМЕТР — КУДА ЛИЦОМ, в градусах азимута (0 = север).
			# Без него тело всегда вставало лицом на север, и на кадре лицо
			# оказывалось в тени: Солнце в Гатчине днём всегда с юга. Я на этом
			# потерял несколько заходов, разглядывая «голову без лица», которая
			# на деле была головой в тени.
			# Связь: fwd = (-sin yaw, 0, -cos yaw), а азимут A даёт направление
			# (sin A, 0, -cos A). Отсюда yaw = -A.
			var wp := arg.split(",")
			var wx := float(wp[0])
			var wz := float(wp[1]) if wp.size() > 1 else 0.0
			var waz := float(wp[2]) if wp.size() > 2 else 0.0
			var gy := terrain.height(wx, wz)
			terrain.update_collision(Vector3(wx, 0.0, wz))
			if not stage._walk_active:
				stage._walk_active = true
				camera.set_process_input(false)
			walker.activate(Vector3(wx, gy + 0.6, wz), -deg_to_rad(waz))
			_reply("ok тело в (%.1f, %.2f, %.1f), лицом на азимут %.0f°"
				% [wx, gy + 0.6, wz, waz])
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
		"cam":
			# ГДЕ КАМЕРА ПЕШЕХОДА. Команда state показывает свободную камеру, и
			# по ней о виде через плечо судить нельзя — я на этом потерял заход,
			# разглядывая пустую землю и гадая, почему герой не в кадре.
			if walker == null or walker.cam == null:
				_reply("нет камеры тела")
			else:
				var c: Camera3D = walker.cam
				var b: Vector3 = walker.global_position
				var d: Vector3 = c.global_position - b
				# СКЛЕЙКА СТРОК ТОЛЬКО ЧЕРЕЗ «+». Здесь стояли два литерала
				# подряд, как пишут в Питоне, — GDScript этого не понимает, и
				# падал ВЕСЬ скрипт стенда, а не одна команда. Поймано сборкой
				# с --check-only; на глаз в правке это было незаметно.
				_reply(("камера тела X %.2f Y %.2f Z %.2f | от тела %.2f м "
					+ "(вверх %.2f) | наклон %.0f° | текущая: %s | третье лицо: %s")
					% [c.global_position.x, c.global_position.y,
						c.global_position.z, d.length(), d.y,
						rad_to_deg(c.global_rotation.x), str(c.current),
						str(walker.third_person)])
		"slow":
			# ЗАМЕДЛИТЬ САМ МИР — ключ ко всей съёмке видео.
			#
			# ИЗМЕРЕНО на этом стенде: кадр рисуется 1.5 с, а игра сообщает,
			# что прожила за него 0.067 с (это потолок: 8 шагов физики по
			# 1/120 с). Значит на СЕКУНДУ ДВИЖЕНИЯ приходится 15 кадров, и
			# снять плавнее нельзя ничем — сколько ни жди, кадры кончатся
			# раньше движения.
			#
			# Но частота съёмки — это отношение: кадров на секунду ИГРОВОГО
			# времени. Замедлив игру вдвое, получаем вдвое больше кадров на ту
			# же секунду движения. Кадр при этом честный: анимация, физика и
			# камера идут своим порядком, просто медленнее. А сборка даёт
			# каждому кадру ЕГО длительность — и видео идёт в настоящем темпе.
			# Плата — только время съёмки.
			Engine.time_scale = clampf(float(arg) if arg != "" else 1.0, 0.02, 4.0)
			_reply("ok мир идёт %.2f× (кадров на секунду движения станет ~%.0f)"
				% [Engine.time_scale, 15.0 / maxf(Engine.time_scale, 0.02)])
		"fast":
			_reply(_fast(not arg.begins_with("off")))
		"film":
			# СНЯТЬ ВИДЕО: film ПАПКА [КАДРОВ]. Ответ придёт, когда снимутся все.
			var fa := arg.split(" ", false)
			if fa.size() < 1:
				_reply("film ПАПКА [КАДРОВ]")
			else:
				_film_dir = fa[0]
				DirAccess.make_dir_recursive_absolute(_film_dir)
				_film_left = maxi(int(fa[1]) if fa.size() > 1 else 60, 2)
				_film_n = 0
				_film_times = ""
				# дизеринг — шахматный шум; в видео он читается кипением
				get_viewport().use_debanding = false
		"clip":
			_reply(_clip(arg))
		"gait":
			# Пустой ответ — замер пошёл; настоящий придёт, когда наберутся кадры.
			var ge := _gait_start(int(arg) if arg != "" else 90)
			if ge != "":
				_reply(ge)
		"jitter":
			if walker == null:
				_reply("нет тела")
			else:
				_jit.clear()
				_jit_left = maxi(int(arg) if arg != "" else 120, 8)
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
		"person":
			# ОТВЕТ ИДЁТ ЧЕРЕЗ _reply, А НЕ return: разборщик команд объявлен
			# void, и «return строка» его не компилирует — падает вся сцена,
			# а не одна команда.
			if stage == null or not stage.has_method("set_person_shown"):
				_reply("нет сцены")
			else:
				var on := arg.begins_with("on") or arg.begins_with("вкл")
				stage.call("set_person_shown", on)
				_reply("ok герой %s — %s" % ["виден" if on else "выключен",
					stage.call("person_report")])
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
