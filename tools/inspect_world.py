#!/usr/bin/env python3
"""Инструмент восприятия мира («вход внутрь ядра»).

Прогоняет game2 на стенде по батарее (сутки + облёт), собирает по каждому кадру
числа состояния мира (положение Солнца, энергия/цвет света, рельеф) и метрики
изображения (гистограмма яркости), и складывает прозрачный отчёт: контактные
листы кадров + таблицу чисел. Это не «вроде норм на скрине», а измеримый взгляд.

Запуск:  python3 tools/inspect_world.py
"""
import json
import os
import re
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

SP = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad"
BIN = f"{SP}/godot-fork/bin/godot.linuxbsd.editor.x86_64"
GAME = os.path.join(os.path.dirname(__file__), "..", "game2")
OUT = f"{SP}/inspect"
os.makedirs(OUT, exist_ok=True)

STATE_RE = re.compile(r"STATE (\{.*\})")


def run_frame(name, utc, campos, camlook):
    """Один прогон: рендер + выгрузка STATE. Возвращает (png_path, state|None)."""
    png = f"{OUT}/{name}.png"
    cmd = [
        "xvfb-run", "-a", BIN,
        "--rendering-driver", "vulkan", "--rendering-method", "forward_plus",
        "--path", GAME, "--",
        "--inspect", f"--utc={utc}", f"--campos={campos}", f"--camlook={camlook}",
        f"--out={png}",
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        print(f"  [{name}] TIMEOUT")
        return png, None
    state = None
    for line in r.stdout.splitlines():
        m = STATE_RE.search(line)
        if m:
            state = json.loads(m.group(1))
    if state is None:
        print(f"  [{name}] нет STATE (stdout хвост): {r.stdout.strip()[-200:]}")
    return png, state


def lum_stats(png):
    """Метрики яркости кадра (без области HUD слева-сверху)."""
    if not os.path.exists(png):
        return None
    im = np.asarray(Image.open(png).convert("RGB"), dtype=np.float32)
    h, w, _ = im.shape
    L = 0.299 * im[..., 0] + 0.587 * im[..., 1] + 0.114 * im[..., 2]
    mask = np.ones((h, w), bool)
    mask[: int(h * 0.42), : int(w * 0.52)] = False  # вырезаем HUD
    v = L[mask]
    return {
        "min": float(v.min()), "mean": float(v.mean()),
        "p5": float(np.percentile(v, 5)), "p95": float(np.percentile(v, 95)),
        "max": float(v.max()), "range": float(v.max() - v.min()),
    }


def contact_sheet(frames, cols, path, cell_w=440):
    """Сетка кадров с подписями (время, высота Солнца, ср.яркость)."""
    imgs = []
    for f in frames:
        if not os.path.exists(f["png"]):
            continue
        im = Image.open(f["png"]).convert("RGB")
        ch = int(cell_w * im.size[1] / im.size[0])
        im = im.resize((cell_w, ch))
        d = ImageDraw.Draw(im)
        st = f.get("state") or {}
        ls = f.get("lum") or {}
        label = "%s  el=%s°" % (f["name"], st.get("sun_el", "?"))
        label2 = "L ср=%.0f  диап=%.0f" % (ls.get("mean", 0), ls.get("range", 0))
        for i, t in enumerate((label, label2)):
            d.text((8, 6 + i * 16), t, fill=(255, 255, 0))
        imgs.append(im)
    if not imgs:
        return
    cw, chh = imgs[0].size
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cw, rows * chh), (20, 20, 24))
    for i, im in enumerate(imgs):
        sheet.paste(im, ((i % cols) * cw, (i // cols) * chh))
    sheet.save(path)
    print("сохранил", path, sheet.size)


def main():
    report = ["# Взгляд изнутри мира — отчёт инспекции\n"]

    # 1) СУТКИ: фиксированная точка обзора, время по кругу (местное = UTC+3)
    print("== СУТКИ ==")
    day_cam = ("40,18,40", "0,2,0")
    day_utc = ["01:00", "03:00", "05:00", "07:00", "10:00", "13:00", "16:00", "19:00"]
    day_frames = []
    for u in day_utc:
        name = "day_%s" % u.replace(":", "")
        png, st = run_frame(name, u, *day_cam)
        lum = lum_stats(png)
        day_frames.append({"name": u, "png": png, "state": st, "lum": lum})
        if st:
            print("  %s local=%s el=%5.1f° az=%5.1f° %s E=%.2f L.ср=%s" % (
                u, st["local"].split()[1], st["sun_el"], st["sun_az"],
                "день" if st["daytime"] else "ночь", st["sun_energy"],
                round(lum["mean"], 0) if lum else "?"))
    contact_sheet(day_frames, 4, f"{OUT}/day_cycle.png")

    report.append("## Сутки над Гатчиной (одна точка обзора)\n")
    report.append("| местное | высота☉ | азимут☉ | день/ночь | энергия☉ | L ср | L диапазон |")
    report.append("|--|--|--|--|--|--|--|")
    for f in day_frames:
        st, lm = f.get("state"), f.get("lum")
        if not st:
            report.append(f"| {f['name']} | — сбой — |||||| ")
            continue
        report.append("| %s | %.1f° | %.0f° | %s | %.2f | %.0f | %.0f |" % (
            st["local"].split()[1] if " " in st["local"] else f["name"],
            st["sun_el"], st["sun_az"], "день" if st["daytime"] else "ночь",
            st["sun_energy"], lm["mean"] if lm else 0, lm["range"] if lm else 0))

    # 2) ОБЛЁТ: фиксированное время (местное 10:00), камера по окружности
    print("== ОБЛЁТ (местное 10:00) ==")
    turn_frames = []
    R, H = 34.0, 14.0
    for deg in range(0, 360, 60):
        rad = np.radians(deg)
        cx, cz = R * np.cos(rad), R * np.sin(rad)
        name = "turn_%03d" % deg
        png, st = run_frame(name, "07:00", f"{cx:.1f},{H},{cz:.1f}", "0,1,0")
        lum = lum_stats(png)
        turn_frames.append({"name": "%d°" % deg, "png": png, "state": st, "lum": lum})
    contact_sheet(turn_frames, 3, f"{OUT}/turntable.png")

    open(f"{OUT}/report.md", "w").write("\n".join(report) + "\n")
    print("\nОтчёт:", f"{OUT}/report.md")
    print("Контактные листы:", f"{OUT}/day_cycle.png", f"{OUT}/turntable.png")


if __name__ == "__main__":
    main()
