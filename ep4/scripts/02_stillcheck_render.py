# -*- coding: utf-8 -*-
"""
Stage 2: 静止画チェック(指定フレームだけを半分の解像度でレンダー)

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/02_stillcheck_render.py" -- 1
  (末尾に cycles を付けるとCyclesでレンダーし、ファイル名に_cyclesを付ける。"--cycles"はCycles自身の
  --cycles-device等の省略形とみなされてBlenderが即終了するので、ハイフンなしにする)
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from frame_state import apply_frame, setup_render
from shots import STILLCHECK_DIR, WIP_BLEND

PREVIEW_PERCENTAGE = 50  # 確認用なので半分の解像度で速く回す


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    cycles = "cycles" in argv
    frames = [int(a) for a in argv if a != "cycles"] or [1]

    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene, PREVIEW_PERCENTAGE, cycles=cycles)
    os.makedirs(STILLCHECK_DIR, exist_ok=True)

    for frame in frames:
        apply_frame(scene, frame)
        output_path = os.path.join(STILLCHECK_DIR, f"ep4_frame_{frame:04d}{'_cycles' if cycles else ''}.png")
        scene.render.filepath = output_path
        bpy.ops.render.render(write_still=True)
        print("[Stage2] rendered:", output_path)


if __name__ == "__main__":
    main()
