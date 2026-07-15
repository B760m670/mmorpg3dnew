extends Node
## Ядро game2 (автолоад «Core»). Три независимые оси настроек + масштабирование.
## На Apple с нашим форком доступен MetalFX (spatial/temporal) — ось «Масштаб».

signal changed

var graphics: String = "balanced"      # smooth / balanced / hd / ultra
var frame_rate: int = 60               # 30 / 60 / 120
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
	frame_rate = int(cf.get_value("gfx", "frame_rate", frame_rate))
	style = cf.get_value("gfx", "style", style)
	scaling = cf.get_value("gfx", "scaling", scaling)
	render_scale = float(cf.get_value("gfx", "render_scale", render_scale))

func save_cfg() -> void:
	var cf := ConfigFile.new()
	cf.set_value("gfx", "graphics", graphics)
	cf.set_value("gfx", "frame_rate", frame_rate)
	cf.set_value("gfx", "style", style)
	cf.set_value("gfx", "scaling", scaling)
	cf.set_value("gfx", "render_scale", render_scale)
	cf.save(PATH)
	apply_frame_rate()
	changed.emit()

func apply_frame_rate() -> void:
	Engine.max_fps = frame_rate

## Масштабирование вьюпорта: MetalFX на Apple (наш форк), иначе билинейно/выкл.
func apply_scaling(vp: Viewport) -> void:
	var mode := scaling
	if mode == "auto":
		mode = "metalfx_temporal" if OS.get_name() in ["iOS", "macOS"] else "off"
	match mode:
		"metalfx_spatial":
			if "SCALING_3D_MODE_METALFX_SPATIAL" in Viewport:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_METALFX_SPATIAL
				vp.scaling_3d_scale = render_scale
		"metalfx_temporal":
			if "SCALING_3D_MODE_METALFX_TEMPORAL" in Viewport:
				vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_METALFX_TEMPORAL
				vp.scaling_3d_scale = render_scale
		"off":
			vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_BILINEAR
			vp.scaling_3d_scale = 1.0
