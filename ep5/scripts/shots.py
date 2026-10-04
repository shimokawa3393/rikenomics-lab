# -*- coding: utf-8 -*-
"""
ep5「車と雷」の共通定数(Blenderに依存しない)。

座標系: 車の中心の真下の地面が原点、上が+Z、車の前が+Y、車の右が+X。
カメラは車の右前の低い位置から、山あいの谷の奥(-Y・-X寄り)を見る。
"""
import os

FPS = 30
TOTAL_FRAMES = 900
RESOLUTION = (1080, 1920)  # 縦型(9:16)

SHOT_FRAMES = {
    "1a": (1, 180),  # 雷が落ちる。車内の明かりは点いたまま
    "2a": (181, 420),  # 巻き戻して落ちる前。電場の線が屋根で止まる
    "3a": (421, 630),  # 落ちる瞬間をスローで。電流がピラーを通って車輪から地面へ
    "4a": (631, 840),  # 屋根なしにすると、電場の線が車内へ
    "4b": (841, 900),  # 屋根が戻る
}

EP5 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIP_BLEND = os.path.join(EP5, "blend", "Rikenomics_Episode05_WIP.blend")
STILLCHECK_DIR = os.path.join(EP5, "stillcheck")
FRAMES_DIR = os.path.join(EP5, "frames")
TEXTURE_DIR = os.path.join(EP5, "textures")
SKY_HDRI = os.path.join(TEXTURE_DIR, "overcast_soil_puresky_8k.hdr")  # Poly Haven(CC0)
ASPHALT = {k: os.path.join(TEXTURE_DIR, f"asphalt_01_{k}_2k.jpg") for k in ("diff", "rough", "nor_gl")}  # Poly Haven(CC0)

# --- 車(セダン)。横から見た形: 後端 y=0 → 前端 y=LENGTH、z=高さ ---
CAR_LENGTH = 4.70
CAR_WIDTH = 1.80
CAR_PROFILE = [  # 売れるセダン: 低い屋根、寝かせたフロント・リアガラス、短いトランク(ファストバック寄り)
    (0.00, 0.26), (0.00, 0.78), (0.12, 0.95), (0.60, 0.99), (1.35, 1.38), (2.75, 1.43),
    (3.55, 0.99), (4.42, 0.88), (4.62, 0.82), (4.72, 0.68), (4.75, 0.44), (4.68, 0.24),
]
ROOF_Z = max(z for _, z in CAR_PROFILE)
BELT = 1.00  # 窓の下端の線(ベルトライン)
ROOF_TAPER = 0.80  # 屋根の幅は、ベルトラインの幅のこの割合(タンブルホーム)
NOSE_TAPER = 0.80  # 前後の端の幅は、真ん中の幅のこの割合(上から見たすぼまり)
TAPER_ZONE = 0.70  # 前後の端からこの距離ですぼまる
AXLES_Y = (0.95, 3.70)  # 後輪・前輪の車軸(後端からの距離)
WHEEL_RADIUS = 0.345
WHEEL_WIDTH = 0.23
ARCH_RADIUS = 0.385
# 窓: 横の窓はAピラー・Cピラーの線から内側へずらした範囲。Bピラーで前後に分ける
SIDE_WINDOW_INSET_A = 0.13  # Aピラーの太さ(水平方向)
SIDE_WINDOW_INSET_C = 0.16
SIDE_WINDOW_BOTTOM = BELT + 0.04
SIDE_WINDOW_TOP = 1.36
B_PILLAR = (2.02, 2.12)
SCREEN_HALF = 0.70  # 前後の窓(フロントガラス・リアガラス)の横幅の半分(下の端)
SCREEN_HALF_TOP = 0.52  # 上の端(上が狭い台形)


def profile_z(y):
    """横から見た形の上の縁の高さ(屋根・ボンネット・トランク)。"""
    top = CAR_PROFILE[1:-1]
    for (y0, z0), (y1, z1) in zip(top, top[1:]):
        if y0 <= y <= y1 and y1 > y0:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return top[-1][1] if y > top[-1][0] else top[0][1]


# --- 駐車場とまわり ---
SLOT_WIDTH = 2.6  # 駐車枠の幅
SLOT_LENGTH = 5.4
LINE_WIDTH = 0.12
LOT_HALF = (40.0, 30.0)  # アスファルトの範囲(x・yの半分)

# --- カメラ(1枚目の参考画像の構図: 車の右前・低め、車は画面の下3分の1) ---
CAM_LOC = (3.6, 6.4, 1.05)
CAM_TARGET = (-0.3, -0.6, 1.55)
CAM_LENS = 26.0
