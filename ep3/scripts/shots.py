# -*- coding: utf-8 -*-
"""
Rikenomics 宇宙スケールシリーズ 第3話「太陽系の螺旋」
台本データ + ジオメトリ生成の共通モジュール。全ステージのスクリプトから import して使う。

設計方針:
  - 惑星の位置はJPLの近似軌道要素(Standish, 1800-2050年有効)からケプラー方程式を解いて求め、
    軌跡の先頭をEPOCH(2026-10-01)の実際の配置にする。周期・離心率・軌道傾斜も実物通り。
  - 軌道半径だけは模式表現(RADIUS_MODE="uniform": 太陽から等間隔)にする。方向は実物のまま、
    距離だけを等間隔に置き換える。実半径＋周期誇張や等間隔＋周期誇張は、内側惑星が団子になる/
    ループして「渦」表現になるため不採用。動画内・投稿文で「軌道の間隔は模式的」と明記すること。
  - 黄道面と太陽の進行方向の関係は、銀河座標→赤道座標→黄道座標の回転行列から厳密に求める
    (進行方向と黄道面の角度は約60°になる)。角度だけ合わせた簡略モデルは傾きの向きが逆だった。

シーン座標系:
  +X = 銀河回転の方向(銀経90°、太陽の進行方向)、+Z = 銀河北極、+Y = 銀河反中心(銀経180°)。
  銀河中心は-Y方向、銀河面はX-Y平面。
"""

import math
from datetime import datetime, timedelta, timezone

FPS = 30

AU_KM = 1.495978707e8  # 1天文単位(km)
YEAR_S = 3.15576e7  # 1年(秒)
SUN_GALACTIC_VELOCITY_KMS = 220.0  # 太陽の銀河公転速度(秒速約220km)

EPOCH = datetime(2026, 10, 1, tzinfo=timezone.utc)  # 軌跡の先頭(=現在)とする日付
TIME_SPAN_YEARS = 3.0  # EPOCHから遡って描く時間幅(全惑星共通)

RADIUS_MODE = "uniform"  # "uniform"=等間隔の模式表現 / "real"=実際の距離
UNIFORM_SPACING = 0.6  # uniform時の隣り合う軌道の間隔(ユニット)。8惑星で海王星が半径4.8に収まる
SCALE_AU = 0.6  # 1AUをBlenderの何ユニットにするか(太陽の前進距離とreal時の半径に使用)

DISPLAY = ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune"]

PLANET_COLORS = {
    "Mercury": (0.60, 0.60, 0.60, 1),
    "Venus": (0.90, 0.85, 0.60, 1),
    "Earth": (0.25, 0.55, 0.95, 1),
    "Mars": (0.85, 0.35, 0.20, 1),
    "Jupiter": (0.85, 0.70, 0.45, 1),
    "Saturn": (0.90, 0.80, 0.55, 1),
    "Uranus": (0.55, 0.85, 0.90, 1),
    "Neptune": (0.25, 0.35, 0.90, 1),
}

# JPL "Keplerian Elements for Approximate Positions of the Major Planets" (Standish), 1800-2050
# (a[AU], e, I[deg], L[deg], 近日点黄経ϖ[deg], 昇交点黄経Ω[deg]) と、その100年あたりの変化率
ELEMENTS = {
    "Mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350, 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175, 0.16047689, -0.12534081)),
    "Venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950, 131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729, 0.00268329, -0.27769418)),
    "Earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166, 102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981, 0.32327364, 0.0)),
    "Mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205, -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499, 0.44441088, -0.29257343)),
    "Jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051, 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775, 0.21252668, 0.20469106)),
    "Saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423, 92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201, -0.41897216, -0.28867794)),
    "Uranus": ((19.18916464, 0.04725744, 0.77263783, 313.23810451, 170.95427630, 74.01692503),
               (-0.00196176, -0.00004397, -0.00242939, 428.48202785, 0.40805281, 0.04240589)),
    "Neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969, 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325, -0.32241464, -0.00508664)),
}

# 銀河座標の基底ベクトルを赤道座標(ICRS/J2000)で表したもの(Hipparcosの変換行列の各行)
GAL_X_EQ = (-0.0548755604, -0.8734370902, -0.4838350155)  # 銀河中心(l=0)
GAL_Y_EQ = (0.4941094279, -0.4448296300, 0.7469822445)  # 銀河回転方向(l=90)
GAL_Z_EQ = (-0.8676661490, -0.1980763734, 0.4559837762)  # 銀河北極
OBLIQUITY_DEG = 23.43928  # J2000の黄道傾斜角

WIP_BLEND = "/Users/shouheishimokawa/rikenomics-lab/ep3/blend/Rikenomics_Episode03_WIP.blend"
STILLCHECK_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep3/stillcheck"
FRAMES_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep3/frames"
RESOLUTION = (1080, 1920)  # 縦型(9:16、SNSリール向け)

J2000 = datetime(2000, 1, 1, 12, tzinfo=timezone.utc)


def _eq_to_ecl(v):
    eps = math.radians(OBLIQUITY_DEG)
    x, y, z = v
    return (x, y * math.cos(eps) + z * math.sin(eps), -y * math.sin(eps) + z * math.cos(eps))


# シーンの各軸を黄道座標で表したもの。黄道座標のベクトルeのシーン座標は (X·e, Y·e, Z·e)。
SCENE_X_ECL = _eq_to_ecl(GAL_Y_EQ)
SCENE_Y_ECL = _eq_to_ecl(tuple(-c for c in GAL_X_EQ))
SCENE_Z_ECL = _eq_to_ecl(GAL_Z_EQ)


def ecliptic_to_scene(e):
    dot = lambda a, b: a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
    return (dot(SCENE_X_ECL, e), dot(SCENE_Y_ECL, e), dot(SCENE_Z_ECL, e))


def heliocentric_ecliptic(name, when):
    """whenにおける惑星の日心黄道座標(AU)。JPL近似要素＋ケプラー方程式。"""
    base, rate = ELEMENTS[name]
    T = (when - J2000).total_seconds() / 86400.0 / 36525.0
    a, e, inc, L, varpi, node = (b + r * T for b, r in zip(base, rate))
    omega = math.radians(varpi - node)
    node_r = math.radians(node)
    inc_r = math.radians(inc)
    M = math.radians((L - varpi + 180.0) % 360.0 - 180.0)

    E = M + e * math.sin(M)
    for _ in range(20):
        E -= (E - e * math.sin(E) - M) / (1 - e * math.cos(E))

    xp = a * (math.cos(E) - e)
    yp = a * math.sqrt(1 - e * e) * math.sin(E)
    co, so = math.cos(omega), math.sin(omega)
    cn, sn = math.cos(node_r), math.sin(node_r)
    ci, si = math.cos(inc_r), math.sin(inc_r)
    x = (co * cn - so * sn * ci) * xp + (-so * cn - co * sn * ci) * yp
    y = (co * sn + so * cn * ci) * xp + (-so * sn + co * cn * ci) * yp
    z = (so * si) * xp + (co * si) * yp
    return (x, y, z)


def display_radius(name):
    return UNIFORM_SPACING * (DISPLAY.index(name) + 1)


def common_forward_extent_units():
    """TIME_SPAN_YEARSの間に太陽が銀河基準で進む距離(Blenderユニット)。全惑星で共通。"""
    total_forward_km = SUN_GALACTIC_VELOCITY_KMS * (TIME_SPAN_YEARS * YEAR_S)
    return (total_forward_km / AU_KM) * SCALE_AU


def _display_scene_offset(name, when):
    """太陽中心から見た惑星の位置(シーン座標、表示用の半径に換算済み)。"""
    ecl = heliocentric_ecliptic(name, when)
    if RADIUS_MODE == "uniform":
        r = math.sqrt(sum(c * c for c in ecl))
        ecl = tuple(c / r * display_radius(name) for c in ecl)
    else:
        ecl = tuple(c * SCALE_AU for c in ecl)
    return ecliptic_to_scene(ecl)


def forward_units(years):
    """太陽が銀河基準でyears年に進む距離(Blenderユニット)。"""
    return common_forward_extent_units() * years / TIME_SPAN_YEARS


def trail_point(name, blend, when, end_time):
    """時刻whenの惑星の位置。太陽(end_time時点)を原点に置いた座標系で返す。

    blend: 基準系。0=太陽基準(過去の位置も太陽の周りに重なる)、1=銀河基準(過去の位置ほど
    太陽の進行方向の後ろ(-X)に残る)。中間値は太陽より遅く進む観測者から見た形になる。
    """
    sx, sy, sz = _display_scene_offset(name, when)
    years_before = (end_time - when).total_seconds() / YEAR_S
    return (sx - blend * forward_units(years_before), sy, sz)


def spiral_points(name, blend=1.0, end_time=EPOCH, start_time=None, n_points=1200):
    """start_time(省略時はTIME_SPAN_YEARS前)からend_timeまでの軌跡。最後の点がend_timeの位置。"""
    if start_time is None:
        start_time = end_time - timedelta(days=TIME_SPAN_YEARS * 365.25)
    span = end_time - start_time
    return [trail_point(name, blend, start_time + span * (i / (n_points - 1)), end_time)
            for i in range(n_points)]


def orbital_period_years(name):
    return ELEMENTS[name][0][0] ** 1.5


def trail_window_years(name):
    """軌跡として持つ過去の長さ。太陽基準では1周分以上あれば閉じた円になる。"""
    return max(orbital_period_years(name), TIME_SPAN_YEARS)


def ecliptic_north_scene():
    return ecliptic_to_scene((0.0, 0.0, 1.0))


# 自転軸(北極)の向き。IAUの値(赤経・赤緯, J2000)。テクスチャの北極と土星の環の面をこれに合わせる。
POLE_RA_DEC = {
    "Sun": (286.13, 63.87),
    "Mercury": (281.01, 61.45),
    "Venus": (272.76, 67.16),
    "Earth": (0.0, 90.0),
    "Mars": (317.68, 52.89),
    "Jupiter": (268.06, 64.50),
    "Saturn": (40.59, 83.54),
    "Uranus": (257.31, -15.18),
    "Neptune": (299.36, 43.46),
}


def pole_scene(name):
    ra, dec = (math.radians(v) for v in POLE_RA_DEC[name])
    eq = (math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec))
    return ecliptic_to_scene(_eq_to_ecl(eq))


# ============================================================
# タイムライン(30fps・600フレーム=20秒)。最終フレームのシミュレーション時刻がEPOCH。
#
# 太陽基準→銀河基準の切り替え: 1aの円は「過去の位置を太陽基準で見た形」なので、軌跡全体を
# 銀河基準へ引き伸ばし、円がそのまま螺旋につながるように見せる(morph_blend)。
# ============================================================
SHOT_FRAMES = {
    "1a": (1, 75),
    "2a": (76, 180),
    "3a": (181, 330),
    "3b": (331, 400),
    "4a": (401, 600),
}
TOTAL_FRAMES = 600
MOTION_START_FRAME = 80


def smoothstep(edge0, edge1, x):
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def time_rate(frame):
    """シミュレーション時間の進む速さ(年/秒)。1aは惑星の公転が見える速さ、動き出してからは
    3bの時点で地球の軌跡が2年分以上伸びている速さにする。"""
    return 0.15 + 0.25 * smoothstep(MOTION_START_FRAME, 200, frame)


_SIM_OFFSET_YEARS = None


def sim_time(frame):
    global _SIM_OFFSET_YEARS
    if _SIM_OFFSET_YEARS is None:
        offsets = [0.0] * (TOTAL_FRAMES + 2)
        for f in range(TOTAL_FRAMES - 1, 0, -1):
            offsets[f] = offsets[f + 1] + time_rate(f) / FPS
        _SIM_OFFSET_YEARS = offsets
    f = min(max(int(frame), 1), TOTAL_FRAMES)
    return EPOCH - timedelta(days=_SIM_OFFSET_YEARS[f] * 365.25)


# 太陽基準の円を、軌跡全体で一様に銀河基準へ引き伸ばす(円がばねのように伸びて螺旋になる)。
# 点ごとに時間差を付ける方式は、太陽の周りに残った古い円と伸びた部分の間を長い線がつないで
# 崩れたため不採用。引き伸ばしの途中(基準系が0.4未満)では内側惑星の線が一瞬コイル状に巻くが、
# これは太陽より遅く進む観測者から見た正しい形で、すぐに伸び切る。
MORPH_FRAMES = (MOTION_START_FRAME, 200)  # 約4秒かけて穏やかに引き伸ばす


def morph_blend(age_years, frame):
    return smoothstep(MORPH_FRAMES[0], MORPH_FRAMES[1], frame)


def morph_trail_points(name, now, frame, n_points=1200):
    window = timedelta(days=365.25 * trail_window_years(name))
    points = []
    for i in range(n_points):
        when = now - window + window * (i / (n_points - 1))
        age = (now - when).total_seconds() / YEAR_S
        points.append(trail_point(name, morph_blend(age, frame), when, now))
    return points


def sun_trail_points(frame, n_points=200):
    points = []
    for i in range(n_points):
        age = TIME_SPAN_YEARS * (1 - i / (n_points - 1))
        points.append((-morph_blend(age, frame) * forward_units(age), 0.0, 0.0))
    return points


if __name__ == "__main__":
    # 検算: EPOCHでの日心黄経と、黄道北極/進行方向の関係
    for n in DISPLAY:
        x, y, z = heliocentric_ecliptic(n, EPOCH)
        print(f"{n:<8} 日心黄経 {math.degrees(math.atan2(y, x)) % 360:7.2f}°  距離 {math.sqrt(x*x+y*y+z*z):6.3f} AU")
    X = SCENE_X_ECL
    print(f"進行方向の黄緯 {math.degrees(math.asin(X[2])):.2f}° (黄道面との角度)")
    print(f"黄道北極のシーン座標 {tuple(round(c, 4) for c in ecliptic_to_scene((0, 0, 1)))}")
