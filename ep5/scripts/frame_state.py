# -*- coding: utf-8 -*-
"""
フレームごとの状態と、レンダー設定(空・コンポジター)。
確認用レンダー(02)とフルレンダー(03)の両方からapply_frameを呼ぶ(ep3で確立した構成)。
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
from shots import RESOLUTION, SKY_HDRI

# 雷雨の空: 曇天のHDRIを暗く落とし、少し青みのある灰色に寄せる
SKY_ROTATION_DEG = 200.0
SKY_CAMERA = 0.22  # カメラに直接映る空の明るさ
SKY_FILL = 0.22  # 空が車や地面を照らす明るさ
SKY_TINT = (0.80, 0.86, 0.95)

# 遠くほど雨と霧で霞む(ミストパス)。空そのものには掛けない
HAZE_COLOR = (0.060, 0.066, 0.075)
HAZE_AMOUNT = 0.70
MIST_START = 30.0
MIST_DEPTH = 4500.0

CLEAR_SKY = 1.0  # 形チェックの空の明るさ(雨の日の約4倍)
EXPOSURE = 0.6  # 全体の明るさ(段)。「全体的に少し明るく」

# 写真の質感(ep4と同じ)
CHROMATIC_DISPERSION = 0.004
VIGNETTE = 0.30
GRAIN = 0.012


def build_world(clear=False):
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputWorld')
    background = nodes.new('ShaderNodeBackground')
    links.new(background.outputs[0], output.inputs[0])
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value = (0, 0, math.radians(SKY_ROTATION_DEG))
    links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    env = nodes.new('ShaderNodeTexEnvironment')
    env.image = bpy.data.images.load(SKY_HDRI, check_existing=True)
    links.new(mapping.outputs['Vector'], env.inputs['Vector'])
    tint = nodes.new('ShaderNodeMix')
    tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.inputs['Factor'].default_value = 1.0
    tint.inputs['B'].default_value = (*SKY_TINT, 1)
    links.new(env.outputs['Color'], tint.inputs['A'])
    links.new(tint.outputs['Result'], background.inputs['Color'])
    light_path = nodes.new('ShaderNodeLightPath')
    strength = nodes.new('ShaderNodeMapRange')
    strength.inputs['To Min'].default_value = CLEAR_SKY if clear else SKY_FILL
    strength.inputs['To Max'].default_value = CLEAR_SKY if clear else SKY_CAMERA
    links.new(light_path.outputs['Is Camera Ray'], strength.inputs['Value'])
    links.new(strength.outputs['Result'], background.inputs['Strength'])
    world.mist_settings.start = MIST_START
    world.mist_settings.depth = MIST_DEPTH
    world.mist_settings.falloff = 'QUADRATIC'


def build_compositor(scene, clear=False):
    ng = bpy.data.node_groups.get("Ep5Compositor")
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    ng = bpy.data.node_groups.new("Ep5Compositor", 'CompositorNodeTree')
    ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    scene.compositing_node_group = ng
    rl = ng.nodes.new('CompositorNodeRLayers')
    over = ng.nodes.new('CompositorNodeAlphaOver')
    ng.links.new(rl.outputs['Environment'], over.inputs['Background'])
    ng.links.new(rl.outputs['Image'], over.inputs['Foreground'])
    haze_fac = ng.nodes.new('ShaderNodeMath')
    haze_fac.operation = 'MULTIPLY'
    ng.links.new(rl.outputs['Mist'], haze_fac.inputs[0])
    ng.links.new(rl.outputs['Alpha'], haze_fac.inputs[1])
    haze_gain = ng.nodes.new('ShaderNodeMath')
    haze_gain.operation = 'MULTIPLY'
    haze_gain.inputs[1].default_value = HAZE_AMOUNT * (0.3 if clear else 1.0)
    ng.links.new(haze_fac.outputs[0], haze_gain.inputs[0])
    haze = ng.nodes.new('ShaderNodeMix')
    haze.data_type = 'RGBA'
    haze.inputs['B'].default_value = (*HAZE_COLOR, 1)
    ng.links.new(haze_gain.outputs[0], haze.inputs['Factor'])
    ng.links.new(over.outputs['Image'], haze.inputs['A'])
    glare = ng.nodes.new('CompositorNodeGlare')
    glare.inputs['Type'].default_value = 'Fog Glow'
    glare.inputs['Quality'].default_value = 'High'
    glare.inputs['Threshold'].default_value = 1.0
    glare.inputs['Size'].default_value = 0.7
    glare.inputs['Strength'].default_value = 1.0
    ng.links.new(haze.outputs['Result'], glare.inputs['Image'])
    lens = ng.nodes.new('CompositorNodeLensdist')
    lens.inputs['Dispersion'].default_value = CHROMATIC_DISPERSION
    ng.links.new(glare.outputs['Image'], lens.inputs['Image'])
    ellipse = ng.nodes.new('CompositorNodeEllipseMask')
    ellipse.inputs['Size'].default_value = (0.95, 0.95)
    soft = ng.nodes.new('CompositorNodeBlur')
    soft.inputs['Size'].default_value = (300, 300)
    ng.links.new(ellipse.outputs['Mask'], soft.inputs['Image'])
    vignette = ng.nodes.new('ShaderNodeMix')
    vignette.data_type = 'RGBA'
    vignette.blend_type = 'MULTIPLY'
    vignette.inputs['Factor'].default_value = 1.0
    v_amount = ng.nodes.new('ShaderNodeMapRange')
    v_amount.inputs['To Min'].default_value = 1.0 - VIGNETTE
    ng.links.new(soft.outputs['Image'], v_amount.inputs['Value'])
    ng.links.new(lens.outputs['Image'], vignette.inputs['A'])
    ng.links.new(v_amount.outputs['Result'], vignette.inputs['B'])
    coords = ng.nodes.new('CompositorNodeImageCoordinates')
    ng.links.new(lens.outputs['Image'], coords.inputs['Image'])
    grain_noise = ng.nodes.new('ShaderNodeTexWhiteNoise')
    grain_noise.noise_dimensions = '4D'
    grain_noise.name = "GrainNoise"
    ng.links.new(coords.outputs['Pixel'], grain_noise.inputs['Vector'])
    grain = ng.nodes.new('ShaderNodeMix')
    grain.data_type = 'RGBA'
    grain.blend_type = 'LINEAR_LIGHT'
    grain.inputs['Factor'].default_value = GRAIN
    ng.links.new(vignette.outputs['Result'], grain.inputs['A'])
    ng.links.new(grain_noise.outputs['Value'], grain.inputs['B'])
    out = ng.nodes.new('NodeGroupOutput')
    ng.links.new(grain.outputs['Result'], out.inputs['Image'])


def apply_frame(scene, frame):
    grain = scene.compositing_node_group.nodes.get("GrainNoise")
    if grain is not None:
        grain.inputs['W'].default_value = frame * 1.37
    scene.frame_set(frame)


def setup_render(scene, resolution_percentage=100, clear=False):
    """clear: 車の形を見るための確認用(雨なし、明るい曇り空)。"""
    build_world(clear)
    rain = bpy.data.collections.get("Rain")
    if rain is not None:
        rain.hide_render = clear
    vl = scene.view_layers[0]
    vl.use_pass_mist = True
    vl.use_pass_environment = True
    scene.render.film_transparent = True
    build_compositor(scene, clear)
    scene.view_settings.view_transform = 'AgX'
    scene.view_settings.look = 'AgX - Medium High Contrast'
    scene.view_settings.exposure = 0.0 if clear else EXPOSURE
    engine_ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_ids else 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_raytracing = True
    scene.eevee.ray_tracing_options.trace_max_roughness = 0.5
    scene.render.fps = 30
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = resolution_percentage
    scene.render.image_settings.file_format = 'PNG'
