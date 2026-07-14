extends Node3D
## Главное меню (сцена по умолчанию). Современный стиль: живой 3D-фон с
## физическим небом и дворцом, заголовок, кнопки, выбор карты, настройки.

# палитра
const BG := Color(0.06, 0.07, 0.09)
const PANEL := Color(0.10, 0.11, 0.13, 0.94)
const CARD := Color(0.14, 0.15, 0.18, 0.96)
const ACCENT := Color(0.84, 0.69, 0.34)      # имперское золото
const ACCENT2 := Color(0.66, 0.16, 0.19)     # багрянец
const TEXT := Color(0.93, 0.94, 0.96)
const MUTED := Color(0.62, 0.65, 0.70)

var cam: Camera3D
var cam_angle := 0.0
var ui: CanvasLayer
var main_col: Control
var map_panel: Control
var settings_panel: Control

func _ready() -> void:
	_build_background()
	_build_ui()

# ---------- живой 3D-фон ----------
func _build_background() -> void:
	var sky_mat := ShaderMaterial.new()
	sky_mat.shader = load("res://shaders/sky.gdshader")
	var sky := Sky.new(); sky.sky_material = sky_mat; sky.radiance_size = Sky.RADIANCE_SIZE_64
	sky.process_mode = Sky.PROCESS_MODE_REALTIME
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY; env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.5
	env.tonemap_mode = Environment.TONE_MAPPER_ACES
	env.tonemap_exposure = 0.95
	env.ssao_enabled = true
	env.glow_enabled = true; env.glow_intensity = 0.4
	env.fog_enabled = true; env.fog_density = 0.0016
	env.fog_light_color = Color(0.72, 0.78, 0.86); env.fog_aerial_perspective = 0.5
	var we := WorldEnvironment.new(); we.environment = env; add_child(we)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-24, -60, 0)   # утреннее солнце для эффектного фона
	sun.light_energy = 3.2; sun.light_color = Color(1.0, 0.93, 0.82)
	sun.shadow_enabled = true
	add_child(sun)

	# земля
	var ground := MeshInstance3D.new()
	var pm := PlaneMesh.new(); pm.size = Vector2(1200, 1200)
	var gm := StandardMaterial3D.new()
	gm.albedo_color = Color(0.20, 0.25, 0.14); gm.roughness = 0.95
	pm.material = gm; ground.mesh = pm; add_child(ground)

	# дворец вдали
	var pal: PackedScene = load("res://world/buildings/palace.glb")
	if pal != null:
		var inst := pal.instantiate() as Node3D
		inst.position = Vector3(0, 0, -70)
		add_child(inst)

	cam = Camera3D.new(); cam.fov = 55; cam.far = 2000.0
	cam.position = Vector3(90, 26, 40); cam.look_at(Vector3(0, 12, -70), Vector3.UP)
	cam.current = true
	add_child(cam)

func _process(delta: float) -> void:
	if cam == null: return
	cam_angle += delta * 0.03
	var r := 120.0
	cam.position = Vector3(sin(cam_angle) * r, 24.0 + sin(cam_angle * 0.5) * 3.0, cos(cam_angle) * r - 10.0)
	cam.look_at(Vector3(0, 13, -70), Vector3.UP)

# ---------- стиль ----------
func _sb(color: Color, border := 0.0, bcol := ACCENT, radius := 8) -> StyleBoxFlat:
	var s := StyleBoxFlat.new()
	s.bg_color = color
	s.corner_radius_top_left = radius; s.corner_radius_top_right = radius
	s.corner_radius_bottom_left = radius; s.corner_radius_bottom_right = radius
	s.content_margin_left = 18; s.content_margin_right = 18
	s.content_margin_top = 12; s.content_margin_bottom = 12
	if border > 0.0:
		s.border_width_left = int(border); s.border_width_right = int(border)
		s.border_width_top = int(border); s.border_width_bottom = int(border)
		s.border_color = bcol
	return s

func _button(text: String, big := false) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", 26 if big else 20)
	b.add_theme_color_override("font_color", TEXT)
	b.add_theme_color_override("font_hover_color", ACCENT)
	b.add_theme_color_override("font_pressed_color", ACCENT)
	b.add_theme_stylebox_override("normal", _sb(Color(0.13, 0.14, 0.17, 0.9)))
	b.add_theme_stylebox_override("hover", _sb(Color(0.18, 0.19, 0.23, 0.96), 2.0, ACCENT))
	b.add_theme_stylebox_override("pressed", _sb(Color(0.10, 0.11, 0.13, 0.98), 2.0, ACCENT2))
	b.add_theme_stylebox_override("focus", _sb(Color(0, 0, 0, 0)))
	b.custom_minimum_size = Vector2(300 if big else 260, 60 if big else 52)
	return b

func _label(text: String, size: int, color := TEXT) -> Label:
	var l := Label.new()
	l.text = text; l.add_theme_font_size_override("font_size", size)
	l.add_theme_color_override("font_color", color)
	return l

# ---------- интерфейс ----------
func _build_ui() -> void:
	ui = CanvasLayer.new(); add_child(ui)

	# лёгкое затемнение слева для читаемости
	var grad := ColorRect.new()
	grad.color = Color(0, 0, 0, 0.32)
	grad.anchor_right = 1.0; grad.anchor_bottom = 1.0
	ui.add_child(grad)

	main_col = Control.new()
	main_col.anchor_right = 1.0; main_col.anchor_bottom = 1.0
	ui.add_child(main_col)

	var title := _label("ИМПЕРИЯ", 76)
	title.add_theme_color_override("font_color", TEXT)
	title.position = Vector2(64, 70)
	main_col.add_child(title)
	var year := _label("1894", 40, ACCENT)
	year.position = Vector2(66, 158)
	main_col.add_child(year)
	var sub := _label("Открытый мир · Россия конца XIX века", 20, MUTED)
	sub.position = Vector2(68, 210)
	main_col.add_child(sub)

	var vb := VBoxContainer.new()
	vb.position = Vector2(64, 300)
	vb.add_theme_constant_override("separation", 14)
	main_col.add_child(vb)

	var play := _button("Играть", true)
	play.pressed.connect(_start_game); vb.add_child(play)
	var maps := _button("Выбор карты")
	maps.pressed.connect(func() -> void: _show(map_panel)); vb.add_child(maps)
	var settings := _button("Настройки")
	settings.pressed.connect(func() -> void: _show(settings_panel)); vb.add_child(settings)
	var quit := _button("Выход")
	quit.pressed.connect(func() -> void: get_tree().quit()); vb.add_child(quit)

	var foot := _label("Николай II · Гатчина · Godot Forward+", 15, MUTED)
	foot.anchor_top = 1.0; foot.anchor_bottom = 1.0
	foot.position = Vector2(64, -40)
	main_col.add_child(foot)

	_build_map_panel()
	_build_settings_panel()

func _dim_overlay() -> Control:
	var c := Control.new()
	c.anchor_right = 1.0; c.anchor_bottom = 1.0
	var d := ColorRect.new(); d.color = Color(0, 0, 0, 0.6)
	d.anchor_right = 1.0; d.anchor_bottom = 1.0
	c.add_child(d)
	return c

func _panel_box(w: int, h: int, title: String) -> Array:
	var root := _dim_overlay(); root.visible = false; ui.add_child(root)
	var pc := PanelContainer.new()
	pc.add_theme_stylebox_override("panel", _sb(PANEL, 1.0, Color(0.3, 0.3, 0.34), 14))
	pc.custom_minimum_size = Vector2(w, h)
	pc.anchor_left = 0.5; pc.anchor_top = 0.5; pc.anchor_right = 0.5; pc.anchor_bottom = 0.5
	pc.offset_left = -w / 2; pc.offset_top = -h / 2; pc.offset_right = w / 2; pc.offset_bottom = h / 2
	root.add_child(pc)
	var vb := VBoxContainer.new(); vb.add_theme_constant_override("separation", 16)
	pc.add_child(vb)
	var head := _label(title, 34, ACCENT); vb.add_child(head)
	var sep := HSeparator.new(); vb.add_child(sep)
	return [root, vb]

func _show(p: Control) -> void:
	main_col.visible = false
	map_panel.visible = false
	settings_panel.visible = false
	p.visible = true

func _back() -> void:
	map_panel.visible = false
	settings_panel.visible = false
	main_col.visible = true

# ---------- выбор карты ----------
func _build_map_panel() -> void:
	var r := _panel_box(720, 560, "Выбор карты")
	map_panel = r[0]; var vb: VBoxContainer = r[1]
	var grid := GridContainer.new(); grid.columns = 2
	grid.add_theme_constant_override("h_separation", 14)
	grid.add_theme_constant_override("v_separation", 14)
	vb.add_child(grid)
	for id in Settings.MAPS.keys():
		grid.add_child(_map_card(id, Settings.MAPS[id]))
	var back := _button("Назад")
	back.pressed.connect(_back); vb.add_child(back)

func _map_card(id: String, m: Dictionary) -> Control:
	var pc := PanelContainer.new()
	pc.add_theme_stylebox_override("panel", _sb(CARD, 1.0, Color(0.28, 0.29, 0.33), 10))
	pc.custom_minimum_size = Vector2(330, 150)
	var vb := VBoxContainer.new(); vb.add_theme_constant_override("separation", 6)
	pc.add_child(vb)
	var t := _label(m["name"] + "  " + m["year"], 24)
	vb.add_child(t)
	var d := _label(m["desc"], 15, MUTED)
	d.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	d.custom_minimum_size = Vector2(300, 48)
	vb.add_child(d)
	if m["available"]:
		var pb := _button("Играть")
		pb.custom_minimum_size = Vector2(150, 44)
		pb.pressed.connect(func() -> void:
			Settings.selected_map = id; Settings.save_settings(); _start_game())
		vb.add_child(pb)
	else:
		var soon := _label("Скоро", 16, ACCENT2)
		vb.add_child(soon)
	return pc

# ---------- настройки ----------
func _build_settings_panel() -> void:
	var r := _panel_box(720, 660, "Настройки")
	settings_panel = r[0]; var outer: VBoxContainer = r[1]

	# прокручиваемая область — вмещает все настройки на любом экране
	var scroll := ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(680, 470)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	outer.add_child(scroll)
	var vb := VBoxContainer.new(); vb.add_theme_constant_override("separation", 14)
	vb.custom_minimum_size = Vector2(660, 0)
	scroll.add_child(vb)

	# --- три оси как в PUBG: Графика (детализация) / Частота кадров / Стиль ---
	vb.add_child(_option_row("Графика", Settings.GRAPHICS_OPTS, Settings.graphics,
		func(k) -> void: Settings.graphics = k))
	vb.add_child(_option_row("Частота кадров", Settings.FRAME_OPTS, Settings.frame_rate,
		func(k) -> void: Settings.frame_rate = int(k)))
	vb.add_child(_option_row("Стиль", Settings.STYLE_OPTS, Settings.style,
		func(k) -> void: Settings.style = k))
	vb.add_child(_toggle_row("Адаптивное разрешение (держит FPS)", Settings.adaptive_res,
		func(on: bool) -> void: Settings.adaptive_res = on))

	# --- Звук ---
	vb.add_child(_slider_row("Громкость", 0.0, 1.0, Settings.master_volume, 0.01,
		func(v: float) -> void: Settings.master_volume = v))

	# --- Управление ---
	vb.add_child(_label("Управление", 20, ACCENT))
	vb.add_child(_slider_row("Чувствительность камеры", 0.3, 2.5, Settings.sensitivity, 0.05,
		func(v: float) -> void: Settings.sensitivity = v))
	vb.add_child(_toggle_row("Инверсия вертикали", Settings.invert_y,
		func(on: bool) -> void: Settings.invert_y = on))
	vb.add_child(_toggle_row("Гироскоп (наклон устройства)", Settings.gyro_enabled,
		func(on: bool) -> void: Settings.gyro_enabled = on))
	vb.add_child(_slider_row("Чувствительность гироскопа", 0.2, 3.0, Settings.gyro_sensitivity, 0.05,
		func(v: float) -> void: Settings.gyro_sensitivity = v))

	# --- Мир ---
	vb.add_child(_label("Мир", 20, ACCENT))
	var tod_lbl := _label("Время суток: %02d:00" % int(Settings.time_of_day), 18, MUTED)
	vb.add_child(tod_lbl)
	vb.add_child(_slider_row("", 0.0, 24.0, Settings.time_of_day, 0.5,
		func(v: float) -> void:
			Settings.time_of_day = v
			tod_lbl.text = "Время суток: %02d:00" % int(v)))

	# кнопки (вне прокрутки, всегда видны)
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 14)
	outer.add_child(row)
	var apply := _button("Применить")
	apply.pressed.connect(func() -> void: Settings.save_settings(); _back())
	row.add_child(apply)
	var back := _button("Назад")
	back.pressed.connect(func() -> void: Settings.load_settings(); _back())
	row.add_child(back)

# ряд взаимоисключающих вариантов (одна ось настроек) с переносом строк
func _option_row(title: String, opts: Dictionary, current: Variant, cb: Callable) -> Control:
	var vb := VBoxContainer.new(); vb.add_theme_constant_override("separation", 6)
	vb.add_child(_label(title, 20, ACCENT))
	var flow := HFlowContainer.new()
	flow.add_theme_constant_override("h_separation", 8)
	flow.add_theme_constant_override("v_separation", 8)
	var btns := {}
	for key in opts.keys():
		var b := _button(str(opts[key])); b.custom_minimum_size = Vector2(150, 44)
		b.add_theme_font_size_override("font_size", 18)
		b.toggle_mode = true; b.button_pressed = (key == current)
		btns[key] = b
		b.pressed.connect(func() -> void:
			for k in btns: btns[k].button_pressed = (k == key)
			cb.call(key))
		flow.add_child(b)
	vb.add_child(flow)
	return vb

# строка-переключатель вкл/выкл
func _toggle_row(name: String, val: bool, cb: Callable) -> Control:
	var row := HBoxContainer.new(); row.add_theme_constant_override("separation", 14)
	var l := _label(name, 18, MUTED); l.custom_minimum_size = Vector2(420, 0)
	row.add_child(l)
	var b := _button("Вкл" if val else "Выкл")
	b.custom_minimum_size = Vector2(120, 44)
	b.toggle_mode = true; b.button_pressed = val
	b.toggled.connect(func(on: bool) -> void:
		b.text = "Вкл" if on else "Выкл"; cb.call(on))
	row.add_child(b)
	return row

func _slider_row(name: String, lo: float, hi: float, val: float, step: float, cb: Callable) -> Control:
	var vb := VBoxContainer.new(); vb.add_theme_constant_override("separation", 4)
	if name != "":
		vb.add_child(_label(name, 18, MUTED))
	var s := HSlider.new()
	s.min_value = lo; s.max_value = hi; s.step = step; s.value = val
	s.custom_minimum_size = Vector2(600, 28)
	s.add_theme_color_override("font_color", TEXT)
	s.value_changed.connect(func(v: float) -> void: cb.call(v))
	vb.add_child(s)
	return vb

# ---------- запуск ----------
func _start_game() -> void:
	var m: Dictionary = Settings.MAPS.get(Settings.selected_map, {})
	var scene: String = m.get("scene", "res://scenes/world.tscn")
	if scene == "":
		scene = "res://scenes/world.tscn"
	get_tree().change_scene_to_file(scene)
