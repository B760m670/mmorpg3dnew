#!/usr/bin/env python3
"""ЧЕЛОВЕК НА ГОТОВОЙ БОЛВАНКЕ. Второй заход, и первый честный.

ЧТО БЫЛО НЕ ТАК В ПЕРВОМ. Я строил фигуру с нуля, выписывая координаты вершин —
сперва в GDScript, потом в Блендере. Оба раза получилась карикатура, и это не
вопрос подбора чисел: я перебирал их весь заход. Потолок у способа низкий,
потому что лицо и тело нельзя задать координатами — их лепят, а лепить я не
умею и не буду уметь.

ТАК ДЕЛАЮТ МАЛЕНЬКИЕ КОМАНДЫ: берут болванку, сделанную художником, и дальше её
подгоняют, одевают и оснащают. Здесь — официальный набор Blender Studio
«Human Base Meshes» (bundle v1.4.1, 50 МБ, CC0, то есть без ограничений на
использование). В нём тело мужчины с правильной топологией: рёберные петли
вокруг глаз, рта, локтей и коленей — ровно то, чего у моих колец не было и
быть не могло.

ЧТО ОСТАЁТСЯ МОЕЙ РАБОТОЙ, и её немало:
  - пропорции под нашего героя (канон 7.5 голов, рост 1.75 м);
  - костюм эпохи: пальто ниже колена, сапоги, картуз — по документам о быте
    Гатчины 1894 года;
  - арматура и веса;
  - вывоз в игру и проверка в кадре.
Болванка снимает только то, что я и не мог сделать: анатомию и топологию.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/person2.py -- --render /tmp/turn.png
"""
import math
import os
import sys

import bpy
from mathutils import Vector

BUNDLE = "/tmp/claude-live/hbm/human-base-meshes-bundle-v1.4.1/human_base_meshes_bundle.blend"
# ИМЯ ОБЪЕКТА В НАБОРЕ. Осторожно: «realistic_body_male» — это КАМЕРА для
# миниатюры каталога, а не тело. Сама сетка называется иначе. Я на этом
# споткнулся: приложение проходило, печатало 10582 вершины, а в кадре был
# пустой фон — потому что в сцену привязывалась камера.
BODY = "GEO-body_male_realistic"
TARGET_H = 1.75          # рост нашего героя, м


def clear():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def append_body():
    """Приложить болванку из набора и поставить ей наш рост."""
    if not os.path.exists(BUNDLE):
        raise SystemExit("нет набора болванок: %s" % BUNDLE)
    # ПРИВЯЗЫВАТЬ НАДО ИМЕННО ТОТ ОБЪЕКТ, ЧТО ВЗЯЛИ. Первый заход брал «любой
    # новый объект в файле» — а приложение тянет за собой и служебные, и в
    # сцену попадал не тот: рендер выходил пустым фоном при успешной загрузке
    # 10582 вершин. Ошибка тихая и потому дорогая.
    with bpy.data.libraries.load(BUNDLE, link=False) as (src, dst):
        names = [n for n in src.objects if BODY in n]
        if not names:
            raise SystemExit("в наборе нет объекта «%s»; есть: %s"
                             % (BODY, sorted(src.objects)[:20]))
        dst.objects = names[:1]
    ob = dst.objects[0]
    if ob is None or ob.type != 'MESH':
        raise SystemExit("приложился не тот объект: %s" % ob)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.objects.active = ob
    print("[человек] взята болванка «%s»: вершин %d, граней %d"
          % (ob.name, len(ob.data.vertices), len(ob.data.polygons)))

    # РОСТ. Болванка приходит в своём масштабе; ставим наш и печатаем оба,
    # чтобы подгонка была видна числом, а не подразумевалась.
    #
    # ПРЕОБРАЗОВАНИЕ ИДЁТ ПО САМИМ ВЕРШИНАМ, а не операторами. bpy.ops требуют,
    # чтобы объект лежал в активном слое вида, а приложенный из библиотеки туда
    # ещё не попал — оператор падал с «ViewLayer does not contain object».
    # Прямая правка данных от контекста не зависит вовсе, и это надёжнее.
    from mathutils import Matrix
    me = ob.data
    me.transform(ob.matrix_world)
    ob.matrix_world = Matrix.Identity(4)
    zs = [v.co.z for v in me.vertices]
    was = max(zs) - min(zs)
    k = TARGET_H / was
    me.transform(Matrix.Diagonal(Vector((k, k, k)).to_4d()))
    lo = min(v.co.z for v in me.vertices)
    me.transform(Matrix.Translation(Vector((0, 0, -lo))))
    me.update()
    bpy.context.view_layer.update()
    d = ob.dimensions
    print("[человек] рост болванки был %.3f м -> стал %.3f м (коэффициент %.3f)"
          % (was, d.z, k))
    print("[человек] габарит: %.3f x %.3f x %.3f м, голова %.3f м, отношение %.2f"
          % (d.x, d.y, d.z, d.z / 7.5, 7.5))
    return ob


def _look_at(frm, to):
    return (to - frm).to_track_quat('-Z', 'Y').to_euler()


def stage_lights():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE_NEXT'
    sc.render.resolution_x = 420
    sc.render.resolution_y = 900
    sc.view_settings.view_transform = 'Standard'
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.32, 0.35, 1)
    sc.world = w
    for name, pos, energy in (("рисующий", (2.2, -2.6, 2.6), 90.0),
                              ("заполняющий", (-2.8, -1.6, 1.4), 32.0),
                              ("контровой", (0.4, 3.2, 2.2), 60.0)):
        lt = bpy.data.lights.new(name, 'AREA')
        lt.energy = energy
        lt.size = 2.0
        lo = bpy.data.objects.new(name, lt)
        lo.location = pos
        lo.rotation_euler = _look_at(Vector(pos), Vector((0, 0, 1.0)))
        bpy.context.collection.objects.link(lo)


def turnaround(path):
    sc = bpy.context.scene
    stage_lights()
    cam_d = bpy.data.cameras.new("cam")
    cam_d.lens = 70.0
    cam = bpy.data.objects.new("cam", cam_d)
    bpy.context.collection.objects.link(cam)
    sc.camera = cam
    outs = []
    for i, ang in enumerate((0.0, 40.0, 90.0, 180.0)):
        a = math.radians(ang)
        d = 3.4
        cam.location = (d * math.sin(a), -d * math.cos(a), 0.95)
        cam.rotation_euler = _look_at(Vector(cam.location), Vector((0, 0, 0.88)))
        p = "/tmp/claude-live/_p2_%d.png" % i
        sc.render.filepath = p
        bpy.ops.render.render(write_still=True)
        outs.append(p)
        print("[человек] вид %3.0f° -> %s" % (ang, p))
    print("[человек] кадры готовы, полоса собирается снаружи:", path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    clear()
    append_body()
    if "--render" in argv:
        turnaround(argv[argv.index("--render") + 1])


if __name__ == "__main__":
    main()
