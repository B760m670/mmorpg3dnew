class_name BuildingPlacer
extends RefCounted
## Расстановка зданий на НЕРОВНОМ рельефе. Крупные памятники (дворец, собор,
## вокзал…) грузятся из GLB по layout. Городская застройка СОБИРАЕТСЯ из
## переиспользуемых элементов (BuildingComposer) — не грузится готовыми примитивами.
## Каждое здание садится по средней высоте пятна + каменный фундамент закрывает
## просветы под углами.

var _world: Node3D
var _data: WorldData
var _kit: ConstructionKit
var _composer: BuildingComposer

func _init(world: Node3D, data: WorldData) -> void:
	_world = world
	_data = data
	_kit = ConstructionKit.new()
	_composer = BuildingComposer.new(_kit)

func build_all() -> void:
	_build_landmarks()
	_build_town()

# --- посадка на грунт + фундамент + коллизия ---
func place_on_ground(node: Node3D, x: float, z: float, rot_deg: float, fw: float, fd: float) -> void:
	var rot := deg_to_rad(rot_deg)
	var hw := fw * 0.5; var hd := fd * 0.5
	var samples: Array[float] = []
	var pts: Array[Vector2] = [Vector2(0, 0), Vector2(hw, hd), Vector2(-hw, hd), Vector2(hw, -hd), Vector2(-hw, -hd),
			Vector2(hw, 0), Vector2(-hw, 0), Vector2(0, hd), Vector2(0, -hd)]
	for c in pts:
		var wx := x + c.x * cos(rot) - c.y * sin(rot)
		var wz := z + c.x * sin(rot) + c.y * cos(rot)
		samples.append(_data.height_at(wx, wz))
	var avg := 0.0; var mn := 1e9
	for hh in samples: avg += hh; mn = minf(mn, hh)
	avg /= samples.size()
	node.position = Vector3(x, avg, z)
	node.rotation.y = rot
	_world.add_child(node)
	_add_foundation(node, fw, fd, avg - mn)

func _add_foundation(node: Node3D, fw: float, fd: float, drop: float) -> void:
	var mi := MeshInstance3D.new()
	var bm := BoxMesh.new()
	var h := drop + 4.5
	bm.size = Vector3(fw * 1.02, h, fd * 1.02)
	mi.mesh = bm
	mi.position = Vector3(0, 0.3 - h * 0.5, 0)
	mi.material_override = _kit.material("stone")
	node.add_child(mi)

func _add_box_collision(node: Node3D, fw: float, fd: float, h: float) -> void:
	var body := StaticBody3D.new()
	var col := CollisionShape3D.new()
	var shp := BoxShape3D.new()
	shp.size = Vector3(fw, h, fd)
	col.shape = shp
	col.position = Vector3(0, h * 0.5, 0)
	body.add_child(col)
	node.add_child(body)

# --- памятники из GLB ---
func _build_landmarks() -> void:
	for b in _data.LY.get("buildings", []):
		var path := "res://world/buildings/" + str(b["file"])
		var packed: PackedScene = load(path)
		if packed == null:
			continue
		var inst := packed.instantiate() as Node3D
		var pos: Array = b["position"]
		var fp: Array = b.get("footprint", [20, 20])
		place_on_ground(inst, float(pos[0]), float(pos[1]), float(b.get("rotation", 0)), float(fp[0]), float(fp[1]))
		_add_box_collision(inst, float(fp[0]), float(fp[1]), float(b.get("height", 12)))

# --- город: дома собираются из переиспользуемых элементов ---
func _build_town() -> void:
	# типы застройки: (материал стен, материал кровли, ширина, глубина, этажей)
	var kinds := [
		["plaster", "roof_tile", 14.0, 10.0, 2],
		["stone", "roof_metal", 12.0, 9.0, 2],
		["brick", "roof_tile", 16.0, 11.0, 3],
	]
	var rng := RandomNumberGenerator.new(); rng.seed = 1894
	var idx := 0
	for blk in _data.LY.get("town", {}).get("blocks", []):
		var c: Array = blk["center"]; var s: Array = blk["size"]
		var rows := int(blk.get("rows", 2))
		var n := int(blk.get("houses", 6))
		var per := int(ceil(float(n) / rows))
		var placed := 0
		for row in range(rows):
			var zc: float = float(c[1]) - float(s[1]) * 0.5 + (row + 0.5) / rows * float(s[1])
			for k in range(per):
				if placed >= n:
					break
				var xc: float = float(c[0]) - float(s[0]) * 0.5 + (k + 0.5) / per * float(s[0])
				var kind: Array = kinds[idx % kinds.size()]
				idx += 1; placed += 1
				var wx := float(kind[2]); var wz := float(kind[3])
				var inst := _composer.compose(wx, wz, int(kind[4]), str(kind[0]), str(kind[1]), 1894 + idx)
				var face := 0.0 if row == 0 else 180.0
				place_on_ground(inst, xc, zc, face + rng.randf_range(-6, 6), wx, wz)
				_add_box_collision(inst, wx, wz, int(kind[4]) * 3.6)
