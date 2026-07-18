# Реальные материалы поверхности — происхождение и лицензия

НАСТОЯЩИЕ сканированные PBR-материалы (не синтез). Все — **ambientCG**, лицензия
**CC0 1.0 (общественное достояние)**: https://docs.ambientcg.com/books/website-licensing/

Занесены путём B (сеть среды к ambientCG.com напрямую закрыта): текстуры
ambientCG, закоммиченные В ДЕРЕВЕ публичного Godot-репозитория, вытянуты через
`raw.githubusercontent.com` (доступен). Файлы 2K→даунсэмпл 1K (для тайла ~2 м —
0.5 см/пиксель, с запасом; вес репозитория разумный).

Источник-пин: **Calinou/godot-cmvalley** @ `40ad117a1ab307799e1a3eebbdb91433f3e58d2f`,
каталог `ambientcg/` (автор репо — Hugo Locurcio, core-контрибьютор Godot).
Лицензия текстур — CC0 самого ambientCG, независимо от репозитория-носителя.

| Папка | ambientCG ID | Назначение в срезе | Каналы |
|------|--------------|--------------------|--------|
| grass004  | Grass004  | газон партера / луг | Color, Normal, Roughness, AmbientOcclusion |
| gravel011 | Gravel011 | гравий аллей / плац | Color, Normal, Roughness, AmbientOcclusion |
| rock030   | Rock030   | камень / берег / цоколь | Color, Normal, Roughness, AmbientOcclusion |
| tiles049  | Tiles049  | мостовая / плитняк | Color, Normal, Roughness |

Normal — в соглашении OpenGL (Godot-совместимо). Проверка целостности:
`tools/verify_materials.py` (размеры, диапазоны каналов). Прувф-релайт:
`tools/preview_surface.py`.

Оригиналы можно перезабрать напрямую с ambientCG (когда сеть открыта):
https://ambientcg.com/view?id=Grass004 (и аналогично Gravel011, Rock030, Tiles049).
