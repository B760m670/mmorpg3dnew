extends Node
## Глобальные настройки игры (autoload «Settings»). Хранятся в user://settings.cfg.
## Мир читает отсюда качество графики, время суток (положение солнца) и чувствительность.

signal changed

var quality: String = "high"        # high / balanced / performance
var master_volume: float = 0.8
var sensitivity: float = 1.0
var time_of_day: float = 10.0       # часы 0..24 — определяют положение солнца
var selected_map: String = "gatchina"

const PATH := "user://settings.cfg"

const MAPS := {
	"gatchina": {"name": "Гатчина", "year": "1894", "available": true,
		"scene": "res://scenes/world.tscn",
		"desc": "Императорская резиденция: дворец, парки, три озера, город."},
	"peterburg": {"name": "Санкт-Петербург", "year": "1894", "available": false,
		"scene": "", "desc": "Столица империи. В разработке."},
	"tsarskoe": {"name": "Царское Село", "year": "1894", "available": false,
		"scene": "", "desc": "Екатерининский и Александровский дворцы. В разработке."},
	"livadia": {"name": "Ливадия", "year": "1894", "available": false,
		"scene": "", "desc": "Крымская резиденция у моря. В разработке."},
}

func _ready() -> void:
	load_settings()

func load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	quality = cf.get_value("gfx", "quality", quality)
	master_volume = cf.get_value("audio", "master_volume", master_volume)
	sensitivity = cf.get_value("control", "sensitivity", sensitivity)
	time_of_day = cf.get_value("world", "time_of_day", time_of_day)
	selected_map = cf.get_value("world", "selected_map", selected_map)
	_apply_volume()

func save_settings() -> void:
	var cf := ConfigFile.new()
	cf.set_value("gfx", "quality", quality)
	cf.set_value("audio", "master_volume", master_volume)
	cf.set_value("control", "sensitivity", sensitivity)
	cf.set_value("world", "time_of_day", time_of_day)
	cf.set_value("world", "selected_map", selected_map)
	cf.save(PATH)
	_apply_volume()
	changed.emit()

func _apply_volume() -> void:
	var db := linear_to_db(clampf(master_volume, 0.0001, 1.0))
	AudioServer.set_bus_volume_db(0, db)

# положение солнца из времени суток: возвышение и азимут
func sun_rotation_deg() -> Vector3:
	var t := time_of_day
	var day := clampf((t - 6.0) / 12.0, 0.0, 1.0)   # 0 на рассвете, 1 на закате
	var elev := sin(day * PI) * 58.0                 # 0° у горизонта, 58° в полдень
	if t < 6.0 or t > 18.0:
		elev = -6.0                                  # ниже горизонта — ночь
	var az := lerpf(-105.0, -20.0, day)              # солнце идёт с востока на запад
	return Vector3(-elev, az, 0.0)

func is_night() -> bool:
	return time_of_day < 6.2 or time_of_day > 17.8
