"""
Rikenomics 第2話 - ストレンジアトラクター（ローレンツアトラクター）生成スクリプト
Blenderの「Scripting」タブ、またはClaude Desktop経由のexecute_blender_codeで実行する。

設計書(Rikenomics_制作設計書.md)の方針に従い、まずカメラワークを組まず、
1枚の静止画として色・質感・構図が成立する状態を確認してから次に進むこと。

人物モデリング・光の歪み(重力レンズ)を一切使わないため、
エピソード1でつまずいた2つの難所を両方とも回避できる構成になっている。
"""

import bpy
import bmesh
import math

# ============================================
# 0. シーンを空にする（エピソード1のオブジェクトが残っていれば削除）
# ============================================
for obj in list(bpy.data.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
for mat in list(bpy.data.materials):
    if mat.users == 0:
        bpy.data.materials.remove(mat)

# 背景を漆黒に（Standardカラーマネジメントで、Filmicの黒浮きを回避）
bpy.context.scene.view_settings.view_transform = 'Standard'
world = bpy.data.worlds.get("World")
if world is None:
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes.get("Background")
bg.inputs[0].default_value = (0, 0, 0, 1)
bg.inputs[1].default_value = 1.0

# ============================================
# 1. ローレンツ方程式を数値計算し、座標列を作る
# ============================================
# dx/dt = sigma * (y - x)
# dy/dt = x * (rho - z) - y
# dz/dt = x * y - beta * z
sigma, rho, beta = 10.0, 28.0, 8.0 / 3.0
dt = 0.005
steps = 6000

x, y, z = 0.1, 0.0, 0.0
points = []
for i in range(steps):
    dx = sigma * (y - x)
    dy = x * (rho - z) - y
    dz = x * y - beta * z
    x += dx * dt
    y += dy * dt
    z += dz * dt
    points.append((x * 0.12, y * 0.12, z * 0.12 - 3.0))  # スケール調整して原点付近に収める

# ============================================
# 2. 座標列からカーブオブジェクトを作成し、チューブ状に太さを持たせる
# ============================================
curve_data = bpy.data.curves.new('LorenzCurve', type='CURVE')
curve_data.dimensions = '3D'
curve_data.resolution_u = 4
curve_data.bevel_depth = 0.025      # チューブの太さ
curve_data.bevel_resolution = 4
curve_data.fill_mode = 'FULL'

polyline = curve_data.splines.new('POLY')
polyline.points.add(len(points) - 1)
for i, coord in enumerate(points):
    polyline.points[i].co = (*coord, 1.0)

curve_obj = bpy.data.objects.new('LorenzAttractor', curve_data)
bpy.context.collection.objects.link(curve_obj)

# ============================================
# 3. 発光マテリアルを設定（進行方向で色が変化するグラデーション）
# ============================================
glow_mat = bpy.data.materials.new(name="AttractorGlowMaterial")
glow_mat.use_nodes = True
nt = glow_mat.node_tree
nt.nodes.clear()
output = nt.nodes.new(type='ShaderNodeOutputMaterial')
emission = nt.nodes.new(type='ShaderNodeEmission')
color_ramp = nt.nodes.new(type='ShaderNodeValToRGB')
tex_coord = nt.nodes.new(type='ShaderNodeTexCoord')
sep_xyz = nt.nodes.new(type='ShaderNodeSeparateXYZ')

# 軌跡の位置(Z成分)に応じて青緑〜マゼンタにグラデーション
color_ramp.color_ramp.elements[0].color = (0.1, 0.5, 1.0, 1)   # 青
color_ramp.color_ramp.elements[1].color = (0.9, 0.1, 0.6, 1)   # マゼンタ
mid = color_ramp.color_ramp.elements.new(0.5)
mid.color = (0.3, 0.9, 0.7, 1)  # 中間: 青緑

nt.links.new(tex_coord.outputs['Object'], sep_xyz.inputs['Vector'])
nt.links.new(sep_xyz.outputs['Z'], color_ramp.inputs['Fac'])
nt.links.new(color_ramp.outputs['Color'], emission.inputs['Color'])
emission.inputs['Strength'].default_value = 6.0
nt.links.new(emission.outputs[0], output.inputs[0])

curve_obj.data.materials.append(glow_mat)

# ============================================
# 4. カメラと控えめな補助光を配置（まずは静止画としての構図を作る）
# ============================================
bpy.ops.object.camera_add(location=(4, -6, 1.5))
camera = bpy.context.active_object
import mathutils
direction = mathutils.Vector((0, 0, -3)) - camera.location
camera.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
bpy.context.scene.camera = camera

bpy.ops.object.light_add(type='POINT', location=(0, -3, 2))
fill = bpy.context.active_object
fill.data.energy = 30
fill.data.color = (0.6, 0.7, 1.0)

# ============================================
# 5. 静止画として1枚レンダリング(確認用)
# ============================================
import os
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items] else 'BLENDER_EEVEE'
scene.render.resolution_x = 900
scene.render.resolution_y = 900
output_path = os.path.expanduser("~/Desktop/spaghettification_frames/ep2_attractor_stillcheck.png")
scene.render.filepath = output_path
scene.render.image_settings.file_format = 'PNG'
bpy.ops.render.render(write_still=True)

print("ローレンツアトラクターの生成が完了しました。")
print("静止画チェック用画像:", output_path)
print("まずはこの1枚が『絵として』成立しているか確認してから、カメラワークを検討すること。")
