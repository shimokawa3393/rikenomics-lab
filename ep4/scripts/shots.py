# -*- coding: utf-8 -*-
"""
ep4「なぜ渋滞は起きる」の共通定数と、道路の形(Blenderに依存しない計算)。

座標系: 我々の車線の進行方向が+Y、上が+Z。日本は左側通行なので、進行方向を向いて
左(-X)が我々の車線、右(+X)が対向車線。中央分離帯がX=0。
"""

FPS = 30
TOTAL_FRAMES = 900
RESOLUTION = (1080, 1920)  # 縦型(9:16、SNSリール向け)

SHOT_FRAMES = {
    "1a": (1, 120),  # 望遠目線のリアルな夜の高速道路、等速
    "rise": (121, 205),  # 斜め上からの俯瞰へ上昇しながら、車を光の点(速度で色分け)に切り替える。等速→2倍
    "2a": (206, 420),  # 1台の軽いブレーキが後ろへ強まりながら伝わる。2倍
    "3": (421, 900),  # 止まる場所が後ろへずれていく。3倍(途中で別の計算に切り替えず、最後まで流す)
}

WIP_BLEND = "/Users/shouheishimokawa/rikenomics-lab/ep4/blend/Rikenomics_Episode04_WIP.blend"
STILLCHECK_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep4/stillcheck"
# 連番の置き場所。それぞれの下に real(リアルな1画面)・top(上の画面)・bottom(下の画面)を作る
FRAMES_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep4/frames"
PREVIEW_FRAMES_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep4/preview_frames"  # 動きの確認用(半分の解像度)
DRAFT_FRAMES_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep4/draft_frames"  # ドラフト(4分の1・2フレームに1枚)

# --- 道路(日本の高速道路の標準的な寸法) ---
LANE_WIDTH = 3.6
LANES = 3
MEDIAN_HALF = 1.8  # 中央分離帯の半幅
SHOULDER = 2.5
OUR_LANE_X = [-(MEDIAN_HALF + LANE_WIDTH * (i + 0.5)) for i in range(LANES)]  # 追越→走行
ONCOMING_LANE_X = [MEDIAN_HALF + LANE_WIDTH * (i + 0.5) for i in range(LANES)]
ROAD_HALF = MEDIAN_HALF + LANE_WIDTH * LANES + SHOULDER
ROAD_START, ROAD_END = -1500.0, 2600.0  # 渋滞はカメラの後ろ側へ伸びていくので、後ろにも道路を延ばす
DASH_LENGTH, DASH_GAP = 8.0, 12.0  # 車線境界線(実線8m・間隔12m)
LAMP_SPACING = 40.0
BRAKE_BOOST = 6.0  # ブレーキ全開でテールランプとその光(後ろの赤いスポット)がこの倍率になる(実物のブレーキランプは尾灯の5〜10倍明るい)
LAMP_HEIGHT = 11.0

# 奥の緩い上り坂(サグ部)。手前は平坦で、SAG_START から勾配が SAG_GRADE までなめらかに増える。
# 望遠で見ると、奥の車列が画面の上へ積み重なって見える(参考画像の見え方)。
SAG_START = 250.0
SAG_TRANSITION = 300.0
SAG_GRADE = 0.03


def road_z(y):
    """道路(と周りの地面)の高さ。"""
    if y <= SAG_START:
        return 0.0
    d = y - SAG_START
    if d < SAG_TRANSITION:
        return SAG_GRADE * d * d / (2 * SAG_TRANSITION)
    return SAG_GRADE * (d - SAG_TRANSITION / 2)


def road_slope(y):
    """道路の勾配(dz/dy)。車を坂に沿って傾けるのに使う。"""
    if y <= SAG_START:
        return 0.0
    d = y - SAG_START
    return SAG_GRADE * min(d / SAG_TRANSITION, 1.0)
