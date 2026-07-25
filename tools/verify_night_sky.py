#!/usr/bin/env python3
"""Сверка НЕБЕСНОЙ МЕХАНИКИ ночного неба ЧИСЛАМИ (закон проекта: не на глаз).

Проверяет ровно ту математику, что уходит в night_sky.gd / world_clock.gd:
  1. GMST (звёздное время) — против опорного значения J2000.
  2. Матрица экватор→горизонт (runtime-поворот купола звёзд) ДОЛЖНА совпасть
     со скалярной формулой alt/az для тех же (RA,Dec) — две независимые дороги.
  3. Луна (Meeus, упрощ.): освещённая доля ≈0 у новолуния, ≈1 у полнолуния.
Конвенции движка: X=восток, Y=вверх, север=−Z (как у Солнца в world_clock.gd).
"""
import math

RAD = math.pi / 180.0
DEG = 180.0 / math.pi
LAT = 59.5648          # Гатчина
LON = 30.1282          # восток +


def julian(unix):
    return unix / 86400.0 + 2440587.5


def unix_of(y, mo, d, h, mi, s):
    # UTC → unix (без часовых поясов), григорианский
    a = (14 - mo) // 12
    yy = y + 4800 - a
    mm = mo + 12 * a - 3
    jdn = d + (153 * mm + 2) // 5 + 365 * yy + yy // 4 - yy // 100 + yy // 400 - 32045
    jd = jdn + (h - 12) / 24.0 + mi / 1440.0 + s / 86400.0
    return (jd - 2440587.5) * 86400.0


def gmst_deg(unix):
    # IAU 1982 средн. звёздное время в Гринвиче, градусы
    jd = julian(unix)
    d = jd - 2451545.0
    t = d / 36525.0
    g = 280.46061837 + 360.98564736629 * d + 0.000387933 * t * t - t * t * t / 38710000.0
    return g % 360.0


def lst_deg(unix):
    return (gmst_deg(unix) + LON) % 360.0


# ---------- Способ A: единая матрица экватор(J2000-декартов)→горизонт(движок) ----------
def rot_z(a):
    c, s = math.cos(a), math.sin(a)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def matmul(A, B):
    return [[sum(A[i][k] * B[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def matvec(M, v):
    return [sum(M[i][k] * v[k] for k in range(3)) for i in range(3)]


def equ_to_horizon_basis(unix):
    """Возвращает 3x3 M: горизонт(движок XYZ, север=−Z) = M · экв_вектор(RA,Dec).
    экв_вектор v0 = (cosDec cosRA, cosDec sinRA, sinDec)."""
    phi = LAT * RAD
    lst = lst_deg(unix) * RAD
    cp, sp = math.cos(phi), math.sin(phi)
    # R: часовой-угол-кадр q=(cosDec cosH, cosDec sinH, sinDec) → движок(X=вост,Y=верх,Z=юг)
    #   q_x(H=0,eq)=(0,cosφ,sinφ) юг+верх; q_y(H=90,eq)=(−1,0,0) запад; q_z(NCP)=(0,sinφ,−cosφ) сев+верх
    R = [[0.0, -1.0, 0.0],
         [cp, 0.0, sp],
         [sp, 0.0, -cp]]
    # q = Rz(−LST)·v0, но с y-флипом (H=LST−RA): берём Rz(−LST) и инвертируем Y-строку
    RzL = rot_z(-lst)
    FY = [[1, 0, 0], [0, -1, 0], [0, 0, 1]]     # y-флип: sin(RA−LST) → −sin(LST−RA)
    return matmul(R, matmul(FY, RzL))


def dir_from_basis(unix, ra_deg, dec_deg):
    ra, dec = ra_deg * RAD, dec_deg * RAD
    v0 = [math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)]
    return matvec(equ_to_horizon_basis(unix), v0)


# ---------- Способ B: независимая скалярная формула alt/az ----------
def dir_scalar(unix, ra_deg, dec_deg):
    phi = LAT * RAD
    H = (lst_deg(unix) - ra_deg) * RAD
    dec = dec_deg * RAD
    sinalt = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(H)
    sinalt = max(-1.0, min(1.0, sinalt))
    alt = math.asin(sinalt)
    ca = math.cos(alt)
    sinA_ca = -math.cos(dec) * math.sin(H)
    cosA_ca = math.sin(dec) * math.cos(phi) - math.cos(dec) * math.sin(phi) * math.cos(H)
    A = math.atan2(sinA_ca, cosA_ca)             # азимут от СЕВЕРА к востоку
    return [ca * math.sin(A), math.sin(alt), -ca * math.cos(A)], alt * DEG, (A * DEG) % 360.0


# ---------- Луна: Meeus (упрощ., гл. 47) ----------
def moon(unix):
    jd = julian(unix)
    T = (jd - 2451545.0) / 36525.0
    Lp = (218.3164477 + 481267.88123421 * T) % 360.0        # средн. долгота
    D = (297.8501921 + 445267.1114034 * T) % 360.0          # элонгация
    M = (357.5291092 + 35999.0502909 * T) % 360.0           # аномалия Солнца
    Mp = (134.9633964 + 477198.8675055 * T) % 360.0         # аномалия Луны
    F = (93.272095 + 483202.0175233 * T) % 360.0            # арг. широты
    d, m, mp, f = D * RAD, M * RAD, Mp * RAD, F * RAD
    lon = Lp + (6.288774 * math.sin(mp) + 1.274027 * math.sin(2 * d - mp)
                + 0.658314 * math.sin(2 * d) + 0.213618 * math.sin(2 * mp)
                - 0.185116 * math.sin(m) - 0.114332 * math.sin(2 * f))
    lat = (5.128122 * math.sin(f) + 0.280602 * math.sin(mp + f)
           + 0.277693 * math.sin(mp - f) + 0.173237 * math.sin(2 * d - f))
    # эклиптика → экватор
    eps = 23.43929 * RAD
    ll, bb = lon * RAD, lat * RAD
    ra = math.atan2(math.sin(ll) * math.cos(eps) - math.tan(bb) * math.sin(eps), math.cos(ll))
    dec = math.asin(math.sin(bb) * math.cos(eps) + math.cos(bb) * math.sin(eps) * math.sin(ll))
    # фаза: угол Солнце–Земля–Луна (элонгация от Солнца по долготе как приближение)
    sun_lon = (280.46646 + 36000.76983 * T) % 360.0
    elong = (lon - sun_lon) % 360.0
    illum = (1.0 - math.cos(elong * RAD)) / 2.0
    return ra * DEG % 360.0, dec * DEG, illum, elong


def main():
    print("=== ЗВЁЗДНОЕ ВРЕМЯ (GMST) ===")
    g = gmst_deg(unix_of(2000, 1, 1, 12, 0, 0))
    print("  J2000 12:00 UT: GMST=%.4f° (%.4fh)  опора 280.4606° / 18.6974h  err=%.4f°"
          % (g, g / 15.0, abs(g - 280.46061837)))

    print("\n=== МАТРИЦА экватор→горизонт == скалярная alt/az (две независимые дороги) ===")
    tests = [
        ("Сириус HR2491", 101.287, -16.716),
        ("Вега HR7001", 279.235, +38.784),
        ("Полярная HR424", 37.955, +89.264),
        ("Бетельгейзе HR2061", 88.793, +7.407),
        ("южный тест", 120.0, -70.0),
    ]
    u = unix_of(2025, 1, 15, 22, 0, 0)
    maxerr = 0.0
    print("  время UTC 2025-01-15 22:00, Гатчина")
    for name, ra, dec in tests:
        da = dir_from_basis(u, ra, dec)
        db, alt, az = dir_scalar(u, ra, dec)
        err = max(abs(da[i] - db[i]) for i in range(3))
        maxerr = max(maxerr, err)
        na = math.sqrt(sum(x * x for x in da))
        print("  %-20s alt=%+6.2f° az=%6.2f°  |Δвектор|=%.2e  |M·v|=%.4f"
              % (name, alt, az, err, na))
    print("  МАКС |Δ| = %.2e  → %s" % (maxerr, "OK — матрица верна" if maxerr < 1e-9 else "ПРОВАЛ"))

    print("\n=== ЛУНА: освещённая доля у новолуния/полнолуния 2000 ===")
    # опорные события: новолуние 2000-01-06 18:14 UT; полнолуние 2000-01-21 04:40 UT
    for label, (y, mo, d, h, mi), exp in [
        ("новолуние 2000-01-06", (2000, 1, 6, 18, 14), 0.0),
        ("полнолуние 2000-01-21", (2000, 1, 21, 4, 40), 1.0),
        ("перв.четверть+~", (2000, 1, 14, 13, 34), 0.5),
    ]:
        ra, dec, illum, elong = moon(unix_of(y, mo, d, h, mi, 0))
        print("  %-22s элонгация=%6.2f°  освещено=%.3f (ожид ~%.1f)  RA=%.2f° Dec=%+.2f°"
              % (label, elong, illum, exp, ra, dec))


if __name__ == "__main__":
    main()
