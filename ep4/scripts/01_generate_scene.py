# -*- coding: utf-8 -*-
"""
Stage 1: 夜の郊外の高速道路(道路・区画線・分離帯・街灯・木立・車)を生成してWIPに保存する

- 車は数種類のメッシュを共有するリンク複製。テールランプの明るさはオブジェクトのカスタム
  プロパティ"brake"(0〜1)をマテリアルのAttributeノードで読み、ブレーキ中ほど明るくする。
- 我々の車線の車は交通流の計算(scenario.py)と同じ台数・車種で作り、毎フレームの位置とブレーキは
  frame_state.pyが計算結果から設定する。テールランプの後ろの赤いスポットライト(EEVEEで光の回り込みを
  まねる)も車の子にして一緒に動かす。

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep4/scripts/01_generate_scene.py"
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import mathutils
import numpy as np
import scenario
from shots import (
    BRAKE_BOOST,
    DASH_GAP,
    DASH_LENGTH,
    LAMP_HEIGHT,
    LAMP_SPACING,
    LANE_WIDTH,
    LANES,
    MEDIAN_HALF,
    ONCOMING_LANE_X,
    OUR_LANE_X,
    ROAD_END,
    ROAD_HALF,
    ROAD_START,
    WIP_BLEND,
    road_slope,
    road_z,
)

SEED = 4
TREE_COLOR = (0.010, 0.016, 0.010)  # 夜の木立(暗いシルエット)
SEGMENT = 5.0  # 道路など帯状のメッシュをY方向に区切る間隔(坂に沿わせるため)

SODIUM = (1.0, 0.50, 0.16)  # 高圧ナトリウム灯のオレンジ
LAMP_HEAD_STRENGTH = 60.0
LAMP_LIGHT_POWER = 4500.0  # W。手前の街灯だけ本物のスポットライトにする
# 腕の形(支柱からの横距離, 支柱の高さLAMP_HEIGHTからの高さ)。支柱から曲線で立ち上がって水平に伸びる
LAMP_ARM = [(0.0, -1.2), (0.15, -0.6), (0.5, -0.2), (1.1, 0.0), (2.9, 0.0)]
LIT_LAMPS = 32  # 本物のライトにする街灯の数(道路の始点から)。奥は発光だけ
TAIL_COLOR = (1.0, 0.015, 0.008)
TAIL_STRENGTH = 10.0
HEAD_COLOR = (1.0, 0.93, 0.82)
HEAD_STRENGTH = 80.0
ASPHALT_ROUGHNESS = (0.22, 0.5)  # 低いほど光が路面に映り込む(乾いた路面の範囲に留める)

# EEVEEではランプの発光は周りを照らさないので、手前の車にだけ本物のライトを仕込む(Cyclesの回り込みの代わり)。
# テールランプ: 後ろ向き・少し下向きの赤いスポット。路面と後ろの車を照らす
TAIL_GLOW_POWER = 20.0  # W。ブレーキ中はBRAKE_BOOST倍
TAIL_GLOW_DISTANCE = 14.0  # m。光の届く上限(すぐ後ろの車と路面だけを照らし、計算も軽くする)
# 対向車のヘッドライト: 前向き・下向きのスポット。路面に光が伸びる
HEAD_BEAM_POWER = 900.0
HEAD_BEAM_DISTANCE = 70.0


# 車体色(夜はほとんど暗く見えるが、街灯の下で白・銀が浮く)
BODY_COLORS = [
    (0.80, 0.80, 0.80), (0.80, 0.80, 0.80), (0.50, 0.50, 0.52), (0.50, 0.50, 0.52),
    (0.02, 0.02, 0.02), (0.02, 0.02, 0.02), (0.10, 0.10, 0.11), (0.05, 0.07, 0.15),
    (0.35, 0.03, 0.03), (0.60, 0.55, 0.45),
]


# ============================================================
# 共通
# ============================================================
def reset_scene():
    bpy.ops.wm.read_homefile(use_empty=True)
    for block in (bpy.data.meshes, bpy.data.materials, bpy.data.lights, bpy.data.cameras):
        for item in list(block):
            block.remove(item)


def collection(name):
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def link(obj, col):
    col.objects.link(obj)
    return obj


def principled(name, color, roughness=0.5, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def emission(name, color, strength):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*color, 1)
    em.inputs['Strength'].default_value = strength
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def mesh_object(name, bm, materials, col):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    return link(bpy.data.objects.new(name, me), col)


def add_box(bm, center, size, mat_index=0, matrix=None):
    m = mathutils.Matrix.Translation(center) @ mathutils.Matrix.Diagonal((*size, 1.0))
    if matrix is not None:
        m = matrix @ m
    verts = bmesh.ops.create_cube(bm, size=1.0, matrix=m)['verts']
    for f in {f for v in verts for f in v.link_faces}:
        f.material_index = mat_index


def y_stations(y0=ROAD_START, y1=ROAD_END, step=SEGMENT):
    n = int((y1 - y0) / step)
    return [y0 + i * step for i in range(n + 1)]


def ribbon(bm, x0, x1, z_offset=0.0, y0=ROAD_START, y1=ROAD_END, mat_index=0, step=SEGMENT):
    """Y方向に伸びる帯。坂に沿わせるためstepごとに区切る。"""
    prev = None
    for y in y_stations(y0, y1, step):
        z = road_z(y) + z_offset
        row = (bm.verts.new((x0, y, z)), bm.verts.new((x1, y, z)))
        if prev:
            f = bm.faces.new((prev[0], prev[1], row[1], row[0]))
            f.material_index = mat_index
        prev = row


def sweep(bm, x, section, y0=ROAD_START, y1=ROAD_END, mat_index=0):
    """断面(横方向のずれ, 高さ)の折れ線をY方向に掃引した壁。"""
    prev = None
    for y in y_stations(y0, y1):
        z = road_z(y)
        row = [bm.verts.new((x + dx, y, z + dz)) for dx, dz in section]
        if prev:
            for i in range(len(section) - 1):
                f = bm.faces.new((prev[i], prev[i + 1], row[i + 1], row[i]))
                f.material_index = mat_index
                f.smooth = True
        prev = row


def wall(bm, x, half_width, height, y0=ROAD_START, y1=ROAD_END, mat_index=0):
    """Y方向に伸びる壁(ガードレール)。上面と両側面。"""
    sweep(bm, x, [(-half_width, 0), (-half_width, height), (half_width, height), (half_width, 0)], y0, y1, mat_index)


# ニュージャージー型の分離帯の断面(下が広がり、上の角は丸い)
MEDIAN_SECTION = [(-0.30, 0.0), (-0.26, 0.08), (-0.13, 0.33), (-0.09, 0.82), (-0.06, 0.88), (0.0, 0.9),
                  (0.06, 0.88), (0.09, 0.82), (0.13, 0.33), (0.26, 0.08), (0.30, 0.0)]


# ============================================================
# 道路・区画線・分離帯
# ============================================================
def build_road(col):
    asphalt = principled("Asphalt", (0.030, 0.030, 0.032), roughness=0.4)
    nt = asphalt.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    patch = nt.nodes.new('ShaderNodeTexNoise')  # 路面のつやのむら(轍・補修跡)
    patch.inputs['Scale'].default_value = 0.08
    patch.inputs['Detail'].default_value = 6.0
    patch_coord = nt.nodes.new('ShaderNodeTexCoord')
    nt.links.new(patch_coord.outputs['Object'], patch.inputs['Vector'])
    rough = nt.nodes.new('ShaderNodeMapRange')
    rough.inputs['From Min'].default_value = 0.35
    rough.inputs['From Max'].default_value = 0.65
    rough.inputs['To Min'].default_value = ASPHALT_ROUGHNESS[0]
    rough.inputs['To Max'].default_value = ASPHALT_ROUGHNESS[1]
    nt.links.new(patch.outputs['Fac'], rough.inputs['Value'])
    nt.links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    shoulder = principled("Shoulder", (0.05, 0.05, 0.05), roughness=0.8)
    paint = principled("LinePaint", (0.75, 0.75, 0.72), roughness=0.4)
    concrete = principled("Concrete", (0.30, 0.30, 0.29), roughness=0.8)
    rail = principled("GuardRail", (0.55, 0.56, 0.58), roughness=0.3, metallic=0.8)
    ground = principled("Ground", (0.012, 0.016, 0.010), roughness=0.95)

    bm = bmesh.new()
    lanes_half = MEDIAN_HALF + LANE_WIDTH * LANES
    for side in (-1, 1):
        ribbon(bm, side * MEDIAN_HALF if side > 0 else -lanes_half, lanes_half if side > 0 else -MEDIAN_HALF, 0.0, mat_index=0)
        ribbon(bm, side * lanes_half if side > 0 else -ROAD_HALF, ROAD_HALF if side > 0 else -lanes_half, 0.0, mat_index=1)
    ribbon(bm, -MEDIAN_HALF, MEDIAN_HALF, 0.0, mat_index=1)
    mesh_object("Road", bm, [asphalt, shoulder], col)

    # 区画線: 外側線(実線)と車線境界線(破線)。路面から1cm浮かせる
    bm = bmesh.new()
    for side in (-1, 1):
        for x in (MEDIAN_HALF + 0.15, MEDIAN_HALF + LANE_WIDTH * LANES - 0.15):
            ribbon(bm, side * x - 0.075, side * x + 0.075, 0.01)
        for i in range(1, LANES):
            x = side * (MEDIAN_HALF + LANE_WIDTH * i)
            y = ROAD_START
            while y < ROAD_END:
                ribbon(bm, x - 0.075, x + 0.075, 0.01, y0=y, y1=y + DASH_LENGTH, step=DASH_LENGTH)
                y += DASH_LENGTH + DASH_GAP
    mesh_object("LaneLines", bm, [paint], col)

    # 中央分離帯のコンクリート壁と、路肩のガードレール
    bm = bmesh.new()
    sweep(bm, 0.0, MEDIAN_SECTION, mat_index=0)
    for side in (-1, 1):
        wall(bm, side * (ROAD_HALF - 0.3), 0.05, 0.75, mat_index=1)
    mesh_object("Barriers", bm, [concrete, rail], col)

    # 周りの地面(道路と同じ坂に沿う)
    bm = bmesh.new()
    for side in (-1, 1):
        x0, x1 = sorted((side * ROAD_HALF, side * 400.0))
        ribbon(bm, x0, x1, -0.3, step=20.0)
    mesh_object("Ground", bm, [ground], col)


# ============================================================
# 街灯(中央分離帯に両側へ腕を伸ばす)
# ============================================================
def build_lamps(col):
    pole_mat = principled("LampPole", (0.25, 0.26, 0.27), roughness=0.4, metallic=0.7)
    head_mat = emission("LampHead", SODIUM, LAMP_HEAD_STRENGTH)
    bm = bmesh.new()
    lamp_ys = []
    y = ROAD_START + 20.0  # カメラの後ろにも並べる(手前の車の後ろの面を照らす)
    while y < ROAD_END:
        z = road_z(y)
        add_box(bm, (0, y, z + (LAMP_HEIGHT - 1.2) / 2), (0.25, 0.25, LAMP_HEIGHT - 1.2), 0)
        for side in (-1, 1):
            arm = [(side * ax, z + LAMP_HEIGHT + az) for ax, az in LAMP_ARM]
            for (x0, z0), (x1, z1) in zip(arm, arm[1:]):
                d = mathutils.Vector((x1 - x0, 0, z1 - z0))
                rot = mathutils.Matrix.Rotation(-math.atan2(d.z, d.x), 4, 'Y')
                m = mathutils.Matrix.Translation(((x0 + x1) / 2, y, (z0 + z1) / 2)) @ rot
                add_box(bm, (0, 0, 0), (d.length + 0.1, 0.14, 0.14), 0, matrix=m)
            add_box(bm, (side * 2.9, y, z + LAMP_HEIGHT - 0.12), (0.7, 0.35, 0.12), 1)
        lamp_ys.append(y)
        y += LAMP_SPACING
    mesh_object("Lamps", bm, [pole_mat, head_mat], col)

    # 本物のライトにするのは、1aのカメラ(y=0)の少し後ろから前の街灯だけ(道路はカメラの後ろへも延びている)
    for i, y in enumerate([y for y in lamp_ys if y > -60.0][:LIT_LAMPS]):
        for side in (-1, 1):
            data = bpy.data.lights.new(f"LampLight_{i:02d}_{side:+d}", 'SPOT')
            data.color = SODIUM
            data.energy = LAMP_LIGHT_POWER
            data["base_power"] = LAMP_LIGHT_POWER
            data.spot_size = math.radians(130)
            data.spot_blend = 0.6
            data.shadow_soft_size = 0.3
            obj = link(bpy.data.objects.new(data.name, data), col)
            obj.location = (side * 2.9, y, road_z(y) + LAMP_HEIGHT - 0.35)  # 真下向き(既定)


# ============================================================
# 木立(道路の両脇の暗いシルエット)
# ============================================================
def _template(build):
    """bmeshで木のひな形を1つ作り、(頂点のnumpy配列, 面の頂点番号のリスト)にする。"""
    bm = bmesh.new()
    build(bm)
    bm.verts.index_update()
    verts = np.array([v.co[:] for v in bm.verts])
    faces = [[v.index for v in f.verts] for f in bm.faces]
    bm.free()
    return verts, faces


def build_trees(col, rng):
    """道路の両脇の暗い木立。1本ずつbmeshで作ると木が多いとき非常に遅いので、球のひな形を
    numpyで拡大・移動したコピーを並べて、1つのメッシュとしてまとめて作る。"""
    leaf = principled("TreeLeaf", TREE_COLOR, roughness=0.9)
    verts0, faces0 = _template(lambda bm: bmesh.ops.create_icosphere(bm, subdivisions=2, radius=1.0))
    all_verts, all_faces, offset = [], [], 0
    for side in (-1, 1):
        y = ROAD_START
        while y < ROAD_END:
            if rng.random() < 0.3:  # 林の切れ目
                y += rng.uniform(15.0, 60.0)
                continue
            x = side * (ROAD_HALF + rng.uniform(12, 60))
            r = rng.uniform(2.0, 4.5)
            all_verts.append(verts0 * np.array([r, r, r * 1.3]) + np.array([x, y, road_z(y) + r * 0.9]))
            all_faces.extend([[i + offset for i in f] for f in faces0])
            offset += len(verts0)
            y += rng.uniform(3.0, 8.0)
    me = bpy.data.meshes.new("Trees")
    me.from_pydata(np.concatenate(all_verts).tolist(), [], all_faces)
    me.materials.append(leaf)
    link(bpy.data.objects.new("Trees", me), col)


# ============================================================
# 車(ローカルの前方が+Y、原点は後輪の間の路面)
# ============================================================
def car_materials():
    body = bpy.data.materials.new("CarBody")
    body.use_nodes = True
    nt = body.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    # 金属感を下げて街灯の光を拡散で受け、クリアコートで屋根やボンネットにつやを出す
    bsdf.inputs['Roughness'].default_value = 0.4
    bsdf.inputs['Metallic'].default_value = 0.15
    bsdf.inputs['Coat Weight'].default_value = 0.8
    bsdf.inputs['Coat Roughness'].default_value = 0.08
    info = nt.nodes.new('ShaderNodeObjectInfo')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.interpolation = 'CONSTANT'
    elements = ramp.color_ramp.elements
    while len(elements) < len(BODY_COLORS):
        elements.new(0.5)
    for i, (element, color) in enumerate(zip(elements, BODY_COLORS)):
        element.position = i / len(BODY_COLORS)
        element.color = (*color, 1)
    nt.links.new(info.outputs['Random'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])

    glass = principled("CarGlass", (0.01, 0.01, 0.012), roughness=0.1)
    dark = principled("CarUnder", (0.01, 0.01, 0.01), roughness=0.9)

    # テールランプ: 明るさ = TAIL_STRENGTH * (1 + brake * (BRAKE_BOOST - 1))
    tail = bpy.data.materials.new("TailLight")
    tail.use_nodes = True
    nt = tail.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (*TAIL_COLOR, 1)
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_type = 'OBJECT'
    attr.attribute_name = 'brake'
    gain = nt.nodes.new('ShaderNodeMath')
    gain.operation = 'MULTIPLY_ADD'
    gain.inputs[1].default_value = TAIL_STRENGTH * (BRAKE_BOOST - 1)
    gain.inputs[2].default_value = TAIL_STRENGTH
    nt.links.new(attr.outputs['Fac'], gain.inputs[0])
    nt.links.new(gain.outputs[0], em.inputs['Strength'])
    nt.links.new(em.outputs[0], out.inputs[0])

    head = emission("HeadLight", HEAD_COLOR, HEAD_STRENGTH)
    return [body, glass, dark, tail, head]


def rounded_box(bm, center, size, mat_index, bevel):
    before = set(bm.edges)
    add_box(bm, center, size, mat_index)
    edges = [e for e in bm.edges if e not in before]
    bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=3, profile=0.5, affect='EDGES', clamp_overlap=True)


def smooth_shading(bm, sharp_deg=35.0):
    """丸めた所はなめらかに、はっきりした折れ目(ランプの縁など)だけ角を残す。"""
    for f in bm.faces:
        f.smooth = True
    limit = math.radians(sharp_deg)
    for e in bm.edges:
        if e.is_manifold and e.calc_face_angle(0.0) > limit:
            e.smooth = False


# 横から見た形(後端y=0→前、z=高さ)を、屋根まで1つのシルエットとして持つ(部品を重ねると段差が出る)。
# beltより上は上へ行くほど内側へすぼめ(タンブルホーム)、その範囲の側面・前後の面を窓の色にする。
CAR_SHAPES = {
    "sedan": dict(
        length=4.6, width=1.78, tail_z=0.70, head_z=0.50, belt=0.96, roof_taper=0.80,
        profile=[(0.0, 0.32), (0.0, 0.80), (0.12, 0.93), (0.72, 0.97), (1.40, 1.38), (2.85, 1.42),
                 (3.55, 0.97), (4.30, 0.84), (4.6, 0.62), (4.6, 0.32)],
    ),
    "van": dict(
        length=4.7, width=1.72, tail_z=0.92, head_z=0.62, belt=1.06, roof_taper=0.86,
        profile=[(0.0, 0.32), (0.0, 1.06), (0.06, 1.70), (0.25, 1.80), (3.0, 1.80), (3.85, 1.07),
                 (4.5, 0.88), (4.7, 0.62), (4.7, 0.32)],
    ),
}


def car_mesh(name, kind, materials):
    """マテリアル: 0車体 1窓 2下回り・タイヤ 3テール 4ヘッド。ローカルの前方が+Y、原点は後端の路面。"""
    shape = CAR_SHAPES[kind]
    length, width, belt = shape["length"], shape["width"], shape["belt"]
    roof = max(z for _, z in shape["profile"])
    bm = bmesh.new()
    rounded_box(bm, (0, length / 2, 0.24), (width * 0.86, length * 0.9, 0.2), 2, 0.05)
    for y in (0.85, length - 0.95):  # タイヤ(後ろから見ると下に覗く)
        for side in (-1, 1):
            rounded_box(bm, (side * (width / 2 - 0.2), y, 0.32), (0.22, 0.64, 0.64), 2, 0.1)

    before = set(bm.faces)
    left = [bm.verts.new((-width / 2, y, z)) for y, z in shape["profile"]]
    face = bm.faces.new(left)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    right = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(width, 0, 0), verts=right)
    body_verts = left + right
    for v in body_verts:  # beltより上を、屋根に向かってなめらかにすぼめる
        if v.co.z > belt:
            t = (v.co.z - belt) / (roof - belt)
            v.co.x *= 1.0 - (1.0 - shape["roof_taper"]) * t ** 0.8
    body_faces = [f for f in bm.faces if f not in before]
    bmesh.ops.recalc_face_normals(bm, faces=body_faces)
    edges = list({e for v in body_verts for e in v.link_edges})
    bmesh.ops.bevel(bm, geom=edges, offset=0.16, segments=4, profile=0.5, affect='EDGES', clamp_overlap=True)
    for f in bm.faces:
        if f in before:
            continue
        c = f.calc_center_median()
        is_glass = belt + 0.04 < c.z < roof - 0.03 and abs(f.normal.z) < 0.9
        f.material_index = 1 if is_glass else 0

    for side in (-1, 1):  # ランプは車体の面に沿った薄い板
        x = side * (width / 2 - 0.28)
        rounded_box(bm, (x, -0.004, shape["tail_z"]), (0.48, 0.012, 0.13), 3, 0.004)
        rounded_box(bm, (x, length + 0.004, shape["head_z"]), (0.34, 0.012, 0.10), 4, 0.004)
    smooth_shading(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    return me


def truck_mesh(name, materials):
    """箱型トラック(実物も箱なので形は箱のまま、角だけ丸める)。荷台7.0m+キャブ1.9m。"""
    box_len, cab_len, width = 7.0, 1.9, 2.40
    bm = bmesh.new()
    rounded_box(bm, (0, (box_len + cab_len) / 2, 0.45), (width * 0.9, box_len + cab_len, 0.4), 2, 0.05)
    for y in (1.2, 2.6, box_len + 1.0):
        for side in (-1, 1):
            rounded_box(bm, (side * (width / 2 - 0.3), y, 0.5), (0.35, 1.0, 1.0), 2, 0.15)
    rounded_box(bm, (0, box_len / 2, 0.65 + 1.35), (width, box_len, 2.7), 0, 0.06)
    rounded_box(bm, (0, box_len + cab_len / 2, 0.55 + 1.15), (width * 0.98, cab_len, 2.3), 0, 0.15)
    rounded_box(bm, (0, box_len + cab_len, 0.55 + 1.65), (width * 0.88, 0.1, 0.8), 1, 0.04)
    for side in (-1, 1):
        x = side * (width / 2 - 0.3)
        rounded_box(bm, (x, -0.02, 0.8), (0.42, 0.05, 0.16), 3, 0.02)
        rounded_box(bm, (x, box_len + cab_len + 0.02, 0.75), (0.32, 0.05, 0.12), 4, 0.02)
    smooth_shading(bm)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    return me


def aim(light_obj, direction):
    """ライトの照射方向(ローカル-Z)を、親(車)のローカル座標の方向へ向ける。"""
    light_obj.rotation_mode = 'QUATERNION'
    light_obj.rotation_quaternion = mathutils.Vector((0, 0, -1)).rotation_difference(mathutils.Vector(direction))


def add_tail_glow(car, kind, col):
    data = bpy.data.lights.new(f"TailGlow_{car.name}", 'SPOT')
    data.color = TAIL_COLOR
    data.energy = TAIL_GLOW_POWER
    data["base_power"] = TAIL_GLOW_POWER  # frame_stateがブレーキの強さに応じて倍率を掛ける
    data.spot_size = math.radians(150)
    data.spot_blend = 1.0
    data.shadow_soft_size = 0.25
    data.use_shadow = False
    data.use_custom_distance = True
    data.cutoff_distance = TAIL_GLOW_DISTANCE
    obj = link(bpy.data.objects.new(data.name, data), col)
    obj.parent = car
    obj.location = (0, -0.15, 0.75 if kind == "truck" else CAR_SHAPES.get(kind, CAR_SHAPES["sedan"])["tail_z"])
    aim(obj, (0, -1, -0.35))
    return obj


def add_head_beam(car, kind, col):
    data = bpy.data.lights.new(f"HeadBeam_{car.name}", 'SPOT')
    data.color = HEAD_COLOR
    data.energy = HEAD_BEAM_POWER
    data.spot_size = math.radians(55)
    data.spot_blend = 0.8
    data.shadow_soft_size = 0.15
    data.use_shadow = False
    data.use_custom_distance = True
    data.cutoff_distance = HEAD_BEAM_DISTANCE
    obj = link(bpy.data.objects.new(data.name, data), col)
    obj.parent = car
    obj.location = (0, scenario.CAR_LENGTH[kind] + 0.2, 0.6)
    aim(obj, (0, 1, -0.08))
    return obj


DOT_COLORS = (  # 速度(時速100kmで1)→色。遅いほど赤
    (0.0, (1.0, 0.04, 0.02)),
    (0.12, (1.0, 0.32, 0.03)),
    (0.40, (1.0, 0.82, 0.55)),
    (0.75, (0.55, 0.78, 1.0)),
)


def dot_material():
    """記号表現の光の点。色はオブジェクトの"speed01"(速度/時速100km)、明るさはノード"DotStrength"(frame_stateが設定)。"""
    mat = bpy.data.materials.new("DotGlow")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    attr = nt.nodes.new('ShaderNodeAttribute')
    attr.attribute_type = 'OBJECT'
    attr.attribute_name = 'speed01'
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    elements = ramp.color_ramp.elements
    while len(elements) < len(DOT_COLORS):
        elements.new(0.5)
    for element, (position, color) in zip(elements, DOT_COLORS):
        element.position = position
        element.color = (*color, 1)
    strength = nt.nodes.new('ShaderNodeValue')
    strength.name = "DotStrength"
    strength.outputs[0].default_value = 0.0
    nt.links.new(attr.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], em.inputs['Color'])
    nt.links.new(strength.outputs[0], em.inputs['Strength'])
    nt.links.new(em.outputs[0], out.inputs[0])
    return mat


def dot_mesh(name, length, material):
    bm = bmesh.new()
    rounded_box(bm, (0, 0, 0), (1.9, length * 0.92, 0.25), 0, 0.12)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(material)
    return me


def add_dot(car, kind, meshes, col):
    dot = link(bpy.data.objects.new(f"Dot_{car.name}", meshes[kind]), col)
    dot.parent = car
    dot.location = (0, scenario.CAR_LENGTH[kind] / 2, 3.6 if kind == "truck" else 2.2)  # 車体より上に浮かせる
    dot["speed01"] = 0.0
    dot.hide_render = True
    return dot


def build_cars(col, rng):
    """我々の車線の車は計算(scenario)と同じ台数・車種で作る。位置・ブレーキは毎フレームframe_stateが設定する。
    車ごとに記号表現の光の点(子オブジェクト)も作り、俯瞰に移ったら車の代わりに見せる。"""
    mats = car_materials()
    glow = dot_material()
    dot_meshes = {k: dot_mesh(f"Dot_{k}", length, glow) for k, length in scenario.CAR_LENGTH.items()}
    meshes = {
        "sedan": car_mesh("Sedan", "sedan", mats),
        "van": car_mesh("Van", "van", mats),
        "truck": truck_mesh("Truck", mats),
    }

    def place(name, kind, x, y, heading):
        obj = link(bpy.data.objects.new(name, meshes[kind]), col)
        obj["x_offset"] = rng.uniform(-0.25, 0.25)  # 車線の中でのわずかな左右のずれ
        obj.location = (x + obj["x_offset"], y, road_z(y))
        obj.rotation_euler = (math.atan(road_slope(y)) * heading, 0, 0 if heading > 0 else math.pi)
        # 長さ方向は計算の車長と合わせるため変えない
        obj.scale = (rng.uniform(0.93, 1.06), 1.0, rng.uniform(0.94, 1.08))
        obj["brake"] = 0.0
        obj["kind"] = kind
        return obj

    n = 0
    for lane, x in enumerate(OUR_LANE_X):
        for i, kind in enumerate(scenario.car_kinds(lane)):
            obj = place(f"Car_L{lane}_{i:03d}", kind, x, ROAD_START + 10.0 * i, +1)
            obj["lane"], obj["index"] = lane, i
            add_tail_glow(obj, kind, col)
            add_dot(obj, kind, dot_meshes, col)
            n += 1
    m = 0
    for lane, y, kind in scenario.oncoming_layout():
        obj = place(f"Oncoming_{m:04d}", kind, ONCOMING_LANE_X[lane], y, -1)
        obj["y0"] = y
        add_head_beam(obj, kind, col)
        m += 1
    lights = sum(1 for o in col.objects if o.type == 'LIGHT' and not o.name.startswith("Dot_"))
    print(f"[Stage1] cars: {n} ours + {m} oncoming, car lights: {lights}")


def main():
    rng = random.Random(SEED)
    reset_scene()
    build_road(collection("Road"))
    build_lamps(collection("Lamps"))
    build_trees(collection("Scenery"), rng)
    build_cars(collection("Cars"), rng)
    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print("[Stage1] saved:", WIP_BLEND)


if __name__ == "__main__":
    main()
