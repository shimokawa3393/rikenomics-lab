# -*- coding: utf-8 -*-
"""
フレームごとの状態(カメラ、車の位置・ブレーキ・速度の色)と、レンダー設定(空・コンポジター)。
確認用レンダー(02)とフルレンダー(03)の両方からapply_frameを呼ぶ(ep3で確立した構成)。

ユーザーが「いい感じで渋滞を表現できてた」とした版に戻したもの:
- 1a: 望遠目線のリアルな夜(ブルーアワー)の高速道路。テールランプの光の回り込みと写真の質感
- 上昇: 斜め上からの固定の俯瞰へ上昇しながら、車・対向車を隠して、車ごとの光の点を速度で色分けして見せる
  (遅いほど赤)。暗い背景で、詰まった車が赤い塊として浮き上がる。街灯は暗くする
- 1つの計算を最後まで流し、映像のスピードだけを上げる。倍率の文字は04_encode_video.pyが重ねる
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bpy
import mathutils
import scenario
from shots import BRAKE_BOOST, OUR_LANE_X, RESOLUTION, road_slope, road_z
from traffic_sim import brake_level

V = mathutils.Vector

# ブルーアワーの空(参考画像の深い青)。視線方向のzで地平線→天頂へ
SKY_GRADIENT = (
    (0.00, (0.035, 0.070, 0.200)),
    (0.10, (0.012, 0.030, 0.110)),
    (0.45, (0.003, 0.008, 0.035)),
)
SKY_STRENGTH = 1.0
SKY_FILL = 0.3  # 空が車体や路面を照らす光の強さ(カメラに直接映る空は1.0のまま)

# 遠くほど空気で霞む(ミストパス)。空そのものには掛けない
HAZE_COLOR = (0.030, 0.055, 0.140)
HAZE_AMOUNT = 0.75
MIST_START = 60.0
MIST_DEPTH = 2200.0

# 1a: 中央分離帯寄りの少し高い位置(陸橋の上程度)から、望遠で車列の奥を見る
CAM_1A_LOC = (-4.0, 0.0, 7.0)
CAM_1A_LOOK_Y = 700.0
CAM_1A_PITCH_DEG = -1.6  # 地平線が画面の上から約1/3に来る
CAM_1A_LENS = 100.0
CAM_1A_FOCUS = 120.0  # m。手前の車と地平線がわずかにボケる
CAM_1A_FSTOP = 11.0

# 俯瞰(画面の上=進行方向): 上り坂の入口(y=250)を画面の上の方に置いて最初の波が生まれる様子を見せ、
# 渋滞が後ろへ伸びるのに合わせて上がりつつ注視点を後ろへずらし、列の後ろの端を画面の下半分に置く
# (後ろから来た白い点が列に加わって赤くなる瞬間を大きく見せる。上げすぎると点が小さくなり見えない)
CAM_RISE = (120, 205)  # このフレームの間に1aの目線から俯瞰Aへ上昇する
CAM_CLIMB = (420, 900)  # このフレームの間に俯瞰Aから上空の俯瞰Bへ上がる
CAM_LANE_X = -7.2  # 我々の3車線の中央
CAM_A = dict(target_y=200.0, back=100.0, height=115.0, lens=30.0)
CAM_B = dict(target_y=60.0, back=120.0, height=240.0, lens=28.0)
CAM_OVERHEAD_FSTOP = 22.0
DOT_GROW = 0.3  # カメラが高くなるほど光の点を大きくする(高さが俯瞰Aの何倍になったかに対する割合)

# 記号表現への切り替え(上昇の途中)
SYMBOLIC = (150, 205)
DOT_STRENGTH = 6.0
LAMP_OVERHEAD = 2.5  # 記号表現では街灯が地面を照らす光をこの倍率にする(上空からだと光の輪が小さく、道路が見えず寂しい)。
# 街灯の頭(光る点)は明るくしない(車の光の点とまぎれる)

# 写真の質感(コンポジット)
CHROMATIC_DISPERSION = 0.006  # レンズの色ずれ(画面の端ほど赤と青がずれる)
VIGNETTE = 0.35  # 周辺減光の強さ
GRAIN = 0.012  # 粒子ノイズの強さ(フレームごとに変わる)


def build_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()
    output = nodes.new('ShaderNodeOutputWorld')
    background = nodes.new('ShaderNodeBackground')
    background.inputs['Strength'].default_value = SKY_STRENGTH
    links.new(background.outputs[0], output.inputs[0])

    tex_coord = nodes.new('ShaderNodeTexCoord')
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(tex_coord.outputs['Generated'], sep.inputs[0])  # ワールドでは視線方向ベクトル
    ramp = nodes.new('ShaderNodeValToRGB')
    elements = ramp.color_ramp.elements
    while len(elements) < len(SKY_GRADIENT):
        elements.new(0.5)
    for element, (position, color) in zip(elements, SKY_GRADIENT):
        element.position = position
        element.color = (*color, 1)
    links.new(sep.outputs['Z'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], background.inputs['Color'])

    # カメラに直接映る空はそのまま、ほかの光線(物を照らす光)だけ弱める
    light_path = nodes.new('ShaderNodeLightPath')
    fill = nodes.new('ShaderNodeMapRange')
    fill.inputs['To Min'].default_value = SKY_FILL * SKY_STRENGTH
    fill.inputs['To Max'].default_value = SKY_STRENGTH
    links.new(light_path.outputs['Is Camera Ray'], fill.inputs['Value'])
    links.new(fill.outputs['Result'], background.inputs['Strength'])

    world.mist_settings.start = MIST_START
    world.mist_settings.depth = MIST_DEPTH
    world.mist_settings.falloff = 'LINEAR'


def build_compositor(scene):
    """Blender 5.x方式(ep3と同じ): ノードグループを明示作成し、Glareの種類はinputs["Type"]に文字列で指定。"""
    ng = bpy.data.node_groups.get("Ep4Compositor")
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    ng = bpy.data.node_groups.new("Ep4Compositor", 'CompositorNodeTree')
    ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    scene.compositing_node_group = ng
    render_layers = ng.nodes.new('CompositorNodeRLayers')
    # 物体(透明背景で描いた画像)を空(環境パス)の上に重ねてから、物体の部分だけを遠さに応じて霞ませる
    over = ng.nodes.new('CompositorNodeAlphaOver')
    ng.links.new(render_layers.outputs['Environment'], over.inputs['Background'])
    ng.links.new(render_layers.outputs['Image'], over.inputs['Foreground'])
    haze_fac = ng.nodes.new('ShaderNodeMath')
    haze_fac.operation = 'MULTIPLY'
    ng.links.new(render_layers.outputs['Mist'], haze_fac.inputs[0])
    ng.links.new(render_layers.outputs['Alpha'], haze_fac.inputs[1])
    haze_gain = ng.nodes.new('ShaderNodeMath')
    haze_gain.operation = 'MULTIPLY'
    haze_gain.inputs[1].default_value = HAZE_AMOUNT
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

    # 写真の質感: レンズの色ずれ → 周辺減光 → 粒子ノイズ
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
    vignette_amount = ng.nodes.new('ShaderNodeMapRange')  # マスク0(端)→1-VIGNETTE、1(中央)→1
    vignette_amount.inputs['To Min'].default_value = 1.0 - VIGNETTE
    ng.links.new(soft.outputs['Image'], vignette_amount.inputs['Value'])
    ng.links.new(lens.outputs['Image'], vignette.inputs['A'])
    ng.links.new(vignette_amount.outputs['Result'], vignette.inputs['B'])
    coords = ng.nodes.new('CompositorNodeImageCoordinates')
    ng.links.new(lens.outputs['Image'], coords.inputs['Image'])
    noise = ng.nodes.new('ShaderNodeTexWhiteNoise')
    noise.noise_dimensions = '4D'
    noise.name = "GrainNoise"  # apply_frameでWにフレーム番号を入れる
    ng.links.new(coords.outputs['Pixel'], noise.inputs['Vector'])
    grain = ng.nodes.new('ShaderNodeMix')
    grain.data_type = 'RGBA'
    grain.blend_type = 'LINEAR_LIGHT'  # 0.5が無変化
    grain.inputs['Factor'].default_value = GRAIN
    ng.links.new(vignette.outputs['Result'], grain.inputs['A'])
    ng.links.new(noise.outputs['Value'], grain.inputs['B'])
    group_output = ng.nodes.new('NodeGroupOutput')
    ng.links.new(grain.outputs['Result'], group_output.inputs['Image'])


def look_rotation(loc, target, up=V((0, 0, 1))):
    """カメラは-Zを向き+Yが画面上。"""
    z = (loc - target).normalized()
    x = up.cross(z).normalized()
    y = z.cross(x)
    return mathutils.Matrix((x, y, z)).transposed().to_quaternion()


def _smooth(a, b, u):
    u = min(max(u, 0.0), 1.0)
    u = u * u * (3 - 2 * u)
    return a + (b - a) * u


def rise_progress(frame):
    return (frame - CAM_RISE[0]) / (CAM_RISE[1] - CAM_RISE[0])


def symbolic_amount(frame):
    """0=リアル、1=記号表現(光の点)。"""
    return _smooth(0.0, 1.0, (frame - SYMBOLIC[0]) / (SYMBOLIC[1] - SYMBOLIC[0]))


def _overhead(pose):
    ty = pose["target_y"]
    target = V((CAM_LANE_X, ty, road_z(ty)))
    loc = V((CAM_LANE_X, ty - pose["back"], road_z(ty) + pose["height"]))
    return loc, target, pose["lens"]


def camera_at(frame):
    """(位置, 注視点, 焦点距離, F値)。1aの目線 → 俯瞰A(坂の入口) → 上空の俯瞰B。"""
    loc_1a = V(CAM_1A_LOC)
    target_1a = V((loc_1a.x, CAM_1A_LOOK_Y, loc_1a.z + CAM_1A_LOOK_Y * math.tan(math.radians(CAM_1A_PITCH_DEG))))
    loc_a, target_a, lens_a = _overhead(CAM_A)
    loc_b, target_b, lens_b = _overhead(CAM_B)
    c = _smooth(0, 1, (frame - CAM_CLIMB[0]) / (CAM_CLIMB[1] - CAM_CLIMB[0]))
    loc_oh, target_oh, lens_oh = loc_a.lerp(loc_b, c), target_a.lerp(target_b, c), lens_a + (lens_b - lens_a) * c
    u = _smooth(0, 1, rise_progress(frame))
    return (loc_1a.lerp(loc_oh, u), target_1a.lerp(target_oh, u),
            CAM_1A_LENS + (lens_oh - CAM_1A_LENS) * u, CAM_1A_FSTOP + (CAM_OVERHEAD_FSTOP - CAM_1A_FSTOP) * u)


def dot_scale(frame):
    """カメラの高さが俯瞰Aの何倍になったかに応じて、光の点を大きくする(高く上がっても見失わないように)。"""
    loc, target, _, _ = camera_at(frame)
    ratio = max((loc.z - target.z) / CAM_A["height"], 1.0)
    return 1.0 + (ratio - 1.0) * DOT_GROW


def apply_camera(scene, frame):
    camera = bpy.data.objects.get("MainCamera")
    if camera is None:
        camera = bpy.data.objects.new("MainCamera", bpy.data.cameras.new("MainCamera"))
        scene.collection.objects.link(camera)
    loc, target, lens, fstop = camera_at(frame)
    camera.location = loc
    camera.rotation_mode = 'QUATERNION'
    camera.rotation_quaternion = look_rotation(loc, target)
    camera.data.lens = lens
    camera.data.clip_start = 0.5
    camera.data.clip_end = 5000
    camera.data.dof.use_dof = True
    camera.data.dof.focus_distance = _smooth(CAM_1A_FOCUS, (loc - target).length, rise_progress(frame))
    camera.data.dof.aperture_fstop = fstop
    scene.camera = camera


_LANES = None


def apply_cars(frame):
    """交通流の計算結果から、我々の車線の車(と光の点)の位置・ブレーキ・速度の色と、対向車の位置を設定する。"""
    global _LANES
    if _LANES is None:
        _LANES = scenario.load()
    t = scenario.sim_time(frame)
    sym = symbolic_amount(frame)
    realistic = sym < 0.5  # 半分を過ぎたら車の実体を隠し、光の点だけにする
    grow = dot_scale(frame)
    for lane, data in enumerate(_LANES):
        y, v, acc = scenario.lane_state(data, t)
        brake = brake_level(acc)
        for i in range(len(y)):
            obj = bpy.data.objects[f"Car_L{lane}_{i:03d}"]
            length = scenario.CAR_LENGTH[obj["kind"]]
            show = scenario.visible(y[i], length)
            obj.hide_render = not (show and realistic)
            for child in obj.children:
                if child.type == 'LIGHT':  # テールランプの赤い光
                    child.hide_render = obj.hide_render
                    child.data.energy = child.data["base_power"] * (1 + float(brake[i]) * (BRAKE_BOOST - 1))
                else:  # 光の点
                    child.hide_render = not (show and sym > 0.0)
                    child["speed01"] = float(min(v[i] / (100 / 3.6), 1.0))
                    child.scale = (grow, grow, 1.0)
            if not show:
                continue
            obj.location = (OUR_LANE_X[lane] + obj["x_offset"], y[i], road_z(y[i]))
            obj.rotation_euler = (math.atan(road_slope(y[i])), 0, 0)
            obj["brake"] = float(brake[i])
    dots = bpy.data.materials.get("DotGlow")
    if dots is not None:
        dots.node_tree.nodes["DotStrength"].outputs[0].default_value = DOT_STRENGTH * sym
    for obj in bpy.data.objects:
        if obj.name.startswith("Oncoming_"):
            y = scenario.oncoming_y(obj["y0"], t)
            obj.location = (obj.location.x, y, road_z(y))
            obj.rotation_euler = (-math.atan(road_slope(y)), 0, math.pi)
            obj.hide_render = not realistic
            for child in obj.children:
                child.hide_render = not realistic


def apply_lamps(frame):
    """記号表現では街灯が地面を照らす光を強める(俯瞰でも道路が見えるように)。"""
    boost = 1.0 + (LAMP_OVERHEAD - 1.0) * symbolic_amount(frame)
    for obj in bpy.data.objects:
        if obj.type == 'LIGHT' and obj.name.startswith("LampLight_"):
            obj.data.energy = obj.data["base_power"] * boost


def apply_frame(scene, frame):
    apply_cars(frame)
    apply_lamps(frame)
    apply_camera(scene, frame)
    grain = scene.compositing_node_group.nodes.get("GrainNoise")
    if grain is not None:
        grain.inputs['W'].default_value = frame * 1.37
    scene.frame_set(frame)


CYCLES_SAMPLES = 256
CYCLES_NOISE_THRESHOLD = 0.02


def use_cycles(scene):
    """CyclesをGPU(Metal)で使う。ランプの光が周りを照らし、映り込みも正確になる(EEVEEの10倍以上遅い)。"""
    scene.render.engine = 'CYCLES'
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for device in prefs.devices:
        device.use = True
    scene.cycles.device = 'GPU'
    scene.cycles.samples = CYCLES_SAMPLES
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = CYCLES_NOISE_THRESHOLD
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    print("[Cycles] devices:", [(d.name, d.type) for d in prefs.devices if d.use])


def setup_render(scene, resolution_percentage=100, cycles=False):
    build_world()
    view_layer = scene.view_layers[0]
    view_layer.use_pass_mist = True
    view_layer.use_pass_environment = True
    scene.render.film_transparent = True  # 空は環境パスから合成する(ミストを空に掛けないため)
    build_compositor(scene)
    scene.view_settings.view_transform = 'AgX'
    engine_ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_ids else 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 64
    scene.eevee.use_raytracing = True  # 路面・車体への映り込み(夜)
    scene.eevee.ray_tracing_options.trace_max_roughness = 0.6
    scene.render.fps = 30
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = resolution_percentage
    scene.render.image_settings.file_format = 'PNG'
    if cycles:
        use_cycles(scene)
