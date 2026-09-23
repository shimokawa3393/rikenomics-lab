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
        "reveal": 0.02,
    },
    {
        "id": "2a",
        "act": "承",
        "frame_start": 41,
        "frame_end": 90,
        "scene": "2つの点が空間を漂いながら進む。まだほとんど重なって見えるが、刃物のように薄い隙間が生まれ始めている。",
        "text": "最初は、ほとんど見分けがつかない。同じ軌道を、同じように進んでいるように見える。",
        "speaker": "ナレーション",
        "reveal": 0.05,
    },
    {
        "id": "3a",
        "act": "転(前半)",
        "frame_start": 91,
        "frame_end": 150,
        "scene": "隙間が急激に広がり、青と白の軌跡が明確に別の方向へ分かれていく。",
        "text": "でも、そのわずかな差は、時間とともに何倍にも膨れ上がっていく。",
        "speaker": "ナレーション",
        "reveal": 0.10,
    },
    {
        "id": "3b",
        "act": "転(後半)",
        "frame_start": 151,
        "frame_end": 210,
        "scene": "2つの軌跡が完全に別々の場所で、全く異なる複雑な模様を描いている。",
        "text": "気づけば、2つはまったく別の場所にいる。同じ場所から、同じ法則で動いているだけなのに。",
        "speaker": "ナレーション",
        "reveal": 0.18,
    },
    {
        "id": "4a",
        "act": "結",
        "frame_start": 211,
        "frame_end": 300,
        "scene": "カメラが一気に引いて全体を俯瞰する。青と白の軌跡が、実は同じ1つの蝶の羽のような形をなぞっていたことが分かる。",
        "text": "ただし、2つの軌跡を遠くから見ると、まったく同じ形を描いている。どこに行くかは予測できない。それでも、どこまでも自由というわけでもない。",
        "speaker": "ナレーション",
        "reveal": 1.0,
    },
]

# frame_start(=1)時点でのreveal(まだ点が現れたばかりの状態)
START_REVEAL = 0.001


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
