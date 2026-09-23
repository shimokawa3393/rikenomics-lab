# -*- coding: utf-8 -*-
"""
Stage 4: フルアニメーションレンダー(300フレーム -> 1本のmp4)

Stage3までで確定したアニメーションを、静止画の連番PNGではなく、Blenderの
FFMPEG出力機能で直接1本の動画ファイルにレンダーする。
(ep1では出力ファイル名だけ.mp4にしてimage_settings.file_formatを連番PNGのままに
していたため、実際には大量の連番PNGが生成される失敗があった。ここではfile_format
自体をFFMPEGに設定することで確実に単一の動画ファイルとして出力する)

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep2/scripts/04_full_render.py"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND, SHOTS

OUTPUT_MP4 = "/Users/shouheishimokawa/rikenomics-lab/ep2/Rikenomics_Episode02_Lorenz.mp4"


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene

    scene.frame_start = 1
    scene.frame_end = SHOTS[-1]["frame_end"]

    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200

    # Blender 5.x以降、file_formatに'FFMPEG'を選ぶ前にmedia_typeを'VIDEO'に
    # 切り替える必要がある(image_settings.media_typeが新設された)
    scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.ffmpeg.audio_codec = 'NONE'

    scene.render.filepath = OUTPUT_MP4

    print(f"[Stage4] rendering {scene.frame_start}-{scene.frame_end} -> {OUTPUT_MP4}")
    bpy.ops.render.render(animation=True)
    print("[Stage4] done:", OUTPUT_MP4)


if __name__ == "__main__":
    main()
