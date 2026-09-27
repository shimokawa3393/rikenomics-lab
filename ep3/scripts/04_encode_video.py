# -*- coding: utf-8 -*-
"""
Stage 4: PNG連番をmp4にまとめる(このマシンにffmpegは無いので、BlenderのVSE経由で書き出す)

Blender 5.x: FFMPEG出力の前にimage_settings.media_type='VIDEO'が必要、VSEは.strips(ep2の教訓)。
BGMができたら AUDIO_PATH にファイルを指定すると音声ストリップも追加する。

実行(--previewで半分の解像度の共有用プレビュー、--range 開始 終了 で一部だけの確認用クリップ):
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep3/scripts/04_encode_video.py" -- --preview
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep3/scripts/04_encode_video.py" -- --range 80 129
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import FPS, FRAMES_DIR, RESOLUTION, TOTAL_FRAMES

OUTPUT_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep3/Rikenomics_Episode03_Spiral.mp4"
PREVIEW_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep3/Rikenomics_Episode03_Spiral_preview.mp4"
AUDIO_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep3/epic-cinematic-orchestral-hybrid-instrumental_092726.mp3"  # 曲側でフェードアウト済み


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    first, last = 1, TOTAL_FRAMES
    output_path = OUTPUT_PATH
    preview = "--preview" in argv
    if preview:
        output_path = PREVIEW_PATH
    if "--range" in argv:
        i = argv.index("--range")
        first, last = int(argv[i + 1]), int(argv[i + 2])
        preview = True
        output_path = OUTPUT_PATH.replace(".mp4", f"_clip_{first:04d}-{last:04d}.mp4")
    bpy.ops.wm.read_homefile(use_empty=True)
    scene = bpy.context.scene
    scene.render.fps = FPS
    scene.frame_start = 1
    scene.frame_end = last - first + 1
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 50 if preview else 100

    editor = scene.sequence_editor_create()
    files = [f"ep3_{i:04d}.png" for i in range(first, last + 1)]
    missing = [f for f in files if not os.path.exists(os.path.join(FRAMES_DIR, f))]
    if missing:
        raise SystemExit(f"[Stage4] missing {len(missing)} frames, e.g. {missing[0]}")
    strip = editor.strips.new_image("Frames", os.path.join(FRAMES_DIR, files[0]), 1, 1)
    for f in files[1:]:
        strip.elements.append(f)
    if AUDIO_PATH:
        editor.strips.new_sound("BGM", AUDIO_PATH, 2, 1)

    scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM' if preview else 'HIGH'
    if AUDIO_PATH:
        scene.render.ffmpeg.audio_codec = 'AAC'
    scene.render.filepath = output_path
    bpy.ops.render.render(animation=True)
    print("[Stage4] video written:", output_path)


if __name__ == "__main__":
    main()
