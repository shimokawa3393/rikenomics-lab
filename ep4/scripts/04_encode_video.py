# -*- coding: utf-8 -*-
"""
Stage 4: PNG連番をmp4にまとめる(このマシンにffmpegは無いので、BlenderのVSE経由で書き出す)

- 画面の左上に映像のスピード(×2、×3)を文字で重ねる

Blender 5.x: FFMPEG出力の前にimage_settings.media_type='VIDEO'が必要、VSEは.strips(ep2の教訓)。
new_effectは終わりのフレームではなく長さ(length)で指定する。画像ストリップにfit_methodは無い。
BGMができたら AUDIO_PATH にファイルを指定すると音声ストリップも追加する。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/04_encode_video.py"
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/04_encode_video.py" -- draft
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
OUTPUT_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep4/Rikenomics_Episode04_Jam.mp4"
AUDIO_PATH = None  # BGMができたら指定する
LABEL_LOCATION = (0.07, 0.94)  # 倍率の文字の位置(画面に対する割合、左上)
LABEL_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"  # VSEの標準フォントには「×」が無い


def image_strip(editor, name, frames_dir, frames, channel, start):
    files = [f"ep4_{f:04d}.png" for f in frames]
    missing = [f for f in files if not os.path.exists(os.path.join(frames_dir, f))]
    if missing:
        raise SystemExit(f"[Stage4] {name}: missing {len(missing)} frames, e.g. {missing[0]}")
    strip = editor.strips.new_image(name, os.path.join(frames_dir, files[0]), channel, start)
    for f in files[1:]:
        strip.elements.append(f)
    return strip  # 5.xにfit_methodは無い。上下の画面は横幅が動画と同じなので、そのまま置けば合う


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    draft, preview = "draft" in argv, "preview" in argv
    step = DRAFT_STEP if draft else 1
    scale = 0.25 if draft else 0.5 if preview else 1.0
    base_dir = DRAFT_FRAMES_DIR if draft else PREVIEW_FRAMES_DIR if preview else FRAMES_DIR
    output_path = (OUTPUT_PATH.replace(".mp4", "_draft.mp4") if draft
                   else OUTPUT_PATH.replace(".mp4", "_preview.mp4") if preview else OUTPUT_PATH)

    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    width, height = int(RESOLUTION[0] * scale), int(RESOLUTION[1] * scale)
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
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
        if label is None:
            continue
        text = editor.strips.new_effect(f"Speed{i}", 'TEXT', 5, frame_start=to_out(f0),
                                        length=to_out(f1) + 1 - to_out(f0))
        text.text = label
        text.font = bpy.data.fonts.load(LABEL_FONT, check_existing=True)
        text.font_size = 64 * scale
        text.location = LABEL_LOCATION
        text.anchor_x = 'LEFT'
        text.anchor_y = 'TOP'
        text.color = (1, 1, 1, 0.9)
        text.blend_type = 'ALPHA_OVER'

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
    if AUDIO_PATH:
        scene.render.ffmpeg.audio_codec = 'AAC'
    scene.render.filepath = output_path
    bpy.ops.render.render(animation=True)
    print("[Stage4] video written:", output_path)


if __name__ == "__main__":
    main()
