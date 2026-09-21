# -*- coding: utf-8 -*-
"""
Rikenomics 重力シリーズ 第1話「スパゲッティフィケーション」
台本データ + タイムライン設計。全ステージのスクリプトから import して使う共通モジュール。

フレーム配分（30fps・全240フレーム=8秒）
※元の没ファイルは180フレーム(6秒)だったが、④結(外部観測者視点)に
  十分な尺を取るため240フレームに拡張している。
"""

FPS = 30

SHOTS = [
    {
        "id": "1a",
        "act": "起",
        "frame_start": 1,
        "frame_end": 30,
        "scene": "漆黒の宇宙空間。遠くに黒い球体(ブラックホール)。宇宙服の人影がそこへ向かって落下している。カメラは人物の背後からブラックホールを見据える構図。",
        "text": "もしブラックホールに落ちたら、あなたはどうなるか。",
        "speaker": "ナレーション",
    },
    {
        "id": "2a",
        "act": "承",
        "frame_start": 31,
        "frame_end": 75,
        "scene": "人物が境界線(事象の地平線)に近づく。表情・姿勢に変化なく平然と落下。カメラは人物に寄っていく。",
        "text": "意外にも、境界線を越えた瞬間、本人は何も感じない。痛みも、衝撃も、何も。",
        "speaker": "ナレーション",
    },
    {
        "id": "3a",
        "act": "転(前半)",
        "frame_start": 76,
        "frame_end": 130,
        "scene": "足元への引力が頭への引力を上回り始め、体のシルエットが縦に伸び始める。",
        "text": "でも、そこから先は違う。足への引力が、頭への引力を上回り始める。",
        "speaker": "ナレーション",
    },
    {
        "id": "3b",
        "act": "転(後半)",
        "frame_start": 131,
        "frame_end": 170,
        "scene": "体が完全に引き伸ばされ、細い一本の糸のようになる。カメラは真横からその様子を克明に映す。",
        "text": "体は縦に引き伸ばされ、横に圧縮されていく。これが「スパゲッティフィケーション」——物理学の、れっきとした正式名称。",
        "speaker": "ナレーション",
    },
    {
        "id": "4a",
        "act": "結",
        "frame_start": 171,
        "frame_end": 240,
        "scene": "視点が切り替わり、外の観測者の視界へ。落ちていった人物が境界線の手前で止まったように見える。",
        "text": "ただし、これはあなた自身が体験する話。外から見ている人には、まったく違う光景が見える。あなたは境界線の手前で、永遠に止まって見え続ける。もう、とっくに引き裂かれているのに。",
        "speaker": "ナレーション",
    },
]


def shot_by_id(shot_id):
    return next(s for s in SHOTS if s["id"] == shot_id)


def total_frame_end():
    return SHOTS[-1]["frame_end"]


SOURCE_BLEND = "/Users/shouheishimokawa/rikenomics-lab/ep1/スパゲティー没.blend"
WIP_BLEND = "/Users/shouheishimokawa/rikenomics-lab/ep1/Rikenomics_Episode01_WIP.blend"
