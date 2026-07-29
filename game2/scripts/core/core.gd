extends Node
## Ядро game2 (автолоад «Core»). Три независимые оси настроек + масштабирование.
## На Apple с нашим форком доступен MetalFX (spatial/temporal) — ось «Масштаб».

signal changed

var graphics: String = "smooth"        # smooth / balanced / hd / ultra
var frame_rate: int = 90               # 0 = АВТО (максимум экрана) / 30 / 60 / 90 / 120
var style: String = "classic"          # тонемап/цветокор — только вид
var scaling: String = "auto"           # auto / off / metalfx_spatial / metalfx_temporal
var render_scale: float = 0.77         # внутренний масштаб при апскейле

const PATH := "user://core.cfg"

func _ready() -> void:
	load_cfg()
	apply_frame_rate()

func load_cfg() -> void:
	var cf := ConfigFile.new()
	if cf.load(PATH) != OK:
		return
	graphics = cf.get_value("gfx", "graphics", graphics)
	# ключ v2: старые конфиги хранили жёсткие 60 — теперь по умолчанию АВТО
	frame_rate = int(cf.get_value("gfx", "frame_rate_v2", frame_rate))
	style = cf.get_value("gfx", "style", style)
	scaling = cf.get_value("gfx", "scaling", scaling)
	render_scale = float(cf.get_value("gfx", "render_scale", render_scale))

func save_cfg() -> void:
	var cf := ConfigFile.new()
	cf.set_value("gfx", "graphics", graphics)
	cf.set_value("gfx", "frame_rate_v2", frame_rate)
	cf.set_value("gfx", "style", style)
	cf.set_value("gfx", "scaling", scaling)
	cf.set_value("gfx", "render_scale", render_scale)
	cf.save(PATH)
	apply_frame_rate()
	changed.emit()

## АВТО: игра сама выжимает максимум экрана устройства (ProMotion 120);
## в режиме энергосбережения iOS движок сам вернёт 60. Явное значение
## (30/60/90/120) — жёсткий лимит для будущего экрана настроек.
func apply_frame_rate() -> void:
	if frame_rate <= 0:
		var hz := DisplayServer.screen_get_refresh_rate()
		Engine.max_fps = int(round(hz)) if hz > 0.0 else 0
	else:
		Engine.max_fps = frame_rate

func frame_rate_label() -> String:
	return ("авто·%d" % Engine.max_fps) if frame_rate <= 0 else str(frame_rate)

## ЧТО ВКЛЮЧЕНО ПРИ ЭТОМ КАЧЕСТВЕ — один источник правды для всей сцены.
##
## ЗАЧЕМ ЭТО ЗДЕСЬ. Ось качества в игре была, но сцена её не читала: в
## light_stage стояли жёсткие «const ENABLE_GI := true» и так далее. Пока
## устройство шло на мобильном рендере, это было незаметно — там половина этих
## эффектов не работает вовсе. Как только рендер стал forward_plus, все они
## включились по-настоящему и кадр упал до 13.
##
## ЦЕНА КАЖДОГО (почему выключается именно это):
##   SDFGI — самый дорогой в Godot: объёмная сетка вокруг камеры, у нас 5
##     каскадов по 1 м на 1024 м. В ОТКРЫТОМ поле под небом он почти ничего не
##     добавляет: рассеянный свет там и так от купола неба. Его место — внутри
##     помещений и в тени зданий.
##   SSIL — полноэкранный проход с трассировкой по глубине.
##   SSAO — ещё один полноэкранный проход.
##   render_scale — квадратично: 0.60 против 0.77 это в 1.65 раза меньше
##     пикселей, а MetalFX temporal возвращает резкость обратно.
##   ssr_steps — шаги трассировки отражений воды, по одной выборке глубины
##     на шаг, только на пикселях воды.
func gfx() -> Dictionary:
	match graphics:
		"ultra":
			return {"sdfgi": true, "ssil": true, "ssao": true, "glow": true,
				"scale": 1.00, "ssr_steps": 24, "shadow": 4096, "shadow_far": 160.0}
		"hd":
			return {"sdfgi": false, "ssil": true, "ssao": true, "glow": true,
				"scale": 0.80, "ssr_steps": 20, "shadow": 4096, "shadow_far": 140.0}
		"balanced":
			return {"sdfgi": false, "ssil": false, "ssao": true, "glow": true,
				"scale": 0.70, "ssr_steps": 14, "shadow": 2048, "shadow_far": 120.0}
		_:   # smooth — цель 90 кадров
			return {"sdfgi": false, "ssil": false, "ssao": false, "glow": true,
				"scale": 0.60, "ssr_steps": 8, "shadow": 2048, "shadow_far": 100.0}

## Масштабирование вьюпорта: MetalFX на Apple (наш форк), иначе билинейно/выкл.
func apply_scaling(vp: Viewport) -> void:
	var mode := scaling
	if mode == "auto":
		mode = "metalfx_temporal" if OS.get_name() in ["iOS", "macOS"] else "off"
	var sc: float = float(gfx()["scale"])
	match mode:
		"metalfx_spatial":
			if "SCALING_3D_MODE_METALFX_SPATIAL" in Viewport:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_METALFX_SPATIAL
				vp.scaling_3d_scale = sc
		"metalfx_temporal":
			if "SCALING_3D_MODE_METALFX_TEMPORAL" in Viewport:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_METALFX_TEMPORAL
				vp.scaling_3d_scale = sc
		"off":
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
			vp.scaling_3d_scale = 1.0
