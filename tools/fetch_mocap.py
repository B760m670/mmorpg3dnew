#!/usr/bin/env python3
"""ЗАПИСИ ДВИЖЕНИЯ CMU: скачать и ОПИСАТЬ ЗАМЕРОМ, а не по названию.

ЗАЧЕМ ЭТО ОТДЕЛЬНЫМ ИНСТРУМЕНТОМ. Записи лежали только во временной папке
(/tmp/claude-live/mocap) — то есть исчезали вместе с машиной, и повторить
сборку героя на чистом месте было нельзя. Пути к ним заданы переменными
CMU_ASF/CMU_AMC, и без файлов экспорт молча брал бы что попало.

ПОЧЕМУ КЛИПЫ СУДЯТСЯ ЗАМЕРОМ. У CMU 2605 записей, и описания к ним написаны
людьми на бегу: «Forward», «motion», «General Subject Capture». По такому
названию нельзя понять, годится ли клип на стойку, шаг или поворот. Зато это
видно из самой записи: у стойки путь около нуля, у поворота путь мал, а разворот
корня велик, у ходьбы скорость держится ровной. Считаем это прямо здесь — по
корневому суставу, без Блендера.

ЛИЦЕНЗИЯ. База CMU открыта: «free for all uses», требуется лишь упоминание
источника (mocap.cs.cmu.edu, при поддержке NSF EIA-0196217).

Запуск:
  python3 tools/fetch_mocap.py 91_29 91_10 91_18 91_56 91_54
  python3 tools/fetch_mocap.py --subject 91 --limit 12
  python3 tools/fetch_mocap.py --report          # описать уже скачанное
"""
import math
import os
import re
import sys
import urllib.request

БАЗА = "http://mocap.cs.cmu.edu/subjects"
ПАПКА = os.environ.get("CMU_DIR", "/tmp/claude-live/mocap")


def скачать(url, путь):
    if os.path.exists(путь) and os.path.getsize(путь) > 0:
        return False
    os.makedirs(os.path.dirname(путь), exist_ok=True)
    with urllib.request.urlopen(url, timeout=90) as r, open(путь, "wb") as f:
        f.write(r.read())
    return True


def взять(имя):
    """имя вида 91_29 — скачать .asf субъекта и .amc испытания."""
    subj = имя.split("_")[0]
    asf = os.path.join(ПАПКА, "%s.asf" % subj)
    amc = os.path.join(ПАПКА, "%s.amc" % имя)
    n1 = скачать("%s/%s/%s.asf" % (БАЗА, subj, subj), asf)
    n2 = скачать("%s/%s/%s.amc" % (БАЗА, subj, имя), amc)
    return asf, amc, (n1 or n2)


# --- ОПИСАНИЕ ЗАМЕРОМ -------------------------------------------------------

def _единица(asf):
    """Сколько метров в одной единице длины ASF (CMU меряет в 0.45 дюйма)."""
    t = open(asf, encoding="latin-1").read()
    m = re.search(r":units(.*?):", t, re.S)
    if m:
        u = re.search(r"length\s+([-\d.eE+]+)", m.group(1))
        if u:
            return 0.0254 / float(u.group(1))
    return 0.0254 / 0.45


def кадры_корня(amc):
    """Сдвиг и разворот корня по кадрам: (x, y, z, ry)."""
    out = []
    for line in open(amc, encoding="latin-1"):
        w = line.split()
        if len(w) >= 7 and w[0] == "root":
            try:
                v = [float(x) for x in w[1:7]]
            except ValueError:
                continue
            out.append((v[0], v[1], v[2], v[4]))
    return out


def описать(asf, amc, fps=120.0):
    k = кадры_корня(amc)
    if len(k) < 10:
        return None
    ед = _единица(asf)
    путь = 0.0
    for a, b in zip(k, k[1:]):
        путь += math.hypot(b[0] - a[0], b[2] - a[2]) * ед
    длит = len(k) / fps
    # РАЗВОРОТ СЧИТАЕТСЯ НАКОПЛЕНИЕМ ПО КАДРАМ, а не разностью «конец минус
    # начало»: иначе полный оборот на 360° даёт ноль и читается как стойка.
    пов = 0.0
    for a, b in zip(k, k[1:]):
        d = (b[3] - a[3] + 180.0) % 360.0 - 180.0
        пов += d
    ампл = max(x[1] for x in k) - min(x[1] for x in k)
    v = путь / длит if длит else 0.0
    # ПОРЯДОК ПРОВЕРОК ВАЖЕН: поворот на месте — это малый путь И большой
    # разворот. Если сперва спрашивать «путь мал?», поворот запишется стойкой:
    # так и вышло на 91_56, где корень развернулся на 82°, а ответ был «стойка».
    if abs(пов) > 45 and v < 0.6:
        род = "поворот на месте"
    elif v < 0.15:
        род = "стойка"
    elif v < 2.2:
        род = "ходьба"
    else:
        род = "бег"
    return {"кадров": len(k), "с": длит, "путь_м": путь, "скорость": v,
            "поворот": пов, "качка_корня_м": ампл * ед, "род": род}


def отчёт(файлы):
    print("%-12s %6s %6s %8s %8s %9s  %s"
          % ("клип", "кадров", "с", "путь,м", "м/с", "поворот°", "род"))
    for asf, amc in файлы:
        d = описать(asf, amc)
        имя = os.path.basename(amc)[:-4]
        if d is None:
            print("%-12s  не прочитался" % имя)
            continue
        print("%-12s %6d %6.1f %8.2f %8.2f %9.0f  %s"
              % (имя, d["кадров"], d["с"], d["путь_м"], d["скорость"],
                 d["поворот"], d["род"]))


def main():
    argv = sys.argv[1:]
    if "--report" in argv:
        файлы = []
        for f in sorted(os.listdir(ПАПКА)):
            if f.endswith(".amc"):
                subj = f.split("_")[0]
                файлы.append((os.path.join(ПАПКА, subj + ".asf"),
                              os.path.join(ПАПКА, f)))
        отчёт(файлы)
        return
    имена = []
    if "--subject" in argv:
        i = argv.index("--subject")
        subj = argv[i + 1]
        n = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 10
        имена = ["%s_%02d" % (subj, k) for k in range(1, n + 1)]
    имена += [a for a in argv if re.fullmatch(r"\d+_\d+", a)]
    файлы = []
    for имя in имена:
        try:
            asf, amc, свежее = взять(имя)
            файлы.append((asf, amc))
            print("%-10s %s" % (имя, "скачан" if свежее else "уже был"))
        except Exception as e:
            print("%-10s НЕ ВЗЯЛСЯ: %s" % (имя, str(e)[:60]))
    print()
    отчёт(файлы)


if __name__ == "__main__":
    main()
