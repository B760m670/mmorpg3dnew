extends Node
## Глобальные настройки игры (autoload «Settings»). Хранятся в user://settings.cfg.
## Мир читает отсюда качество графики, время суток (положение солнца) и чувствительность.

signal changed

# --- три независимые оси настроек (как в PUBG Mobile) ---
var graphics: String = "balanced"    # smooth / balanced / hd / ultra — ДЕТАЛИЗАЦИЯ
var frame_rate: int = 60             # 30 / 40 / 60 / 90 / 120 — ЧАСТОТА КАДРОВ
var style: String = "classic"        # classic / colorful / realistic / soft / movie — СТИЛЬ
var adaptive_res: bool = true        # адаптивное разрешение: держит FPS, не грея телефон

# наборы вариантов для меню (ключ -> подпись)
const GRAPHICS_OPTS := {"smooth": "Плавно", "balanced": "Баланс", "hd": "HD", "ultra": "Ультра HD"}
const FRAME_OPTS := {30: "Эконом", 40: "Средне", 60: "Высоко", 90: "Ультра", 120: "Экстрим 120"}
const STYLE_OPTS := {"classic": "Классический", "colorful": "Насыщенный",
	"realistic": "Реалистичный", "soft": "Мягкий", "movie": "Киношный"}

var master_volume: float = 0.8
var sensitivity: float = 1.0        # чувствительность камеры (свайп)
var gyro_enabled: bool = false      # управление камерой гироскопом
var gyro_sensitivity: float = 1.0   # чувствительность гироскопа
var invert_y: bool = false          # инверсия вертикали камеры
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
	# частота кадров из настроек; на ProMotion iPhone до 120 раскрывается при наличии
	# ключа CADisableMinimumFrameDurationOnPhone в Info.plist (см. export_presets).
	Engine.max_fps = frame_rate

func load_settings() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	graphics = cf.get_value("gfx", "graphics", graphics)
	frame_rate = int(cf.get_value("gfx", "frame_rate", frame_rate))
	style = cf.get_value("gfx", "style", style)
	adaptive_res = cf.get_value("gfx", "adaptive_res", adaptive_res)
	# миграция со старой одиночной настройки «quality»
	var old_q = cf.get_value("gfx", "quality", null)
	if old_q != null and not cf.has_section_key("gfx", "graphics"):
		match old_q:
			"performance": graphics = "smooth"
			"high": graphics = "ultra"
			_: graphics = "balanced"
	master_volume = cf.get_value("audio", "master_volume", master_volume)
	sensitivity = cf.get_value("control", "sensitivity", sensitivity)
	gyro_enabled = cf.get_value("control", "gyro_enabled", gyro_enabled)
	gyro_sensitivity = cf.get_value("control", "gyro_sensitivity", gyro_sensitivity)
	invert_y = cf.get_value("control", "invert_y", invert_y)
	time_of_day = cf.get_value("world", "time_of_day", time_of_day)
	selected_map = cf.get_value("world", "selected_map", selected_map)
	_apply_volume()

func save_settings() -> void:
	var cf := ConfigFile.new()
	cf.set_value("gfx", "graphics", graphics)
	cf.set_value("gfx", "frame_rate", frame_rate)
	cf.set_value("gfx", "style", style)
	cf.set_value("gfx", "adaptive_res", adaptive_res)
	cf.set_value("audio", "master_volume", master_volume)
	cf.set_value("control", "sensitivity", sensitivity)
	cf.set_value("control", "gyro_enabled", gyro_enabled)
	cf.set_value("control", "gyro_sensitivity", gyro_sensitivity)
	cf.set_value("control", "invert_y", invert_y)
	cf.set_value("world", "time_of_day", time_of_day)
	cf.set_value("world", "selected_map", selected_map)
	cf.save(PATH)
	_apply_volume()
	Engine.max_fps = frame_rate
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
