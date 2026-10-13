#!/usr/bin/env python3
"""ОБМЕР ПО СИЛУЭТУ: один прибор для фотографии живого человека и для нашего
кадра.

ЗАЧЕМ. Заказчик показал фотографию стоящего мужчины и сказал: пропорции у тебя
неправильные. Спорить об этом словами нельзя, а сравнивать наш обмер (по
сетке, в метрах) с фотографией (в пикселях) — нечестно: разные приборы врут
по-разному. Поэтому здесь ОДИН прибор, который меряет и то и другое
одинаково: по силуэту.

КАК. Фон отсекается по яркости, остаётся маска тела. Дальше по каждой строке
пикселей известна ширина тела, и этого хватает на всё, что нужно:
  рост         — от макушки до подошв;
  голова       — от макушки до подбородка (первое заметное сужение шеи);
  плечи        — наибольшая ширина в верхней трети;
  талия        — наименьшая ширина между плечами и тазом;
  таз          — наибольшая ширина ниже талии;
  стопы врозь  — расстояние между серединами стоп у самого пола;
  руки         — по разрыву силуэта: там, где рука отходит от корпуса, строка
                 распадается на три куска, и по ним видно и просвет, и ширину.
Всё делится на рост, поэтому пиксели и метры сравнимы напрямую.

ЧЕГО ЭТОТ ПРИБОР НЕ УМЕЕТ, и это надо помнить: силуэт не знает глубины. Он не
отличит человека, стоящего строго анфас, от повёрнутого на десять градусов, и
занижает ширину плеч у второго. Поэтому сравнивать имеет смысл только кадры,
снятые анфас.
"""
import sys


def mask(path, thr=238):
    """Силуэт: True там, где тело. Фон считается светлым."""
    from PIL import Image
    im = Image.open(path).convert("L")
    w, h = im.size
    px = im.load()
    m = [[px[x, y] < thr for x in range(w)] for y in range(h)]
    # выкинуть мелкий мусор (подписи, водяной знак): в строке оставляем только
    # самый широкий связный кусок и то, что рядом с ним
    for y in range(h):
        runs, s = [], None
        for x in range(w + 1):
            on = x < w and m[y][x]
            if on and s is None:
                s = x
            elif not on and s is not None:
                runs.append((s, x - 1))
                s = None
        if not runs:
            continue
        big = max(runs, key=lambda r: r[1] - r[0])
        if big[1] - big[0] < 3:
            for a, b in runs:
                for x in range(a, b + 1):
                    m[y][x] = False
            continue
        cx = (big[0] + big[1]) / 2
        keep = [r for r in runs if abs((r[0] + r[1]) / 2 - cx) < w * 0.30]
        for a, b in runs:
            if (a, b) not in keep:
                for x in range(a, b + 1):
                    m[y][x] = False
    return m, w, h


def rows(m, w, h, merge=0):
    """По каждой строке: ширина тела и куски силуэта.

    MERGE СКЛЕИВАЕТ БЛИЗКИЕ КУСКИ, и без этого прибор врёт. На образце талия
    вышла шириной в один пиксель: молния на плавках дала светлую полосу, и
    строка распалась надвое ровно там, где меряется талия. Всё, что разделено
    щелью меньше пары процентов роста, — это одно тело.
    """
    out = []
    for y in range(h):
        runs, s = [], None
        for x in range(w + 1):
            on = x < w and m[y][x]
            if on and s is None:
                s = x
            elif not on and s is not None:
                runs.append((s, x - 1))
                s = None
        if merge and len(runs) > 1:
            mg = [list(runs[0])]
            for a, b in runs[1:]:
                if a - mg[-1][1] <= merge:
                    mg[-1][1] = b
                else:
                    mg.append([a, b])
            runs = [tuple(r) for r in mg]
        if runs:
            out.append((y, runs[0][0], runs[-1][1], runs))
        else:
            out.append((y, None, None, []))
    return out


def analyse(path, name=""):
    m, w, h = mask(path)
    R0 = rows(m, w, h)
    body0 = [r for r in R0 if r[1] is not None]
    if not body0:
        print("силуэт не найден:", path)
        return None
    H0 = body0[-1][0] - body0[0][0]
    R = rows(m, w, h, merge=max(2, int(H0 * 0.02)))
    body = [r for r in R if r[1] is not None]
    top, bot = body[0][0], body[-1][0]
    H = bot - top

    cx = sum((r[1] + r[2]) / 2 for r in body) / len(body)

    def full(y):
        r = R[y]
        return 0 if r[1] is None else r[2] - r[1] + 1

    def torso(y):
        """Ширина ТОЛЬКО корпуса. Руки, отошедшие от тела, дают в строке
        отдельные куски — их надо выбросить, иначе «плечи» найдутся на уровне
        локтей: именно так прибор и ошибся в первый раз."""
        rr = R[y][3]
        if not rr:
            return 0
        c = min(rr, key=lambda r: abs((r[0] + r[1]) / 2 - cx))
        return c[1] - c[0] + 1

    def frac(y):
        return (y - top) / H

    # ГОЛОВА: ниже макушки ширина сперва растёт (череп), потом резко падает
    # (шея). Подбородок — самое узкое место в верхней шестой части.
    lo = min(range(top + int(H * 0.06), top + int(H * 0.22)), key=full)
    head = lo - top
    # ПЛЕЧИ: сразу под подбородком, в пределах одной высоты головы — там
    # корпус шире всего, и это дельты
    sh_y = max(range(lo, lo + max(4, int(head * 1.0))), key=torso)
    # ПРОМЕЖНОСТЬ: первая строка ниже середины, где корпус распался на две
    # ноги. Ниже неё талию и таз мерить бессмысленно.
    # СЧИТАЕМ ТОЛЬКО КУСКИ У ОСИ: руки тоже дают куски, и без этого условия
    # «промежность» находилась там, где просто отошла рука.
    crotch = top + int(H * 0.55)
    for y in range(top + int(H * 0.42), top + int(H * 0.62)):
        rr = [r for r in R[y][3]
              if abs((r[0] + r[1]) / 2 - cx) < H * 0.13 and r[1] - r[0] > H * 0.03]
        if len(rr) >= 2:
            crotch = y
            break
    # ТАЛИЯ И ТАЗ БЕРУТСЯ НА ЗАДАННЫХ ВЫСОТАХ, а не поиском наибольшего и
    # наименьшего. Поиск оказался неустойчив: стоит границе поиска съехать на
    # пару процентов — и «таз» находится уже на бедре, число прыгает вдвое, а
    # сравнивать становится нечего. Высоты взяты из ANSUR II: пупок на 0.602
    # роста, тазовая кость на 0.53.
    wa_y = top + int(H * (1.0 - 0.602))
    hi_y = top + int(H * (1.0 - 0.530))
    width = torso
    # СТОПЫ: по нижним 3% роста, расстояние между серединами двух кусков
    feet = 0
    for y in range(bot - int(H * 0.03), bot):
        rr = R[y][3]
        if len(rr) >= 2:
            a = (rr[0][0] + rr[0][1]) / 2
            b = (rr[-1][0] + rr[-1][1]) / 2
            feet = max(feet, b - a)
    # ПРОСВЕТ ПОД РУКОЙ: наибольший разрыв между корпусом и рукой в полосе
    # 0.30..0.55 роста — по нему видно, висит рука вдоль тела или отставлена
    gap = 0
    for y in range(top + int(H * 0.30), top + int(H * 0.55)):
        rr = R[y][3]
        if len(rr) >= 3:
            g = max(rr[i + 1][0] - rr[i][1] for i in range(len(rr) - 1))
            gap = max(gap, g)
    out = {
        "рост_пкс": H,
        "голова/рост": head / H,
        "ростов в голове": H / head if head else 0,
        "плечи/рост": width(sh_y) / H,
        "талия/рост": width(wa_y) / H,
        "таз/рост": width(hi_y) / H,
        "плечи/таз": width(sh_y) / width(hi_y) if width(hi_y) else 0,
        "талия/плечи": width(wa_y) / width(sh_y) if width(sh_y) else 0,
        "стопы врозь/рост": feet / H,
        "просвет под рукой/рост": gap / H,
        "высота плеч": frac(sh_y),
        "высота талии": frac(wa_y),
        "высота промежности": frac(crotch),
    }
    print("СИЛУЭТ %s (%dx%d, рост %d пкс)" % (name or path, w, h, H))
    for k, v in out.items():
        if k != "рост_пкс":
            print("   %-24s %.3f" % (k, v))
    return out


def compare(a, b, na="образец", nb="наш"):
    print("=" * 66)
    print("%-24s %10s %10s %10s" % ("признак", na, nb, "разница"))
    for k in a:
        if k == "рост_пкс" or k not in b:
            continue
        d = (b[k] - a[k]) / a[k] * 100 if a[k] else 0
        mark = "" if abs(d) < 8 else "  <-- "
        print("   %-22s %9.3f %10.3f %+9.1f%%%s" % (k, a[k], b[k], d, mark))
    print("=" * 66)


if __name__ == "__main__":
    res = [analyse(p, p.split("/")[-1]) for p in sys.argv[1:]]
    if len(res) == 2 and all(res):
        compare(res[0], res[1])
