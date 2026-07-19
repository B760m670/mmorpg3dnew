class_name GrassField
extends Node3D
## ТРАВЯНОЙ ЯРУС — посев по РЕАЛЬНЫМ зонам землепользования (модель
## Decima/Ghost of Tsushima: растительность не хранится в базе — она
## детерминированно сеется вокруг наблюдателя по картам правил).
##
## Тайлы 16 м кольцом ±104 м следуют за наблюдателем; в каждом тайле кусты
## травы (MultiMesh, 7 лезвий на куст) сеются хешем от координат тайла:
## при каждом возвращении на место — ТА ЖЕ трава, без базы инстансов.
## Правила посева — из реальности: зона землепользования (луг/парк/лес/поля/
## болото), уклон рельефа (крутые склоны голые), вода — пусто.
## Корень куста — terrain.height() (та же сетка, что физика): трава стоит
## НА земле. Ветер и растворение вдали — в вершинном шейдере (без щелчков).

const TILE_M := 16.0
const RADIUS_TILES := 6              # покрытие ±104 м вокруг наблюдателя
const NEAR_TILES := 2                # ближний пояс (±40 м) — плотнее
const CLUMPS_M2_NEAR := 9.0          # кустов на м² вблизи — густой покров у ног
const CLUMPS_M2_FAR := 2.5
const BLADES_PER_CLUMP := 7
const TRIS_PER_BLADE := 3
const BUILDS_PER_FRAME := 4          # амортизация достройки на ходу (без рывков)
const SLOPE_MIN_NY := 0.82           # круче ~35° — голый грунт (как в шейдере земли)

const ZONES_PATH := "res://assets/dem/zones_1024.bin"
const ZONES_N := 1024
const SLICE_BIN := "res://assets/dem/slice_palace.bin"
const SLICE_META := "res://assets/dem/slice_palace.json"
# ПОЛЕ ЖИЗНИ (tools/build_lifefield.py): плотность/высота/сочность травы,
# ВЫЧИСЛЕННЫЕ из реальных условий (влага от воды/низин, свет от склона/полога,
# вид от land-cover) — не подобранные. Внутри среза оно ведёт посев вместо
# захардкоженных правил: трава вырастает из условий, а не «походит» на траву.
const LIFE_BIN := "res://assets/life/slice_lifefield.bin"
const LIFE_META := "res://assets/life/slice_lifefield.json"
const LIFE_DRY := Color(0.42, 0.40, 0.16)   # сухой покров (низкая сочность)
const LIFE_WET := Color(0.16, 0.40, 0.12)   # сочный покров (высокая сочность)

var terrain: Terrain
var zone_size_m := 12288.0
var clump_count: int = 0

var _zones: PackedByteArray
var _slice: PackedByteArray
var _slice_n := 0
var _slice_cx := 0.0
var _slice_cy := 0.0
var _slice_half := 0.0
var _life: PackedByteArray
var _life_n := 0
var _life_cx := 0.0
var _life_cy := 0.0
var _life_half := 0.0
var _life_hmax := 1.3
var _mesh: ArrayMesh
var _mat: ShaderMaterial
var _tiles: Dictionary = {}          # Vector2i -> {"node":..., "band":int, "n":int}
var _queue: Array[Vector2i] = []
var _center := Vector2i(1 << 30, 1 << 30)
var _reported := false

## правила зоны: [вероятность куста 0..1, высота куста м, базовый цвет]
func _zone_rule(z: int) -> Array:
	match z:
		1: return [0.55, 0.42, Color(0.25, 0.38, 0.12)]   # парк — ниже, ухоженнее
		2: return [0.28, 0.30, Color(0.14, 0.24, 0.10)]   # лес — тёмный подлесок
		3: return [0.95, 0.80, Color(0.45, 0.42, 0.16)]   # поля — высокие злаки
		4: return [0.06, 0.30, Color(0.30, 0.36, 0.14)]   # город — пробивается редко
		5: return [0.00, 0.00, Color.BLACK]               # вода — пусто
		6: return [0.70, 0.55, Color(0.24, 0.34, 0.12)]   # кустарник — высокотравье
		7: return [0.60, 0.70, Color(0.20, 0.30, 0.14)]   # болото — осока
		8: return [0.04, 0.25, Color(0.26, 0.33, 0.13)]   # дорога — утоптано
		_: return [1.00, 0.55, Color(0.30, 0.41, 0.13)]   # луг

## правила посева среза (детальные поверхности Дворцового парка):
## [вероятность, высота м, цвет]
func _slice_rule(s: int) -> Array:
	match s:
		1: return [0.90, 0.14, Color(0.20, 0.40, 0.10)]   # газон — густой, СТРИЖЕНЫЙ
		2: return [0.42, 0.35, Color(0.16, 0.24, 0.10)]   # роща — редкий подлесок
		3: return [0.24, 0.30, Color(0.12, 0.20, 0.09)]   # лес — тёмный подлесок
		4: return [0.00, 0.00, Color.BLACK]               # аллея — гравий, пусто
		5: return [0.00, 0.00, Color.BLACK]               # плац — песок, пусто
		6: return [0.00, 0.00, Color.BLACK]               # вода
		7: return [0.75, 0.95, Color(0.34, 0.40, 0.16)]   # берег — высокий камыш
		8: return [0.00, 0.00, Color.BLACK]               # мостовая
		_: return [1.00, 0.60, Color(0.28, 0.42, 0.12)]   # луг

func _ready() -> void:
	var f := FileAccess.open(ZONES_PATH, FileAccess.READ)
	if f != null:
		_zones = f.get_buffer(ZONES_N * ZONES_N)
	if _zones.size() != ZONES_N * ZONES_N:
		_zones = PackedByteArray()
		push_warning("[grass] нет карты зон — вся трава по правилу луга")
	_load_slice()
	_load_life()
	_mesh = _build_clump_mesh()
	_mat = ShaderMaterial.new()
	_mat.shader = load("res://shaders/world/grass.gdshader")

func _load_slice() -> void:
	var fm := FileAccess.open(SLICE_META, FileAccess.READ)
	var fb := FileAccess.open(SLICE_BIN, FileAccess.READ)
	if fm == null or fb == null:
		return
	var meta: Dictionary = JSON.parse_string(fm.get_as_text())
	_slice_n = int(meta["n"])
	_slice_cx = float(meta["cx"])
	_slice_cy = float(meta["cy"])
	_slice_half = float(meta["half_m"])
	_slice = fb.get_buffer(_slice_n * _slice_n)
	if _slice.size() != _slice_n * _slice_n:
		_slice = PackedByteArray()
		_slice_half = 0.0

func _load_life() -> void:
	var fm := FileAccess.open(LIFE_META, FileAccess.READ)
	var fb := FileAccess.open(LIFE_BIN, FileAccess.READ)
	if fm == null or fb == null:
		return
	var meta: Dictionary = JSON.parse_string(fm.get_as_text())
	_life_n = int(meta["n"])
	_life_cx = float(meta["cx"])
	_life_cy = float(meta["cy"])
	_life_half = float(meta["half_m"])
	_life_hmax = float(meta.get("h_max_m", 1.3))
	_life = fb.get_buffer(_life_n * _life_n * 3)
	if _life.size() != _life_n * _life_n * 3:
		_life = PackedByteArray()

## поле жизни в точке: [плотность 0..1, высота м, сочность 0..1] или [] вне поля
func _life_at(x: float, z: float) -> Array:
	if _life.is_empty():
		return []
	var u := int((x - _life_cx + _life_half) / (2.0 * _life_half) * float(_life_n))
	# строка 0 = север; data_y = −z
	var v := int((_life_cy + _life_half - (-z)) / (2.0 * _life_half) * float(_life_n))
	if u < 0 or v < 0 or u >= _life_n or v >= _life_n:
		return []
	var idx := (v * _life_n + u) * 3
	return [float(_life[idx]) / 255.0,
		float(_life[idx + 1]) / 255.0 * _life_hmax,
		float(_life[idx + 2]) / 255.0]

func _zone_at(x: float, z: float) -> int:
	if _zones.is_empty():
		return 0
	var u := int((x + zone_size_m * 0.5) / zone_size_m * float(ZONES_N))
	var v := int((z + zone_size_m * 0.5) / zone_size_m * float(ZONES_N))
	if u < 0 or v < 0 or u >= ZONES_N or v >= ZONES_N:
		return 0
	return _zones[v * ZONES_N + u]

## класс поверхности среза в точке (x=восток, z движка=−север), или −1 вне среза
func _slice_at(x: float, z: float) -> int:
	if _slice.is_empty():
		return -1
	var u := int((x - _slice_cx + _slice_half) / (2.0 * _slice_half) * float(_slice_n))
	# строка 0 = север; data_y = −z
	var v := int((_slice_cy + _slice_half - (-z)) / (2.0 * _slice_half) * float(_slice_n))
	if u < 0 or v < 0 or u >= _slice_n or v >= _slice_n:
		return -1
	return _slice[v * _slice_n + u]

# ------------------------------------------------------------------ куст
## куст = 7 лезвий чистой геометрией (без альфа-текстур: ни сортировки,
## ни просветов). Лезвие — сужающаяся полоса из 3 треугольников с наклоном
## кончика; разнобой высоты/поворота внутри куста зашит в меш.
func _build_clump_mesh() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var rng := RandomNumberGenerator.new()
	rng.seed = 1894
	for b in range(BLADES_PER_CLUMP):
		var yaw := TAU * float(b) / float(BLADES_PER_CLUMP) + rng.randf_range(-0.4, 0.4)
		var off := Vector3(rng.randf_range(-0.11, 0.11), 0.0, rng.randf_range(-0.11, 0.11))
		var hgt := rng.randf_range(0.65, 1.0)
		var lean := rng.randf_range(0.06, 0.22)
		var rot := Basis(Vector3.UP, yaw)
		var w := 0.032
		var p0 := off + rot * Vector3(-w * 0.5, 0.0, 0.0)
		var p1 := off + rot * Vector3(w * 0.5, 0.0, 0.0)
		var mh := hgt * 0.55
		var p2 := off + rot * Vector3(-w * 0.30, mh, lean * 0.35)
		var p3 := off + rot * Vector3(w * 0.30, mh, lean * 0.35)
		var tip := off + rot * Vector3(0.0, hgt, lean)
		_tri(st, p0, p1, p2, 0.0, 0.0, mh)
		_tri(st, p1, p3, p2, 0.0, mh, mh)
		_tri(st, p2, p3, tip, mh, mh, hgt)
	return st.commit()

## UV.y — доля высоты лезвия: ею шейдер ведёт градиент цвета и вес ветра
func _tri(st: SurfaceTool, a: Vector3, b: Vector3, c: Vector3,
		ua: float, ub: float, uc: float) -> void:
	st.set_uv(Vector2(0.0, ua)); st.add_vertex(a)
	st.set_uv(Vector2(0.0, ub)); st.add_vertex(b)
	st.set_uv(Vector2(0.0, uc)); st.add_vertex(c)

# ------------------------------------------------------------------ тайлы
func _process(_delta: float) -> void:
	var cam := get_viewport().get_camera_3d()
	if cam == null or terrain == null:
		return
	var c := Vector2i(int(floorf(cam.global_position.x / TILE_M)),
		int(floorf(cam.global_position.z / TILE_M)))
	if c != _center:
		_center = c
		_refresh_desired()
	if _tiles.is_empty() and not _queue.is_empty():
		# первый заход — весь ковёр сразу (момент загрузки, рывок не виден)
		while not _queue.is_empty():
			_build_tile(_queue.pop_front())
		_report_once()
		return
	for i in range(BUILDS_PER_FRAME):
		if _queue.is_empty():
			_report_once()
			break
		_build_tile(_queue.pop_front())

func _band_of(key: Vector2i) -> int:
	var d := maxi(absi(key.x - _center.x), absi(key.y - _center.y))
	return 0 if d <= NEAR_TILES else 1

func _refresh_desired() -> void:
	var desired: Dictionary = {}
	for tj in range(_center.y - RADIUS_TILES, _center.y + RADIUS_TILES + 1):
		for ti in range(_center.x - RADIUS_TILES, _center.x + RADIUS_TILES + 1):
			var key := Vector2i(ti, tj)
			desired[key] = _band_of(key)
	for key in _tiles.keys():
		if not desired.has(key):
			_drop_tile(key)
	_queue.clear()
	for key in desired:
		if not _tiles.has(key) or _tiles[key]["band"] != desired[key]:
			_queue.append(key)
	# ближние тайлы — первыми: трава у ног не ждёт
	_queue.sort_custom(func(a: Vector2i, b: Vector2i) -> bool:
		return maxi(absi(a.x - _center.x), absi(a.y - _center.y)) \
			< maxi(absi(b.x - _center.x), absi(b.y - _center.y)))

func _drop_tile(key: Vector2i) -> void:
	var t: Dictionary = _tiles[key]
	if t["node"] != null:
		(t["node"] as Node).queue_free()
	clump_count -= t["n"]
	_tiles.erase(key)

## посев тайла: детерминированный хеш от координат тайла — тот же мир всегда
func _build_tile(key: Vector2i) -> void:
	if _tiles.has(key):
		_drop_tile(key)
	var band := _band_of(key)
	var density := CLUMPS_M2_NEAR if band == 0 else CLUMPS_M2_FAR
	var rng := RandomNumberGenerator.new()
	rng.seed = int(key.x) * 73856093 ^ int(key.y) * 19349663
	var attempts := int(TILE_M * TILE_M * density)
	var xforms: Array[Transform3D] = []
	var colors: Array[Color] = []
	for k in range(attempts):
		var x := (float(key.x) + rng.randf()) * TILE_M
		var z := (float(key.y) + rng.randf()) * TILE_M
		# источник посева: ПОЛЕ ЖИЗНИ (реальные условия), иначе — правила зоны
		var life := _life_at(x, z)
		var prob: float
		var base_h: float
		var base_col: Color
		if not life.is_empty():
			prob = life[0]                       # плотность из влаги/света/вида
			base_h = life[1]                     # высота вырастает из условий
			base_col = LIFE_DRY.lerp(LIFE_WET, life[2])   # сочность → цвет
		else:
			var sc := _slice_at(x, z)
			var rule := _slice_rule(sc) if sc >= 0 else _zone_rule(_zone_at(x, z))
			prob = float(rule[0])
			base_h = float(rule[1])
			base_col = rule[2]
		if rng.randf() > prob:
			continue
		if terrain.normal_at(x, z).y < SLOPE_MIN_NY:
			continue
		var h := terrain.height(x, z)
		var hgt := base_h * rng.randf_range(0.72, 1.3)
		var wxz := rng.randf_range(0.8, 1.25)
		var basis := Basis(Vector3.UP, rng.randf() * TAU) \
			* Basis.from_scale(Vector3(wxz, hgt, wxz))
		xforms.append(Transform3D(basis, Vector3(x, h, z)))
		var tone := rng.randf_range(0.82, 1.14)
		colors.append(Color(base_col.r * tone * rng.randf_range(0.9, 1.1),
			base_col.g * tone, base_col.b * tone * rng.randf_range(0.9, 1.1)))
	var node: MultiMeshInstance3D = null
	if not xforms.is_empty():
		var mm := MultiMesh.new()
		mm.transform_format = MultiMesh.TRANSFORM_3D
		mm.use_colors = true
		mm.mesh = _mesh
		mm.instance_count = xforms.size()
		for i in range(xforms.size()):
			mm.set_instance_transform(i, xforms[i])
			mm.set_instance_color(i, colors[i])
		node = MultiMeshInstance3D.new()
		node.multimesh = mm
		node.material_override = _mat
		# тень от каждого лезвия — двойная цена кадра; контакт даёт SSAO
		node.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		add_child(node)
	_tiles[key] = {"node": node, "band": band, "n": xforms.size()}
	clump_count += xforms.size()

func _report_once() -> void:
	if _reported:
		return
	_reported = true
	print("[grass] посев: тайлы %d (±%.0f м), кустов=%d, лезвий=%d, △=%d" % [
		_tiles.size(), (float(RADIUS_TILES) + 0.5) * TILE_M, clump_count,
		clump_count * BLADES_PER_CLUMP,
		clump_count * BLADES_PER_CLUMP * TRIS_PER_BLADE])

func report() -> Dictionary:
	return {"clumps": clump_count, "tiles": _tiles.size(),
		"tris": clump_count * BLADES_PER_CLUMP * TRIS_PER_BLADE}
