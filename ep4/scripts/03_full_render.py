# -*- coding: utf-8 -*-
"""
Stage 3: PNG連番をレンダーする(状態はframe_state.apply_frameが毎フレーム計算)

実行(開始・終了フレームは省略可。preview: 半分の解像度で ep4/preview_frames へ。
draft: 動きの確認用に4分の1の解像度・低画質・2フレームに1枚で ep4/draft_frames へ):
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/03_full_render.py"
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/03_full_render.py" -- draft
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/03_full_render.py" -- 121 420 preview
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from frame_state import apply_frame, setup_render
from shots import DRAFT_FRAMES_DIR, FRAMES_DIR, PREVIEW_FRAMES_DIR, TOTAL_FRAMES, WIP_BLEND

DRAFT_STEP = 2  # ドラフトは2フレームに1枚(15fpsで再生)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    draft, preview = "draft" in argv, "preview" in argv
    numbers = [int(a) for a in argv if a.isdigit()]
    start = numbers[0] if len(numbers) > 0 else 1
    end = numbers[1] if len(numbers) > 1 else TOTAL_FRAMES
    out_dir = DRAFT_FRAMES_DIR if draft else PREVIEW_FRAMES_DIR if preview else FRAMES_DIR

    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene, 25 if draft else 50 if preview else 100)
    if draft:
        scene.eevee.taa_render_samples = 8
        scene.eevee.use_raytracing = False
    os.makedirs(out_dir, exist_ok=True)

    step = DRAFT_STEP if draft else 1
    first = start + (-(start - 1) % step)  # ドラフトでは奇数フレーム(1, 3, 5, ...)にそろえる
    for frame in range(first, end + 1, step):
        apply_frame(scene, frame)
        scene.render.filepath = os.path.join(out_dir, f"ep4_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"[Stage3] frame {frame}/{end}", flush=True)


if __name__ == "__main__":
    main()
