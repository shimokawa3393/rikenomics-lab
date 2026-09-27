# -*- coding: utf-8 -*-
"""
Stage 3: 全フレームをPNG連番でレンダーする(状態はframe_state.apply_frameが毎フレーム計算)

実行(開始・終了フレームは省略可):
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep3/scripts/03_full_render.py" -- 1 720
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from frame_state import apply_frame, setup_render
from shots import FRAMES_DIR, TOTAL_FRAMES, WIP_BLEND


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    start = int(argv[0]) if len(argv) > 0 else 1
    end = int(argv[1]) if len(argv) > 1 else TOTAL_FRAMES

    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene)
    os.makedirs(FRAMES_DIR, exist_ok=True)

    for frame in range(start, end + 1):
        apply_frame(scene, frame)
        scene.render.filepath = os.path.join(FRAMES_DIR, f"ep3_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[Stage3] frame {frame}/{end}", flush=True)


if __name__ == "__main__":
    main()
