class_name Person
extends Node3D
## ЧЕЛОВЕК. Скелет, скиннированная сетка, силуэт эпохи.
##
## Это то, чего в игре не было вовсе. В мире есть настоящий рельеф Гатчины,
## физическое небо, астрономия Солнца и Луны, вода с оптикой, горизонты почвы —
## и ни одного человека. Пешеход (walker.gd) существовал как капсула коллизии с
## камерой в глазах: тело было, видно его не было.
##
## ПОЧЕМУ ПРОЦЕДУРНО, А НЕ МОДЕЛЬЮ ИЗ ФАЙЛА. Купленную или скачанную модель мы
## не можем ни поправить в нужную сторону, ни объяснить, ни привязать к эпохе.
## Здесь фигура задана числами: пропорции, длины костей, ширины — всё это
## правится и видно в тексте. Цена — грубость формы; она честная и её видно.
##
## ПРОПОРЦИИ — 7.5 ГОЛОВ, канон рисования фигуры взрослого мужчины (8 голов —
## героический канон, живой человек ближе к 7.5). При росте 1.75 м голова
## выходит 0.233 м. Опорные точки в головах от земли, снизу вверх:
##   лодыжка 0.35 · колено 2.0 · пах 3.75 (ровно половина роста) · пупок 4.7 ·
##   соски 5.5 · плечи 6.1 · подбородок 6.5 · темя 7.5
## Ширина плеч — две головы. Это НЕ измерение, а канон: он не описывает
## конкретного человека, он не даёт фигуре выглядеть уродом.
##
## СИЛУЭТ ЭПОХИ. Разбор чужих кадров дал простую вещь: на расстоянии работает
## только силуэт, текстура начинает читаться с полутора-трёх метров. Поэтому
## одежда здесь не украшение, а первое, что делает фигуру узнаваемой: пальто
## ниже колена, сапоги, картуз. Городской обыватель Гатчины 1894 года.

const H := 1.75                       # рост, м
const HEAD := H / 7.5                 # высота головы, м — единица всех пропорций

# опорные высоты (в головах от земли -> в метрах)
const Y_ANKLE := 0.35 * HEAD
const Y_KNEE := 2.00 * HEAD
const Y_CROTCH := 3.75 * HEAD
const Y_WAIST := 4.70 * HEAD
const Y_CHEST := 5.50 * HEAD
const Y_SHOULDER := 6.10 * HEAD
const Y_CHIN := 6.50 * HEAD
const Y_TOP := 7.50 * HEAD

const SHOULDER_W := 2.00 * HEAD       # ширина плеч — две головы
const HIP_W := 1.20 * HEAD

# Кости: имя -> [родитель, конец кости в позе покоя (мир)]. Начало кости — конец
# родителя. Скелет минимальный: всё, что нужно для походки и руки с фонарём, и
# ничего сверх того — лишние кости здесь означали бы лишние догадки о форме.
const BONES := [
	["hips",       "",           Vector3(0.0, Y_CROTCH, 0.0)],
	["spine",      "hips",       Vector3(0.0, Y_WAIST, 0.0)],
	["chest",      "spine",      Vector3(0.0, Y_SHOULDER, 0.0)],
	["neck",       "chest",      Vector3(0.0, Y_CHIN, 0.0)],
	["head",       "neck",       Vector3(0.0, Y_TOP, 0.0)],

	["clav.L",     "chest",      Vector3(SHOULDER_W * 0.5, Y_SHOULDER, 0.0)],
	["arm.L",      "clav.L",     Vector3(SHOULDER_W * 0.5 + 0.02, Y_CHEST - 0.16, 0.0)],
	["farm.L",     "arm.L",      Vector3(SHOULDER_W * 0.5 + 0.05, Y_WAIST - 0.09, 0.0)],
	["hand.L",     "farm.L",     Vector3(SHOULDER_W * 0.5 + 0.06, Y_CROTCH + 0.02, 0.0)],

	["clav.R",     "chest",      Vector3(-SHOULDER_W * 0.5, Y_SHOULDER, 0.0)],
	["arm.R",      "clav.R",     Vector3(-SHOULDER_W * 0.5 - 0.02, Y_CHEST - 0.16, 0.0)],
	["farm.R",     "arm.R",      Vector3(-SHOULDER_W * 0.5 - 0.05, Y_WAIST - 0.09, 0.0)],
	["hand.R",     "farm.R",     Vector3(-SHOULDER_W * 0.5 - 0.06, Y_CROTCH + 0.02, 0.0)],

	["thigh.L",    "hips",       Vector3(HIP_W * 0.5, Y_KNEE, 0.0)],
	["shin.L",     "thigh.L",    Vector3(HIP_W * 0.5, Y_ANKLE, 0.0)],
	["foot.L",     "shin.L",     Vector3(HIP_W * 0.5, 0.02, 0.15)],

	["thigh.R",    "hips",       Vector3(-HIP_W * 0.5, Y_KNEE, 0.0)],
	["shin.R",     "thigh.R",    Vector3(-HIP_W * 0.5, Y_ANKLE, 0.0)],
	["foot.R",     "shin.R",     Vector3(-HIP_W * 0.5, 0.02, 0.15)],
]

# Начало кости hips (таз опирается на землю через ноги, но сама кость начинается
# в паху и растёт вверх — поэтому её «голова» лежит там же, где и конец).
const HIPS_HEAD := Vector3(0.0, Y_CROTCH, 0.0)

var skel: Skeleton3D
var mesh_inst: MeshInstance3D
var _bone_id: Dictionary = {}          # имя -> индекс
var _rest_head: Dictionary = {}        # имя -> начало кости в мире (поза покоя)
var _rest_tail: Dictionary = {}        # имя -> конец кости в мире (поза покоя)

# --- материалы: четыре, по числу разных поверхностей в силуэте ---
var _mat_coat: StandardMaterial3D
var _mat_skin: StandardMaterial3D
var _mat_boot: StandardMaterial3D
var _mat_cap: StandardMaterial3D


# --- тело из файла --------------------------------------------------------
#
# ПОЧЕМУ ТЕПЕРЬ ВСЁ-ТАКИ МОДЕЛЬ, а не числа. В шапке этого файла стоял довод:
# «купленную или скачанную модель мы не можем ни поправить, ни объяснить, ни
# привязать к эпохе». Довод был верный ровно до тех пор, пока модель была
# чужая. Наша — не чужая: она собрана в studio/hero.py из открытых частей и
# ПОДОГНАНА ПО ОБМЕРУ 4082 мужчин (ANSUR II), а не по канону рисования. Каждое
# число объяснимо и лежит в тексте, как и здесь.
#
# ЧТО ЭТИМ ПРИОБРЕТАЕТСЯ, кроме вида: походка из настоящей записи движения
# (CMU), лицо с 52 единицами ARKit и визимами речи, кости глаз. Числами такого
# не написать.
#
# ПРОЦЕДУРНОЕ ТЕЛО ОСТАЁТСЯ ЗАПАСНЫМ ПУТЁМ и не выбрасывается: если файла нет
# (свежая проверка, чужая машина, незапечённый экспорт), игра поднимется с
# фигурой по канону, а не упадёт.
const HERO := "res://assets/models/hero.glb"

# ИЗМЕРЕНО на записи 07_01: путь за цикл 1.415 м, длительность 1.125 с, то есть
# СОБСТВЕННАЯ СКОРОСТЬ КЛИПА 1.29 м/с. Ею и делится скорость тела: клип,
# пущенный со скоростью v/1.29, проходит ровно тот путь, что и тело, и стопа не
# скользит ни на какой скорости.
const CLIP_STRIDE := 1.423
const CLIP_SPEED := 1.294

var from_file := false
var anim: AnimationPlayer
var clip := ""            # цикл ходьбы
var clip_idle := ""       # стойка


func build() -> void:
	if _build_from_file():
		return
	_make_materials()
	_make_skeleton()
	_make_mesh()


func _build_from_file() -> bool:
	if not ResourceLoader.exists(HERO):
		print("[человек] нет %s — строю по канону числами" % HERO)
		return false
	var packed: PackedScene = load(HERO)
	if packed == null:
		print("[человек] %s не загрузился — строю по канону" % HERO)
		return false
	var root: Node = packed.instantiate()
	add_child(root)
	# РАЗВОРОТ НА 180°, И ЭТО НЕ ПРИДИРКА К ВКУСУ. В Блендере перёд тела — это
	# −Y (по нему всю дорогу считались грудь, лицо и сосок). Экспорт с yup
	# кладёт блендеровский −Y в +Z, а у Годо перёд — это −Z. Без разворота
	# человек идёт СПИНОЙ ВПЕРЁД, и на кадре это выглядит просто «странной
	# походкой», пока не поставишь камеру севернее и не увидишь лицо там, где
	# должна быть спина. Проверяется так: тело лицом на юг, камера с севера —
	# видно обязано быть спину.
	if root is Node3D:
		(root as Node3D).rotate_y(PI)
	skel = _find_skeleton(root)
	anim = _find_anim(root)
	if skel == null:
		print("[человек] в %s нет скелета — строю по канону" % HERO)
		root.queue_free()
		return false
	# КЛИПЫ ИЩЕМ ПО ИМЕНИ, а не по порядку: порядок в файле не обещан никем, а
	# перепутать ходьбу со стойкой — значит получить человека, шагающего на
	# месте стоя. Имена задаются в studio/export_hero.py.
	if anim != null:
		for a in anim.get_animation_list():
			if a.findn("покой") >= 0 or a.findn("idle") >= 0:
				clip_idle = a
			elif clip == "":
				clip = a
		if clip == "" and anim.get_animation_list().size() > 0:
			clip = anim.get_animation_list()[0]
	from_file = true
	print("[человек] тело из файла: костей %d, ходьба «%s», покой «%s», сеток %d"
		% [skel.get_bone_count(), clip, clip_idle, _count_meshes(root)])
	return true


func _find_skeleton(n: Node) -> Skeleton3D:
	if n is Skeleton3D:
		return n
	for c in n.get_children():
		var s := _find_skeleton(c)
		if s != null:
			return s
	return null


func _find_anim(n: Node) -> AnimationPlayer:
	if n is AnimationPlayer:
		return n
	for c in n.get_children():
		var a := _find_anim(c)
		if a != null:
			return a
	return null


func _count_meshes(n: Node) -> int:
	var k := 1 if n is MeshInstance3D else 0
	for c in n.get_children():
		k += _count_meshes(c)
	return k


func _make_materials() -> void:
	# ЦВЕТА ПРИГЛУШЕНЫ НАМЕРЕННО. Сукно 1890-х — это не чёрный и не яркий цвет:
	# красители тех лет дают глухие тёмные тона, а на солнце они выгорают в
	# серо-бурый. Насыщенный чёрный в кадре читается дырой, а не одеждой.
	_mat_coat = StandardMaterial3D.new()
	_mat_coat.resource_name = "пальто"
	_mat_coat.albedo_color = Color(0.16, 0.15, 0.14)     # тёмное сукно
	_mat_coat.roughness = 0.92
	_mat_coat.metallic = 0.0

	_mat_skin = StandardMaterial3D.new()
	_mat_skin.resource_name = "кожа"
	_mat_skin.albedo_color = Color(0.62, 0.46, 0.38)
	_mat_skin.roughness = 0.66
	# Кожа НЕ матовая и не зеркальная: свет уходит под поверхность и выходит
	# рядом. Полного подповерхностного рассеяния мы не тянем на телефоне, но
	# без него лицо в тёплом свете лампы выглядит крашеным деревом.
	_mat_skin.subsurf_scatter_enabled = true
	_mat_skin.subsurf_scatter_strength = 0.28

	_mat_boot = StandardMaterial3D.new()
	_mat_boot.resource_name = "сапоги"
	_mat_boot.albedo_color = Color(0.09, 0.075, 0.065)   # вакса
	_mat_boot.roughness = 0.44                            # сапоги чистят, они блестят

	_mat_cap = StandardMaterial3D.new()
	_mat_cap.resource_name = "картуз"
	_mat_cap.albedo_color = Color(0.13, 0.13, 0.135)
	_mat_cap.roughness = 0.85


func _make_skeleton() -> void:
	skel = Skeleton3D.new()
	skel.name = "Скелет"
	add_child(skel)
	for b: Array in BONES:
		var nm: String = b[0]
		var parent: String = b[1]
		var tail: Vector3 = b[2]
		var head: Vector3 = HIPS_HEAD if parent == "" else _rest_tail[parent]
		_rest_head[nm] = head
		_rest_tail[nm] = tail
		var id := skel.add_bone(nm)
		_bone_id[nm] = id
		if parent != "":
			skel.set_bone_parent(id, _bone_id[parent])
		# Поза покоя задаётся В СИСТЕМЕ РОДИТЕЛЯ: смещение начала кости
		# относительно начала родителя. Поворотов в покое нет — фигура стоит
		# прямо, и все вращения приходят от походки.
		var parent_head: Vector3 = HIPS_HEAD if parent == "" else _rest_head[parent]
		var local: Vector3 = head - parent_head
		skel.set_bone_rest(id, Transform3D(Basis(), local))
	skel.reset_bone_poses()


## Глобальное положение начала кости в позе покоя — оно же bind pose скиннинга.
func _rest_global(nm: String) -> Transform3D:
	return Transform3D(Basis(), _rest_head[nm])


# ---------------------------------------------------------------------------
# СЕТКА
#
# Тело собирается из КОЛЕЦ, нанизанных на кости. Кольцо — это эллипс (ширина
# по X, глубина по Z) на заданной высоте; между соседними кольцами натягивается
# полоса треугольников. Так строится всё: торс, пальто, руки, ноги, голова.
#
# Скиннинг — по ОДНОЙ кости на кольцо, с плавным переходом на стыках: у кольца
# задаются две кости и вес между ними. Полноценных весов по вершинам здесь нет
# и не нужно — одежда скрывает деформацию суставов, ради которой они и заводятся.
# ---------------------------------------------------------------------------

const SIDES := 12                      # граней в кольце: силуэт на телефоне

class Ring:
	var y: float                       # высота кольца (поза покоя), м
	var x: float                       # полуширина, м
	var z: float                       # полуглубина, м
	var cx: float = 0.0                # смещение центра по X
	var cz: float = 0.0
	var bone_a: String = "hips"
	var bone_b: String = "hips"
	var w: float = 1.0                 # вес кости a (1-w уходит на b)
	# ДУГА, А НЕ ВСЕГДА КОЛЬЦО. Волосы, козырёк, борода — это не кольца вокруг
	# головы, а куски. Пока кольцо было только полным, волосы лезли сплошной
	# полосой на лоб (замерено: перед волос на Z −0.087 при лице на −0.079, то
	# есть чёлка выступала перед лицом), а козырёк превращался в поля шляпы.
	# Отсчёт угла: 0 — ЗАТЫЛОК (+Z), π — ЛИЦО (−Z).
	var a0: float = 0.0
	var a1: float = TAU

	func _init(py: float, px: float, pz: float, ba: String, bb: String = "",
			pw: float = 1.0, pcx: float = 0.0, pcz: float = 0.0,
			pa0: float = 0.0, pa1: float = TAU) -> void:
		y = py; x = px; z = pz
		cx = pcx; cz = pcz
		bone_a = ba
		bone_b = bb if bb != "" else ba
		w = pw
		a0 = pa0; a1 = pa1


var _verts := PackedVector3Array()
var _norms := PackedVector3Array()
var _uvs := PackedVector2Array()
var _bones := PackedInt32Array()
var _weights := PackedFloat32Array()
var _idx := PackedInt32Array()


func _emit_ring(r: Ring, v_uv: float) -> int:
	## Кладёт кольцо в буферы и возвращает индекс его первой вершины.
	var first := _verts.size()
	var ia: int = _bone_id[r.bone_a]
	var ib: int = _bone_id[r.bone_b]
	for i in range(SIDES + 1):          # +1 — шов, чтобы UV не рвался
		var a: float = r.a0 + (r.a1 - r.a0) * float(i) / float(SIDES)
		var sx := sin(a)
		var cz := cos(a)
		_verts.append(Vector3(r.cx + r.x * sx, r.y, r.cz + r.z * cz))
		# нормаль эллипса: направление наружу с учётом разных полуосей
		_norms.append(Vector3(sx / maxf(r.x, 1e-4), 0.0, cz / maxf(r.z, 1e-4)).normalized())
		_uvs.append(Vector2(float(i) / float(SIDES), v_uv))
		_bones.append_array([ia, ib, 0, 0])
		_weights.append_array([r.w, 1.0 - r.w, 0.0, 0.0])
	return first


func _stitch(a0: int, b0: int) -> void:
	## Сшивает два подряд идущих кольца полосой треугольников.
	for i in range(SIDES):
		var a := a0 + i
		var b := b0 + i
		_idx.append_array([a, b, a + 1])
		_idx.append_array([a + 1, b, b + 1])


func _ellipsoid(c: Vector3, r: Vector3, bone: String, rows := 6) -> void:
	## Шар с разными полуосями: уши, глаза, нос-кончик. Кольцами по Y такое не
	## сделать — там всё насажено на вертикаль, а эти детали лежат вбок.
	var first := _verts.size()
	var ib: int = _bone_id[bone]
	for j in range(rows + 1):
		var v := PI * float(j) / float(rows)
		var sy := cos(v)
		var rr := sin(v)
		for i in range(SIDES + 1):
			var u := TAU * float(i) / float(SIDES)
			var n := Vector3(sin(u) * rr, sy, cos(u) * rr)
			_verts.append(c + Vector3(n.x * r.x, n.y * r.y, n.z * r.z))
			_norms.append(Vector3(n.x / r.x, n.y / r.y, n.z / r.z).normalized())
			_uvs.append(Vector2(float(i) / float(SIDES), float(j) / float(rows)))
			_bones.append_array([ib, ib, 0, 0])
			_weights.append_array([1.0, 0.0, 0.0, 0.0])
	var w := SIDES + 1
	for j in range(rows):
		for i in range(SIDES):
			var a := first + j * w + i
			var b := a + w
			_idx.append_array([a, b, a + 1, a + 1, b, b + 1])


func _cap(first: int, r: Ring, up: bool) -> void:
	## Закрывает кольцо крышкой (макушка, подошва, торец рукава).
	var c := _verts.size()
	_verts.append(Vector3(r.cx, r.y, r.cz))
	_norms.append(Vector3(0, 1 if up else -1, 0))
	_uvs.append(Vector2(0.5, 0.5))
	_bones.append_array([_bone_id[r.bone_a], _bone_id[r.bone_b], 0, 0])
	_weights.append_array([r.w, 1.0 - r.w, 0.0, 0.0])
	for i in range(SIDES):
		if up:
			_idx.append_array([first + i, c, first + i + 1])
		else:
			_idx.append_array([first + i + 1, c, first + i])


func _loft(rings: Array, cap_lo: bool, cap_hi: bool) -> void:
	## Нанизывает цепочку колец и при надобности закрывает концы.
	var firsts: Array[int] = []
	for i in range(rings.size()):
		var r: Ring = rings[i]
		firsts.append(_emit_ring(r, float(i) / float(maxi(rings.size() - 1, 1))))
	for i in range(rings.size() - 1):
		_stitch(firsts[i], firsts[i + 1])
	if cap_lo:
		_cap(firsts[0], rings[0], false)
	if cap_hi:
		_cap(firsts[rings.size() - 1], rings[rings.size() - 1], true)


func _flush(mesh: ArrayMesh, mat: Material) -> void:
	## Отдаёт накопленное как одну поверхность и очищает буферы.
	if _idx.is_empty():
		return
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = _verts
	arr[Mesh.ARRAY_NORMAL] = _norms
	arr[Mesh.ARRAY_TEX_UV] = _uvs
	arr[Mesh.ARRAY_BONES] = _bones
	arr[Mesh.ARRAY_WEIGHTS] = _weights
	arr[Mesh.ARRAY_INDEX] = _idx
	mesh.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	mesh.surface_set_material(mesh.get_surface_count() - 1, mat)
	_verts = PackedVector3Array()
	_norms = PackedVector3Array()
	_uvs = PackedVector2Array()
	_bones = PackedInt32Array()
	_weights = PackedFloat32Array()
	_idx = PackedInt32Array()


func _make_mesh() -> void:
	var mesh := ArrayMesh.new()

	# --- ПАЛЬТО: от плеч до середины голени. Главная линия силуэта. ---
	# Расширяется книзу: так пальто и висит, и так фигура читается на просвет.
	# ПЕРВАЯ ВЕРСИЯ ВЫШЛА БАЛАХОНОМ: плечи уже груди, талии нет, подол шире
	# плеч — в кадре это читалось рясой, а не пальто. Мужская верхняя одежда
	# устроена иначе: САМОЕ ШИРОКОЕ МЕСТО — ПЛЕЧИ, ниже идёт лёгкое сужение к
	# талии, и подол расходится только чуть-чуть, не выходя за ширину плеч.
	# Отсюда и «плечистый» силуэт, который узнаётся с любого расстояния.
	var hem := Y_KNEE - 0.10
	_loft([
		Ring.new(Y_SHOULDER + 0.015, SHOULDER_W * 0.53, 0.125, "chest"),  # плечо — шире всего
		Ring.new(Y_SHOULDER - 0.045, SHOULDER_W * 0.52, 0.126, "chest"),
		Ring.new(Y_CHEST,            SHOULDER_W * 0.47, 0.124, "chest"),
		Ring.new(Y_WAIST + 0.05,     SHOULDER_W * 0.41, 0.111, "chest", "spine", 0.4),
		Ring.new(Y_WAIST - 0.05,     SHOULDER_W * 0.40, 0.109, "spine"),  # талия — уже всего
		Ring.new(Y_CROTCH + 0.04,    SHOULDER_W * 0.45, 0.128, "spine", "hips", 0.35),
		Ring.new(Y_CROTCH - 0.12,    SHOULDER_W * 0.48, 0.140, "hips"),
		Ring.new(hem + 0.10,         SHOULDER_W * 0.50, 0.148, "hips"),
		Ring.new(hem,                SHOULDER_W * 0.51, 0.150, "hips"),
	], false, false)
	# Воротник — короткий и стоячий: он держит голову в силуэте отдельно от плеч
	# и закрывает шею почти до челюсти. Раньше он кончался на 9 см ниже
	# подбородка, и между воротником и головой оставался голый стебель.
	_loft([
		Ring.new(Y_SHOULDER - 0.02, 0.092, 0.086, "chest"),
		Ring.new(Y_CHIN - 0.075,    0.077, 0.072, "chest", "neck", 0.4),
		Ring.new(Y_CHIN - 0.040,    0.073, 0.069, "neck"),
	], false, false)
	# Рукава
	for s: float in [1.0, -1.0]:
		var side := "L" if s > 0.0 else "R"
		var sx := s * SHOULDER_W * 0.5
		_loft([
			Ring.new(Y_SHOULDER - 0.02, 0.062, 0.062, "clav." + side, "arm." + side, 0.5, sx, 0.0),
			Ring.new(Y_CHEST - 0.16,    0.052, 0.052, "arm." + side, "", 1.0, sx + s * 0.02, 0.0),
			Ring.new(Y_WAIST - 0.09,    0.045, 0.045, "farm." + side, "", 1.0, sx + s * 0.05, 0.0),
			Ring.new(Y_CROTCH + 0.06,   0.041, 0.041, "farm." + side, "", 1.0, sx + s * 0.06, 0.0),
		], true, false)
	_flush(mesh, _mat_coat)

	# --- КИСТИ И ГОЛОВА: открытая кожа. Их мало, и потому они дороги: в кадре
	# при лампе только они и светятся тёплым. ---
	for s: float in [1.0, -1.0]:
		var side := "L" if s > 0.0 else "R"
		var sx := s * (SHOULDER_W * 0.5 + 0.06)
		_loft([
			Ring.new(Y_CROTCH + 0.06, 0.038, 0.036, "hand." + side, "", 1.0, sx, 0.0),
			Ring.new(Y_CROTCH - 0.02, 0.042, 0.030, "hand." + side, "", 1.0, sx, 0.0),
			Ring.new(Y_CROTCH - 0.09, 0.034, 0.024, "hand." + side, "", 1.0, sx, 0.0),
		], true, true)
	# ШЕЯ И ГОЛОВА.
	#
	# Первая попытка дала голый цилиндр телесного цвета: ни лица, ни ушей, ни
	# волос. В кадре это читалось манекеном, и никакая работа над одеждой этого
	# не спасала — глаз идёт к лицу раньше, чем куда-либо ещё.
	#
	# ЧЕЛОВЕК СМОТРИТ В −Z (вперёд у пешехода — Vector3(-sin yaw, 0, -cos yaw)).
	# Значит лицо на отрицательном Z, затылок на положительном. Первый картуз
	# был построен с козырьком на +Z, то есть козырьком назад: спереди его не
	# было видно вовсе, а сзади торчал непонятный выступ.
	#
	# ЧЕРЕП — НЕ ШАР. Он длиннее спереди назад, чем поперёк (у человека примерно
	# 1.25:1), затылок выступает НАЗАД за линию шеи, а лицевая часть от скул к
	# подбородку сходится клином. Отсюда смещения центров колец по Z: cz>0
	# уводит кольцо к затылку. Без этого смещения голова выходит бочкой.
	var occ := 0.012                      # насколько затылок вынесен назад
	_loft([
		Ring.new(Y_CHIN - 0.075,       0.062, 0.058, "neck"),               # шея
		Ring.new(Y_CHIN - 0.015,       0.064, 0.062, "neck", "head", 0.4),
		Ring.new(Y_CHIN + 0.012,       0.055, 0.070, "head", "", 1.0, 0.0, 0.008),  # подбородок
		Ring.new(Y_CHIN + 0.055,       0.068, 0.086, "head", "", 1.0, 0.0, occ * 0.5),  # челюсть
		Ring.new(Y_CHIN + 0.105,       0.076, 0.094, "head", "", 1.0, 0.0, occ),        # скулы
		Ring.new(Y_CHIN + 0.150,       0.077, 0.093, "head", "", 1.0, 0.0, occ * 1.2),  # глаза
		Ring.new(Y_TOP - 0.048,        0.072, 0.086, "head", "", 1.0, 0.0, occ),
		Ring.new(Y_TOP - 0.012,        0.046, 0.052, "head", "", 1.0, 0.0, occ * 0.6),
	], false, true)
	# НОС. Мелочь на два сантиметра, а без неё профиля нет вовсе: силуэт головы
	# сбоку определяется носом и подбородком, больше ничем.
	var y_nose := Y_CHIN + 0.115
	_loft([
		Ring.new(y_nose + 0.038, 0.011, 0.013, "head", "", 1.0, 0.0, -0.070),
		Ring.new(y_nose + 0.010, 0.014, 0.020, "head", "", 1.0, 0.0, -0.082),
		Ring.new(y_nose - 0.014, 0.019, 0.022, "head", "", 1.0, 0.0, -0.086),
		Ring.new(y_nose - 0.026, 0.017, 0.016, "head", "", 1.0, 0.0, -0.080),
	], false, false)
	# УШИ. Стоят на линии между бровью и кончиком носа — это анатомическое
	# правило, а не приближение: у человека ухо занимает ровно эту высоту.
	for s: float in [1.0, -1.0]:
		_ellipsoid(Vector3(s * 0.074, Y_CHIN + 0.122, 0.014),
			Vector3(0.008, 0.026, 0.017), "head", 5)
	_flush(mesh, _mat_skin)

	# ГЛАЗА. При таком числе граней вылепить веки нельзя, и пытаться незачем.
	# Но тёмное пятно в глазнице глаз ищет прежде всего остального: без него
	# лицо мёртвое, с ним — уже лицо.
	# ПЕРВАЯ ПОПЫТКА ИХ ПОХОРОНИЛА: шарики стояли на Z −0.066 при поверхности
	# лица на −0.079, то есть на 13 мм ВНУТРИ черепа. Замерено габаритом
	# поверхности, а не увидено — на кадре это выглядело просто «лица нет».
	# Настоящий глаз утоплен в глазницу, но глазницы у нас нет, поэтому пятно
	# ставится вровень с лицом и чуть наружу.
	var eye := StandardMaterial3D.new()
	eye.resource_name = "глаза"
	eye.albedo_color = Color(0.055, 0.045, 0.04)
	eye.roughness = 0.18                  # глаз влажный и потому бликует
	for s: float in [1.0, -1.0]:
		_ellipsoid(Vector3(s * 0.031, Y_CHIN + 0.148, -0.079),
			Vector3(0.013, 0.010, 0.012), "head", 5)
	# БРОВИ. Тёмная горизонтальная черта над глазом делает для «живого лица»
	# больше, чем сам глаз: она задаёт выражение, которого у шарика нет.
	for s: float in [1.0, -1.0]:
		_ellipsoid(Vector3(s * 0.032, Y_CHIN + 0.168, -0.078),
			Vector3(0.019, 0.005, 0.011), "head", 4)
	_flush(mesh, eye)

	# ВОЛОСЫ, БАКЕНБАРДЫ И УСЫ. Усы у взрослого мужчины 1890-х — не характер, а
	# норма: гладко выбритое лицо в эту эпоху скорее исключение. Одна тёмная
	# полоска под носом переводит фигуру из «человек вообще» в «человек оттуда».
	var hair := StandardMaterial3D.new()
	hair.resource_name = "волосы"
	hair.albedo_color = Color(0.10, 0.075, 0.055)
	hair.roughness = 0.80
	# ЗАТЫЛОК И ВИСКИ — то, что видно из-под картуза. ДУГА, А НЕ КОЛЬЦО: полное
	# кольцо давало чёлку поперёк лба и закрывало лицо целиком (замерено: перед
	# волос −0.087 против лица −0.079). Берём 0..±0.66π от затылка — это ровно
	# затылок с висками, лоб остаётся открытым.
	var hb := 0.66 * PI
	_loft([
		Ring.new(Y_CHIN + 0.085, 0.072, 0.091, "head", "", 1.0, 0.0, occ * 1.4, -hb, hb),
		Ring.new(Y_CHIN + 0.125, 0.082, 0.100, "head", "", 1.0, 0.0, occ * 1.3, -hb, hb),
		Ring.new(Y_TOP - 0.070,  0.081, 0.096, "head", "", 1.0, 0.0, occ * 1.1, -hb, hb),
	], false, false)
	# бакенбарды
	for s: float in [1.0, -1.0]:
		_ellipsoid(Vector3(s * 0.066, Y_CHIN + 0.082, -0.006),
			Vector3(0.012, 0.030, 0.026), "head", 5)
	# усы
	_ellipsoid(Vector3(0.0, y_nose - 0.036, -0.072),
		Vector3(0.030, 0.009, 0.016), "head", 5)
	_flush(mesh, hair)

	# --- КАРТУЗ: тулья и козырёк. Одна деталь, а фигура сразу из эпохи. ---
	# Тулья слегка завалена назад — так картуз и сидит, если его не поправлять.
	_loft([
		Ring.new(Y_TOP - 0.072, 0.084, 0.099, "head", "", 1.0, 0.0, occ),
		Ring.new(Y_TOP - 0.028, 0.087, 0.101, "head", "", 1.0, 0.0, occ * 1.4),
		Ring.new(Y_TOP + 0.006, 0.078, 0.090, "head", "", 1.0, 0.0, occ * 1.8),
	], false, true)
	# КОЗЫРЁК — ВПЕРЁД, ТО ЕСТЬ НА −Z, И ТОЛЬКО ВПЕРЁД. В первой версии он стоял
	# на +Z: спереди его не было видно вовсе, а сзади из головы торчал выступ.
	# Во второй он стал полным кольцом — то есть полями шляпы, а картуз это не
	# шляпа. Дуга 0.62π..1.38π вокруг лица даёт именно козырёк.
	var vb0 := 0.62 * PI
	var vb1 := 1.38 * PI
	_loft([
		Ring.new(Y_TOP - 0.072, 0.086, 0.101, "head", "", 1.0, 0.0, occ, vb0, vb1),
		Ring.new(Y_TOP - 0.083, 0.092, 0.132, "head", "", 1.0, 0.0, -0.030, vb0, vb1),
	], false, false)
	_flush(mesh, _mat_cap)

	# --- НОГИ И САПОГИ. Выше края пальто ног не видно, поэтому строим от бедра
	# только то, что попадает в кадр: голенище, стопа. ---
	for s: float in [1.0, -1.0]:
		var side := "L" if s > 0.0 else "R"
		var sx := s * HIP_W * 0.5
		_loft([
			Ring.new(Y_KNEE + 0.06,  0.058, 0.058, "thigh." + side, "", 1.0, sx, 0.0),
			Ring.new(Y_KNEE - 0.02,  0.053, 0.054, "shin." + side, "", 1.0, sx, 0.0),
			Ring.new(Y_ANKLE + 0.22, 0.049, 0.052, "shin." + side, "", 1.0, sx, 0.0),
			Ring.new(Y_ANKLE + 0.04, 0.042, 0.048, "shin." + side, "foot." + side, 0.5, sx, 0.0),
			Ring.new(Y_ANKLE - 0.03, 0.043, 0.055, "foot." + side, "", 1.0, sx, 0.012),
			Ring.new(0.022,          0.044, 0.075, "foot." + side, "", 1.0, sx, 0.055),
			Ring.new(0.004,          0.042, 0.078, "foot." + side, "", 1.0, sx, 0.060),
		], true, false)
	_flush(mesh, _mat_boot)

	# --- ПРИВЯЗКА К СКЕЛЕТУ ---
	# Skin хранит bind pose — ОБРАТНОЕ положение кости в позе покоя. Без него
	# сетка уезжает в сторону при первом же повороте кости: движок считает, что
	# вершины заданы в системе кости, а они заданы в мире.
	var skin := Skin.new()
	for b: Array in BONES:
		var nm: String = b[0]
		skin.add_bind(_bone_id[nm], _rest_global(nm).affine_inverse())
		skin.set_bind_name(skin.get_bind_count() - 1, nm)

	mesh_inst = MeshInstance3D.new()
	mesh_inst.name = "Тело"
	mesh_inst.mesh = mesh
	skel.add_child(mesh_inst)
	mesh_inst.skeleton = NodePath("..")
	mesh_inst.skin = skin
	# Тени от фигуры обязательны: без собственной тени человек висит над землёй,
	# и это первое, что выдаёт подделку — заметнее любой ошибки в форме.
	mesh_inst.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON


## Куда цеплять фонарь: положение кисти в текущей позе, мировые координаты.
func hand_transform(right := true) -> Transform3D:
	# ИМЕНА КОСТЕЙ У ДВУХ ТЕЛ РАЗНЫЕ. У процедурного они наши: hand.R. У модели
	# — скелета cmu_mb, под который снята вся база движения: RightHand. Ищем по
	# обоим набором имён, иначе фонарь повиснет в начале координат.
	var names := ["RightHand", "hand.R"] if right else ["LeftHand", "hand.L"]
	for nm in names:
		var id := skel.find_bone(nm)
		if id >= 0:
			return skel.global_transform * skel.get_bone_global_pose(id)
	return skel.global_transform


## САМОПРОВЕРКА ЧИСЛАМИ: печатает пропорции построенной фигуры и сверяет их с
## каноном. Нужна затем, что «фигура выглядит неправильно» — не диагноз, а
## ощущение; отношение роста к голове — диагноз.
func self_test() -> void:
	var tri := 0
	for s in range(mesh_inst.mesh.get_surface_count()):
		tri += mesh_inst.mesh.surface_get_array_index_len(s) / 3
	print("[человек] рост %.3f м, голова %.3f м, отношение %.2f (канон 7.5)"
		% [H, HEAD, H / HEAD])
	print("[человек] плечи %.3f м (%.2f головы), пах на %.3f м (%.0f%% роста)"
		% [SHOULDER_W, SHOULDER_W / HEAD, Y_CROTCH, 100.0 * Y_CROTCH / H])
	print("[человек] костей %d, поверхностей %d, треугольников %d"
		% [skel.get_bone_count(), mesh_inst.mesh.get_surface_count(), tri])
	# ГАБАРИТ КАЖДОЙ ПОВЕРХНОСТИ ОТДЕЛЬНО. Нужно затем, что «лица не видно» —
	# это два разных случая: детали не построились или построились внутри
	# черепа. Человек смотрит в −Z, значит нос, глаза и козырёк обязаны иметь
	# минимум по Z меньше, чем сам череп. Проверяется числом, а не кадром: я
	# трижды снял затылок, считая, что снимаю лицо, и потерял на этом полчаса.
	for s2 in range(mesh_inst.mesh.get_surface_count()):
		var vs: PackedVector3Array = mesh_inst.mesh.surface_get_arrays(s2)[Mesh.ARRAY_VERTEX]
		var lo := vs[0]
		var hi := vs[0]
		for v in vs:
			lo = lo.min(v)
			hi = hi.max(v)
		var mt: Material = mesh_inst.mesh.surface_get_material(s2)
		var nm2: String = mt.resource_name if mt != null and mt.resource_name != "" else "№%d" % s2
		print("   %-10s X %.3f..%.3f  Y %.3f..%.3f  Z %.3f..%.3f"
			% [nm2, lo.x, hi.x, lo.y, hi.y, lo.z, hi.z])
