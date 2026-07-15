#!/usr/bin/env python3
"""Станок №8: ИНЖЕНЕРНОЕ ЗРЕНИЕ ЛИЦА (MediaPipe FaceMesh, 478 ландмарок).

Меряет лицо на изображении (наш рендер ИЛИ фотография) и выдаёт:
  • антропометрические отношения против канонов пластической анатомии,
  • асимметрию по зонам (в % от ширины лица),
  • разметку поверх изображения (*_landmarks.png),
  • JSON с сырыми точками — для сравнения рендера с эталонными фото
    (лупа сходства: рендер → сравнение → правка таргетов MPFB).

Запуск: python3 tools/face_audit.py <image.png> [--json out.json]
"""
import sys, os, json, math
import cv2
import numpy as np
import mediapipe as mp

# ключевые индексы канонической сетки FaceMesh
L = {
    "iris_r": 468, "iris_l": 473,          # центры зрачков (refine)
    "eye_r_out": 33, "eye_r_in": 133,      # правый глаз (со стороны субъекта)
    "eye_l_in": 362, "eye_l_out": 263,
    "brow_r": 105, "brow_l": 334, "glabella": 9,
    "nose_tip": 4, "subnasale": 2,
    "ala_r": 49, "ala_l": 279,
    "mouth_r": 61, "mouth_l": 291, "lip_top": 0, "lip_bot": 17,
    "menton": 152, "forehead_top": 10,
    "zyg_r": 234, "zyg_l": 454,            # ширина лица на уровне скул
    "jaw_r": 132, "jaw_l": 361,            # ширина ниже (углы челюсти)
}
# пары для оценки асимметрии (правый, левый)
SYM_PAIRS = [("eye_r_out", "eye_l_out"), ("eye_r_in", "eye_l_in"),
             ("brow_r", "brow_l"), ("ala_r", "ala_l"),
             ("mouth_r", "mouth_l"), ("zyg_r", "zyg_l"), ("jaw_r", "jaw_l")]

def audit(path, json_out=None):
    img = cv2.imread(path)
    if img is None:
        raise SystemExit("нет изображения: " + path)
    h, w = img.shape[:2]
    fm = mp.solutions.face_mesh.FaceMesh(static_image_mode=True,
                                         refine_landmarks=True, max_num_faces=1)
    res = fm.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
    if not res.multi_face_landmarks:
        raise SystemExit("лицо не распознано: " + path)
    lms = res.multi_face_landmarks[0].landmark
    P = {k: np.array([lms[i].x * w, lms[i].y * h]) for k, i in L.items()}
    ALL = np.array([[p.x * w, p.y * h] for p in lms])

    def d(a, b):
        return float(np.linalg.norm(P[a] - P[b]))

    ipd = d("iris_r", "iris_l")
    brow_y = (P["brow_r"][1] + P["brow_l"][1]) / 2
    mid_third = P["subnasale"][1] - brow_y
    low_third = P["menton"][1] - P["subnasale"][1]
    bizygo = d("zyg_r", "zyg_l")
    bigonial = d("jaw_r", "jaw_l")
    intercanthal = d("eye_r_in", "eye_l_in")
    eye_w = (d("eye_r_out", "eye_r_in") + d("eye_l_in", "eye_l_out")) / 2
    alar = d("ala_r", "ala_l")
    mouth = d("mouth_r", "mouth_l")
    face_h = P["menton"][1] - brow_y

    # асимметрия: у пар |xR+xL-2*mid| / ширина лица
    midx = np.mean([P[k][0] for k in ("glabella", "nose_tip", "subnasale", "menton")])
    asym = {}
    for r, l in SYM_PAIRS:
        asym[r + "/" + l] = abs((P[r][0] - midx) + (P[l][0] - midx)) / bizygo * 100

    def verdict(val, lo, hi):
        if val < lo: return f"{val:.2f}  МАЛО (канон {lo}-{hi})"
        if val > hi: return f"{val:.2f}  МНОГО (канон {lo}-{hi})"
        return f"{val:.2f}  ok (канон {lo}-{hi})"

    rows = [
        ("Средняя/нижняя трети", verdict(mid_third / max(low_third, 1e-6), 0.9, 1.1)),
        ("Межслёзное/ширина глаза", verdict(intercanthal / max(eye_w, 1e-6), 0.9, 1.25)),
        ("Крылья носа/межслёзное", verdict(alar / max(intercanthal, 1e-6), 0.95, 1.15)),
        ("Рот/IPD", verdict(mouth / max(ipd, 1e-6), 0.75, 0.95)),
        ("Лицевой индекс (высота/скуловая)", verdict(face_h / max(bizygo, 1e-6), 0.80, 0.95)),
        ("Челюсть/скулы", verdict(bigonial / max(bizygo, 1e-6), 0.72, 0.88)),
        ("Глаз-в-глазах (5 глаз в скуловой)", verdict(bizygo / max(eye_w, 1e-6), 4.4, 5.4)),
    ]
    print(f"=== АУДИТ ЛИЦА: {os.path.basename(path)} (IPD={ipd:.0f}px) ===")
    for name, v in rows:
        print(f"  {name:38s} {v}")
    print("  --- асимметрия (% от скуловой ширины; >1.5% заметно) ---")
    for k, v in asym.items():
        flag = " !!" if v > 1.5 else ""
        print(f"  {k:38s} {v:.2f}%{flag}")

    # разметка
    vis = img.copy()
    for x, y in ALL.astype(int):
        cv2.circle(vis, (x, y), 1, (0, 255, 0), -1)
    for k in L:
        x, y = P[k].astype(int)
        cv2.circle(vis, (x, y), 3, (0, 0, 255), -1)
    out_png = os.path.splitext(path)[0] + "_landmarks.png"
    cv2.imwrite(out_png, vis)
    print("  разметка ->", out_png)

    data = {"image": path, "ipd_px": ipd,
            "metrics": {n: v for n, v in rows}, "asymmetry_pct": asym,
            "landmarks_px": {k: P[k].tolist() for k in P},
            "all_landmarks": ALL.tolist()}
    if json_out:
        with open(json_out, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        print("  json ->", json_out)
    return data

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    jo = None
    if "--json" in sys.argv:
        jo = sys.argv[sys.argv.index("--json") + 1]
    audit(args[0], jo)
