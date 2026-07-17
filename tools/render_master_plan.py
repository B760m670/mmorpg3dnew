#!/usr/bin/env python3
"""Карта генплана: зоны/вода/дороги/ориентиры поверх РЕАЛЬНОГО рельефа Гатчины.

Фон — теневая отмывка (hillshade) нашей сетки высот (реальные измерения),
поверх — слои из game2/data/master_plan.json. Выход — PNG на утверждение.

Запуск: python3 tools/render_master_plan.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLAN = json.load(open(os.path.join(ROOT, "game2", "data", "master_plan.json")))
DEM = os.path.join(ROOT, "game2", "assets", "dem", "gatchina_cm.bin")
OUT = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/master_plan.png"

# охват карты (м от дворца) и размер изображения
EXT = 4200                    # -EXT..+EXT по обеим осям
PX = 1500
S = PX / (2.0 * EXT)          # пикселей на метр

FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
FONT_S = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
FONT_B = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)


def to_px(p):
    """(восток, север) м → пиксели (x вправо, y вниз)"""
    return (PX / 2 + p[0] * S, PX / 2 - p[1] * S)


def hillshade_bg():
    g = np.fromfile(DEM, dtype="<i2").reshape(513, 513) / 100.0
    # окно ±EXT из сетки (шаг 32 м, центр 256)
    n = int(EXT / 32)
    c = 256
    sub = g[c - n:c + n + 1, c - n:c + n + 1]
    gy, gx = np.gradient(sub, 32.0)
    # свет с северо-запада, высота 45°
    az, alt = np.radians(315.0), np.radians(45.0)
    slope = np.arctan(np.hypot(gx, gy))
    aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip((hs + 1) / 2, 0, 1)
    # высотная подкраска: ниже — темнее и зеленее, выше — светлее и суше
    t = (sub - sub.min()) / max(1e-6, (sub.max() - sub.min()))
    base = np.stack([
        168 + 50 * t, 172 + 40 * t, 150 + 34 * t], axis=-1)
    img = (base * (0.55 + 0.45 * hs[..., None])).astype(np.uint8)
    return Image.fromarray(img).resize((PX, PX), Image.BILINEAR)


ZONE_STYLE = {
    "парк": ((70, 140, 60, 70), (40, 110, 40)),
    "лес": ((30, 100, 40, 80), (20, 80, 30)),
    "город": ((200, 150, 90, 60), (150, 100, 50)),
    "поля": ((190, 190, 110, 40), (150, 150, 80)),
}


def main():
    img = hillshade_bg().convert("RGB")
    ov = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    for z in PLAN["zones"]:
        fill, outline = ZONE_STYLE.get(z["kind"], ((120, 120, 120, 40), (90, 90, 90)))
        d.polygon([to_px(p) for p in z["poly"]], fill=fill, outline=outline, width=3)

    for r in PLAN["roads"]:
        pts = [to_px(p) for p in r["line"]]
        w = max(2, int(r["width_m"] * S * 2.2))
        col = (70, 70, 75, 230) if r["kind"] == "железная дорога" else (235, 220, 180, 235)
        d.line(pts, fill=col, width=w, joint="curve")

    for w in PLAN["water"]:
        if "poly" in w:
            d.polygon([to_px(p) for p in w["poly"]], fill=(60, 110, 170, 200),
                      outline=(30, 70, 120), width=3)
        else:
            d.line([to_px(p) for p in w["line"]],
                   fill=(60, 110, 170, 220), width=max(3, int(w["width_m"] * S * 2)),
                   joint="curve")

    img = Image.alpha_composite(img.convert("RGBA"), ov)
    d = ImageDraw.Draw(img)

    for lm in PLAN["landmarks"]:
        x, y = to_px(lm["pos"])
        d.ellipse([x - 7, y - 7, x + 7, y + 7], fill=(180, 30, 30), outline=(255, 255, 255), width=2)
        d.text((x + 11, y - 13), lm["name"], font=FONT_S, fill=(30, 20, 15),
               stroke_width=3, stroke_fill=(255, 255, 255))

    # подписи зон и воды
    for z in PLAN["zones"]:
        cx = sum(p[0] for p in z["poly"]) / len(z["poly"])
        cy = sum(p[1] for p in z["poly"]) / len(z["poly"])
        x, y = to_px((cx, cy))
        d.text((x, y), z["name"], font=FONT, fill=(25, 45, 25), anchor="mm",
               stroke_width=3, stroke_fill=(240, 245, 235))
    for w in PLAN["water"]:
        pts = w.get("poly") or w["line"]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        x, y = to_px((cx, cy))
        d.text((x, y + 14), w["name"], font=FONT_S, fill=(15, 40, 80), anchor="mm",
               stroke_width=3, stroke_fill=(235, 240, 250))

    # заголовок, легенда, масштаб
    d.text((20, 14), PLAN["title"], font=FONT_B, fill=(20, 15, 10),
           stroke_width=4, stroke_fill=(255, 255, 255))
    d.text((20, 50), PLAN["status"], font=FONT_S, fill=(90, 30, 30),
           stroke_width=3, stroke_fill=(255, 255, 255))
    # шкала 1 км
    x0, y0 = 30, PX - 40
    d.line([(x0, y0), (x0 + 1000 * S, y0)], fill=(0, 0, 0), width=5)
    d.text((x0 + 500 * S, y0 - 12), "1 км", font=FONT_S, fill=(0, 0, 0), anchor="mm",
           stroke_width=3, stroke_fill=(255, 255, 255))
    d.text((PX - 30, PX - 40), "фон: реальный рельеф (DEM), отмывка", font=FONT_S,
           fill=(60, 60, 60), anchor="rm", stroke_width=3, stroke_fill=(255, 255, 255))

    img.convert("RGB").save(OUT)
    print("карта:", OUT)


if __name__ == "__main__":
    main()
