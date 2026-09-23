# -*- coding: utf-8 -*-
"""
Rikenomics カオス理論シリーズ 第2話「ストレンジアトラクター」
台本データ + タイムライン設計。全ステージのスクリプトから import して使う共通モジュール。

フレーム配分（30fps・全300フレーム=10秒）
④結(カメラが引いて全体を俯瞰する)に十分な尺を取るため、他ショットより長めに配分している。
"""

FPS = 30

SHOTS = [
    {
        "id": "1a",
        "act": "起",
        "frame_start": 1,
        "frame_end": 40,
        "scene": "漆黒の空間に、ほぼ同じ場所から出発した2つの発光点(青と白)。ぴったり重なって1本の線にしか見えない。",
        "text": "この2つの点は、ほぼ同じ場所から出発する。その差は、10万分の1。",
        "speaker": "ナレーション",
    },
    {
        "id": "2a",
        "act": "承",
        "frame_start": 41,
        "frame_end": 90,
        "scene": "2つの点が空間を漂いながら進む。まだほとんど重なって見えるが、刃物のように薄い隙間が生まれ始めている。",
        "text": "最初は、ほとんど見分けがつかない。同じ軌道を、同じように進んでいるように見える。",
        "speaker": "ナレーション",
    },
    {
        "id": "3a",
        "act": "転(前半)",
        "frame_start": 91,
        "frame_end": 150,
        "scene": "隙間が急激に広がり、青と白の軌跡が明確に別の方向へ分かれていく。",
        "text": "でも、そのわずかな差は、時間とともに何倍にも膨れ上がっていく。",
        "speaker": "ナレーション",
    },
    {
        "id": "3b",
        "act": "転(後半)",
        "frame_start": 151,
        "frame_end": 210,
        "scene": "2つの軌跡が完全に別々の場所で、全く異なる複雑な模様を描いている。",
        "text": "気づけば、2つはまったく別の場所にいる。同じ場所から、同じ法則で動いているだけなのに。",
        "speaker": "ナレーション",
    },
    {
        "id": "4a",
        "act": "結",
        "frame_start": 211,
        "frame_end": 300,
        "scene": "カメラが一気に引いて全体を俯瞰する。青と白の軌跡が、実は同じ1つの蝶の羽のような形をなぞっていたことが分かる。",
        "text": "ただし、2つの軌跡を遠くから見ると、まったく同じ形を描いている。どこに行くかは予測できない。それでも、どこまでも自由というわけでもない。",
        "speaker": "ナレーション",
    },
]

# frame_start(=1)時点でのreveal(まだ点が現れたばかりの状態)
START_REVEAL = 0.001

# 軌跡のリビール(bevel_factor_end)は、ショット境目ごとの階段状ではなく、
# frame全体を1本の指数カーブ(イーズイン)でなめらかに加速させる。
# reveal(frame) = START + (1-START) * t^REVEAL_EASE_POWER, t = (frame-1)/(total-1)
# べき指数1.3は実測に基づく: 系統A/B(初期値差1e-5)の視覚的分離(距離>0.12)が
# frame135(③転前半=3aの中盤)で自然に始まり、3a終了時(frame150)には距離1.9まで
# 広がるよう校正済み。台詞「わずかな差は時間とともに何倍にも膨れ上がっていく」
# (3aのテキスト)と展開が一致する。
REVEAL_EASE_POWER = 1.3


def reveal_at_frame(frame, total_frames=None):
    total_frames = total_frames or total_frame_end()
    t = (frame - 1) / (total_frames - 1)
    return START_REVEAL + (1 - START_REVEAL) * (t ** REVEAL_EASE_POWER)


def shot_by_id(shot_id):
    return next(s for s in SHOTS if s["id"] == shot_id)


def total_frame_end():
    return SHOTS[-1]["frame_end"]


# ============================================
# ローレンツ方程式パラメータ(2系統: A=基準, B=Aを10万分の1だけ摂動)
# ============================================
SIGMA, RHO, BETA = 10.0, 28.0, 8.0 / 3.0
DT = 0.006
TOTAL_STEPS = 10000  # t = DT * TOTAL_STEPS = 60 (羽の中を何十周もする密度を確保)
EPSILON = 1e-5  # 「10万分の1」の初期値差
X0, Y0, Z0 = 0.1, 0.0, 0.0
SCALE = 0.12
Z_OFFSET = -3.0

WIP_BLEND = "/Users/shouheishimokawa/rikenomics-lab/ep2/Rikenomics_Episode02_WIP.blend"
STILLCHECK_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep2/stillcheck"


def compute_trajectory(x0, y0, z0):
    """ローレンツ方程式を数値積分し、シーン座標系にスケール済みの座標列を返す。
    01(ジオメトリ生成)と03(カメラ・リビール同期)の両方から同じ結果を再現するために使う。"""
    x, y, z = x0, y0, z0
    points = []
    for _ in range(TOTAL_STEPS):
        dx = SIGMA * (y - x)
        dy = x * (RHO - z) - y
        dz = x * y - BETA * z
        x += dx * DT
        y += dy * DT
        z += dz * DT
        points.append((x * SCALE, y * SCALE, z * SCALE + Z_OFFSET))
    return points


def point_at_reveal(points, reveal):
    """reveal(0.0-1.0)に対応する座標列上のインデックスの点を返す。"""
    index = max(0, min(len(points) - 1, int(reveal * (len(points) - 1))))
    return points[index]
