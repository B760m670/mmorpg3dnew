#!/usr/bin/env python3
"""ПОЧВА ИЗ РЕАЛЬНОГО ФОТО — верхний слой из настоящей местной почвы (фото
пользователя: сухой растрескавшийся суглинок Гатчины). Фото→бесшовный PBR:

  1. ДЕЛАЙТИНГ: убираем крупное освещение (делим на сильно размытую копию) —
     остаётся чистый альбедо, тени трещин уходят из цвета в геометрию.
  2. БЕСШОВНОСТЬ: кроп + смешение противоположных краёв (тайлируется).
  3. ВЫСОТА: из делит-яркости (трещины тёмные=низ, плитки=верх), трещины
     подчёркнуты. НОРМАЛЬ из высоты (собель). AO из высоты (в трещинах темнее).
  4. ШЕРОХОВАТОСТЬ: сухая почва матовая, лёгкая вариация.

Выход: game2/assets/materials/created/soil_gatchina/ (Color/Normal/Roughness/
Height/AmbientOcclusion) + превью под солнцем (relight в numpy — проверка глазами
в окружении, а не вслепую). Запуск: python3 tools/soil_from_photo.py <photo.jpg>
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, sobel

ROOT = os.path.join(os.path.dirname(__file__), "..")
CREATED = os.path.join(ROOT, "game2", "assets", "materials", "created")
RES = 2048


def srgb_to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def lin_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def make_tileable(img):
    """бесшовность методом OFFSET+HEAL (без зеркал): сдвиг на полтайла делает
    прежние края серединой (края становятся бесшовными по wrap), а новый шов в
    центре лечим мягким размытием ВДОЛЬ него — без зеркальных призраков."""
    n = img.shape[0]
    hlf = n // 2
    r = np.roll(np.roll(img, hlf, axis=0), hlf, axis=1)
    b = n // 96                                                             # узкая полоса лечения
    wnd = gaussian_filter(r, sigma=(3, 0, 0) if img.ndim == 3 else (3, 0))  # поперёк гориз. шва
    wvt = gaussian_filter(r, sigma=(0, 3, 0) if img.ndim == 3 else (0, 3))  # поперёк верт. шва
    a = (np.abs(np.arange(n) - hlf) / b).clip(0, 1)                          # 0 на шве..1 вне
    fy = a[:, None, None] if img.ndim == 3 else a[:, None]
    fx = a[None, :, None] if img.ndim == 3 else a[None, :]
    r = r * fy + wnd * (1 - fy)     # лечим горизонтальный шов (строка hlf)
    r = r * fx + wvt * (1 - fx)     # лечим вертикальный шов (столбец hlf)
    return r


def main():
    photo = sys.argv[1] if len(sys.argv) > 1 else \
        "/root/.claude/uploads/283ce6a4-bcad-5286-9fb2-0f049fba2e1d/64161fe0-IMG_3454.jpeg"
    name = sys.argv[2] if len(sys.argv) > 2 else "soil_gatchina"
    OUT = os.path.join(CREATED, name)
    os.makedirs(OUT, exist_ok=True)
    im = Image.open(photo).convert("RGB")
    # центральный квадрат (без виньетки/краёв), в рабочее разрешение
    w, h = im.size
    s = min(w, h)
    im = im.crop(((w - s) // 2, (h - s) // 2, (w + s) // 2, (h + s) // 2)).resize((RES, RES), Image.LANCZOS)
    rgb = np.asarray(im).astype(np.float32) / 255.0
    lin = srgb_to_lin(rgb)

    # --- 1. ДЕЛАЙТИНГ: убрать крупное освещение (делим на сильно размытую копию) ---
    lum = lin @ np.array([0.2126, 0.7152, 0.0722])
    low = gaussian_filter(lum, sigma=RES / 12.0) + 1e-4
    gain = (lum.mean() / low)[..., None]
    alb = np.clip(lin * gain, 0, 1)
    # трещины (тёмные борозды) — приподнять в АЛЬБЕДО (их темнота уходит в AO/высоту)
    flat = lum / low * lum.mean()
    crack = np.clip((flat.mean() - flat) / (flat.std() + 1e-4), 0, 3)   # >0 в трещинах
    alb = np.clip(alb + crack[..., None] * 0.05, 0, 1)

    # --- 2. БЕСШОВНОСТЬ ---
    alb = make_tileable(alb)

    # --- 3. ВЫСОТА / НОРМАЛЬ / AO ---
    lum2 = gaussian_filter(alb @ np.array([0.2126, 0.7152, 0.0722]), sigma=1.0)
    height = (lum2 - lum2.min()) / (lum2.max() - lum2.min())
    height = make_tileable(height)
    # трещины — врезать глубже (усилить борозды)
    height = np.clip(height - crack * 0.12, 0, 1)
    height = make_tileable(height)
    # нормаль (собель по высоте), сила бампа
    STR = 2.5
    gx = sobel(height, axis=1) * STR
    gy = sobel(height, axis=0) * STR
    nz = np.ones_like(height)
    nrm = np.stack([-gx, -gy, nz], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    nrm_img = ((nrm * 0.5 + 0.5) * 255).astype(np.uint8)
    # AO: впадины (низкая высота относительно окрестности) темнее
    ao = np.clip(0.6 + (height - gaussian_filter(height, sigma=8.0)) * 3.0, 0, 1)
    # шероховатость: матовая, чуть ниже на «полированных» плитках
    rough = np.clip(0.93 - height * 0.08, 0, 1)

    Image.fromarray((lin_to_srgb(alb) * 255).astype(np.uint8)).save(os.path.join(OUT, "Color.png"))
    Image.fromarray(nrm_img).save(os.path.join(OUT, "Normal.png"))
    Image.fromarray((rough * 255).astype(np.uint8)).save(os.path.join(OUT, "Roughness.png"))
    Image.fromarray((height * 255).astype(np.uint8)).save(os.path.join(OUT, "Height.png"))
    Image.fromarray((ao * 255).astype(np.uint8)).save(os.path.join(OUT, "AmbientOcclusion.png"))

    # --- ПРОВЕРКА ЧИСЛАМИ ---
    print("soil_gatchina из фото:", os.path.basename(photo))
    print("  альбедо linear (делит) = %.3f/%.3f/%.3f" % tuple(alb.reshape(-1, 3).mean(0)))
    print("  высота σ=%.3f  трещин(доля crack>0.5)=%.1f%%" % (height.std(), 100 * (crack > 0.5).mean()))

    # --- ПРЕВЬЮ: relight под наклонным солнцем (albedo*NdotL + ambient), чтобы
    #     ГЛАЗАМИ увидеть рельеф трещин, а не вслепую ---
    L = np.array([0.5, 0.5, 0.7]); L = L / np.linalg.norm(L)
    ndl = np.clip(nrm @ L, 0, 1)
    lit = lin_to_srgb(alb * (0.25 * ao[..., None] + 0.9 * ndl[..., None]))
    prev = (np.clip(lit, 0, 1) * 255).astype(np.uint8)
    # 2×2 тайл — проверить бесшовность
    tile = np.concatenate([np.concatenate([prev, prev], 1), np.concatenate([prev, prev], 1)], 0)
    Image.fromarray(tile).resize((900, 900)).save("/tmp/%s_preview.png" % name)
    print("  превью 2×2 (relight) → /tmp/%s_preview.png [%s]" % (name, name))


if __name__ == "__main__":
    main()
