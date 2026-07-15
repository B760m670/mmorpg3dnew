> **ЗАМОРОЖЕНО**: старый мир — черновик-референс. Пересоздаётся заново (game2/) по docs/rebuild_masterplan.md.

# Мир Гатчины 1894

Единый источник истины — `gatchina/layout.json`. Из него генерируются рельеф,
карта и размещение зданий, поэтому мир и карта не расходятся.

Квадрат города — **6×6 км** (`terrain.size` в layout). Гатчинский комплекс в
центре, вокруг — луга, поля, леса.

## Конвейер

```
tools/ground_gen.py    -> world/textures/ground/*   БИБЛИОТЕКА ГРУНТОВ: 8 типов
                          + ground_library.json      почвы (луг, сухая трава, лесная
                                                     подстилка, пашня, садовая земля,
                                                     тропа, песок, суглинок) — тайловые
                                                     PBR (albedo+normal+rough). Делаются
                                                     ОДИН РАЗ, применяются к любой области.
layout.json ──┬─> tools/terrain_gen.py  -> gatchina/heights.json (поле высот 6 км;
              │                             сам меш рельефа строит Godot в движке)
              ├─> tools/buildings_gen.py -> world/buildings/*.glb (дворец, Приорат, собор,
              │                             обелиск, вокзал, дома — каждое отдельным файлом)
              ├─> tools/palace_gen.py    -> world/buildings/palace.glb (детальный дворец)
              ├─> tools/materials_gen.py -> world/textures/*   PBR зданий (ашлар, кровля…)
              └─> tools/map_gen.py       -> gatchina/map.png   (обзорная карта)
```

Пересборка (пример):
```
python3 game/world/tools/ground_gen.py    -- /path/to/repo
python3 game/world/tools/terrain_gen.py   -- /path/to/repo
python3 game/world/tools/buildings_gen.py -- /path/to/repo
python3 game/world/tools/map_gen.py       -- /path/to/repo
```

## В игре (Godot)

`scripts/world.gd` строит рельеф прямо в движке из `heights.json` (SurfaceTool,
явные нормали) и красит его по типам грунта из библиотеки: шейдер
`shaders/terrain.gdshader` смешивает до 4 слоёв почвы по вершинному цвету
(луг / лесная подстилка / тропа / пашня-огород — зоны берутся из `layout.json`:
`forests`, `roads`, `fields`, `gardens`). Плюс: физическое небо
(`shaders/sky.gdshader`), вода озёр (`shaders/water.gdshader`), деревья через
MultiMesh, здания с коллизиями, игрок (физика) и карта с маркером.
Растительность (кусты, сады, огороды, лес) — следующий слой библиотеки.

## География (как в реальной Гатчине)

Дворец на холме над Серебряным озером → Дворцовый парк вокруг Белого озера →
Большой проспект через площадь Коннетабля к собору Св. Павла → Приоратский дворец
на берегу Чёрного озера → вокзал на юге. Местность равнинная (Ижорское плато);
горных районов здесь нет — они появятся в других локациях тем же конвейером.
