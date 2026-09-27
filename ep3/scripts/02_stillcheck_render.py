# -*- coding: utf-8 -*-
"""
Stage 2 / 2.5: 代表フレームの静止画チェック

アニメーションと同じframe_state.apply_frameで指定フレームの状態を作り、1枚ずつレンダーする。
設計書「3. 制作の順序」の通り、フルレンダーの前に各ショットの境目・中間フレームで
フレームアウトや演出タイミングのズレがないかをここで確認する。

実行(フレーム番号を省略すると各ショットの中間と境目):
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep3/scripts/02_stillcheck_render.py" -- 45 300
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from frame_state import apply_frame, setup_render
from shots import SHOT_FRAMES, STILLCHECK_DIR, WIP_BLEND

PREVIEW_PERCENTAGE = 50  # 確認用なので半分の解像度で速く回す


def default_frames():
    frames = set()
    for start, end in SHOT_FRAMES.values():
        frames.update((start, (start + end) // 2, end))
    return sorted(frames)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    frames = [int(a) for a in argv] or default_frames()

    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene, PREVIEW_PERCENTAGE)
    os.makedirs(STILLCHECK_DIR, exist_ok=True)

    for frame in frames:
        apply_frame(scene, frame)
        output_path = os.path.join(STILLCHECK_DIR, f"ep3_frame_{frame:04d}.png")
        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
        print("[Stage2.5] rendered:", output_path)


if __name__ == "__main__":
    main()
