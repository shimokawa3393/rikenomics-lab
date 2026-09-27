# -*- coding: utf-8 -*-
"""
Stage 1: 太陽・惑星・軌道リング・軌跡のジオメトリを生成する

- 太陽は常に原点に置き、軌跡は太陽の後ろ(-X)に伸びる(カメラは太陽基準で置けばよい)。
  太陽・点光源・惑星は空オブジェクト"HelioFrame"(原点)の子にする。
- 1aの円軌道は専用のオブジェクトを持たず、軌跡そのものを太陽基準で表示したもの。
- ジオメトリは最終フレーム(銀河基準・EPOCH)の状態で生成し、フレームごとの状態
  (軌跡の頂点、惑星位置、表示・強調)はframe_state.pyが更新する。
- 軌跡のフェード(先頭が明るく過去ほど暗い)はマテリアル内のMap RangeのFrom Min
  (=-blend*forward_extent)をframe_state.pyから更新する。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep3/scripts/01_generate_geometry.py"
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import mathutils
from shots import (
    DISPLAY,
    PLANET_COLORS,
    TOTAL_FRAMES,
    WIP_BLEND,
    common_forward_extent_units,
    spiral_points,
    pole_scene,
    sun_trail_points,
)

# 見た目上の球の半径(実寸比ではない。軌道間隔0.6ユニットに対して読める大きさ)
PLANET_DISPLAY_RADIUS = {
    "Mercury": 0.09,
    "Venus": 0.13,
    "Earth": 0.14,
    "Mars": 0.11,
    "Jupiter": 0.30,
    "Saturn": 0.25,
    "Uranus": 0.19,
    "Neptune": 0.19,
}
# 土星の環(土星半径に対する内径・外径。実物はおよそ1.24〜2.27倍)
SATURN_RING_RADII = (1.24, 2.27)

# Solar System Scope のテクスチャ(CC BY 4.0、投稿文にクレジット表記が必要)
TEXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "textures")
TEXTURES = {
    "Sun": "2k_sun.jpg",
    "Mercury": "2k_mercury.jpg",
    "Venus": "2k_venus_atmosphere.jpg",
    "Earth": "2k_earth_daymap.jpg",
    "Mars": "2k_mars.jpg",
    "Jupiter": "2k_jupiter.jpg",
    "Saturn": "2k_saturn.jpg",
    "Uranus": "2k_uranus.jpg",
    "Neptune": "2k_neptune.jpg",
}
SATURN_RING_TEXTURE = "2k_saturn_ring_alpha.png"
SATURN_RING_TRANSLUCENCY = 0.5  # 裏へ透ける光の割合(影の面から見たときの明るさ)
SUN_RADIUS = 0.3
TRAIL_STRENGTH = 3.0
TRAIL_FADE_POWER = 3.0  # 大きいほど過去側が早く消える(frame_state.pyの値で毎フレーム上書き)
TRAIL_OPACITY = 0.5  # 先頭での不透明度(最初から少し透かす)
SUN_TRAIL_COLOR = (1.0, 0.8, 0.5, 1)


def new_material(name):
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat, mat.node_tree


def build_trail_material(name, color, forward_extent):
    """先頭(x=0)で最も濃く、過去(-X)に向かって透けながら消えていく発光マテリアル。
    明るさは落とさず不透明度だけを下げるので、線の奥の星や天の川が透けて見える。

    frame_state.pyから触るノード: MAP_RANGE(From Minでフェード範囲)、POWER(フェードの効き)、
    名前"Gain"のMath(明るさの倍率)。
    """
    mat, nt = new_material(name)
    mat.surface_render_method = 'BLENDED'
    output = nt.nodes.new('ShaderNodeOutputMaterial')
    emission = nt.nodes.new('ShaderNodeEmission')
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    tex_coord = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    map_range = nt.nodes.new('ShaderNodeMapRange')
    power = nt.nodes.new('ShaderNodeMath')
    opacity = nt.nodes.new('ShaderNodeMath')
    gain = nt.nodes.new('ShaderNodeMath')
    gain.name = "Gain"

    map_range.inputs['From Min'].default_value = -forward_extent
    map_range.inputs['From Max'].default_value = 0.0
    map_range.clamp = True
    power.operation = 'POWER'
    power.inputs[1].default_value = TRAIL_FADE_POWER
    opacity.operation = 'MULTIPLY'
    opacity.inputs[1].default_value = TRAIL_OPACITY
    gain.operation = 'MULTIPLY'
    gain.inputs[0].default_value = 1.0
    gain.inputs[1].default_value = TRAIL_STRENGTH
    emission.inputs['Color'].default_value = color

    nt.links.new(tex_coord.outputs['Object'], sep.inputs[0])
    nt.links.new(sep.outputs['X'], map_range.inputs['Value'])
    nt.links.new(map_range.outputs[0], power.inputs[0])
    nt.links.new(power.outputs[0], opacity.inputs[0])
    nt.links.new(gain.outputs[0], emission.inputs['Strength'])
    nt.links.new(opacity.outputs[0], mix.inputs['Fac'])
    nt.links.new(transparent.outputs[0], mix.inputs[1])
    nt.links.new(emission.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], output.inputs[0])
    return mat


def build_emission_material(name, color, strength):
    mat, nt = new_material(name)
    output = nt.nodes.new('ShaderNodeOutputMaterial')
    emission = nt.nodes.new('ShaderNodeEmission')
    emission.inputs['Color'].default_value = color
    emission.inputs['Strength'].default_value = strength
    nt.links.new(emission.outputs[0], output.inputs[0])
    return mat


def build_polyline(name, points, material, bevel_depth, cyclic=False, parent=None):
    curve_data = bpy.data.curves.new(name, type='CURVE')
    curve_data.dimensions = '3D'
    curve_data.resolution_u = 1
    curve_data.bevel_depth = bevel_depth
    curve_data.bevel_resolution = 2
    curve_data.fill_mode = 'FULL'
    curve_data.use_fill_caps = not cyclic

    polyline = curve_data.splines.new('POLY')
    polyline.points.add(len(points) - 1)
    for i, coord in enumerate(points):
        polyline.points[i].co = (*coord, 1.0)
    polyline.use_cyclic_u = cyclic

    obj = bpy.data.objects.new(name, curve_data)
    bpy.context.collection.objects.link(obj)
    obj.parent = parent
    obj.data.materials.append(material)
    return obj


def build_sphere(name, radius, location, material, parent):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=radius, location=(0, 0, 0), segments=48, ring_count=24)
    obj = bpy.context.active_object
    obj.name = name
    bpy.ops.object.shade_smooth()  # プリミティブはデフォルトでフラットシェーディング(設計書の既知の罠)
    obj.parent = parent
    obj.location = location
    obj.data.materials.append(material)
    return obj


def load_texture(nt, filename):
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(os.path.join(TEXTURE_DIR, filename), check_existing=True)
    return tex


def build_planet_material(name, texture):
    mat, nt = new_material(name)
    output = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.8
    nt.links.new(load_texture(nt, texture).outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(bsdf.outputs[0], output.inputs[0])
    return mat


def build_sun_material():
    mat, nt = new_material("SunSurface")
    output = nt.nodes.new('ShaderNodeOutputMaterial')
    emission = nt.nodes.new('ShaderNodeEmission')
    emission.inputs['Strength'].default_value = 25.0
    nt.links.new(load_texture(nt, TEXTURES["Sun"]).outputs['Color'], emission.inputs['Color'])
    nt.links.new(emission.outputs[0], output.inputs[0])
    return mat


def align_to_pole(obj, name):
    """球のローカル+Z(テクスチャの北極)を実際の自転軸の向きに合わせる。"""
    obj.rotation_mode = 'QUATERNION'
    obj.rotation_quaternion = mathutils.Vector((0, 0, 1)).rotation_difference(mathutils.Vector(pole_scene(name)))


def build_saturn_ring(saturn, planet_radius, segments=96):
    """土星の子として環(平らな円環)を作る。土星の球が自転軸に合わせて傾いているので、
    環は土星のローカルXY平面に置けば赤道面に一致する。テクスチャは内側→外側の帯。"""
    inner, outer = (planet_radius * r for r in SATURN_RING_RADII)
    verts, faces = [], []
    for i in range(segments):
        a = 2 * math.pi * i / segments
        verts.append((inner * math.cos(a), inner * math.sin(a), 0.0))
        verts.append((outer * math.cos(a), outer * math.sin(a), 0.0))
    for i in range(segments):
        j = (i + 1) % segments
        faces.append((2 * i, 2 * i + 1, 2 * j + 1, 2 * j))
    mesh = bpy.data.meshes.new("SaturnRing")
    mesh.from_pydata(verts, [], faces)
    uv = mesh.uv_layers.new(name="UVMap")
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi = mesh.loops[li].vertex_index
            uv.data[li].uv = (float(vi % 2), 0.5)  # 偶数=内径, 奇数=外径
    ring = bpy.data.objects.new("SaturnRing", mesh)
    bpy.context.collection.objects.link(ring)
    ring.parent = saturn

    # 環は氷の粒が太陽光を透かして散らすので、影の面から見ても暗く光って見える。
    # 表側の反射(Principled)と裏へ透ける光(Translucent)を半分ずつ混ぜ、PNGのアルファで抜く。
    mat, nt = new_material("SaturnRingSurface")
    output = nt.nodes.new('ShaderNodeOutputMaterial')
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.inputs['Roughness'].default_value = 0.9
    translucent = nt.nodes.new('ShaderNodeBsdfTranslucent')
    transparent = nt.nodes.new('ShaderNodeBsdfTransparent')
    lit_mix = nt.nodes.new('ShaderNodeMixShader')
    lit_mix.inputs['Fac'].default_value = SATURN_RING_TRANSLUCENCY
    alpha_mix = nt.nodes.new('ShaderNodeMixShader')
    tex = load_texture(nt, SATURN_RING_TEXTURE)
    nt.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
    nt.links.new(tex.outputs['Color'], translucent.inputs['Color'])
    nt.links.new(bsdf.outputs[0], lit_mix.inputs[1])
    nt.links.new(translucent.outputs[0], lit_mix.inputs[2])
    nt.links.new(tex.outputs['Alpha'], alpha_mix.inputs['Fac'])
    nt.links.new(transparent.outputs[0], alpha_mix.inputs[1])
    nt.links.new(lit_mix.outputs[0], alpha_mix.inputs[2])
    nt.links.new(alpha_mix.outputs[0], output.inputs[0])
    ring.data.materials.append(mat)
    return ring


def main():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for block in (bpy.data.materials, bpy.data.curves, bpy.data.meshes, bpy.data.lights, bpy.data.images):
        for item in list(block):
            if item.users == 0:
                block.remove(item)

    forward_extent = common_forward_extent_units()
    head = (0.0, 0.0, 0.0)

    helio = bpy.data.objects.new("HelioFrame", None)
    bpy.context.collection.objects.link(helio)
    helio.location = head

    sun = build_sphere("Sun", SUN_RADIUS, (0, 0, 0), build_sun_material(), helio)
    align_to_pole(sun, "Sun")
    sun.visible_shadow = False  # 内側の点光源を遮らないように

    light_data = bpy.data.lights.new("SunLight", type='POINT')
    light_data.energy = 5000
    light_data.color = (1.0, 0.9, 0.75)
    light_data.shadow_soft_size = SUN_RADIUS
    light = bpy.data.objects.new("SunLight", light_data)
    bpy.context.collection.objects.link(light)
    light.parent = helio

    for name in DISPLAY:
        color = PLANET_COLORS[name]
        points = spiral_points(name, blend=1.0)
        build_polyline(f"Trail_{name}", points, build_trail_material(f"Trail_{name}Glow", color, forward_extent), 0.02)

        tip = points[-1]
        offset = (tip[0] - head[0], tip[1] - head[1], tip[2] - head[2])
        planet = build_sphere(name, PLANET_DISPLAY_RADIUS[name], offset,
                              build_planet_material(f"{name}Surface", TEXTURES[name]), helio)
        align_to_pole(planet, name)
        if name == "Saturn":
            build_saturn_ring(planet, PLANET_DISPLAY_RADIUS[name])

    # 太陽自身の軌跡(銀河基準では直線)。惑星の軌跡と同じく、1aでは長さ0の点から伸びていく。
    build_polyline("SunTrail", sun_trail_points(TOTAL_FRAMES),
                   build_trail_material("SunTrailGlow", SUN_TRAIL_COLOR, forward_extent), 0.03)

    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print(f"[Stage1] saved WIP file: {WIP_BLEND}")
    print(f"[Stage1] forward_extent={forward_extent:.2f}, planets: {DISPLAY}")


if __name__ == "__main__":
    main()
