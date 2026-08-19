#!/usr/bin/env python3
"""ЛИЦО — ЭТО ТЕКСТУРА, А НЕ ГЕОМЕТРИЯ.

Главное, на чём держится весь этот файл: в 3D-аниме глаза, брови и рот НЕ
лепятся. Их рисуют плоскими на простой болванке головы и проецируют спереди —
так сделаны Guilty Gear Xrd, Genshin, VRoid и вообще почти всё 3D-аниме. Именно
поэтому у таких персонажей лицо читается с любого ракурса в пределах разумного
угла и разваливается в профиль: там нечему держать форму, там краска.

И это ровно та часть работы, которую можно написать кодом. Аниме-глаз — не
выразительный росчерк от руки, а конструкция из считанных фигур:
    ресничная линия  — толстая дуга переменной толщины, самая тёмная и самая
                       главная: она одна задаёт и разрез, и выражение;
    радужка          — эллипс с вертикальным градиентом (сверху темнее, снизу
                       светлее — отражение неба сверху, отсвет щеки снизу);
    зрачок           — эллипс поменьше;
    блики            — два: крупный со стороны источника и мелкий напротив.
                       Без второго глаз мёртвый, это известное правило;
    нижнее веко      — тонкая линия, НЕ замкнутая: замкнутый контур глаза даёт
                       «кукольный» взгляд.

Всё рисуется с четырёхкратной передискретизацией и потом уменьшается: PIL не
сглаживает контуры сам, а зубчатая ресничная линия убивает лицо мгновенно.

Запуск: python3 studio/face_texture.py [выход.png]
"""
import sys
from PIL import Image, ImageDraw, ImageFilter

SS = 4                    # передискретизация

# СЖАТИЕ ПО ГОРИЗОНТАЛИ. Текстура квадратная, но на голову она ложится
# неравномерно: по ширине на 0.584 высоты головы, а по высоте на всю высоту.
# Значит, всё нарисованное сплющивается по горизонтали в 1/0.584 = 1.71 раза —
# на первом кадре лицо вышло узким и вытянутым. Компенсируем в самом рисунке:
# горизонтальные размеры множатся на AR. Это не подгонка, это отношение
# охватов, и если изменится ширина головы, изменится и оно.
AR = 1.0 / 0.584
W = H = 1024              # итоговый размер

# ЦВЕТА — ИЗ ПАЛИТРЫ СЦЕНЫ, А НЕ ПОДОБРАННЫЕ ЗДЕСЬ.
# У Ghibli на весь фильм 262-600 цветов (Ясуда), то есть цвет назначается один
# раз и переиспользуется. Здесь тот же принцип: список, а не произвол.
PAL = {
    "skin":        (247, 224, 208, 255),
    "skin_shadow": (226, 186, 176, 255),
    "blush":       (240, 176, 168, 255),
    "line":        ( 62,  44,  52, 255),   # тушь: не чёрная, тёмно-сливовая
    "line_soft":   (168, 130, 128, 255),
    "iris_dark":   ( 46,  78,  92, 255),
    "iris_light":  (118, 168, 176, 255),
    "pupil":       ( 28,  34,  46, 255),
    "white":       (252, 252, 250, 255),
    "brow":        ( 92,  62,  58, 255),
    "mouth":       (176, 104, 104, 255),
}


def ellipse(d, cx, cy, rx, ry, fill):
    d.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=fill)


def _lid_curves(w, h, n=64):
    """Две линии век. ПРОРЕЗЬ ГЛАЗА — ЭТО ОНИ, а не эллипс.

    Верхнее веко: полная дуга с вершиной, СМЕЩЁННОЙ К ВНУТРЕННЕМУ УГЛУ (t~0.40).
    Симметричная дуга даёт кукольный глаз — вершина обязана быть смещена.
    Нижнее: вдвое площе и провисает ближе к внешнему углу.
    Внешний угол приподнят относительно внутреннего: это и задаёт разрез.
    """
    import math
    up, dn = [], []
    tilt = h * 0.10                      # насколько внешний угол выше внутреннего
    # ВЕРШИНА СМЕЩАЕТСЯ ИСКРИВЛЕНИЕМ АРГУМЕНТА, А НЕ СКЛЕЙКОЙ ДВУХ ВЕТВЕЙ.
    # Первый заход брал две степенные ветви слева и справа от вершины: в точке
    # стыка производная рвётся, и прорезь вышла ТРЕУГОЛЬНОЙ, с острым верхом.
    # Синус гладок всюду; чтобы его вершина уехала с t=0.5 на t=0.40, искривляем
    # сам аргумент: u = t^k, где k = ln(0.5)/ln(0.40).
    K_UP = math.log(0.5) / math.log(0.40)
    K_DN = math.log(0.5) / math.log(0.56)
    for i in range(n + 1):
        t = i / n
        x = -w + 2 * w * t
        lift = tilt * t
        u = t ** K_UP
        up.append((x, -h * (math.sin(math.pi * u) ** 0.80) - lift))
        v = t ** K_DN
        dn.append((x, h * 0.44 * (math.sin(math.pi * v) ** 0.95) - lift))
    return up, dn


def eye(d, im, cx, cy, w, h, flip, light=-1):
    """Один глаз. flip=-1 зеркалит по x. light — с какой стороны свет.

    БЛИКИ У ОБОИХ ГЛАЗ С ОДНОЙ СТОРОНЫ. Зеркалить их вместе с глазом —
    классическая ошибка: источник света один, и блик от него не зеркалится.
    """
    sx = flip
    up, dn = _lid_curves(w, h)
    poly = [(cx + sx * x, cy + y) for x, y in up] + \
           [(cx + sx * x, cy + y) for x, y in reversed(dn)]

    # прорезь как маска: всё содержимое глаза обрезается ею, а не рисуется поверх
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).polygon(poly, fill=255)

    lay = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ld = ImageDraw.Draw(lay)
    ld.polygon(poly, fill=PAL["white"])

    # РАДУЖКА КРУПНЕЕ ПРОРЕЗИ ПО ВЫСОТЕ — её срезают оба века. Глаз, где радужка
    # видна целиком, читается испуганным. По ширине белки остаются в углах.
    iy = cy - h * 0.02
    ir = h * 0.70
    # ГРАДИЕНТ РАДУЖКИ ОБРЕЗАЕТСЯ ОКРУЖНОСТЬЮ. Полосы рисуются прямоугольниками
    # во весь диаметр и потом маскируются кругом: если рисовать их эллипсами «на
    # глаз», у краёв остаётся пила — она была видна на первом кадре.
    irm = Image.new("L", im.size, 0)
    ImageDraw.Draw(irm).ellipse([cx - ir, iy - ir, cx + ir, iy + ir], fill=255)
    gl = Image.new("RGBA", im.size, (0, 0, 0, 0))
    gd = ImageDraw.Draw(gl)
    steps = 48
    for i in range(steps):
        t = i / (steps - 1)
        c = tuple(int(PAL["iris_dark"][k] + (PAL["iris_light"][k] - PAL["iris_dark"][k]) * (t ** 1.4))
                  for k in range(3)) + (255,)
        y0 = iy - ir + 2 * ir * i / steps
        y1 = iy - ir + 2 * ir * (i + 1.6) / steps
        gd.rectangle([cx - ir, y0, cx + ir, y1], fill=c)
    lay = Image.composite(Image.alpha_composite(lay, gl), lay, irm)
    ld = ImageDraw.Draw(lay)
    ld.ellipse([cx - ir, iy - ir, cx + ir, iy + ir], outline=PAL["pupil"], width=int(ir * 0.16))
    ld.ellipse([cx - ir * 0.34, iy - ir * 0.40, cx + ir * 0.34, iy + ir * 0.40], fill=PAL["pupil"])

    # тень от верхнего века НА радужке — без неё глаз плоский
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon(
        [(cx + sx * x, cy + y) for x, y in up] +
        [(cx + sx * x, cy + y + h * 0.42) for x, y in reversed(up)],
        fill=(40, 30, 44, 92))
    lay = Image.alpha_composite(lay, sh)
    ld = ImageDraw.Draw(lay)

    ld.ellipse([cx + light * ir * 0.62 - ir * 0.30, iy - ir * 0.62 - ir * 0.26,
                cx + light * ir * 0.62 + ir * 0.30, iy - ir * 0.62 + ir * 0.26],
               fill=PAL["white"])
    ld.ellipse([cx - light * ir * 0.34 - ir * 0.13, iy + ir * 0.44 - ir * 0.11,
                cx - light * ir * 0.34 + ir * 0.13, iy + ir * 0.44 + ir * 0.11],
               fill=(252, 252, 250, 210))

    im.paste(lay, (0, 0), Image.composite(lay.split()[3], Image.new("L", im.size, 0), mask))
    d = ImageDraw.Draw(im)

    # РЕСНИЧНАЯ ЛИНИЯ поверх верхнего века. Толщина растёт к внешнему углу,
    # линия ВЫХОДИТ за прорезь остриём — это то, что даёт взгляду характер.
    lash = [(cx + sx * x, cy + y) for x, y in up]
    back = []
    for i, (x, y) in enumerate(up):
        t = i / (len(up) - 1)
        back.append((cx + sx * x, cy + y + h * (0.11 + 0.16 * t)))
    d.polygon(lash + list(reversed(back)), fill=PAL["line"])
    ox, oy = cx + sx * w, cy + up[-1][1]
    d.polygon([(ox, oy), (ox + sx * w * 0.42, oy - h * 0.34),
               (ox - sx * w * 0.06, oy + h * 0.30)], fill=PAL["line"])

    # нижнее веко — тонкое, короче прорези и не смыкается с верхним
    low = [(cx + sx * x, cy + y) for x, y in dn][6:-10]
    d.line(low, fill=PAL["line_soft"], width=max(2, int(h * 0.075)), joint="curve")


def brow(d, cx, cy, w, flip, raise_=0.0):
    """Бровь. Толщина падает к внешнему концу, наклон задаёт настроение."""
    sx = flip
    pts = []
    n = 24
    for i in range(n + 1):
        t = i / n
        x = cx + sx * (-w + 2 * w * t)
        y = cy - w * (0.16 * (1 - (2 * t - 1) ** 2)) + w * 0.10 * t * sx * 0 - raise_
        pts.append((x, y))
    for i in range(n, -1, -1):
        t = i / n
        x = cx + sx * (-w + 2 * w * t)
        th = w * (0.115 - 0.075 * t)
        y = cy - w * (0.16 * (1 - (2 * t - 1) ** 2)) + th - raise_
        pts.append((x, y))
    d.polygon(pts, fill=PAL["brow"])


def build(out):
    im = Image.new("RGBA", (W * SS, H * SS), PAL["skin"])
    d = ImageDraw.Draw(im)
    S = SS

    # СЕТКА ЛИЦА. Текстура проецируется спереди на болванку головы, поэтому
    # координаты здесь — это доли ШИРИНЫ И ВЫСОТЫ ГОЛОВЫ, а не что попало.
    # Линия глаз в аниме ниже, чем у человека: у людей середина головы, здесь
    # 0.44 от подбородка. Это и даёт большой лоб, то есть «детскость».
    eye_y = int(H * 0.505 * S)
    eye_dx = int(W * 0.146 * AR * S)          # от оси до центра глаза
    eye_w = int(W * 0.098 * AR * S)
    eye_h = int(W * 0.106 * S)
    cx = W * S // 2

    # румянец под глазами — мягкое пятно, кладётся ПЕРВЫМ, под всё
    blush = Image.new("RGBA", im.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(blush)
    for s in (-1, 1):
        ellipse(bd, cx + s * eye_dx, eye_y + int(eye_h * 1.05),
                int(eye_w * 0.82), int(eye_h * 0.26), PAL["blush"][:3] + (88,))
    blush = blush.filter(ImageFilter.GaussianBlur(radius=int(26 * S)))
    im = Image.alpha_composite(im, blush)
    d = ImageDraw.Draw(im)

    for s in (-1, 1):
        eye(d, im, cx + s * eye_dx, eye_y, eye_w, eye_h, s)
        brow(d, cx + s * int(W * 0.152 * AR * S), eye_y - int(eye_h * 2.30),
             int(W * 0.082 * AR * S), s)

    # НОС — ОДИН ШТРИХ. В аниме нос это тень, а не форма; полноценный нос
    # ломает стиль сильнее, чем что-либо ещё.
    ny = eye_y + int(eye_h * 1.72)
    d.line([(cx + int(W * 0.008 * AR * S), ny), (cx + int(W * 0.021 * AR * S), ny + int(H * 0.013 * S))],
           fill=PAL["skin_shadow"], width=int(5 * S))

    # РОТ — маленький, смещён вниз, дуга и подтень нижней губы
    # РОТ МАЛЕНЬКИЙ. В аниме он вчетверо уже глаза и почти всегда лишь дуга;
    # угол вниз читается как уныние, поэтому концы чуть подняты.
    my = eye_y + int(eye_h * 2.72)
    mw = int(W * 0.030 * AR * S)
    pts = []
    for i in range(17):
        t = i / 16
        pts.append((cx - mw + 2 * mw * t, my + mw * 0.42 * (1 - (2 * t - 1) ** 2)))
    d.line(pts, fill=PAL["mouth"], width=int(6 * S), joint="curve")
    # подтень нижней губы — короткая и светлее рта
    d.line([(cx - mw * 0.45, my + mw * 0.78), (cx + mw * 0.45, my + mw * 0.78)],
           fill=PAL["skin_shadow"], width=int(5 * S))

    im = im.resize((W, H), Image.LANCZOS).convert("RGB")
    im.save(out)
    print("лицо:", out, im.size)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "/tmp/face.png")
