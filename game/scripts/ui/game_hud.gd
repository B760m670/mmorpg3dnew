class_name GameHUD
extends CanvasLayer
## Игровой HUD: заголовок, статус, кнопки (меню/карта/бег), джойстик, прыжок.
## Каждая кнопка — свой обработчик, наружу отдаёт сигналы; контроллер мира
## подписывается и не знает деталей вёрстки.

signal menu_pressed
signal map_pressed
signal run_toggled(on: bool)
signal jump_pressed

var joystick: Control
var status_label: Label

func build() -> void:
	var title := Label.new()
	title.text = "ГАТЧИНА • 1894"
	title.add_theme_font_size_override("font_size", 26)
	title.position = Vector2(28, 16)
	add_child(title)

	status_label = Label.new()
	status_label.text = "Открытый мир"
	status_label.add_theme_font_size_override("font_size", 15)
	status_label.position = Vector2(28, 50)
	add_child(status_label)

	var vbox := VBoxContainer.new()
	vbox.anchor_left = 1.0; vbox.anchor_right = 1.0
	vbox.offset_left = -220; vbox.offset_right = -24; vbox.offset_top = 16
	vbox.add_theme_constant_override("separation", 12)
	add_child(vbox)

	var menu_btn := UiKit.button("☰ Меню")
	menu_btn.pressed.connect(func() -> void: menu_pressed.emit())
	vbox.add_child(menu_btn)

	var map_btn := UiKit.button("🗺 Карта")
	map_btn.pressed.connect(func() -> void: map_pressed.emit())
	vbox.add_child(map_btn)

	var run_btn := UiKit.button("Бег")
	run_btn.toggle_mode = true
	run_btn.toggled.connect(func(on: bool) -> void: run_toggled.emit(on))
	vbox.add_child(run_btn)

	joystick = load("res://scripts/joystick.gd").new()
	joystick.anchor_top = 1.0; joystick.anchor_bottom = 1.0
	joystick.offset_left = 48; joystick.offset_top = -320
	joystick.offset_right = 48 + 250; joystick.offset_bottom = -70
	add_child(joystick)

	var jump_btn := UiKit.button("Прыжок", 26)
	jump_btn.anchor_left = 1.0; jump_btn.anchor_right = 1.0
	jump_btn.anchor_top = 1.0; jump_btn.anchor_bottom = 1.0
	jump_btn.offset_left = -230; jump_btn.offset_right = -48
	jump_btn.offset_top = -180; jump_btn.offset_bottom = -84
	jump_btn.pressed.connect(func() -> void: jump_pressed.emit())
	add_child(jump_btn)
