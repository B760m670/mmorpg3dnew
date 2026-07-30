# Имя класса НЕ объявляем: подключаемся через preload (см. light_stage.gd).
extends Node3D
## ПОКРОВ: настоящая геометрия растений вокруг наблюдателя.
##
## ЧЕМ ЭТО ОТЛИЧАЕТСЯ ОТ СТАРОЙ ТРАВЫ. Старая была «лезвие = плоский
## треугольник, 7 штук в кусте, 9 кустов на метр» — 63 побега/м² при настоящих
## 11 000. Она читалась размазанным ворсом, и её убрали. Здесь растения приходят
## готовой геометрией, испечённой по ботанике (tools/bake_plants.py), а густота
## берётся из ПРОЕКТИВНОГО ПОКРЫТИЯ сообщества, а не из вкуса.
##
## ДВА УРОВНЯ, И ОБА ИЗМЕРЕНЫ:
##   ДЕРНИНА — вблизи, лист настоящей ширины. Луг требует 494 дернин/м², это
##     54 505 △/м², и на бюджете 400 тыс. △ геометрия доходит до 1.5 м.
##   КУРТИНА 0.5x0.5 м — средняя даль, лист расширен втрое. Луг: 149 листьев,
##     покрытие 97%, 1490 △; при 4 куртинах/м² это 5 960 △/м² — в девять раз
##     дешевле дернин за то же покрытие, и геометрия уходит на 6.5 м.
##   ДАЛЬШЕ покров держит материал земли. Иначе кадра не будет ни на чём.
## ПОЧЕМУ РАСШИРЕНИЕ ЛИСТА НЕ ОБМАН: на телефоне (1290 пикселей, 66°) один
## пиксель на 8 м закрывает 8 мм, а лист травы — 5-9 мм, то есть ровно пиксель.
## Тоньше пикселя лист нарисовать нельзя, он исчезает или мерцает.
##
## РАДИУС НЕ НАЗНАЧЕН, А ВЫВЕДЕН из бюджета треугольников и густоты сообщества.
## Бюджет — единственное, что тут задано руками, и его надо замерить на
## устройстве, а не назначить.

const PLANTS_BIN := "res://assets/plants/plants.bin"
const PATCHES_BIN := "res://assets/plants/patches.bin"
const VEG_JSON := "res://data/real/vegetation.json"

## Бюджеты треугольников на покров в кадре. ЭТО НАДО ЗАМЕРИТЬ НА УСТРОЙСТВЕ.
const TUFT_BUDGET := 400000
const PATCH_BUDGET := 400000
## Насколько наблюдатель должен сместиться, чтобы пересеять. Пересев стоит
## заметно, поэтому не каждый кадр.
const RESEED_MOVE := 1.5

var terrain: Terrain

var _tuft_mesh: Dictionary = {}       # латинское имя -> ArrayMesh
var _tuft_tri: Dictionary = {}        # латинское имя -> треугольников
var _tuft_cover: Dictionary = {}      # латинское имя -> покрытие, м²
var _tuft_top: Dictionary = {}        # латинское имя -> природная высота, м
var _patch_mesh: Dictionary = {}      # сообщество -> ArrayMesh
var _patch_tri: Dictionary = {}
var _patch_top: Dictionary = {}
var _veg: Dictionary = {}
var _zone_names := ["луг", "парк", "лес", "поле", "город", "берег"]

var _mm_tuft: Dictionary = {}         # имя -> MultiMeshInstance3D
var _mm_patch: Dictionary = {}        # сообщество -> MultiMeshInstance3D
var _last_seed_pos := Vector3(1e9, 0, 1e9)
var _mat: ShaderMaterial

var last_report := {}
var _reported := false
## ЗА КОЛЬЦОМ КУРТИН они не обрываются разом, а РЕДЕЮТ до нуля. Иначе на кадре
## видна окружность, за которой трава кончается — её сразу заметно, и это
## единственное, что выдаёт приём. Растворение стоит немного: за кольцом стоит
## лишь малая доля куртин.
const FADE_OUT := 2.2

func build() -> void:
	_load_veg()
	_load_plants()
	_load_patches()
	_mat = _material()
	for lat in _tuft_mesh.keys():
		_mm_tuft[lat] = _make_mm(_tuft_mesh[lat])
	for cname in _patch_mesh.keys():
		_mm_patch[cname] = _make_mm(_patch_mesh[cname])
	print("[покров] видов %d, куртин сообществ %d — дернина в среднем %d △, куртина %d △"
		% [_tuft_mesh.size(), _patch_mesh.size(),
		_avg(_tuft_tri), _avg(_patch_tri)])

func _avg(d: Dictionary) -> int:
	if d.is_empty():
		return 0
	var s := 0
	for v in d.values():
		s += int(v)
	return s / d.size()

func _load_veg() -> void:
	var f := FileAccess.open(VEG_JSON, FileAccess.READ)
	if f == null:
		push_warning("[покров] нет ботаники %s" % VEG_JSON)
		return
	_veg = JSON.parse_string(f.get_as_text())

func _make_mm(mesh: ArrayMesh) -> MultiMeshInstance3D:
	var mm := MultiMesh.new()
	mm.transform_format = MultiMesh.TRANSFORM_3D
	mm.mesh = mesh
	mm.instance_count = 0
	var mi := MultiMeshInstance3D.new()
	mi.multimesh = mm
	mi.material_override = _mat
	mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	add_child(mi)
	return mi

## Читает испечённый бинарь дернин. Формат — в tools/bake_plants.py.
func _load_plants() -> void:
	var f := FileAccess.open(PLANTS_BIN, FileAccess.READ)
	if f == null:
		push_warning("[покров] нет %s — запусти tools/bake_plants.py" % PLANTS_BIN)
		return
	var ver := f.get_32()
	var count := f.get_32()
	if ver != 1 or count <= 0 or count > 1000:
		push_warning("[покров] дернины не читаются")
		return
	for _k in range(count):
		var nlen := f.get_8()
		var _code := f.get_8()
		var top := f.get_float()
		var cover := f.get_float()
		var lat := f.get_buffer(nlen).get_string_from_utf8()
		var nv := f.get_32()
		var ni := f.get_32()
		var mesh := _read_mesh(f, nv, ni)
		_tuft_mesh[lat] = mesh
		_tuft_tri[lat] = ni / 3
		_tuft_cover[lat] = cover
		_tuft_top[lat] = top

func _load_patches() -> void:
	var f := FileAccess.open(PATCHES_BIN, FileAccess.READ)
	if f == null:
		push_warning("[покров] нет %s" % PATCHES_BIN)
		return
	var ver := f.get_32()
	var count := f.get_32()
	if ver != 1 or count <= 0 or count > 100:
		return
	for _k in range(count):
		var nlen := f.get_8()
		var _zone := f.get_8()
		var _top: float = f.get_float()
		var _cov := f.get_float()
		var cname := f.get_buffer(nlen).get_string_from_utf8()
		var nv := f.get_32()
		var ni := f.get_32()
		_patch_mesh[cname] = _read_mesh(f, nv, ni)
		_patch_tri[cname] = ni / 3
		_patch_top[cname] = _top

## Вершина: 3 float место, 3 float нормаль, 4 байта цвет. Цвет лежит в вершине:
## у травы он свойство вида и части растения, отдельной текстуры не нужно.
func _read_mesh(f: FileAccess, nv: int, ni: int) -> ArrayMesh:
	var pos := PackedVector3Array()
	var nrm := PackedVector3Array()
	var col := PackedColorArray()
	pos.resize(nv)
	nrm.resize(nv)
	col.resize(nv)
	for i in range(nv):
		pos[i] = Vector3(f.get_float(), f.get_float(), f.get_float())
		nrm[i] = Vector3(f.get_float(), f.get_float(), f.get_float())
		var r := f.get_8()
		var g := f.get_8()
		var b := f.get_8()
		var a := f.get_8()
		col[i] = Color(r / 255.0, g / 255.0, b / 255.0, a / 255.0)
	var idx := PackedInt32Array()
	idx.resize(ni)
	for i in range(ni):
		idx[i] = f.get_32()
	var arr := []
	arr.resize(Mesh.ARRAY_MAX)
	arr[Mesh.ARRAY_VERTEX] = pos
	arr[Mesh.ARRAY_NORMAL] = nrm
	arr[Mesh.ARRAY_COLOR] = col
	arr[Mesh.ARRAY_INDEX] = idx
	var m := ArrayMesh.new()
	m.add_surface_from_arrays(Mesh.PRIMITIVE_TRIANGLES, arr)
	return m

func _material() -> ShaderMaterial:
	var m := ShaderMaterial.new()
	m.shader = load("res://shaders/world/plants.gdshader")
	return m

## Сообщество в точке — по растру зон того же рельефа, что рисует землю.
func community_at(x: float, z: float) -> String:
	if terrain == null:
		return "луг"
	var z_idx := terrain.zone_at(x, z) if terrain.has_method("zone_at") else 0
	if z_idx < 0 or z_idx >= _zone_names.size():
		return "луг"
	return _zone_names[z_idx]

## Густота дернин на м², выведенная из ПОКРЫТИЯ сообщества, а не назначенная.
## При случайной раскладке доля закрытой земли равна 1-exp(-n·покрытие),
## отсюда n = -ln(1-цель)/покрытие.
func _tuft_density(com: Dictionary) -> Array:
	var mix: Dictionary = com.get("mix", {})
	var cov := 0.0
	var tri := 0.0
	var species: Dictionary = _veg.get("species", {})
	for sname in mix.keys():
		if not species.has(sname):
			continue
		var lat: String = species[sname]["lat"]
		if not _tuft_cover.has(lat):
			continue
		cov += float(mix[sname]) * float(_tuft_cover[lat])
		tri += float(mix[sname]) * float(_tuft_tri[lat])
	if cov <= 0.0:
		return [0.0, 1.0]
	var target: float = clampf(float(com.get("cover", 0.9)), 0.05, 0.995)
	var n := -log(1.0 - target) / cov
	return [n, maxf(tri, 1.0)]

## ПОСЕВ. Сетка с детерминированным сдвигом внутри ячейки: одно и то же место
## всегда получает одну и ту же траву, без базы посаженных экземпляров. Это то
## же правило, по которому уже расставлен город.
func reseed(observer: Vector3) -> void:
	if _mm_tuft.is_empty() or terrain == null:
		return
	if _last_seed_pos.distance_to(observer) < RESEED_MOVE:
		return
	_last_seed_pos = observer
	var cname := community_at(observer.x, observer.z)
	var coms: Dictionary = _veg.get("communities", {})
	if not coms.has(cname):
		cname = "луг"
	var com: Dictionary = coms.get(cname, {})
	var dens := _tuft_density(com)
	var n_m2: float = dens[0]
	var tri_tuft: float = dens[1]
	# РАДИУС ИЗ БЮДЖЕТА: сколько дернин влезает в отведённые треугольники
	var r_near := 0.0
	if n_m2 > 0.0 and tri_tuft > 0.0:
		r_near = sqrt(float(TUFT_BUDGET) / (n_m2 * tri_tuft) / PI)
	r_near = clampf(r_near, 0.5, 12.0)
	var patch_tri: float = float(_patch_tri.get(cname, 1500))
	# куртина закрывает свои 0.25 м², значит 4 на квадратный метр
	var r_mid: float = clampf(sqrt(float(PATCH_BUDGET) / (4.0 * patch_tri) / PI), r_near, 40.0)

	_seed_tufts(observer, cname, com, n_m2, r_near)
	_seed_patches(observer, cname, com, r_near, r_mid)
	if not _reported:
		_reported = true
		print("[покров] %s: дернин %.0f/м², геометрия до %.1f м, куртины до %.1f м (растворяются до %.1f м)"
			% [cname, n_m2, r_near, r_mid, r_mid * FADE_OUT])
		print("[покров] в кадре: дернин %d, куртин %d, всего %d △"
			% [_count(_mm_tuft), _count(_mm_patch), _tris()])
	last_report = {
		"community": cname,
		"tuft_density_m2": n_m2,
		"r_near": r_near,
		"r_mid": r_mid,
		"tufts": _count(_mm_tuft),
		"patches": _count(_mm_patch),
		"tris": _tris(),
	}

func _count(d: Dictionary) -> int:
	var s := 0
	for mi in d.values():
		s += (mi as MultiMeshInstance3D).multimesh.instance_count
	return s

func _tris() -> int:
	var s := 0
	for lat in _mm_tuft.keys():
		s += int(_tuft_tri[lat]) * (_mm_tuft[lat] as MultiMeshInstance3D).multimesh.instance_count
	for cn in _mm_patch.keys():
		s += int(_patch_tri[cn]) * (_mm_patch[cn] as MultiMeshInstance3D).multimesh.instance_count
	return s

func _hash2(i: int, j: int, salt: int) -> float:
	var h := (i * 73856093) ^ (j * 19349663) ^ (salt * 83492791)
	h = (h ^ (h >> 13)) * 1274126177
	return float((h ^ (h >> 16)) & 0xFFFFFF) / float(0xFFFFFF)

## ВЫСОТА ТРАВОСТОЯ — свойство СООБЩЕСТВА, а не только вида.
## ИЗМЕРЕНО по кадру: в парке выросла трава по колено, хотя парк — это скошенный
## газон 5-9 см (в ботанике так и записано: mown = true). Я брал природную
## высоту вида и не смотрел на сообщество. Скошенный газон — те же виды, только
## срезанные, поэтому сжимаем по высоте, а не подменяем растение.
func _sward_scale(com: Dictionary, natural_h: float) -> float:
	var hr: Array = com.get("h_cm", [])
	if hr.size() < 2 or natural_h <= 0.01:
		return 1.0
	var target: float = (float(hr[0]) + float(hr[1])) * 0.5 / 100.0
	return clampf(target / natural_h, 0.12, 1.6)

func _seed_tufts(obs: Vector3, cname: String, com: Dictionary,
		n_m2: float, radius: float) -> void:
	var species: Dictionary = _veg.get("species", {})
	var mix: Dictionary = com.get("mix", {})
	# накопительное распределение видов
	var lats := PackedStringArray()
	var cum := PackedFloat32Array()
	var acc := 0.0
	for sname in mix.keys():
		if not species.has(sname):
			continue
		var lat: String = species[sname]["lat"]
		if not _tuft_mesh.has(lat):
			continue
		acc += float(mix[sname])
		lats.append(lat)
		cum.append(acc)
	if lats.is_empty():
		return
	var per: Dictionary = {}
	for lat in lats:
		per[lat] = []
	var cell: float = 1.0 / sqrt(maxf(n_m2, 0.01))
	var half := int(ceil(radius / cell))
	var ci := int(floor(obs.x / cell))
	var cj := int(floor(obs.z / cell))
	for dj in range(-half, half + 1):
		for di in range(-half, half + 1):
			var gi := ci + di
			var gj := cj + dj
			var px: float = (float(gi) + _hash2(gi, gj, 1)) * cell
			var pz: float = (float(gj) + _hash2(gi, gj, 2)) * cell
			var d := Vector2(px - obs.x, pz - obs.z).length()
			if d > radius:
				continue
			var u: float = _hash2(gi, gj, 3) * acc
			var pick: String = lats[lats.size() - 1]
			for k in range(cum.size()):
				if u <= cum[k]:
					pick = lats[k]
					break
			var y: float = terrain.height(px, pz)
			var yaw: float = _hash2(gi, gj, 4) * TAU
			var sc: float = 0.8 + _hash2(gi, gj, 5) * 0.45
			# высоту сжимаем к травостою сообщества, ширину листа не трогаем:
			# скошенный лист остаётся своей ширины, он просто короче
			var sy: float = sc * _sward_scale(com, float(_tuft_top.get(pick, 0.5)))
			var t := Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3(sc, sy, sc)),
				Vector3(px, y, pz))
			(per[pick] as Array).append(t)
	for lat in _mm_tuft.keys():
		var mm: MultiMesh = (_mm_tuft[lat] as MultiMeshInstance3D).multimesh
		var list: Array = per.get(lat, [])
		mm.instance_count = list.size()
		for k in range(list.size()):
			mm.set_instance_transform(k, list[k])

func _seed_patches(obs: Vector3, cname: String, com: Dictionary,
		r_in: float, r_out: float) -> void:
	for cn in _mm_patch.keys():
		if cn != cname:
			(_mm_patch[cn] as MultiMeshInstance3D).multimesh.instance_count = 0
	if not _mm_patch.has(cname):
		return
	var mm: MultiMesh = (_mm_patch[cname] as MultiMeshInstance3D).multimesh
	var cell := 0.5                      # куртина 0.5 x 0.5 м
	var half := int(ceil(r_out * FADE_OUT / cell))
	var ci := int(floor(obs.x / cell))
	var cj := int(floor(obs.z / cell))
	var list: Array = []
	for dj in range(-half, half + 1):
		for di in range(-half, half + 1):
			var gi := ci + di
			var gj := cj + dj
			var px := float(gi) * cell
			var pz := float(gj) * cell
			var d := Vector2(px + 0.25 - obs.x, pz + 0.25 - obs.z).length()
			# КОЛЬЦО: вблизи стоят дернины, куртины начинаются за ними, иначе
			# один и тот же покров рисовался бы дважды
			if d <= r_in or d > r_out * FADE_OUT:
				continue
			# РЕДЕНИЕ за кольцом: доля оставленных куртин падает от 1 до 0.
			# Решение детерминированное (по хешу клетки), поэтому при движении
			# куртины не мигают.
			if d > r_out:
				var keep := 1.0 - (d - r_out) / (r_out * (FADE_OUT - 1.0))
				if _hash2(gi, gj, 11) > keep * keep:
					continue
			var y: float = terrain.height(px + 0.25, pz + 0.25)
			var yaw: float = floor(_hash2(gi, gj, 7) * 4.0) * (PI * 0.5)
			var sy: float = _sward_scale(com, float(_patch_top.get(cname, 0.5)))
			list.append(Transform3D(Basis(Vector3.UP, yaw).scaled(Vector3(1.0, sy, 1.0)),
				Vector3(px, y, pz)))
	mm.instance_count = list.size()
	for k in range(list.size()):
		mm.set_instance_transform(k, list[k])
