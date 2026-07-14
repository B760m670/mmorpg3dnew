class_name UiKit
extends RefCounted
## Переиспользуемые элементы интерфейса. Одна фабрика кнопок на все экраны —
## единый стиль, никакого дублирования кода кнопок по файлам.

static func button(text: String, font_size: int = 24) -> Button:
	var b := Button.new()
	b.text = text
	b.add_theme_font_size_override("font_size", font_size)
	b.custom_minimum_size = Vector2(190, 56)
	return b
