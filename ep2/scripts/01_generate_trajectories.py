# -*- coding: utf-8 -*-
"""
Stage 1: 2系統のローレンツ軌跡ジオメトリを生成する

設計書(Rikenomics_制作設計書.md)の方針に従い、この段階ではカメラワークを組まない。
まず「静止画として色・質感・構図が成立する状態」を作ることだけが目的。
アニメーション(bevel_factor_endの推移)はStage 3で追加する。

系統A(基準)とB(Aの初期値をわずか10万分の1だけ摂動したもの)を別オブジェクトとして生成し、
それぞれに固有の色調(A=寒色, B=暖色寄り)を与えて見分けがつくようにする。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep2/scripts/01_generate_trajectories.py"
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import mathutils
from shots import (
    SIGMA, RHO, BETA, DT, TOTAL_STEPS, EPSILON,
    X0, Y0, Z0, SCALE, Z_OFFSET, WIP_BLEND,
)


def compute_trajectory(x0, y0, z0):
    x, y, z = x0, y0, z0
    points = []
    for _ in range(TOTAL_STEPS):
        dx = SIGMA * (y - x)
        dy = x * (RHO - z) - y
        dz = x * y - BETA * z
        x += dx * DT
        y += dy * DT
        z += dz * DT
        points.append((x * SCALE, y * SCALE, z * SCALE + Z_OFFSET))
    return points


def build_curve_object(name, points, bevel_depth):
    curve_data = bpy.data.curves.new(name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 1
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = 2
    curve_data.fill_mode = 'FULL'
    # Stage 3でbevel_factor_endをアニメーションさせるための下準備。
    # このStageでは常に全長(1.0)を表示する。
    curve_data.use_fill_caps = True
    curve_data.bevel_factor_mapping_start = 'RESOLUTION'
    curve_data.bevel_factor_mapping_end = 'RESOLUTION'
    curve_data.bevel_factor_end = 1.0

    polyline = curve_data.splines.new('POLY')
    polyline.points.add(len(points) - 1)
    for i, coord in enumerate(points):
        polyline.points[i].co = (*coord, 1.0)

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    return obj


def build_glow_material(name, color_near, color_mid, color_far, strength):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    output = nt.nodes.new(type='ShaderNodeOutputMaterial')
    emission = nt.nodes.new(type='ShaderNodeEmission')
    color_ramp = nt.nodes.new(type='ShaderNodeValToRGB')
    tex_coord = nt.nodes.new(type='ShaderNodeTexCoord')
    sep_xyz = nt.nodes.new(type='ShaderNodeSeparateXYZ')

    color_ramp.color_ramp.elements[0].color = color_near
    color_ramp.color_ramp.elements[1].color = color_far
    mid = color_ramp.color_ramp.elements.new(0.5)
    mid.color = color_mid

    nt.links.new(tex_coord.outputs['Object'], sep_xyz.inputs['Vector'])
    nt.links.new(sep_xyz.outputs['Z'], color_ramp.inputs['Fac'])
    nt.links.new(color_ramp.outputs['Color'], emission.inputs['Color'])
    emission.inputs['Strength'].default_value = strength
    nt.links.new(emission.outputs[0], output.inputs[0])
    return mat


def build_tip_marker(name, curve_obj, color, strength):
    """軌跡の先端を示す発光点。Follow Pathでカーブ上の位置に正確に追従させる。
    Stage 3で offset_factor をキーフレーム化し、bevel_factor_endと完全同期させる。"""
    bpy.ops.mesh.primitive_ico_sphere_add(radius=0.06, subdivisions=2)
    marker = bpy.context.active_object
    marker.name = name

    mat = bpy.data.materials.new(name=f"{name}Material")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    output = nt.nodes.new(type='ShaderNodeOutputMaterial')
    emission = nt.nodes.new(type='ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = strength
    nt.links.new(emission.outputs[0], output.inputs[0])
    marker.data.materials.append(mat)

    constraint = marker.constraints.new('FOLLOW_PATH')
    constraint.target = curve_obj
    constraint.use_fixed_location = True
    constraint.offset_factor = 1.0  # このStageでは軌跡の末端に置く(全長表示のため)
    return marker


def main():
    # ------------------------------------------------------------
    # 0. シーンを空にする
    # ------------------------------------------------------------
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)

    bpy.context.scene.view_settings.view_transform = 'Standard'
    world = bpy.data.worlds.get("World")
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs[0].default_value = (0, 0, 0, 1)
    bg.inputs[1].default_value = 1.0

    # ------------------------------------------------------------
    # 1. 2系統のローレンツ軌跡を計算
    # ------------------------------------------------------------
    points_a = compute_trajectory(X0, Y0, Z0)
    points_b = compute_trajectory(X0 + EPSILON, Y0, Z0)

    # ------------------------------------------------------------
    # 2. カーブオブジェクト生成(参照画像に合わせ、細い発光チューブに)
    # ------------------------------------------------------------
    curve_a = build_curve_object('TrajectoryA', points_a, bevel_depth=0.008)
    curve_b = build_curve_object('TrajectoryB', points_b, bevel_depth=0.008)

    # 系統A: 寒色(紺 -> 水色 -> 白)
    mat_a = build_glow_material(
        'TrajectoryAGlow',
        color_near=(0.05, 0.15, 0.5, 1),
        color_mid=(0.2, 0.6, 0.95, 1),
        color_far=(0.85, 0.95, 1.0, 1),
        strength=4.0,
    )
    curve_a.data.materials.append(mat_a)

    # 系統B: 暖色寄り(白 -> 黄 -> オレンジ)
    mat_b = build_glow_material(
        'TrajectoryBGlow',
        color_near=(1.0, 1.0, 0.95, 1),
        color_mid=(1.0, 0.85, 0.4, 1),
        color_far=(1.0, 0.55, 0.15, 1),
        strength=4.0,
    )
    curve_b.data.materials.append(mat_b)

    # ------------------------------------------------------------
    # 3. 先端の発光点マーカー
    # ------------------------------------------------------------
    build_tip_marker('TipMarkerA', curve_a, color=(0.4, 0.75, 1.0, 1), strength=15.0)
    build_tip_marker('TipMarkerB', curve_b, color=(1.0, 0.8, 0.5, 1), strength=15.0)

    # ------------------------------------------------------------
    # 4. 保存
    # ------------------------------------------------------------
    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage1] saved WIP file: {WIP_BLEND}")
    print(f"[Stage1] TrajectoryA points: {len(points_a)}, TrajectoryB points: {len(points_b)}")


if __name__ == "__main__":
    main()
