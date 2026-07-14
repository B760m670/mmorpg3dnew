class_name WorldData
extends RefCounted
## Слой ДАННЫХ мира: layout.json + карта высот и все запросы к ним.
## Ни одна геометрия здесь не строится — только «истина» о мире (высота, тип
## грунта, попадание в озеро/здание). Строители (builder-модули) читают отсюда.

var LY: Dictionary = {}              # layout.json
var _h := PackedFloat32Array()       # высотная карта (res*res)
var _hres := 0
var _hsize := 1800.0

func size() -> float:
	return _hsize

func spawn_xz() -> Vector2:
	var sp: Array = LY.get("spawn", {}).get("position", [40, 90])
	return Vector2(float(sp[0]), float(sp[1]))

func spawn_heading() -> float:
	return float(LY.get("spawn", {}).get("heading", 200))

func load_all() -> void:
	var f := FileAccess.open("res://world/gatchina/layout.json", FileAccess.READ)
	if f != null:
		LY = JSON.parse_string(f.get_as_text())
	var hf := FileAccess.open("res://world/gatchina/heights.json", FileAccess.READ)
	if hf != null:
		var d: Dictionary = JSON.parse_string(hf.get_as_text())
		_hres = int(d["res"]); _hsize = float(d["size"])
		for v in d["h"]:
			_h.append(float(v))

# билинейная выборка высоты рельефа в мировой точке (X — восток, Z — юг)
func height_at(x: float, z: float) -> float:
	if _hres == 0:
		return 0.0
	var half := _hsize * 0.5
	var fx: float = clampf((x + half) / _hsize, 0.0, 1.0) * (_hres - 1)
	var fz: float = clampf((z + half) / _hsize, 0.0, 1.0) * (_hres - 1)
	var i0 := int(fx); var j0 := int(fz)
	var i1: int = mini(i0 + 1, _hres - 1); var j1: int = mini(j0 + 1, _hres - 1)
	var tx := fx - i0; var tz := fz - j0
	var h00 := _h[j0 * _hres + i0]; var h10 := _h[j0 * _hres + i1]
	var h01 := _h[j1 * _hres + i0]; var h11 := _h[j1 * _hres + i1]
	return lerpf(lerpf(h00, h10, tx), lerpf(h01, h11, tx), tz)

# доступ к карте высот для строителя рельефа (сырые значения узлов)
func heights_res() -> int:
	return _hres

func height_node(i: int, j: int) -> float:
	return _h[j * _hres + i]

# расстояние от точки до отрезка (для покраски дорог)
func seg_dist(px: float, pz: float, ax: float, az: float, bx: float, bz: float) -> float:
	var vx := bx - ax; var vz := bz - az
	var wx := px - ax; var wz := pz - az
	var t: float = clampf((wx * vx + wz * vz) / (vx * vx + vz * vz + 1e-6), 0.0, 1.0)
	var dx := px - (ax + t * vx); var dz := pz - (az + t * vz)
	return sqrt(dx * dx + dz * dz)

# вес типов грунта в точке: R=луг, G=лесная подстилка, B=тропа, A=пашня/огород
func ground_color(x: float, z: float) -> Color:
	var g := 0.0
	for fr in LY.get("forests", []):
		var c: Array = fr["center"]; var r: Array = fr["radius"]
		var d := sqrt(pow((x - float(c[0])) / float(r[0]), 2.0) + pow((z - float(c[1])) / float(r[1]), 2.0))
		if d < 1.05:
			g = maxf(g, clampf((1.05 - d) / 0.3, 0.0, 1.0))
	var b := 0.0
	for rd in LY.get("roads", []):
		var pts: Array = rd["points"]; var hw := float(rd["width"]) * 0.5 + 1.0
		var dm := 1e9
		for i in range(pts.size() - 1):
			dm = minf(dm, seg_dist(x, z, float(pts[i][0]), float(pts[i][1]), float(pts[i + 1][0]), float(pts[i + 1][1])))
		if dm < hw + 3.0:
			b = maxf(b, clampf((hw + 3.0 - dm) / 4.0, 0.0, 1.0))
	var a := 0.0
	for zone in (LY.get("fields", []) + LY.get("gardens", [])):
		var c2: Array = zone["center"]; var s2: Array = zone["size"]
		var fx: float = 1.0 - clampf((absf(x - float(c2[0])) - float(s2[0]) * 0.35) / (float(s2[0]) * 0.15), 0.0, 1.0)
		var fz: float = 1.0 - clampf((absf(z - float(c2[1])) - float(s2[1]) * 0.35) / (float(s2[1]) * 0.15), 0.0, 1.0)
		a = maxf(a, fx * fz)
	var r: float = maxf(0.0, 1.0 - g - b - a)
	return Color(r, g, b, a)

func in_lake(x: float, z: float) -> bool:
	for lk in LY.get("lakes", []):
		var c: Array = lk["center"]; var r: Array = lk["radius"]
		var d := pow((x - float(c[0])) / float(r[0]), 2.0) + pow((z - float(c[1])) / float(r[1]), 2.0)
		if d < 1.15:
			return true
	return false

func near_building(x: float, z: float, margin: float) -> bool:
	for b in LY.get("buildings", []):
		var p: Array = b["position"]; var fp: Array = b.get("footprint", [20, 20])
		if absf(x - float(p[0])) < float(fp[0]) * 0.5 + margin and absf(z - float(p[1])) < float(fp[1]) * 0.5 + margin:
			return true
	return false
