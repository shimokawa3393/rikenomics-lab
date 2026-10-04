# -*- coding: utf-8 -*-
"""
車の形の確認: 前後左右と斜め4方向の計8枚(雨なし・明るい曇り空、横長)を stillcheck/turnaround へ

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep5/scripts/02b_turnaround_render.py"
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import mathutils
from frame_state import apply_frame, setup_render
from shots import STILLCHECK_DIR, WIP_BLEND

DISTANCE = 8.0
HEIGHT = 1.5
TARGET = mathutils.Vector((0, 0, 0.72))
LENS = 40.0
VIEWS = [  # (名前, 車の前(+Y)から時計回り(上から見て)の角度)
    ("1_front", 0), ("2_front_right", 45), ("3_right", 90), ("4_rear_right", 135),
    ("5_rear", 180), ("6_rear_left", 225), ("7_left", 270), ("8_front_left", 315),
]


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene
    setup_render(scene, 100, clear=True)
    scene.render.resolution_x, scene.render.resolution_y = 1600, 900
    cam = scene.camera
    cam.data.lens = LENS
    cam.data.sensor_fit = 'HORIZONTAL'
    cam.data.sensor_width = 36.0
    cam.data.dof.use_dof = False
    out_dir = os.path.join(STILLCHECK_DIR, "turnaround")
    os.makedirs(out_dir, exist_ok=True)
    apply_frame(scene, 1)
    for name, deg in VIEWS:
        a = math.radians(deg)
        cam.location = TARGET + mathutils.Vector((DISTANCE * math.sin(a), DISTANCE * math.cos(a), HEIGHT - TARGET.z))
        cam.rotation_euler = (TARGET - cam.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = os.path.join(out_dir, f"{name}.png")
        bpy.ops.render.render(write_still=True)
        print("[Turnaround] rendered:", scene.render.filepath)


if __name__ == "__main__":
    main()
