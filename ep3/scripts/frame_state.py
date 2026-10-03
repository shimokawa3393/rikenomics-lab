# -*- coding: utf-8 -*-
"""
フレームごとのシーン状態(軌跡・惑星・表示・カメラ)を設定する共通モジュール。
02(代表フレームの確認)と03(フルレンダー)の両方から使う。

座標系の対応(銀河座標との整合):
  シーン+X = 太陽の進行方向(銀経90°)、シーン+Z = 銀河北極 とすると、
  右手系から銀河中心(銀経0°)はシーン-Y方向になる。銀河面はX-Y平面。
  太陽は常に原点。横からのカットはカメラを+Y側に置き、太陽系の奥に銀河中心のバルジが見える。

カメラ: 位置・注視点・上方向・焦点距離を毎フレーム計算して向きを決める
(Track Toはロールできず、疎なキーフレームの補間は破綻しやすい、というep2の教訓)。
横からのカットは画面の上を銀河南極側(-Z)にする。銀河北極を上にして銀河中心側を見ると
進行方向(+X)が必ず画面左になるため。
螺旋を軸方向から覗くと遠近法でループ状に見え「渦」表現と区別がつかないため、
軸に近いアングルは使わない。
"""
import math
import os

import bpy
import mathutils
from shots import (
    DISPLAY,
    MORPH_FRAMES,
    MOTION_START_FRAME,
    RESOLUTION,
    TIME_SPAN_YEARS,
    ecliptic_north_scene,
    forward_units,
    morph_trail_points,
    sim_time,
    smoothstep,
    sun_trail_points,
    trail_point,
)

# 01_generate_geometry.pyで設定している既定値と同じ値
TRAIL_STRENGTH_DEFAULT = 3.0
FADE_POWER_DEFAULT = 3.0  # 大きいほど後方が早く透けて消える

# 背景はNASA SVS「Deep Star Maps 2020」(銀河座標版)。投稿文に「NASA/Goddard Space Flight Center
# Scientific Visualization Studio」のクレジットを入れる。天の川(微光星の集まり)と明るい恒星が別画像なので、
# 天の川だけを長時間露光の天体写真風に強調し、恒星はそのまま鋭く載せる。
TEXTURE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "textures")
MILKYWAY_EXR = os.path.join(TEXTURE_DIR, "milkyway_2020_8k_gal.exr")
STARS_EXR = os.path.join(TEXTURE_DIR, "hiptyc_2020_16k_gal.exr")
MILKYWAY_STRENGTH = 6.0  # 元画像は帯の平均が約0.02と暗い(肉眼相当)ので、天体写真程度まで持ち上げる
MILKYWAY_GAMMA = 1.2  # 1より大きいほど淡い部分が沈み、暗黒帯のコントラストが立つ
MILKYWAY_SATURATION = 1.15  # 元データはバルジ側が黄橙なので、上げすぎるとオレンジ一色になる
# 明るさに応じた色味(天体写真風): 淡い所は青紫、中くらいはピンク寄り、明るい中心は暖かい白
MILKYWAY_TINT = (
    (0.0, (0.70, 0.72, 1.35)),
    (0.08, (0.95, 0.75, 1.25)),
    (0.35, (1.00, 0.92, 1.00)),
)
STAR_STRENGTH = 1.5

def _sky_texture(nodes, links, vector, path):
    tex = nodes.new('ShaderNodeTexEnvironment')
    tex.image = bpy.data.images.load(path, check_existing=True)
    tex.interpolation = 'Cubic'
    links.new(vector, tex.inputs['Vector'])
    return tex.outputs['Color']


def build_world():
    world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nodes, links = nt.nodes, nt.links
    nodes.clear()

    output = nodes.new('ShaderNodeOutputWorld')
    background = nodes.new('ShaderNodeBackground')
    background.inputs['Strength'].default_value = 1.0
    links.new(background.outputs[0], output.inputs[0])

    # 銀河座標の正距円筒図は、BlenderではZ軸回りの回転なしだと銀経0°が+X、銀経90°が+Yに来る。
    # シーンは銀河中心(銀経0°)が-Y、進行方向(銀経90°)が+Xなので、視線方向をZ軸回りに+90°回す。
    tex_coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(90))
    links.new(tex_coord.outputs['Generated'], mapping.inputs['Vector'])

    milkyway = _sky_texture(nodes, links, mapping.outputs[0], MILKYWAY_EXR)
    gain = nodes.new('ShaderNodeMix')
    gain.data_type = 'RGBA'
    gain.blend_type = 'MULTIPLY'
    gain.inputs['Factor'].default_value = 1.0
    gain.inputs['B'].default_value = (MILKYWAY_STRENGTH,) * 3 + (1,)
    links.new(milkyway, gain.inputs['A'])
    gamma = nodes.new('ShaderNodeGamma')
    gamma.inputs['Gamma'].default_value = MILKYWAY_GAMMA
    links.new(gain.outputs['Result'], gamma.inputs['Color'])
    saturation = nodes.new('ShaderNodeHueSaturation')
    saturation.inputs['Saturation'].default_value = MILKYWAY_SATURATION
    links.new(gamma.outputs[0], saturation.inputs['Color'])
    brightness = nodes.new('ShaderNodeRGBToBW')
    links.new(saturation.outputs[0], brightness.inputs['Color'])
    tint = nodes.new('ShaderNodeValToRGB')
    elements = tint.color_ramp.elements
    while len(elements) < len(MILKYWAY_TINT):
        elements.new(0.5)
    for element, (position, color) in zip(elements, MILKYWAY_TINT):
        element.position = position
        element.color = (*color, 1)
    links.new(brightness.outputs[0], tint.inputs['Fac'])
    tinted = nodes.new('ShaderNodeMix')
    tinted.data_type = 'RGBA'
    tinted.blend_type = 'MULTIPLY'
    tinted.inputs['Factor'].default_value = 1.0
    links.new(saturation.outputs[0], tinted.inputs['A'])
    links.new(tint.outputs['Color'], tinted.inputs['B'])

    stars = _sky_texture(nodes, links, mapping.outputs[0], STARS_EXR)
    star_gain = nodes.new('ShaderNodeMix')
    star_gain.data_type = 'RGBA'
    star_gain.blend_type = 'MULTIPLY'
    star_gain.inputs['Factor'].default_value = 1.0
    star_gain.inputs['B'].default_value = (STAR_STRENGTH,) * 3 + (1,)
    links.new(stars, star_gain.inputs['A'])

    add = nodes.new('ShaderNodeMix')
    add.data_type = 'RGBA'
    add.blend_type = 'ADD'
    add.inputs['Factor'].default_value = 1.0
    links.new(tinted.outputs['Result'], add.inputs['A'])
    links.new(star_gain.outputs['Result'], add.inputs['B'])
    links.new(add.outputs['Result'], background.inputs['Color'])

def build_compositor(scene):
    """Blender 5.x方式: ノードグループを明示作成し、Glareの種類はinputs["Type"]に文字列で指定。"""
    ng = bpy.data.node_groups.get("Ep3Compositor")
    if ng is not None:
        bpy.data.node_groups.remove(ng)
    ng = bpy.data.node_groups.new("Ep3Compositor", 'CompositorNodeTree')
    ng.interface.new_socket(name="Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    scene.compositing_node_group = ng

    render_layers = ng.nodes.new('CompositorNodeRLayers')
    glare = ng.nodes.new('CompositorNodeGlare')
    glare.inputs['Type'].default_value = 'Fog Glow'
    glare.inputs['Quality'].default_value = 'High'
    glare.inputs['Threshold'].default_value = 1.0
    glare.inputs['Size'].default_value = 0.9
    glare.inputs['Strength'].default_value = 1.2
    group_output = ng.nodes.new('NodeGroupOutput')
    ng.links.new(render_layers.outputs['Image'], glare.inputs['Image'])
    ng.links.new(glare.outputs['Image'], group_output.inputs['Image'])




# ============================================================
# カメラ
# ============================================================
V = mathutils.Vector
FINAL_SHIFT_Y = 0.0  # 横型では奥の銀河が見切れたため上へずらしていた。縦型では不要
X_AXIS = V((1.0, 0.0, 0.0))


def _auto_up(loc, target):
    """画面の右が進行方向(+X)になる上方向。"""
    back = (loc - target).normalized()
    right = (X_AXIS - back * X_AXIS.dot(back)).normalized()
    return back.cross(right)


def _top_down(distance):
    north = V(ecliptic_north_scene())
    down = V((0, 0, -1))
    return north * distance, V((0, 0, 0)), (down - north * down.dot(north)).normalized()


def _key(frame, loc, target, up, lens):
    return (frame, V(loc), V(target), V(up).normalized(), lens)


def _camera_keys():
    """(frame, 位置, 注視点, 画面の上方向, 焦点距離)。太陽は原点、進行方向は+X。
    2a〜3aは太陽系のすぐ周りを飛び回り、進行方向が画面の右・奥・上・右と変わる。視点を増やしすぎると
    目まぐるしく疲れるため、キーの間隔は35〜80フレーム取る。
    上方向は隣り合うキー同士で視線と平行にならないよう、回転がつながる向きを選んでいる。"""
    top0, top1 = _top_down(16.5), _top_down(15.0)
    side_loc, side_target = V((-6, 3, 8.5)), V((-3, 0, 0))
    # 4a: 太陽より前方の斜め上(画面の上=銀河南極側へ約25°)から、後ろへ伸びる軌跡を見下ろす。
    # 前に出しすぎず、進行方向の軸から十分離して遠近法でループ状に見えないようにする。
    # 縦型では軌跡が横に細長い帯になるため、画面を約40°回して斜めに流れる構図にする
    tilt = math.radians(40)
    pose_4a = ((-6, 48, -23), (-12, 0, 0), (-math.sin(tilt), 0, -math.cos(tilt)), 24)
    keys = [
        _key(1, *top0, 35),                                          # 1a: 教科書の俯瞰図
        _key(70, *top1, 35),
        _key(135, side_loc, side_target, _auto_up(side_loc, side_target), 24),  # 斜め上から: 右へ
        _key(185, (-10, 1, 2.5), (3, 0, 0.3), (0, 0, 1), 20),         # 後方オンボード: 奥へ
        _key(220, (-7, 1, -4), (0, 0, 0), (0, 1, 0), 22),             # ゆっくり横転しながら下へ
        _key(255, (-2, 1, -9), (-2, 0, 0), (1, 0, 0), 24),            # 真下から: 画面の上へ
        _key(335, (-6, 8.5, -1), (-4, 0, 0), (0, 0, -1), 24),         # 長く滑空して横へ: 右へ
        _key(560, *pose_4a),                                          # 4a: 引いて全体を見せる
        _key(600, *pose_4a),
    ]
    return _tame_acro(keys)


ACRO_KEY_FRAMES = (185, 220, 255)  # アクロバット区間の途中キー(両端の135と335は動かさない)
ACRO_INTENSITY = 0.8  # 途中キーの振れ幅。1.0=元の動き、0=両端を素直につないだ動き


def _tame_acro(keys):
    """アクロバット区間の途中キーを、両端のキーを素直につないだ基準の動きへACRO_INTENSITYの割合まで寄せる。
    位置は線形補間、向きはクォータニオンのslerpで縮めるので、上方向が反転するような大回転でも破綻しない。"""
    by_frame = {k[0]: k for k in keys}
    a, b = by_frame[135], by_frame[335]
    qa, qb = look_rotation(a[1], a[2], a[3]), look_rotation(b[1], b[2], b[3])
    out = []
    for k in keys:
        if k[0] not in ACRO_KEY_FRAMES:
            out.append(k)
            continue
        t = (k[0] - a[0]) / (b[0] - a[0])
        base_loc = a[1].lerp(b[1], t)
        loc = base_loc.lerp(k[1], ACRO_INTENSITY)
        q = qa.slerp(qb, t).slerp(look_rotation(k[1], k[2], k[3]), ACRO_INTENSITY)
        distance = (k[2] - k[1]).length
        target = loc + q @ V((0, 0, -distance))
        up = q @ V((0, 1, 0))
        out.append((k[0], loc, target, up, k[4]))
    return out


def _catmull_rom(p0, p1, p2, p3, t):
    t2, t3 = t * t, t * t * t
    return 0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3)


def _same_pose(a, b):
    """位置・注視点・上方向がすべて同じ(=カメラを止めておく区間)か。"""
    return all((a[f] - b[f]).length < 1e-6 for f in (1, 2, 3))


def camera_at(frame):
    """キーの間をCatmull-Romでつなぎ、キーごとに止まらず飛び続けるようにする。
    静止区間(同じ値のキーが続く所)だけは特別扱いする: 静止区間の中はキーの値をそのまま返し、
    静止区間へ入る区間は終点の接線を0にしてなめらかに減速させる。そのままのCatmull-Romだと、
    勢いを保ったまま静止区間に入って急停止し、さらに静止区間の中で一度はみ出して戻るため、
    最後の引きで「カクン」と揺れて傾いた。"""
    keys = _camera_keys()
    if frame <= keys[0][0]:
        return keys[0][1:]
    if frame >= keys[-1][0]:
        return keys[-1][1:]
    i = next(j for j in range(len(keys) - 1) if keys[j][0] <= frame <= keys[j + 1][0])
    k0, k1, k2, k3 = keys[max(i - 1, 0)], keys[i], keys[i + 1], keys[min(i + 2, len(keys) - 1)]
    t = (frame - k1[0]) / (k2[0] - k1[0])
    if _same_pose(k1, k2):
        return k1[1].copy(), k1[2].copy(), k1[3].copy(), k1[4]
    next_is_hold = _same_pose(k2, k3) and k3 is not k2
    out = []
    for field in (1, 2, 3):
        # 次が静止区間なら、p3=p1として終点の接線(p3-p1)/2を0にする
        p3 = k1[field] if next_is_hold else k3[field]
        out.append(_catmull_rom(k0[field], k1[field], k2[field], p3, t))
    lens = k1[4] + (k2[4] - k1[4]) * (t * t * (3 - 2 * t))
    return out[0], out[1], out[2], lens


def look_rotation(loc, target, up):
    """カメラは-Zを向き+Yが画面上。upは視線と直交するよう補正する。"""
    z = (loc - target).normalized()
    x = up.cross(z)
    if x.length < 1e-4:  # 念のため: 上方向が視線と平行になったら直前の軸で代用
        x = V((0, 0, 1)).cross(z)
    x.normalize()
    y = z.cross(x)
    return mathutils.Matrix((x, y, z)).transposed().to_quaternion()


def apply_camera(scene, frame):
    camera = bpy.data.objects.get("MainCamera")
    if camera is None:
        camera = bpy.data.objects.new("MainCamera", bpy.data.cameras.new("MainCamera"))
        scene.collection.objects.link(camera)
    for c in list(camera.constraints):
        camera.constraints.remove(c)
    loc, target, up, lens = camera_at(frame)
    camera.location = loc
    camera.rotation_mode = 'QUATERNION'
    camera.rotation_quaternion = look_rotation(loc, target, up)
    camera.data.lens = lens
    # 4a: 向きを変えずに画角だけ上へずらし、奥の天の川と銀河中心が見切れないようにする
    camera.data.shift_y = FINAL_SHIFT_Y * smoothstep(400, 560, frame)
    camera.data.clip_end = 1000
    scene.camera = camera


# ============================================================
# 軌跡・惑星・表示
# ============================================================
# 追従中に見せる軌跡の長さ(太陽から後ろへのユニット数)。カメラが近いと遠くの軌跡ほど軸方向から
# 覗く角度になり、遠近法で長いコイル(「渦」)に見えるため、見える範囲を太陽の近くに絞る。
ACRO_TRAIL_UNITS = 14.0
NO_FADE_UNITS = 250.0


def trail_view_limit(frame):
    """1a(太陽基準の円)はフェードなし → 引き伸ばす間に追従用の長さへ → 4aの引きの画へ移る間に全長。"""
    limit = NO_FADE_UNITS + (ACRO_TRAIL_UNITS - NO_FADE_UNITS) * smoothstep(MORPH_FRAMES[0], MORPH_FRAMES[1], frame)
    return limit + (NO_FADE_UNITS - limit) * smoothstep(335, 450, frame)


def _trail_nodes(obj):
    nt = obj.active_material.node_tree
    map_range = next(n for n in nt.nodes if n.type == 'MAP_RANGE')
    power = next(n for n in nt.nodes if n.type == 'MATH' and n.operation == 'POWER')
    return map_range, power, nt.nodes["Gain"]


def _set_trail_material(obj, fade_range, fade_power, gain):
    map_range, power, gain_node = _trail_nodes(obj)
    map_range.inputs['From Min'].default_value = -fade_range
    power.inputs[1].default_value = fade_power
    gain_node.inputs[1].default_value = TRAIL_STRENGTH_DEFAULT * gain


def apply_frame(scene, frame):
    """太陽は常に原点。1aは軌跡を太陽基準で表示した円で、太陽が動き出すと軌跡全体が
    銀河基準へ引き伸ばされ、円がそのまま螺旋につながる(shots.morph_blend)。"""
    now = sim_time(frame)
    fade_range = min(trail_view_limit(frame), forward_units(TIME_SPAN_YEARS))
    fade_range = max(fade_range, 0.5) if frame > MOTION_START_FRAME else NO_FADE_UNITS

    for name in DISPLAY:
        bpy.data.objects[name].location = trail_point(name, 0.0, now, now)
        trail = bpy.data.objects[f"Trail_{name}"]
        for p, co in zip(trail.data.splines[0].points, morph_trail_points(name, now, frame)):
            p.co = (*co, 1.0)
        _set_trail_material(trail, fade_range, FADE_POWER_DEFAULT, 1.0)

    sun_trail = bpy.data.objects["SunTrail"]
    for p, co in zip(sun_trail.data.splines[0].points, sun_trail_points(frame)):
        p.co = (*co, 1.0)
    sun_trail.hide_render = frame <= MOTION_START_FRAME
    _set_trail_material(sun_trail, fade_range, FADE_POWER_DEFAULT, 1.0)

    apply_camera(scene, frame)
    scene.frame_set(frame)


def setup_render(scene, resolution_percentage=100):
    build_world()
    build_compositor(scene)
    scene.view_settings.view_transform = 'AgX'
    engine_ids = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engine_ids else 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = resolution_percentage
    scene.render.image_settings.file_format = 'PNG'
