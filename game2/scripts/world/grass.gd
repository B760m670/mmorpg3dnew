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
const CLUMPS_M2_NEAR := 1.0          # кустов на м² вблизи
const CLUMPS_M2_FAR := 0.35
const BLADES_PER_CLUMP := 7
const TRIS_PER_BLADE := 3
const BUILDS_PER_FRAME := 4          # амортизация достройки на ходу (без рывков)
const SLOPE_MIN_NY := 0.82           # круче ~35° — голый грунт (как в шейдере земли)

const ZONES_PATH := "res://assets/dem/zones_1024.bin"
const ZONES_N := 1024

var terrain: Terrain
var zone_size_m := 12288.0
var clump_count: int = 0

var _zones: PackedByteArray
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

func _ready() -> void:
	var f := FileAccess.open(ZONES_PATH, FileAccess.READ)
	if f != null:
		_zones = f.get_buffer(ZONES_N * ZONES_N)
	if _zones.size() != ZONES_N * ZONES_N:
		_zones = PackedByteArray()
		push_warning("[grass] нет карты зон — вся трава по правилу луга")
	_mesh = _build_clump_mesh()
	_mat = ShaderMaterial.new()
	_mat.shader = load("res://shaders/world/grass.gdshader")

func _zone_at(x: float, z: float) -> int:
	if _zones.is_empty():
		return 0
	var u := int((x + zone_size_m * 0.5) / zone_size_m * float(ZONES_N))
	var v := int((z + zone_size_m * 0.5) / zone_size_m * float(ZONES_N))
	if u < 0 or v < 0 or u >= ZONES_N or v >= ZONES_N:
		return 0
	return _zones[v * ZONES_N + u]

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
		var rule := _zone_rule(_zone_at(x, z))
		if rng.randf() > float(rule[0]):
			continue
		if terrain.normal_at(x, z).y < SLOPE_MIN_NY:
			continue
		var h := terrain.height(x, z)
		var hgt := float(rule[1]) * rng.randf_range(0.72, 1.3)
		var wxz := rng.randf_range(0.8, 1.25)
		var basis := Basis(Vector3.UP, rng.randf() * TAU) \
			* Basis.from_scale(Vector3(wxz, hgt, wxz))
		xforms.append(Transform3D(basis, Vector3(x, h, z)))
		var c: Color = rule[2]
		var tone := rng.randf_range(0.82, 1.14)
		colors.append(Color(c.r * tone * rng.randf_range(0.9, 1.1),
			c.g * tone, c.b * tone * rng.randf_range(0.9, 1.1)))
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
