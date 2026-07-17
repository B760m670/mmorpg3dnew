#!/usr/bin/env python3
"""Карта генплана v2 — РЕАЛЬНЫЕ контуры Гатчины поверх реального рельефа.

Слои из game2/data/real (Overture): землепользование, вода, дороги/ж-д,
здания; ориентиры из game2/data/master_plan.json. Фон — теневая отмывка DEM.

Запуск: python3 tools/render_master_plan.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), "..")
PLAN = json.load(open(os.path.join(ROOT, "game2", "data", "master_plan.json")))
REAL = os.path.join(ROOT, "game2", "data", "real")
DEM = os.path.join(ROOT, "game2", "assets", "dem", "gatchina_cm.bin")
OUT = "/tmp/claude-0/-home-user-mmorpg3dnew/45dce9e0-e4bb-550f-b915-c58072470dda/scratchpad/master_plan.png"

EXT = 3000                    # показываем центр: -EXT..+EXT м
PX = 1600
S = PX / (2.0 * EXT)

FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
FONT_S = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 17)
FONT_B = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)

LU_FILL = {
    "park": (90, 155, 80, 110), "garden": (90, 155, 80, 110),
    "grass": (120, 170, 95, 90), "meadow": (140, 180, 100, 90),
    "recreation_ground": (110, 165, 90, 90),
    "forest": (45, 110, 55, 120), "wood": (45, 110, 55, 120),
    "farmland": (200, 195, 120, 70), "orchard": (150, 180, 90, 80),
    "cemetery": (120, 140, 110, 80), "residential": (205, 170, 120, 55),
    "military": (170, 150, 130, 60),
}


def to_px(p):
    return (PX / 2 + p[0] * S, PX / 2 - p[1] * S)


def hillshade_bg():
    g = np.fromfile(DEM, dtype="<i2").reshape(513, 513) / 100.0
    n = int(EXT / 32)
    c = 256
    sub = g[c - n:c + n + 1, c - n:c + n + 1]
    gy, gx = np.gradient(sub, 32.0)
    az, alt = np.radians(315.0), np.radians(45.0)
    slope = np.arctan(np.hypot(gx, gy) * 2.0)
    aspect = np.arctan2(-gx, gy)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    hs = np.clip((hs + 1) / 2, 0, 1)
    t = (sub - sub.min()) / max(1e-6, (sub.max() - sub.min()))
    base = np.stack([190 + 40 * t, 188 + 34 * t, 172 + 30 * t], axis=-1)
    img = (base * (0.6 + 0.4 * hs[..., None])).astype(np.uint8)
    return Image.fromarray(img).resize((PX, PX), Image.BILINEAR)


def draw_polys(d, rec, fill, outline=None, width=1):
    for poly in rec.get("polys", []):
        for k, ring in enumerate(poly):
            if len(ring) < 3:
                continue
            f = (0, 0, 0, 0) if k > 0 else fill      # дырки не заливаем
            d.polygon([to_px(p) for p in ring], fill=f,
                      outline=outline, width=width)


def main():
    img = hillshade_bg().convert("RGBA")
    ov = Image.new("RGBA", (PX, PX), (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)

    landuse = json.load(open(os.path.join(REAL, "landuse.json")))
    for z in landuse:
        f = LU_FILL.get(z["class"])
        if f:
            draw_polys(d, z, f)

    roads = json.load(open(os.path.join(REAL, "roads.json")))
    order = {"rail": 0, "residential": 1, "unclassified": 1, "living_street": 1,
             "pedestrian": 1, "tertiary": 2, "secondary": 3, "primary": 4,
             "trunk": 5, "motorway": 5}
    for r in sorted(roads, key=lambda r: order.get(r["class"] if r["kind"] == "road" else "rail", 1)):
        if r["kind"] == "rail":
            col, w = (60, 55, 60, 235), 4
        elif r["class"] in ("primary", "trunk", "motorway"):
            col, w = (250, 235, 190, 245), 7
        elif r["class"] in ("secondary", "tertiary"):
            col, w = (250, 245, 215, 235), 5
        else:
            col, w = (255, 255, 255, 200), 3
        for line in r.get("lines", []):
            d.line([to_px(p) for p in line], fill=col, width=w, joint="curve")

    water = json.load(open(os.path.join(REAL, "water.json")))
    for w in water:
        draw_polys(d, w, (70, 125, 185, 235), outline=(35, 80, 130), width=2)
        for line in w.get("lines", []):
            d.line([to_px(p) for p in line], fill=(70, 125, 185, 235), width=4, joint="curve")

    buildings = json.load(open(os.path.join(REAL, "buildings.json")))
    for b in buildings:
        draw_polys(d, b, (95, 85, 80, 190))

    img = Image.alpha_composite(img, ov)
    d = ImageDraw.Draw(img)

    for lm in PLAN["landmarks"]:
        x, y = to_px(lm["pos"])
        d.ellipse([x - 8, y - 8, x + 8, y + 8], fill=(185, 25, 25),
                  outline=(255, 255, 255), width=3)
        d.text((x + 12, y - 14), lm["name"], font=FONT, fill=(35, 15, 10),
               stroke_width=4, stroke_fill=(255, 255, 255))

    # подписи крупных озёр
    lake_labels = {"Белое озеро", "Серебряное озеро", "Чёрное озеро", "Колпанское озеро"}
    for w in water:
        if w.get("name") in lake_labels and w.get("polys"):
            ring = w["polys"][0][0]
            cx = sum(p[0] for p in ring) / len(ring)
            cy = sum(p[1] for p in ring) / len(ring)
            d.text(to_px((cx, cy)), w["name"], font=FONT_S, fill=(10, 35, 75),
                   anchor="mm", stroke_width=3, stroke_fill=(225, 235, 250))

    d.text((20, 14), PLAN["title"] + " — контуры РЕАЛЬНЫЕ", font=FONT_B,
           fill=(20, 15, 10), stroke_width=4, stroke_fill=(255, 255, 255))
    d.text((20, 50), "вода/парки/улицы/здания: Overture Maps (реальные данные) · фон: реальный рельеф",
           font=FONT_S, fill=(70, 45, 25), stroke_width=3, stroke_fill=(255, 255, 255))
    x0, y0 = 30, PX - 40
    d.line([(x0, y0), (x0 + 1000 * S, y0)], fill=(0, 0, 0), width=5)
    d.text((x0 + 500 * S, y0 - 12), "1 км", font=FONT_S, fill=(0, 0, 0),
           anchor="mm", stroke_width=3, stroke_fill=(255, 255, 255))

    img.convert("RGB").save(OUT)
    print("карта:", OUT)


if __name__ == "__main__":
    main()
