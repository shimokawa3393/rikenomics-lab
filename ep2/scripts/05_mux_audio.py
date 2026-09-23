# -*- coding: utf-8 -*-
"""
Stage 5: BGMを焼き込んで最終動画を出力する

ffmpeg CLIがこのマシンに無いため、Blender自体に組み込まれているFFMPEGを使う。
シーンのVideo Sequence Editorに音声ストリップを追加すると、3Dビューポート
(カメラ)からのレンダリングに、アニメーションレンダー時に自動でミックスされる。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep2/scripts/05_mux_audio.py"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND, SHOTS

MP3_PATH = "/Users/shouheishimokawa/rikenomics-lab/ep2/minimal-ambient-electronic-slow-arpeggiated_092326.mp3"
OUTPUT_MP4 = "/Users/shouheishimokawa/rikenomics-lab/ep2/Rikenomics_Episode02_Lorenz.mp4"

FADE_IN_FRAMES = 10
FADE_OUT_FRAMES = 20


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    total_frames = SHOTS[-1]["frame_end"]

    if scene.sequence_editor is None:
        scene.sequence_editor_create()
    seq = scene.sequence_editor

    # 再実行に備えて既存のサウンドストリップをクリア
    # (Blender 5.x以降、SequenceEditor.sequences/sequences_allはstrips/strips_allに改名)
    for s in list(seq.strips_all):
        if s.type == 'SOUND':
            seq.strips.remove(s)

    sound_strip = seq.strips.new_sound(
        name="BGM", filepath=MP3_PATH, channel=1, frame_start=1
    )

    # フェードイン/アウト(音量キーフレーム)
    sound_strip.volume = 0.0
    sound_strip.keyframe_insert(data_path="volume", frame=1)
    sound_strip.volume = 1.0
    sound_strip.keyframe_insert(data_path="volume", frame=1 + FADE_IN_FRAMES)
    sound_strip.volume = 1.0
    sound_strip.keyframe_insert(data_path="volume", frame=total_frames - FADE_OUT_FRAMES)
    sound_strip.volume = 0.0
    sound_strip.keyframe_insert(data_path="volume", frame=total_frames)

    scene.frame_start = 1
    scene.frame_end = total_frames

    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.image_settings.media_type = 'VIDEO'
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'
    scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
    scene.render.ffmpeg.audio_codec = 'AAC'
    scene.render.ffmpeg.audio_bitrate = 192

    scene.render.filepath = OUTPUT_MP4

    print(f"[Stage5] rendering {scene.frame_start}-{scene.frame_end} (with BGM) -> {OUTPUT_MP4}")
    bpy.ops.render.render(animation=True)
    print("[Stage5] done:", OUTPUT_MP4)


if __name__ == "__main__":
    main()
