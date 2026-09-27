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

BAND_HALF_WIDTH = 0.22  # 天の川の帯の太さ(方向ベクトルのz成分)
BAND_STRENGTH = 0.16  # 長時間露光の天体写真程度の明るさ(位置・幅は実物通りに保つ)
BULGE_STRENGTH = 0.5
BULGE_POWER = 60.0  # 大きいほど銀河中心の光が小さくまとまる
STAR_SCALE = 80.0  # 全天で約6千個。細かくしすぎると1ピクセル未満の点が並んで粒状ノイズに見える
STAR_THRESHOLD = 0.04
STAR_STRENGTH = 5.0
DENSE_STAR_SCALE = 700.0  # 帯の中だけに散らす微光星(天の川の粒状感)
DENSE_STAR_THRESHOLD = 0.05
FAINT_STAR_SCALE = 170.0  # 空全体の微光星(約2万個)
FAINT_STAR_THRESHOLD = 0.045
FAINT_STAR_STRENGTH = 2.5


def math_node(nodes, op, a=None, b=None):
    n = nodes.new('ShaderNodeMath')
    n.operation = op
    if a is not None:
        n.inputs[0].default_value = a
    if b is not None:
        n.inputs[1].default_value = b
    return n


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

    tex_coord = nodes.new('ShaderNodeTexCoord')
    direction = tex_coord.outputs['Generated']  # ワールドでは視線方向ベクトル

    # --- 恒星(ep1のVoronoi方式) ---
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (STAR_SCALE,) * 3
    voronoi = nodes.new('ShaderNodeTexVoronoi')
    voronoi.voronoi_dimensions = '3D'
    ramp = nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
    ramp.color_ramp.elements[1].position = STAR_THRESHOLD
    ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
    links.new(direction, mapping.inputs['Vector'])
    links.new(mapping.outputs[0], voronoi.inputs['Vector'])
    links.new(voronoi.outputs['Distance'], ramp.inputs['Fac'])
    star_mask = ramp.outputs['Color']

    # --- 天の川の帯(銀河面=X-Y平面 → 方向ベクトルのzが0付近) ---
    sep = nodes.new('ShaderNodeSeparateXYZ')
    links.new(direction, sep.inputs[0])
    abs_z = math_node(nodes, 'ABSOLUTE')
    links.new(sep.outputs['Z'], abs_z.inputs[0])
    band = nodes.new('ShaderNodeMapRange')
    band.interpolation_type = 'SMOOTHERSTEP'
    band.inputs['From Min'].default_value = 0.0
    band.inputs['From Max'].default_value = BAND_HALF_WIDTH
    band.inputs['To Min'].default_value = 1.0
    band.inputs['To Max'].default_value = 0.0
    links.new(abs_z.outputs[0], band.inputs['Value'])

    # 帯のむら(星雲状の濃淡)と暗黒帯
    cloud = nodes.new('ShaderNodeTexNoise')
    cloud.inputs['Scale'].default_value = 7.0
    cloud.inputs['Detail'].default_value = 15.0
    cloud.inputs['Roughness'].default_value = 0.6
    links.new(direction, cloud.inputs['Vector'])
    cloud_contrast = nodes.new('ShaderNodeMapRange')
    cloud_contrast.inputs['From Min'].default_value = 0.4
    cloud_contrast.inputs['From Max'].default_value = 0.7
    cloud_contrast.inputs['To Min'].default_value = 0.15
    links.new(cloud.outputs['Fac'], cloud_contrast.inputs['Value'])

    # 暗黒帯: 銀河面に沿って横長に伸ばしたノイズを、帯の中心付近(|z|小)だけに効かせる
    dust_mapping = nodes.new('ShaderNodeMapping')
    dust_mapping.inputs['Scale'].default_value = (6.0, 6.0, 40.0)
    links.new(direction, dust_mapping.inputs['Vector'])
    dust = nodes.new('ShaderNodeTexNoise')
    dust.inputs['Scale'].default_value = 1.0
    dust.inputs['Detail'].default_value = 10.0
    dust.inputs['Roughness'].default_value = 0.55
    links.new(dust_mapping.outputs[0], dust.inputs['Vector'])
    dust_dark = nodes.new('ShaderNodeMapRange')
    dust_dark.inputs['From Min'].default_value = 0.45
    dust_dark.inputs['From Max'].default_value = 0.65
    dust_dark.inputs['To Min'].default_value = 0.0
    dust_dark.inputs['To Max'].default_value = 0.9  # 暗くする量(0=なし)
    links.new(dust.outputs['Fac'], dust_dark.inputs['Value'])
    lane_center = nodes.new('ShaderNodeMapRange')
    lane_center.interpolation_type = 'SMOOTHSTEP'
    lane_center.inputs['From Min'].default_value = 0.0
    lane_center.inputs['From Max'].default_value = 0.05
    lane_center.inputs['To Min'].default_value = 1.0
    lane_center.inputs['To Max'].default_value = 0.0
    links.new(abs_z.outputs[0], lane_center.inputs['Value'])
    dust_amount = math_node(nodes, 'MULTIPLY')
    links.new(dust_dark.outputs[0], dust_amount.inputs[0])
    links.new(lane_center.outputs[0], dust_amount.inputs[1])
    dust_mask = math_node(nodes, 'SUBTRACT', a=1.0)  # 1 - 暗くする量
    links.new(dust_amount.outputs[0], dust_mask.inputs[1])

    band_density = math_node(nodes, 'MULTIPLY')
    links.new(band.outputs[0], band_density.inputs[0])
    links.new(cloud_contrast.outputs[0], band_density.inputs[1])
    band_dusty = math_node(nodes, 'MULTIPLY')
    links.new(band_density.outputs[0], band_dusty.inputs[0])
    links.new(dust_mask.outputs[0], band_dusty.inputs[1])

    # --- 銀河中心のバルジ(-Y方向) ---
    dot = nodes.new('ShaderNodeVectorMath')
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = (0.0, -1.0, 0.0)
    links.new(direction, dot.inputs[0])
    bulge_clamp = math_node(nodes, 'MAXIMUM', b=0.0)
    links.new(dot.outputs['Value'], bulge_clamp.inputs[0])
    bulge = math_node(nodes, 'POWER', b=BULGE_POWER)
    links.new(bulge_clamp.outputs[0], bulge.inputs[0])
    bulge_in_band = math_node(nodes, 'MULTIPLY')
    links.new(bulge.outputs[0], bulge_in_band.inputs[0])
    links.new(band.outputs[0], bulge_in_band.inputs[1])
    bulge_dusty = math_node(nodes, 'MULTIPLY')
    links.new(bulge_in_band.outputs[0], bulge_dusty.inputs[0])
    links.new(dust_mask.outputs[0], bulge_dusty.inputs[1])

    # --- 合成: 帯(淡い白) + バルジ(暖色) + 星(帯の中はやや多く見えるよう明るく) ---
    band_color = nodes.new('ShaderNodeMix')
    band_color.data_type = 'RGBA'
    band_color.blend_type = 'MULTIPLY'
    band_color.inputs['Factor'].default_value = 1.0
    band_color.inputs['B'].default_value = (0.74 * BAND_STRENGTH, 0.82 * BAND_STRENGTH, 1.0 * BAND_STRENGTH, 1)
    links.new(band_dusty.outputs[0], band_color.inputs['A'])

    bulge_color = nodes.new('ShaderNodeMix')
    bulge_color.data_type = 'RGBA'
    bulge_color.blend_type = 'MULTIPLY'
    bulge_color.inputs['Factor'].default_value = 1.0
    bulge_color.inputs['B'].default_value = (1.0 * BULGE_STRENGTH, 0.68 * BULGE_STRENGTH, 0.36 * BULGE_STRENGTH, 1)
    links.new(bulge_dusty.outputs[0], bulge_color.inputs['A'])

    star_boost = math_node(nodes, 'MULTIPLY_ADD', b=3.0, )
    star_boost.inputs[2].default_value = 2.5  # 帯の外=2.5、帯の中=5.5
    links.new(band.outputs[0], star_boost.inputs[0])
    # 星ごとの明るさのばらつき(Voronoiのセルごとの乱数色を使う)
    star_random = nodes.new('ShaderNodeSeparateColor')
    links.new(voronoi.outputs['Color'], star_random.inputs[0])
    star_variation = math_node(nodes, 'MULTIPLY_ADD', b=1.2)
    star_variation.inputs[2].default_value = 0.2  # 0.2〜1.4倍
    links.new(star_random.outputs[0], star_variation.inputs[0])
    star_varied = math_node(nodes, 'MULTIPLY')
    links.new(star_boost.outputs[0], star_varied.inputs[0])
    links.new(star_variation.outputs[0], star_varied.inputs[1])
    star_gain = math_node(nodes, 'MULTIPLY', b=STAR_STRENGTH)
    links.new(star_varied.outputs[0], star_gain.inputs[0])
    stars = nodes.new('ShaderNodeMix')
    stars.data_type = 'RGBA'
    stars.blend_type = 'MULTIPLY'
    stars.inputs['Factor'].default_value = 1.0
    links.new(star_mask, stars.inputs['A'])
    links.new(star_gain.outputs[0], stars.inputs['B'])

    add1 = nodes.new('ShaderNodeMix')
    add1.data_type = 'RGBA'
    add1.blend_type = 'ADD'
    add1.inputs['Factor'].default_value = 1.0
    links.new(band_color.outputs['Result'], add1.inputs['A'])
    links.new(bulge_color.outputs['Result'], add1.inputs['B'])
    add2 = nodes.new('ShaderNodeMix')
    add2.data_type = 'RGBA'
    add2.blend_type = 'ADD'
    add2.inputs['Factor'].default_value = 1.0
    links.new(add1.outputs['Result'], add2.inputs['A'])
    links.new(stars.outputs['Result'], add2.inputs['B'])

    # 帯の中だけの微光星: 雲の濃い所ほど多く、暗黒帯では消える
    dense_mapping = nodes.new('ShaderNodeMapping')
    dense_mapping.inputs['Scale'].default_value = (DENSE_STAR_SCALE,) * 3
    dense_voronoi = nodes.new('ShaderNodeTexVoronoi')
    dense_voronoi.voronoi_dimensions = '3D'
    dense_ramp = nodes.new('ShaderNodeValToRGB')
    dense_ramp.color_ramp.interpolation = 'CONSTANT'
    dense_ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
    dense_ramp.color_ramp.elements[1].position = DENSE_STAR_THRESHOLD
    dense_ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
    links.new(direction, dense_mapping.inputs['Vector'])
    links.new(dense_mapping.outputs[0], dense_voronoi.inputs['Vector'])
    links.new(dense_voronoi.outputs['Distance'], dense_ramp.inputs['Fac'])
    dense_amount = math_node(nodes, 'MULTIPLY', b=3.0)
    links.new(band_dusty.outputs[0], dense_amount.inputs[0])
    dense_stars = nodes.new('ShaderNodeMix')
    dense_stars.data_type = 'RGBA'
    dense_stars.blend_type = 'MULTIPLY'
    dense_stars.inputs['Factor'].default_value = 1.0
    links.new(dense_ramp.outputs['Color'], dense_stars.inputs['A'])
    links.new(dense_amount.outputs[0], dense_stars.inputs['B'])

    add3 = nodes.new('ShaderNodeMix')
    add3.data_type = 'RGBA'
    add3.blend_type = 'ADD'
    add3.inputs['Factor'].default_value = 1.0
    links.new(add2.outputs['Result'], add3.inputs['A'])
    links.new(dense_stars.outputs['Result'], add3.inputs['B'])

    # 空全体に散らばる微光星(帯の外も星が散りばめられて見えるように)
    faint_mapping = nodes.new('ShaderNodeMapping')
    faint_mapping.inputs['Scale'].default_value = (FAINT_STAR_SCALE,) * 3
    faint_voronoi = nodes.new('ShaderNodeTexVoronoi')
    faint_voronoi.voronoi_dimensions = '3D'
    faint_ramp = nodes.new('ShaderNodeValToRGB')
    faint_ramp.color_ramp.interpolation = 'CONSTANT'
    faint_ramp.color_ramp.elements[0].color = (FAINT_STAR_STRENGTH,) * 3 + (1,)
    faint_ramp.color_ramp.elements[1].position = FAINT_STAR_THRESHOLD
    faint_ramp.color_ramp.elements[1].color = (0, 0, 0, 1)
    links.new(direction, faint_mapping.inputs['Vector'])
    links.new(faint_mapping.outputs[0], faint_voronoi.inputs['Vector'])
    links.new(faint_voronoi.outputs['Distance'], faint_ramp.inputs['Fac'])
    add4 = nodes.new('ShaderNodeMix')
    add4.data_type = 'RGBA'
    add4.blend_type = 'ADD'
    add4.inputs['Factor'].default_value = 1.0
    links.new(add3.outputs['Result'], add4.inputs['A'])
    links.new(faint_ramp.outputs['Color'], add4.inputs['B'])
    links.new(add4.outputs['Result'], background.inputs['Color'])


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
    return [
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
