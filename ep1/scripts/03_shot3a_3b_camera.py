# -*- coding: utf-8 -*-
"""
Stage 3: Shot 3a(転-前半)・3b(転-後半) カメラワーク

台本指定:「カメラは真横から、その様子を克明に映す」――Stage1で設定済みの
Astronaut_Root スケールアニメーションにより体が縦に最大7倍まで伸びるため、
伸びに応じてカメラをX軸上(真横)で引いていき、常に全身が画角に収まるようにする。

注記: Stage2のfall motionにより、この区間ではAstronaut_Rootが事象の地平線の
内側(Black Hole球の中、中心z=-4.2にほぼ重なる位置)にいる。3a/3bは地平線通過後の
本人視点の変形描写であり、本来は外部から見えないはずの領域なので、Black Hole・
Accretion Disk・Event Horizon Ringをこの区間だけ非表示にし、人物の変形のみに
フォーカスさせる(4a開始で元に戻す)。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background \
    --python ep1/scripts/03_shot3a_3b_camera.py
"""
import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import WIP_BLEND, shot_by_id
from blender_compat import set_all_keyframes_interpolation

LENS_MM = 24
SENSOR_MM = 36
MARGIN = 1.3  # 全身の上下に少し余白を持たせる係数

BASE_HEIGHT = 2.9  # 通常体型(scale=1.0)での人物のおおよその全高(m)

BLACK_HOLE_RELATED = ["Black Hole", "Accretion Disk", "Event Horizon Ring"]


def ensure_camera(name):
    cam = bpy.data.objects.get(name)
    if cam is None:
        cam_data = bpy.data.cameras.new(name)
        cam = bpy.data.objects.new(name, cam_data)
        bpy.context.collection.objects.link(cam)
    cam.data.lens = LENS_MM
    cam.data.sensor_fit = "VERTICAL"
    cam.data.sensor_height = SENSOR_MM
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


def key_hide_render(obj, frame, hidden):
    obj.hide_render = hidden
    obj.keyframe_insert(data_path="hide_render", frame=frame)


def distance_for_height(height):
    half_fov = math.atan((SENSOR_MM / 2) / LENS_MM)
    return (height / 2) / math.tan(half_fov) * MARGIN


def setup_shot_3a_3b():
    """真横(X軸)からスパゲッティ化を捉える。体の伸びに応じてカメラを引く。"""
    root = bpy.data.objects["Astronaut_Root"]
    shot_3a = shot_by_id("3a")
    shot_3b = shot_by_id("3b")
    scene = bpy.context.scene

    cam = ensure_camera("Shot3ab Camera")
    add_track_to(cam, root)

    # (frame, Astronaut_Root.scale.z) はStage1のキーフレームと一致させる
    keyframes = [
        (shot_3a["frame_start"], 1.0),
        (shot_3a["frame_end"], 3.4),
        (shot_3b["frame_end"], 7.0),
    ]
    for frame, scale_z in keyframes:
        # Astronaut_Root.location はStage2で落下アニメーション済みなので、
        # 該当フレームまで評価を進めてから実際のZ位置を取得する
        # (ファイルロード直後の値のまま読むとframe1の位置になってしまう)
        scene.frame_set(frame)
        root_z = root.matrix_world.translation.z
        height = BASE_HEIGHT * scale_z
        dist = distance_for_height(height)
        key_loc(cam, frame, (dist, 0.0, root_z))

    set_all_keyframes_interpolation(cam, interpolation="SINE", easing="EASE_IN_OUT")
    print("[Stage3] Shot3ab camera keyframed (target=Astronaut_Root)")
    return cam


def setup_black_hole_visibility():
    """3a/3b区間だけBlack Hole周りを非表示にし、人物の変形描写にフォーカスする。"""
    shot_2a = shot_by_id("2a")
    shot_3a = shot_by_id("3a")
    shot_3b = shot_by_id("3b")
    shot_4a = shot_by_id("4a")

    for name in BLACK_HOLE_RELATED:
        obj = bpy.data.objects[name]
        obj.animation_data_clear()
        key_hide_render(obj, shot_2a["frame_end"], False)
        key_hide_render(obj, shot_3a["frame_start"], True)
        key_hide_render(obj, shot_3b["frame_end"], True)
        key_hide_render(obj, shot_4a["frame_start"], False)
        set_all_keyframes_interpolation(obj, interpolation="CONSTANT", easing="EASE_IN_OUT")
    print("[Stage3] Black Hole/Disk/Ring hidden during 3a-3b")


def set_active_camera_switch():
    scene = bpy.context.scene
    shot_3a = shot_by_id("3a")
    cam_3ab = bpy.data.objects["Shot3ab Camera"]

    m = scene.timeline_markers.new("cam_3ab", frame=shot_3a["frame_start"])
    m.camera = cam_3ab
    print("[Stage3] camera switch marker: cam_3ab @", shot_3a["frame_start"])


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    setup_shot_3a_3b()
    setup_black_hole_visibility()
    set_active_camera_switch()
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage3] saved WIP file: {WIP_BLEND}")


if __name__ == "__main__":
    main()
