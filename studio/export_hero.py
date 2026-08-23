#!/usr/bin/env python3
"""ГЕРОЙ В ИГРУ: сборка, ходьба, постановка на землю, вывод в glTF.

ЗАЧЕМ ОТДЕЛЬНЫЙ ФАЙЛ. До сих пор человек существовал только в Блендере: в
`game2/` персонажа нет вовсе. Пока он не в игре, всё сделанное — картинки.
Здесь собирается ровно то, что игра может открыть: один .glb со скелетом,
одеждой и одним циклом ходьбы.

ЦИКЛ, А НЕ ОТРЕЗОК. Из записи вырезается кусок от постановки левой стопы до
следующей постановки левой — тогда клип крутится петлёй.
ИЗМЕРЕНО на записи CMU 07_01: цикл 1.12 с, шаг 1.515 м, скорость 1.35 м/с,
шов петли в среднем 3.4°, худшая кость 12°. Это ходьба взрослого человека
(норма 1.0–1.2 с и 1.2–1.4 м/с) — и это единственная независимая проверка
того, что перенос движения не врёт: числа походки не подгонялись ни под что.

НА МЕСТЕ, А НЕ С ПЕРЕМЕЩЕНИЕМ. Горизонтальный ход из клипа вычитается: пусть
персонажа двигает игра, а анимация только шагает. Так походка сцепляется со
скоростью (шаг ускоряется — значит и ноги), и так проще с физикой и склонами.
Боковое покачивание таза при этом остаётся: оно настоящее.

Запуск:
  LIBGL_ALWAYS_SOFTWARE=1 xvfb-run -a /opt/blender/blender -b -noaudio \
      -P studio/export_hero.py -- --out game2/assets/hero/hero.glb [--nude]
"""
import os
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ground   # noqa: E402
import hero     # noqa: E402
import mocap    # noqa: E402

ASF = os.environ.get("CMU_ASF", "/tmp/claude-live/mocap/07.asf")
AMC = os.environ.get("CMU_AMC", "/tmp/claude-live/mocap/07_01.amc")
STEP = 3          # 120 к/с записи -> 40 к/с клипа
CLIP = "ходьба"


def inplace(arm, f0, f1, root="Hips"):
    """Вычесть из корня равномерный горизонтальный ход за цикл.

    Вычитается именно ПРЯМАЯ между началом и концом цикла, а не всё движение:
    покачивание таза вбок и вверх-вниз — часть настоящей походки, его трогать
    нельзя. Уходит только равномерный проезд вперёд.
    """
    pb = arm.pose.bones[root]
    rest = arm.data.bones[root].matrix_local.to_3x3()
    Wi = arm.matrix_world.to_3x3().inverted()
    pts = {}
    for f in (f0, f1):
        bpy.context.scene.frame_set(f)
        dg = bpy.context.evaluated_depsgraph_get()
        pts[f] = arm.evaluated_get(dg).pose.bones[root].head.copy()
    d = pts[f1] - pts[f0]
    d.z = 0.0
    for f in range(f0, f1 + 1):
        bpy.context.scene.frame_set(f)
        w = (f - f0) / max(1, f1 - f0)
        pb.location = pb.location - rest.transposed() @ (Wi @ (d * w))
        pb.keyframe_insert("location", frame=f)
    bpy.context.view_layer.update()
    print("[клип] ход вперёд вычтен: %.3f м за %d кадров" % (d.length, f1 - f0))
    return d.length


def trim(arm, f0, f1):
    """Оставить в действии только кадры цикла и подвинуть их к единице."""
    act = arm.animation_data.action
    for fc in list(act.fcurves):
        keep = [kp for kp in fc.keyframe_points if f0 <= kp.co.x <= f1]
        if not keep:
            act.fcurves.remove(fc)
            continue
        vals = [(kp.co.x - f0 + 1, kp.co.y) for kp in keep]
        for _ in range(len(fc.keyframe_points)):
            fc.keyframe_points.remove(fc.keyframe_points[0], fast=True)
        fc.keyframe_points.add(len(vals))
        for kp, (x, y) in zip(fc.keyframe_points, vals):
            kp.co = (x, y)
            kp.interpolation = 'LINEAR'
        fc.update()
    act.name = CLIP
    if hasattr(act, "use_frame_range"):
        act.use_frame_range = True
        act.frame_start = 1
        act.frame_end = f1 - f0 + 1
    sc = bpy.context.scene
    sc.frame_start = 1
    sc.frame_end = f1 - f0 + 1
    print("[клип] обрезан до %d кадров, назван «%s»" % (sc.frame_end, CLIP))


# ПРЕДЕЛ РАЗМЕРА ТЕКСТУРЫ, в пикселях. Первый вывод весил 80 МБ, из них 46 —
# две карты пальто по 4096². На телефоне такая карта занимает столько же
# видеопамяти, сколько весь остальной герой, а на экране 6.9 дюйма её никто
# не различит. Лицо — исключение: камера через плечо смотрит на затылок и
# щёку вплотную, поэтому коже оставляем 2048.
CAP = [("Jartur", 2048), ("eye", 512), ("eyelash", 256), ("eyebrow", 256),
       ("teeth", 256), ("tongue", 256), ("short02", 1024)]
CAP_DEFAULT = 1024


def shrink():
    """Ужать текстуры до разумного и заставить экспортёр их пережать."""
    было = после = 0
    for im in bpy.data.images:
        # В фоновом Блендере картинка не загружена, пока её не тронешь:
        # has_data лжёт False, size показывает нули. Поэтому сначала reload.
        if im.size[0] == 0:
            try:
                im.reload()
            except Exception:
                pass
        w, h = im.size
        if w == 0:
            continue
        было += w * h
        cap = CAP_DEFAULT
        for key, c in CAP:
            if key.lower() in im.name.lower():
                cap = c
                break
        k = max(w, h) / float(cap)
        if k > 1.0:
            im.scale(max(1, int(w / k)), max(1, int(h / k)))
            print("[текстуры] %-46s %dx%d -> %dx%d"
                  % (im.name[:46], w, h, im.size[0], im.size[1]))
        после += im.size[0] * im.size[1]
    print("[текстуры] пикселей всего: %.1f -> %.1f млн"
          % (было / 1e6, после / 1e6))


def export(path):
    shrink()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.export_scene.gltf(
        filepath=path, export_format='GLB', use_selection=True,
        export_animations=True, export_frame_range=True,
        export_animation_mode='ACTIONS', export_skins=True,
        export_apply=True, export_yup=True,
        export_image_format='AUTO', export_jpeg_quality=88,
    )
    mb = os.path.getsize(path) / 1048576.0
    print("[вывод] %s — %.1f МБ" % (path, mb))
    return mb


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[argv.index("--out") + 1] if "--out" in argv \
        else "game2/assets/hero/hero.glb"
    body = hero.build(skip_clothes=("--nude" in argv))
    arm = next(o for o in bpy.data.objects if o.type == 'ARMATURE')

    n = mocap.load_cmu(arm, ASF, AMC, start=1, count=0, step=STEP)
    F = list(range(1, n + 1))
    ground.lock(body, arm, F)
    ground.lock(body, arm, F)     # второй проход: опора уточняется по первому
    ground.report(body, arm, F, "ПЕРЕД ВЫВОДОМ")
    c = ground.cycle(body, arm, F)
    if not c:
        raise SystemExit("цикл шага не найден")
    f0, f1, dist, dur, seam = c
    inplace(arm, f0, f1)
    trim(arm, f0, f1)

    tri = sum(len(o.data.loop_triangles) if o.data.loop_triangles else 0
              for o in bpy.data.objects if o.type == 'MESH')
    if not tri:
        for o in bpy.data.objects:
            if o.type == 'MESH':
                o.data.calc_loop_triangles()
        tri = sum(len(o.data.loop_triangles) for o in bpy.data.objects
                  if o.type == 'MESH')
    print("[герой] треугольников %d, объектов %d, костей %d"
          % (tri, len([o for o in bpy.data.objects if o.type == 'MESH']),
             len(arm.data.bones)))
    mb = export(out)
    print("[итог] клип «%s»: %.2f с, шаг %.3f м, скорость %.2f м/с, "
          "шов %.1f°, файл %.1f МБ" % (CLIP, dur, dist, dist / dur, seam, mb))


if __name__ == "__main__":
    main()
