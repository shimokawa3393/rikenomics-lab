# -*- coding: utf-8 -*-
"""
Stage 2: 落下運動 + Shot 1a(起)・2a(承) カメラワーク

- Astronaut_Root のZ位置に落下アニメーションを追加する。
  事象の地平線(z=-4.2)に近づくほど動きが遅くなる(EASE_OUT)よう設計し、
  重力赤方偏移――外部から見ると地平線への接近が無限に引き延ばされて見える現象――を
  視覚的に予告しておく（実際の「止まって見える」演出は Stage 4 の4aで作る）。
- カメラの向きは Track To コンストレイントで自動追尾させる
  (位置だけキーフレームすればよく、手動のオイラー角計算によるミスを避けられる)。
- Shot 1a: カメラは人物の背後、ブラックホールを見据える構図 → target = Black Hole
- Shot 2a: カメラは人物にゆっくり寄っていく(ドリーイン) → target = Astronaut_Root

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python c1/scripts/02_shot1a_2a_camera.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND, shot_by_id
from blender_compat import set_all_keyframes_interpolation


def ensure_camera(name):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam_data = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cam_data)
        bpy.context.collection.objects.link(cam)
    return cam


def add_track_to(cam, target):
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    con = cam.constraints.new("TRACK_TO")
    con.target = target
    con.track_axis = "TRACK_NEGATIVE_Z"
    con.up_axis = "UP_Y"
    return con


def key_loc(obj, frame, loc):
    obj.location = loc
    obj.keyframe_insert(data_path="location", frame=frame)


def setup_fall_motion():
    """Astronaut_Root のZ位置に落下アニメーションを追加する。"""
    root = bpy.data.objects["Astronaut_Root"]

    shot_1a = shot_by_id("1a")
    shot_2a = shot_by_id("2a")
    shot_3a = shot_by_id("3a")
    shot_3b = shot_by_id("3b")

    # x, yは0のまま、z方向にまっすぐ落下させる
    key_loc(root, shot_1a["frame_start"], (0.0, 0.0, 3.0))
    key_loc(root, shot_1a["frame_end"], (0.0, 0.0, 1.2))
    key_loc(root, shot_2a["frame_end"], (0.0, 0.0, -3.8))   # 事象の地平線(z=-4.2)に接近
    key_loc(root, shot_3a["frame_end"], (0.0, 0.0, -4.15))  # 地平線のすぐ内側、動きが目に見えて遅くなる
    key_loc(root, shot_3b["frame_end"], (0.0, 0.0, -4.22))

    set_all_keyframes_interpolation(root, interpolation="SINE", easing="EASE_OUT")
    print("[Stage2] fall motion keyframed on Astronaut_Root.location")


def setup_shot_1a():
    """カメラは人物の背後(やや上空)から、その先のブラックホールを見据える構図。

    人物は真下(-Z方向)のブラックホールへ落下していくので、カメラは
    「人物 → ブラックホール」の視線とほぼ一直線に重なる後方上空に置き、
    人物のシルエットとブラックホールを同一画角に収める。
    """
    shot = shot_by_id("1a")
    cam = ensure_camera("Shot1a Camera")
    cam.data.lens = 35  # 広角寄りにして人物とブラックホールを収めやすくする
    black_hole = bpy.data.objects["Black Hole"]
    add_track_to(cam, black_hole)

    key_loc(cam, shot["frame_start"], (0.0, 2.0, 6.2))
    key_loc(cam, shot["frame_end"], (0.0, 1.8, 4.2))

    set_all_keyframes_interpolation(cam, interpolation="SINE", easing="EASE_IN_OUT")
    print("[Stage2] Shot1a camera keyframed (target=Black Hole)")
    return cam


def setup_shot_2a():
    """カメラは人物に寄っていく(ドリーイン)。人物のすぐ後方から追従する。"""
    shot = shot_by_id("2a")
    cam = ensure_camera("Shot2a Camera")
    cam.data.lens = 35
    root = bpy.data.objects["Astronaut_Root"]
    add_track_to(cam, root)

    key_loc(cam, shot["frame_start"], (0.0, 1.6, 3.6))
    key_loc(cam, shot["frame_end"], (0.0, 3.5, -0.8))  # Black Hole球(半径1.45,中心距離約4.9)に十分な距離を確保

    set_all_keyframes_interpolation(cam, interpolation="SINE", easing="EASE_IN_OUT")
    print("[Stage2] Shot2a camera keyframed (target=Astronaut_Root)")
    return cam


def set_active_camera_switch():
    """シーンカメラをShot1a→Shot2aで切り替えるマーカーを打つ。"""
    scene = bpy.context.scene
    shot_1a = shot_by_id("1a")
    shot_2a = shot_by_id("2a")

    cam_1a = bpy.data.objects["Shot1a Camera"]
    cam_2a = bpy.data.objects["Shot2a Camera"]

    m1 = scene.timeline_markers.new("cam_1a", frame=shot_1a["frame_start"])
    m1.camera = cam_1a
    m2 = scene.timeline_markers.new("cam_2a", frame=shot_2a["frame_start"])
    m2.camera = cam_2a

    scene.camera = cam_1a
    print("[Stage2] camera switch markers: cam_1a @",
          shot_1a["frame_start"], " cam_2a @", shot_2a["frame_start"])


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    setup_fall_motion()
    setup_shot_1a()
    setup_shot_2a()
    set_active_camera_switch()
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage2] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
