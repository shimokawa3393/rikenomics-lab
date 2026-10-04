# -*- coding: utf-8 -*-
"""
Stage 2: 静止画チェック(指定フレームだけを半分の解像度でレンダー)

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep5/scripts/02_stillcheck_render.py" -- 1
  (full を付けると本番の解像度。clear を付けると雨なし・明るい曇り空で車の形を見る)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from frame_state import apply_frame, setup_render
from shots import STILLCHECK_DIR, WIP_BLEND


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    full = "full" in argv
    clear = "clear" in argv
    frames = [int(a) for a in argv if a.isdigit()] or [1]
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene, 100 if full else 50, clear)
    os.makedirs(STILLCHECK_DIR, exist_ok=True)
    for frame in frames:
        apply_frame(scene, frame)
        path = os.path.join(STILLCHECK_DIR, f"ep5_frame_{frame:04d}{'_clear' if clear else ''}{'_full' if full else ''}.png")
        scene.render.filepath = path
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print(f"[Stage2] rendered: {path} ({time.time() - t0:.1f}s)")


if __name__ == "__main__":
    main()
