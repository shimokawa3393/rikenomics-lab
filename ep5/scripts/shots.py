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
    "1a": (1, 90),  # 雨の駐車場。「もしも、あなたが落雷に見舞われたら…」
    "2a": (91, 180),  # 91フレーム目に屋根へ落ちる。落ちた瞬間で静止(編集でくり返す)、電流・温度のテロップ
    "3a": (181, 540),  # 巻き戻してスロー、科学の目。電流がピラーを通って車輪から地面へ。「あなたの体を通る電流 0%」
    "4a": (541, 660),  # 色が戻る。「あなたは無事」「でも車は…」
    "5a": (661, 810),  # 同じアングルで背景の木に雷。蒸気、一拍おいて倒れる。「もしも、あの木の下にいたら」
    "5b": (811, 900),  # 倒れた木と無事な車。「雷は、一番通りやすい道を選ぶ」
}

EP5 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WIP_BLEND = os.path.join(EP5, "blend", "Rikenomics_Episode05_WIP.blend")
STILLCHECK_DIR = os.path.join(EP5, "stillcheck")
FRAMES_DIR = os.path.join(EP5, "frames")
TEXTURE_DIR = os.path.join(EP5, "textures")
SKY_HDRI = os.path.join(TEXTURE_DIR, "overcast_soil_puresky_8k.hdr")  # Poly Haven(CC0)
ASPHALT = {k: os.path.join(TEXTURE_DIR, f"asphalt_01_{k}_2k.jpg") for k in ("diff", "rough", "nor_gl")}  # Poly Haven(CC0)
GRASS_TEX = {k: os.path.join(TEXTURE_DIR, f"aerial_grass_rock_{k}_2k.jpg") for k in ("diff", "rough", "nor_gl")}  # Poly Haven(CC0)
SOIL_TEX = {k: os.path.join(TEXTURE_DIR, f"forest_ground_04_{k}_2k.jpg") for k in ("diff", "rough", "nor_gl")}  # Poly Haven(CC0)

# --- 車(セダン)。横から見た形: 後端 y=0 → 前端 y=LENGTH、z=高さ ---
CAR_LENGTH = 4.78
CAR_WIDTH = 1.80
CAR_PROFILE = [  # 今のセダン(参考画像)。重厚感: 高く厚い鼻先と水平に近いボンネット、高いベルトライン、短く高いトランク
    (0.05, 0.26), (0.00, 0.46), (0.00, 0.86), (0.10, 1.01), (0.45, 1.05), (1.45, 1.41), (2.55, 1.45),
    (3.45, 1.04), (4.30, 0.95), (4.60, 0.89), (4.74, 0.78), (4.78, 0.50), (4.70, 0.24),
]
ROOF_Z = max(z for _, z in CAR_PROFILE)
BELT = 1.04  # 窓の下端の線(ベルトライン)
ROOF_TAPER = 0.80  # 屋根の幅は、ベルトラインの幅のこの割合(タンブルホーム)
NOSE_TAPER = 0.86  # 前後の端の幅は、真ん中の幅のこの割合(上から見たすぼまり)
TAPER_ZONE = 0.70  # 前後の端からこの距離ですぼまる
AXLES_Y = (0.95, 3.74)  # 後輪・前輪の車軸(後端からの距離)
WHEEL_RADIUS = 0.36
WHEEL_WIDTH = 0.23
ARCH_RADIUS = 0.40
# 窓: 横の窓はAピラー・Cピラーの線から内側へずらした範囲。Bピラーで前後に分ける
SIDE_WINDOW_INSET_A = 0.07  # Aピラーの太さ(水平方向)
SIDE_WINDOW_INSET_C = 0.16
SIDE_WINDOW_BOTTOM = BELT + 0.04
SIDE_WINDOW_TOP = 1.37
WINDOW_KICK = (1.55, 0.12)  # 窓の下の縁は、このy(後端から)より後ろで上へ跳ね上がる(後ろの端で+0.12m)
B_PILLAR = (1.98, 2.08)
SCREEN_HALF = 0.76  # 前後の窓(フロントガラス・リアガラス)の横幅の半分(下の端)
SCREEN_HALF_TOP = 0.59  # 上の端(上が狭い台形)


# 計算で使う、ワールド座標(車の中心が原点)でのピラーの位置
B_PILLAR_WORLD = (B_PILLAR[0] - CAR_LENGTH / 2, B_PILLAR[1] - CAR_LENGTH / 2)
A_PILLAR_Y_MIN = 0.05  # これより前(+y)の窓の高さの金属はAピラー


def profile_z(y):
    """横から見た形の上の縁の高さ(屋根・ボンネット・トランク)。"""
    top = CAR_PROFILE[1:-1]
    for (y0, z0), (y1, z1) in zip(top, top[1:]):
        if y0 <= y <= y1 and y1 > y0:
            return z0 + (z1 - z0) * (y - y0) / (y1 - y0)
    return top[-1][1] if y > top[-1][0] else top[0][1]


# --- 雷(1aで落ちる) ---
STRIKE_FRAME = 91  # 落ちる瞬間(3秒)。この前後数フレームだけ光る
STRIKE_POINT = (0.0, -0.35, 1.47)  # 屋根の真ん中(落ちる点)
LIGHTNING_TOP = (-210.0, -400.0, 230.0)  # 雷雲の下の端。カメラから見て車の真上の奥(画面では縦に下りてくる)


# --- 駐車場とまわり ---
SLOT_WIDTH = 2.6  # 駐車枠の幅
SLOT_LENGTH = 5.4
LINE_WIDTH = 0.12
LOT_HALF = (40.0, 30.0)  # アスファルトの範囲(x・yの半分)

# --- カメラ(1枚目の参考画像の構図: 車の右前・低め、車は画面の下3分の1) ---
CAM_LOC = (3.6, 6.4, 1.05)
CAM_TARGET = (-0.3, -0.6, 1.55)
CAM_LENS = 26.0
