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
import numpy as np
from mathutils import Quaternion, Vector
from shots import (CAM_LENS, CAM_LOC, CAM_TARGET, FPS, RESOLUTION, SKY_HDRI, STRIKE_FRAME, TREE_BREAK_Z, TREE_FALL_DIR_DEG,
                   TREE_FALL_START, TREE_STRIKE_FRAME)

# 雷雨の空: 曇天のHDRIを暗く落とし、少し青みのある灰色に寄せる
SKY_ROTATION_DEG = 200.0
SKY_CAMERA = 0.42  # カメラに直接映る空の明るさ
SKY_FILL = 0.50  # 空が車や地面を照らす明るさ
SKY_TINT = (0.80, 0.86, 0.95)

# 遠くほど雨と霧で霞む(ミストパス)。空そのものには掛けない
HAZE_COLOR = (0.15, 0.16, 0.18)  # 雨の霞は明るい灰色(暗い色だと夜っぽくなる)
HAZE_AMOUNT = 0.55
MIST_START = 30.0
MIST_DEPTH = 4500.0

CLEAR_SKY = 1.0  # 形チェックの空の明るさ(雨の日の約4倍)
EXPOSURE = 0.6  # 全体の明るさ(段)。「全体的に少し明るく」

# 雷の閃光: 落ちたフレームを1として、数フレームでちらつきながら消える(本物の雷は数回光り直す)
FLASH_CURVE = {0: 1.0, 1: 0.35, 2: 0.8, 3: 0.2, 4: 0.05}
FLASH_SKY = 1.3  # 閃光のとき、空の明るさを何倍にするか(雲の中で光る)
FLASH_LIGHT = 4.0e5  # 雷の道のすぐ上の点光源の強さ[W]

# 雨: 筋ごとに落ちて、見える範囲の下まで行ったら上に戻る
RAIN_SPEED = 9.0  # 落ちる速さ[m/s](大きな雨粒)

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
    strength.name = "SkyStrength"
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
    science = ng.nodes.new('CompositorNodeHueSat')  # 科学の目で見る時間: 色を抜いて暗く(apply_scienceで動かす)
    science.name = "Science"
    science.inputs['Saturation'].default_value = 1.0
    science.inputs['Value'].default_value = 1.0
    ng.links.new(haze.outputs['Result'], science.inputs['Image'])
    lines_pass = ng.nodes.new('CompositorNodeRLayers')  # 光の筋は色を抜かずに上から足す(別のビューレイヤー)
    lines_pass.name = "LinesPass"
    lines_pass.layer = "Lines" if "Lines" in scene.view_layers else scene.view_layers[0].name
    add = ng.nodes.new('ShaderNodeMix')
    add.data_type = 'RGBA'
    add.blend_type = 'ADD'
    add.name = "LinesAdd"
    add.inputs['Factor'].default_value = 1.0 if "Lines" in scene.view_layers else 0.0
    ng.links.new(science.outputs['Image'], add.inputs['A'])
    ng.links.new(lines_pass.outputs['Image'], add.inputs['B'])
    ng.links.new(add.outputs['Result'], glare.inputs['Image'])
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


STRIKES = (("Lightning", STRIKE_FRAME), ("TreeLightning", TREE_STRIKE_FRAME))  # (雷のコレクション, 落ちるフレーム)


def flash_amount(frame, strike=STRIKE_FRAME):
    return FLASH_CURVE.get(frame - strike, 0.0)


def apply_flash(scene, frame):
    """雷の閃光: 雷の道を見せ、点光源を点け、空を明るくする(車と杉の2回)。"""
    sky = 0.0
    for name, strike in STRIKES:
        flash = flash_amount(frame, strike)
        col = bpy.data.collections.get(name)
        if col is not None:
            col.hide_render = flash <= 0.0
        light = bpy.data.lights.get(f"{name}Glow")
        if light is not None:
            light.energy = FLASH_LIGHT * flash
        sky = max(sky, flash)
    node = scene.world.node_tree.nodes.get("SkyStrength")
    if node is not None:
        if "base" not in node:
            node["base"] = (node.inputs['To Min'].default_value, node.inputs['To Max'].default_value)
        lo, hi = node["base"]
        k = 1.0 + (FLASH_SKY - 1.0) * sky
        node.inputs['To Min'].default_value = lo * k
        node.inputs['To Max'].default_value = hi * k


# 杉が倒れる: 折れた点を軸に回る長さLの棒(θ'' = (3g/2L) sinθ)。真っすぐのまま、裂けたはずみの小さな回転だけで倒れはじめる。
# 傾きが小さいうちはほとんど動かず(最初の1秒で約4°)、そこから一気に倒れる。最初から傾けると、その1フレームで先端が約1m跳んでカクッとなる
FALL_LENGTH = 16.0
FALL_START_ANGLE = 0.0  # [rad]
FALL_START_SPEED = 0.06  # [rad/s]。着地は約4.1秒後(800フレームごろ)
FALL_LAND_DEG = 92.0  # 枝が地面に着く角度
BOUNCE_DEG = 4.0  # 着いたときの跳ね返り
STEAM_DENSITY = 4.0
STEAM_FADE = 2.5  # 蒸気が薄れる時間[s]
SCAR_GLOW = 3.0  # 裂けた跡が熱で赤く光る強さ(すぐ消える)


def _fall_table():
    g, dt = 9.81, 1.0 / (FPS * 10)
    th, om, t, table = FALL_START_ANGLE, FALL_START_SPEED, 0.0, [(0.0, FALL_START_ANGLE)]
    while th < math.radians(FALL_LAND_DEG):
        om += 1.5 * g / FALL_LENGTH * math.sin(th) * dt
        th += om * dt
        t += dt
        table.append((t, th))
    return table


_FALL = _fall_table()
FALL_DURATION = _FALL[-1][0]


def fall_angle(frame):
    """倒れはじめてからの角度[rad]。地面に着いたら、小さく跳ねて止まる。"""
    t = (frame - TREE_FALL_START) / FPS
    if t <= 0:
        return 0.0
    if t < FALL_DURATION:
        return next(th for tt, th in _FALL if tt >= t)
    u = t - FALL_DURATION
    return math.radians(FALL_LAND_DEG) - math.radians(BOUNCE_DEG) * abs(math.sin(2 * math.pi * 2.5 * u)) * math.exp(-u / 0.25)


def apply_tree(frame):
    """杉に落ちてから: 裂けた跡が現れて一瞬赤く光り、幹から蒸気が噴き出し、一拍おいて上の部分が倒れる。"""
    t = (frame - TREE_STRIKE_FRAME) / FPS
    bark = bpy.data.materials.get("HeroBark")
    if bark is not None:
        nodes = bark.node_tree.nodes
        nodes["Scar"].outputs[0].default_value = 1.0 if t >= 0 else 0.0
        nodes["ScarGlow"].outputs[0].default_value = SCAR_GLOW * math.exp(-t / 0.25) if t >= 0 else 0.0
    steam = bpy.data.collections.get("Steam")
    if steam is not None:
        steam.hide_render = t < 0
        if t >= 0:
            bpy.data.materials["Steam"].node_tree.nodes["SteamDensity"].outputs[0].default_value = (
                STEAM_DENSITY * (1.0 - math.exp(-t / 0.08)) * math.exp(-t / STEAM_FADE))
            for o in steam.objects:
                grow = o["size"] * (0.4 + 1.6 * (1.0 - math.exp(-t / 0.6)))
                o.scale = (grow, grow, grow)
                o.location = Vector(o["origin"]) + Vector(o["drift"]) * t
    tree = bpy.data.objects.get("HeroTree")
    if tree is not None:
        a = math.radians(TREE_FALL_DIR_DEG)
        axis = Vector((0, 0, 1)).cross(Vector((math.cos(a), math.sin(a), 0)))
        tree.rotation_quaternion = Quaternion(axis, fall_angle(frame))


_rain_cache = {}


def animate_rain(frame):
    """雨の筋を、フレームに応じて筋の向き(風で少し傾いた下向き)に落とす。筋ごとに、カメラからの距離で見える高さの範囲を決め、
    その範囲の中で上から下へ回す(遠い筋ほど範囲が広い)。最初の位置(生成したときの形)からのずらしなので、何フレーム目からでも同じ絵になる。"""
    obj = bpy.data.objects.get("Rain")
    if obj is None:
        return
    me = obj.data
    if me.name not in _rain_cache:
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        quads = co.reshape(-1, 4, 3)
        bottom, top = quads[:, :2].mean(axis=1), quads[:, 2:].mean(axis=1)
        axis = top - bottom
        axis /= np.linalg.norm(axis, axis=1, keepdims=True)
        center = quads.mean(axis=1)
        fwd = np.array(CAM_TARGET) - np.array(CAM_LOC)
        fwd /= np.linalg.norm(fwd)
        depth = (center - np.array(CAM_LOC)) @ fwd
        span = 2.2 * (18.0 / CAM_LENS) * depth  # その距離で画面に映る高さ
        phase = np.random.default_rng(7).random(len(quads)) * span
        _rain_cache[me.name] = (quads.copy(), axis, span, phase)
    quads, axis, span, phase = _rain_cache[me.name]
    u = (phase + RAIN_SPEED * (frame - 1) / FPS) % span
    moved = quads + (axis * (span / 2 - u)[:, None] - axis * (span / 2 - phase)[:, None])[:, None, :]
    me.vertices.foreach_set("co", moved.reshape(-1))
    me.update()


SCIENCE_SATURATION = 0.15  # 科学の目の時間の彩度
SCIENCE_VALUE = 0.35  # 科学の目の時間の明るさ
CURRENT_STRENGTH = 8.0  # 電流の筋の光の強さ(強いとにじんで太い帯になる)


def apply_science(scene, amount, lines=0.0):
    """科学の目で見る時間: amount(0〜1)で画面の色を抜いて暗くし、lines(0〜1)で電流の筋を出す。"""
    node = scene.compositing_node_group.nodes.get("Science")
    if node is not None:
        node.inputs['Saturation'].default_value = 1.0 + (SCIENCE_SATURATION - 1.0) * amount
        node.inputs['Value'].default_value = 1.0 + (SCIENCE_VALUE - 1.0) * amount
    col = bpy.data.collections.get("CurrentLines")
    if col is not None:
        col.hide_render = lines <= 0.0
        mat = bpy.data.materials.get("CurrentLine")
        if mat is not None:
            mat.node_tree.nodes["Emission"].inputs['Strength'].default_value = CURRENT_STRENGTH * lines


def apply_frame(scene, frame):
    animate_rain(frame)
    grain = scene.compositing_node_group.nodes.get("GrainNoise")
    if grain is not None:
        grain.inputs['W'].default_value = frame * 1.37
    apply_flash(scene, frame)
    apply_tree(frame)
    scene.frame_set(frame)


def setup_lines_layer(scene):
    """電流の筋だけを描く2つ目のビューレイヤー「Lines」(色を抜いた画面の上に、色のまま足すため)。
    車は隠す側(ホールドアウト)にして、車の裏側の筋は見えないようにする。メインのレイヤーからは筋を外す。"""
    if bpy.data.collections.get("CurrentLines") is None:
        return
    main = scene.view_layers[0]
    lines = scene.view_layers.get("Lines") or scene.view_layers.new("Lines")
    for lc in main.layer_collection.children:
        lc.exclude = lc.name == "CurrentLines"
    for lc in lines.layer_collection.children:
        lc.exclude = lc.name not in ("CurrentLines", "Car")
        lc.holdout = lc.name == "Car"
    lines.use_pass_mist = False


def setup_render(scene, resolution_percentage=100, clear=False):
    """clear: 車の形を見るための確認用(雨なし、明るい曇り空)。"""
    build_world(clear)
    setup_lines_layer(scene)
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
    rt = scene.eevee.ray_tracing_options
    rt.trace_max_roughness = 0.5
    # 濡れた路面に車が映るように、画面の光線追跡を細かく(既定は半分の解像度・品質0.25で、映り込みがぼやけて消える)
    rt.resolution_scale = '1'
    rt.screen_trace_quality = 1.0
    rt.screen_trace_thickness = 3.0  # 車の陰(画面に映らない床下)に当たった光線も車に当たったとみなす。薄いと空の映り込みで代用され、車の脇の路面が白く光る
    scene.render.fps = 30
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = resolution_percentage
    scene.render.image_settings.file_format = 'PNG'
    # 杉の蒸気(体積)。カメラから杉まで(約48m)を細かく、影は切る
    scene.eevee.volumetric_start = 30.0
    scene.eevee.volumetric_end = 70.0
    scene.eevee.volumetric_tile_size = '4'
    scene.eevee.use_volumetric_shadows = False
