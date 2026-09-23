# -*- coding: utf-8 -*-
"""
Stage 2: 静止画ゲート ── ④結(全体俯瞰)の構図で1枚レンダーし、絵作りを確認する

制作設計書「3. 制作の順序」に従い、カメラワークを組む前にここで一旦止める。
このレンダーで「2本の軌跡が編み込まれて同じ蝶の形に見えるか」「色・質感が
狙い通りか」をユーザーに確認してもらってから、Stage 3(カメラアニメーション)に進む。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep2/scripts/02_stillcheck_render.py"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import mathutils
from shots import WIP_BLEND, STILLCHECK_DIR


def main():
    bpy.ops.wm.open_mainfile(filepath=WIP_BLEND)
    scene = bpy.context.scene

    # ------------------------------------------------------------
    # 参照画像の斜め見下ろしアングルに寄せたカメラ配置
    # ------------------------------------------------------------
    target = bpy.data.objects.get("AttractorCenter")
    if target is None:
        bpy.ops.object.empty_add(type='PLAIN_AXES', location=(0, 0, 0))
        target = bpy.context.active_object
        target.name = "AttractorCenter"

    camera = bpy.data.objects.get("MainCamera")
    if camera is None:
        bpy.ops.object.camera_add(location=(6.0, -8.5, 3.5))
        camera = bpy.context.active_object
        camera.name = "MainCamera"
    camera.location = (6.0, -8.5, 3.5)

    track = camera.constraints.get("Track To")
    if track is None:
        track = camera.constraints.new('TRACK_TO')
    track.target = target
    track.track_axis = 'TRACK_NEGATIVE_Z'
    track.up_axis = 'UP_Y'

    scene.camera = camera

    fill = bpy.data.objects.get("FillLight")
    if fill is None:
        bpy.ops.object.light_add(type='POINT', location=(0, -5, 4))
        fill = bpy.context.active_object
        fill.name = "FillLight"
    fill.data.energy = 60
    fill.data.color = (0.6, 0.7, 1.0)

    # ------------------------------------------------------------
    # レンダー設定
    # ------------------------------------------------------------
    engine_ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_ids else 'BLENDER_EEVEE'
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1200
    scene.render.image_settings.file_format = 'PNG'

    os.makedirs(STILLCHECK_DIR, exist_ok=True)
    output_path = os.path.join(STILLCHECK_DIR, "ep2_stillcheck_4a.png")
    scene.render.filepath = output_path
    bpy.ops.render.render(write_still=True)

    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)

    print("[Stage2] stillcheck rendered:", output_path)
    print("[Stage2] この絵が『同じ蝶の形』『色・質感』として成立しているか確認してから Stage 3 へ。")


if __name__ == "__main__":
    main()
