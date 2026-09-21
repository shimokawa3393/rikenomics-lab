# -*- coding: utf-8 -*-
"""
Stage 1: タイムライン設計

- 没ファイルを開き、作業用WIPファイルとして保存する
- シーンのフレーム範囲を240フレーム(8秒 @ 30fps)に拡張
- Astronaut_Root のスケールアニメーションを新タイムラインに合わせて再設定
  (③転=3a/3bの間で通常体型→引き伸ばされた糸状に変形。④結=4aでは伸びきった状態を維持)

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python c1/scripts/01_setup_timeline.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import SOURCE_BLEND, WIP_BLEND, FPS, shot_by_id, total_frame_end
from blender_compat import set_all_keyframes_interpolation


def setup_timeline():
    bpy.ops.wm.open_mainfile(filepath=SOURCE_BLEND)
    scene = bpy.context.scene

    scene.frame_start = 1
    scene.frame_end = total_frame_end()
    scene.render.fps = FPS
    print(f"[Stage1] timeline set to {scene.frame_start}-{scene.frame_end} @ {scene.render.fps}fps")

    root = bpy.data.objects["Astronaut_Root"]
    root.animation_data_clear()

    shot_1a = shot_by_id("1a")
    shot_2a = shot_by_id("2a")
    shot_3a = shot_by_id("3a")
    shot_3b = shot_by_id("3b")

    def key_scale(frame, scale):
        root.scale = scale
        root.keyframe_insert(data_path="scale", frame=frame)

    # 起・承：まだ通常の体型のまま平然と落下
    key_scale(shot_1a["frame_start"], (1.0, 1.0, 1.0))
    key_scale(shot_2a["frame_end"], (1.0, 1.0, 1.0))
    # 転(前半)：足への引力が勝り始め、伸び始める
    key_scale(shot_3a["frame_end"], (0.55, 0.55, 3.4))
    # 転(後半)：完全に引き伸ばされ糸状になる
    key_scale(shot_3b["frame_end"], (0.16, 0.16, 7.0))
    # 結：外部観測者視点では、もう変化は進まない(引き裂かれた状態で固定)

    set_all_keyframes_interpolation(root, interpolation="QUAD", easing="EASE_IN")

    print("[Stage1] Astronaut_Root scale keyframes:", shot_1a["frame_start"], shot_2a["frame_end"],
          shot_3a["frame_end"], shot_3b["frame_end"])

    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage1] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    setup_timeline()
