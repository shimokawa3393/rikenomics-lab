# -*- coding: utf-8 -*-
"""
Stage 4: PNG連番をmp4にまとめる(このマシンにffmpegは無いので、BlenderのVSE経由で書き出す)

- 画面の左、真ん中より少し下に映像のスピード(×2、×3)を文字で重ねる(左上だとテロップや各アプリのボタンとかぶる)
- telop を付けると、テロップ(数字なしの短い補助。ep4/txt/テロップ.txt)を画面の上の方に重ねた投稿用の版を書き出す
  (en を付けると英語。テロップ入りもテロップなしと同じ最高画質。ユーザー「画質が落ちるなら、テロップ入りはいい」)

Blender 5.x: FFMPEG出力の前にimage_settings.media_type='VIDEO'が必要、VSEは.strips(ep2の教訓)。
new_effectは終わりのフレームではなく長さ(length)で指定する。画像ストリップにfit_methodは無い。
BGMができたら AUDIO_PATH にファイルを指定すると音声ストリップも追加する。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/04_encode_video.py"
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/04_encode_video.py" -- draft
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/04_encode_video.py" -- telop [en] [share]
  (preview: 半分の解像度の連番から。draft: 4分の1・2フレームに1枚の連番から15fpsで。
   still 数字 を付けると、組み上がった画面のその1コマ(書き出す動画のフレーム番号)だけをPNGで stillcheck へ)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import scenario
from shots import DRAFT_FRAMES_DIR, FPS, FRAMES_DIR, PREVIEW_FRAMES_DIR, RESOLUTION, STILLCHECK_DIR, TOTAL_FRAMES

DRAFT_STEP = 2
OUTPUT_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep4/mp4/final/Rikenomics_Episode04_Jam.mp4"
PREVIEW_DIR = "/Users/shouheishimokawa/rikenomics-lab/ep4/mp4/preview"  # draft・preview・share(確認用)はこちらへ
AUDIO_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep4/wav/Rikenomics_Episode04_mix.wav"  # 05_mix_audio.py で走行音とBGMを組んだもの
SHOW_SPEED_LABEL = False  # 台数の計器とテロップで情報が増え「倍速表示もいらない」。倍速は投稿文の注記に書く
LABEL_LOCATION = (0.12, 0.83)  # 倍率の文字の位置(画面に対する割合、下から。左上、説明テロップの下)。
# 最初は左の真ん中より少し下だったが、台数の計器と並べると情報がまとまりすぎるので分けた
LABEL_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"  # VSEの標準フォントには「×」が無い
LABEL_SIZE = 80  # 本番解像度でのピクセル

# テロップ: (始まりの秒, 終わりの秒, 日本語, English)。上から約11%の位置(各アプリが上端に重ねるボタンの少し下)。
# 次のテロップの1秒前に消してワンテンポ置き、次は映像の変わり目(7秒で×2、14秒で×3)ちょうどに出す。
# 最初は冒頭の夜の高速道路を一瞬見せてから、1秒で出す。4枚目は「どこまでも」だと渋滞の育ち始めで終わる映像と
# 合わないので「まだまだ」(「どんどん」は3枚目の「伸びていく」と中身が重なる)
TELOPS = [
    (1.0, 6.0, "なぜ渋滞は起きる？", "Why do traffic jams happen?"),
    (7.0, 13.0, "前が少し遅くなっただけ", "The cars ahead just slowed a little"),
    (14.0, 21.0, "渋滞は後ろへ伸びていく", "The jam grows backward"),
    (22.0, 30.0, "まだまだ長くなっていく…", "And it's only getting longer..."),
]
TELOP_LOCATION = (0.5, 0.89)
TELOP_FONT = {"ja": "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc", "en": LABEL_FONT}

# 倍率の下に、計算から数えたノロノロ運転(時速20km以下)の車の台数を重ねる(動画だけでも理系の中身が見えるように)。
# 「交通流シミュレーション」の注記も入れたが「邪魔になってきた」ので外し、定義とともに投稿文の注記へ回した
JAM_FROM = 206  # 光の点に切り替わったところから(元のフレーム番号)
JAM_TITLE_LOCATION = (0.12, 0.355)  # 小さい見出し「ノロノロ運転」(1行だと長く、道路の光の点にかかった)
JAM_TITLE_SIZE = 32
JAM_LOCATION = (0.12, 0.335)  # その下に台数を大きく
JAM_SIZE = 64
JAM_SUB_LOCATION = (0.12, 0.282)  # さらにその下に基準の速さを小さく(「時速20km以下はいると思う」)
JAM_SUB_SIZE = 28
TELOP_SIZE = 68  # 本番解像度(横1080)でのピクセル
SHARE_BITRATE = 6000  # kbps。スマホへ送って確認する用(share。送れる上限30MBに収める。投稿には使わない)
TELOP_FADE = 0.4  # 秒。全テロップでフェードイン・フェードアウト(ユーザーの好み。2行のテロップはステップフェードにする)


def image_strip(editor, name, frames_dir, frames, channel, start):
    files = [f"ep4_{f:04d}.png" for f in frames]
    missing = [f for f in files if not os.path.exists(os.path.join(frames_dir, f))]
    if missing:
        raise SystemExit(f"[Stage4] {name}: missing {len(missing)} frames, e.g. {missing[0]}")
    strip = editor.strips.new_image(name, os.path.join(frames_dir, files[0]), channel, start)
    for f in files[1:]:
        strip.elements.append(f)
    return strip  # 5.xにfit_methodは無い。上下の画面は横幅が動画と同じなので、そのまま置けば合う


def overlay_text(editor, name, channel, start, length, text, font, size, location, alpha=1.0):
    strip = editor.strips.new_effect(name, 'TEXT', channel, frame_start=start, length=length)
    strip.text = text
    strip.font = font
    strip.font_size = size
    strip.location = location
    strip.anchor_x = 'LEFT'
    strip.anchor_y = 'TOP'
    strip.color = (1, 1, 1, alpha)
    strip.blend_type = 'ALPHA_OVER'
    return strip


def add_jam_counter(editor, lang, scale, to_out):
    """ノロノロ運転の車の台数を、値が変わるごとに文字のストリップで置く。"""
    font = bpy.data.fonts.load(TELOP_FONT["ja"] if lang == "ja" else LABEL_FONT, check_existing=True)
    lanes = scenario.load()
    end = to_out(TOTAL_FRAMES) + 1
    step = TOTAL_FRAMES // (end - 1)
    segments = []
    for out in range(to_out(JAM_FROM), end):
        count = int(round(scenario.slow_car_count(lanes, scenario.sim_time((out - 1) * step + 1))))
        if segments and segments[-1][0] == count:
            segments[-1][2] = out + 1
        else:
            segments.append([count, out, out + 1])
    start = to_out(JAM_FROM)
    overlay_text(editor, "JamTitle", 9, start, end - start, "ノロノロ運転" if lang == "ja" else "Crawling cars",
                 font, JAM_TITLE_SIZE * scale, JAM_TITLE_LOCATION, 0.8)
    overlay_text(editor, "JamSub", 10, start, end - start, "時速20km以下" if lang == "ja" else "below 20 km/h",
                 font, JAM_SUB_SIZE * scale, JAM_SUB_LOCATION, 0.7)
    for i, (count, s0, s1) in enumerate(segments):
        text = f"{count}台" if lang == "ja" else f"{count}"
        overlay_text(editor, f"Jam{i}", 8, s0, s1 - s0, text, font, JAM_SIZE * scale, JAM_LOCATION)
    print("[Stage4] slow cars:", [(c, s0) for c, s0, _ in segments][::max(len(segments) // 8, 1)])


def add_telops(scene, editor, lang, scale):
    fps = scene.render.fps
    font = bpy.data.fonts.load(TELOP_FONT[lang], check_existing=True)
    for i, (t0, t1, ja, en) in enumerate(TELOPS):
        f0, f1 = int(round(t0 * fps)) + 1, int(round(t1 * fps)) + 1
        text = editor.strips.new_effect(f"Telop{i}", 'TEXT', 7, frame_start=f0, length=f1 - f0)
        text.text = ja if lang == "ja" else en
        text.font = font
        text.font_size = TELOP_SIZE * scale
        text.location = TELOP_LOCATION
        text.anchor_x = 'CENTER'
        text.anchor_y = 'CENTER'
        text.color = (1, 1, 1, 1)
        text.use_outline = True
        text.outline_color = (0, 0, 0, 0.85)
        text.outline_width = 0.06
        text.use_shadow = True
        text.shadow_color = (0, 0, 0, 0.6)
        text.shadow_blur = 0.5
        text.blend_type = 'ALPHA_OVER'
        fade = max(int(TELOP_FADE * fps), 1)
        for frame, alpha in [(f0, 0.0), (f0 + fade, 1.0), (f1 - fade, 1.0), (f1, 0.0)]:
            text.blend_alpha = alpha
            text.keyframe_insert("blend_alpha", frame=frame)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    draft, preview = "draft" in argv, "preview" in argv
    step = DRAFT_STEP if draft else 1
    scale = 0.25 if draft else 0.5 if preview else 1.0
    base_dir = DRAFT_FRAMES_DIR if draft else PREVIEW_FRAMES_DIR if preview else FRAMES_DIR
    telop_lang = ("en" if "en" in argv else "ja") if "telop" in argv else None
    output_path = (OUTPUT_PATH.replace(".mp4", "_draft.mp4") if draft
                   else OUTPUT_PATH.replace(".mp4", "_preview.mp4") if preview else OUTPUT_PATH)
    if telop_lang:
        output_path = output_path.replace(".mp4", "_telop.mp4" if telop_lang == "ja" else "_telop_EN.mp4")
        if "share" in argv:
            output_path = output_path.replace(".mp4", "_share.mp4")
    if draft or preview or "share" in argv:
        output_path = os.path.join(PREVIEW_DIR, os.path.basename(output_path))

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    width, height = int(RESOLUTION[0] * scale), int(RESOLUTION[1] * scale)
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    # 連番はレンダーの時点で色の変換(AgX)済み。新しいシーンの既定のAgXのままだと二重にかかり、全体が暗くくすみ、
    # 白い文字も灰色になる(2026-10-04に気づいた。それまでのドラフトはすべてこの状態だった)
    scene.view_settings.view_transform = 'Standard'
    scene.render.fps = FPS // step

    def to_out(frame):  # 元のフレーム番号 → 書き出す動画のフレーム番号
        return (frame - 1) // step + 1

    scene.frame_start = 1
    scene.frame_end = to_out(TOTAL_FRAMES)
    editor = scene.sequence_editor_create()

    image_strip(editor, "Frames", base_dir, range(1, TOTAL_FRAMES + 1, step), 1, 1)

    # 早送りの倍率: 倍率がほぼ一定の区間ごとに文字のストリップを置く
    segments = []
    for f in range(1, TOTAL_FRAMES + 1):
        factor = scenario.speed_factor(f)
        label = "×3" if factor >= 2.95 else "×2" if 1.95 <= factor < 2.05 else None
        if segments and segments[-1][0] == label:
            segments[-1][2] = f
        else:
            segments.append([label, f, f])
    for i, (label, f0, f1) in enumerate(segments):
        if label is None or not SHOW_SPEED_LABEL:
            continue
        text = editor.strips.new_effect(f"Speed{i}", 'TEXT', 5, frame_start=to_out(f0),
                                        length=to_out(f1) + 1 - to_out(f0))
        text.text = label
        text.font = bpy.data.fonts.load(LABEL_FONT, check_existing=True)
        text.font_size = LABEL_SIZE * scale
        text.location = LABEL_LOCATION
        text.anchor_x = 'LEFT'
        text.anchor_y = 'TOP'
        text.color = (1, 1, 1, 0.9)
        text.blend_type = 'ALPHA_OVER'

    add_jam_counter(editor, telop_lang or "ja", scale, to_out)

    if telop_lang:
        add_telops(scene, editor, telop_lang, scale)

    if AUDIO_PATH:
        editor.strips.new_sound("BGM", AUDIO_PATH, 6, 1)

    if "still" in argv:
        out_frame = int(argv[argv.index("still") + 1])
        scene.frame_set(out_frame)
        scene.render.image_settings.file_format = 'PNG'
        scene.render.filepath = os.path.join(STILLCHECK_DIR, f"ep4_composite_{out_frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("[Stage4] still written:", scene.render.filepath)
        return

    scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM' if (draft or preview) else 'HIGH'
    if "share" in argv:
        # スマホへ送って確認する用はビットレートを決める(粒子ノイズで圧縮が効かず、画質指定だけだと190〜340MBになる)
        scene.render.ffmpeg.constant_rate_factor = 'NONE'
        scene.render.ffmpeg.video_bitrate = SHARE_BITRATE
        scene.render.ffmpeg.maxrate = SHARE_BITRATE * 2
        scene.render.ffmpeg.buffersize = SHARE_BITRATE * 2
    if AUDIO_PATH:
        scene.render.ffmpeg.audio_codec = 'AAC'
    scene.render.filepath = output_path
    bpy.ops.render.render(animation=True)
    print("[Stage4] video written:", output_path)


if __name__ == "__main__":
    main()
