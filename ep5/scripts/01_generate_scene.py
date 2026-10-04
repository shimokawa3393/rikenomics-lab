# -*- coding: utf-8 -*-
"""
Stage 1: 雷雨の山あいの駐車場(地面・駐車枠・山・木立・車)を生成してWIPに保存する

- 車はep4の作り方(横から見た形を押し出して角を丸める)を土台に、上から見たすぼまり、タンブルホーム、
  ピラーと窓の塗り分け、フェンダーの切り欠き、円柱のタイヤとホイール、ミラー、ライトを足したもの
- 窓の面は材質番号1(ガラス)。のちの電流の計算は、このメッシュの金属の面(材質0)だけで解く

実行:
  /Applications/Blender.app/Contents/MacOS/Blender --background --python "ep5/scripts/01_generate_scene.py"
"""
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import bmesh
import bpy
import mathutils
from mathutils import noise
from mathutils.bvhtree import BVHTree
from shots import (
    ARCH_RADIUS, ASPHALT, ROOF_Z, SCREEN_HALF_TOP, AXLES_Y, B_PILLAR, BELT, CAM_LENS, CAM_LOC, CAM_TARGET, CAR_LENGTH, CAR_PROFILE,
    CAR_WIDTH, LINE_WIDTH, LOT_HALF, NOSE_TAPER, ROOF_TAPER, SCREEN_HALF, SIDE_WINDOW_BOTTOM,
    SIDE_WINDOW_INSET_A, SIDE_WINDOW_INSET_C, SIDE_WINDOW_TOP, SLOT_LENGTH, SLOT_WIDTH, TAPER_ZONE,
    WHEEL_RADIUS, WHEEL_WIDTH, WIP_BLEND,
)

V = mathutils.Vector
SEED = 5
PAINT = (0.33, 0.34, 0.36)  # シルバー(明るすぎると曇り空を映して白く飛ぶ)
FOREST = (0.014, 0.030, 0.016)
GRASS = (0.035, 0.045, 0.025)
RAIN_COUNT = 5000
RAIN_OPACITY = 0.10
RAIN_BRIGHTNESS = 0.5


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


def principled(name, color, roughness=0.5, metallic=0.0, coat=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = next(n for n in mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Base Color'].default_value = (*color, 1)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    bsdf.inputs['Coat Weight'].default_value = coat
    bsdf.inputs['Coat Roughness'].default_value = 0.04
    return mat


def mesh_object(name, bm, materials, col):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    return link(bpy.data.objects.new(name, me), col)


def smooth_shading(bm, sharp_deg=40.0):
    for f in bm.faces:
        f.smooth = True
    limit = math.radians(sharp_deg)
    for e in bm.edges:
        if e.is_manifold and e.calc_face_angle(0.0) > limit:
            e.smooth = False


def rounded_box(bm, center, size, mat_index, bevel, segments=3, matrix=None):
    before = set(bm.edges)
    m = mathutils.Matrix.Translation(center) @ (matrix if matrix is not None else mathutils.Matrix.Identity(4)) \
        @ mathutils.Matrix.Diagonal((*size, 1.0))
    ret = bmesh.ops.create_cube(bm, size=1.0, matrix=m)
    for v in ret['verts']:
        for f in v.link_faces:
            f.material_index = mat_index
    edges = [e for e in bm.edges if e not in before]
    bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=segments, profile=0.5, affect='EDGES', clamp_overlap=True)


def slice_plane(bm, co, no):
    geom = list(bm.verts) + list(bm.edges) + list(bm.faces)
    bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no)


# ============================================================
# 車
# ============================================================
def car_materials():
    paint = principled("CarPaint", PAINT, roughness=0.38, metallic=0.75, coat=1.0)  # 下地はメタリックの粒、上に鋭いクリアコート
    next(n for n in paint.node_tree.nodes if n.type == 'BSDF_PRINCIPLED').inputs['Coat Roughness'].default_value = 0.015
    glass = principled("CarGlass", (0.015, 0.017, 0.02), roughness=0.03, coat=0.0)
    under = principled("CarUnder", (0.012, 0.012, 0.012), roughness=0.8)
    tire = principled("Tire", (0.02, 0.02, 0.02), roughness=0.75)
    rim = principled("Rim", (0.55, 0.56, 0.58), roughness=0.25, metallic=1.0)
    lamp = principled("HeadLamp", (0.06, 0.065, 0.07), roughness=0.05, metallic=0.8, coat=1.0)
    drl = bpy.data.materials.new("DRL")  # デイライト(細い白い光の線)
    drl.use_nodes = True
    em = next(n for n in drl.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    em.inputs['Emission Color'].default_value = (1.0, 0.97, 0.92, 1)
    em.inputs['Emission Strength'].default_value = 6.0
    grille = principled("Grille", (0.01, 0.01, 0.01), roughness=0.35, coat=0.5)
    plate = principled("Plate", (0.75, 0.75, 0.72), roughness=0.35)
    return [paint, glass, under, tire, rim, lamp, grille, drl, plate]


def line_plane(p1, p2):
    """横から見た(y,z)の線分p1→p2を含み、x方向に伸びる平面。"""
    dy, dz = p2[0] - p1[0], p2[1] - p1[1]
    no = V((0.0, -dz, dy)).normalized()
    return V((0.0, p1[0], p1[1])), no


def pillar_line_y(p_low, p_high, z, inset):
    """窓の斜めの縁(ピラーの線)の、高さzでのy。p_low→p_highの線を水平にinsetだけ窓側へずらす。"""
    t = (z - p_low[1]) / (p_high[1] - p_low[1])
    return p_low[0] + (p_high[0] - p_low[0]) * t + inset


FRONT_Z_CUTS = (0.27, 0.30, 0.33, 0.40, 0.52, 0.53, 0.600, 0.613, 0.700, 0.705, 0.71)
def screen_half(z):
    """前後の窓の横幅の半分。ベルトラインでSCREEN_HALF、屋根でSCREEN_HALF_TOP(車体のすぼまりに合わせた台形)。"""
    t = min(max((z - BELT) / (ROOF_Z - BELT), 0.0), 1.0)
    return SCREEN_HALF + (SCREEN_HALF_TOP - SCREEN_HALF) * t


FRONT_X_CUTS = (0.28, 0.32, 0.48, 0.55, 0.68)


def front_face_material(c, n):
    """前の面(と角)のどこを何色に塗るか。c=面の中心、n=法線。材質: 4めっき 5ライトのレンズ 6黒い開口 7デイライト"""
    facing = (c.y > 4.35 and n.y > 0.25) or (c.y > 4.30 and abs(n.x) > 0.3 and n.y > 0.05)
    if not facing:
        return None
    ax, z = abs(c.x), c.z
    if 0.613 < z < 0.705 and ax > 0.32:
        return 5
    if 0.600 < z < 0.613 and ax > 0.32:
        return 7
    if ax < 0.28 and 0.53 < z < 0.70:  # グリル(ナンバーより上)
        return 6
    if ax < 0.30 and 0.52 < z < 0.71:
        return 4
    if ax < 0.48 and 0.27 < z < 0.33:  # 下の開口(ナンバーより下)
        return 6
    if 0.55 < ax < 0.68 and 0.30 < z < 0.40:
        return 6
    return None


SHOULDER_Z = 0.86  # 肩のキャラクターライン
DOOR_SEAMS = (3.38, 2.07, 1.02)  # 前のドアの前端、前後のドアの境、後ろのドアの後端(後端からの距離)
A_LOW, A_HIGH = (3.55, 0.99), (2.75, 1.43)  # フロントガラスの下端・上端(横から見た線)
C_LOW, C_HIGH = (0.60, 0.99), (1.35, 1.38)  # リアガラス


def in_side_window(y, z):
    if not (SIDE_WINDOW_BOTTOM < z < SIDE_WINDOW_TOP):
        return False
    front = pillar_line_y(A_LOW, A_HIGH, z, -SIDE_WINDOW_INSET_A)
    rear = pillar_line_y(C_LOW, C_HIGH, z, SIDE_WINDOW_INSET_C)
    return rear < y < front and not (B_PILLAR[0] < y < B_PILLAR[1])


def body_mesh(bm):
    """ボディ(材質0)と窓(材質1)。ローカル座標: 後端y=0→前端y=CAR_LENGTH、幅の中心x=0。"""
    half = CAR_WIDTH / 2
    left = [bm.verts.new((-half, y, z)) for y, z in CAR_PROFILE]
    face = bm.faces.new(left)
    ret = bmesh.ops.extrude_face_region(bm, geom=[face])
    right = [g for g in ret['geom'] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(CAR_WIDTH, 0, 0), verts=right)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bmesh.ops.bevel(bm, geom=list(bm.edges), offset=0.13, segments=5, profile=0.5, affect='EDGES', clamp_overlap=True)
    # すぼめるための切れ目(yは8cmごと、ベルトラインより上はzも4cmごと)
    for i in range(1, int(CAR_LENGTH / 0.08)):
        slice_plane(bm, (0, i * 0.08, 0), (0, 1, 0))
    z = BELT + 0.04
    while z < ROOF_Z:
        slice_plane(bm, (0, 0, z), (0, 0, 1))
        z += 0.04
    for v in bm.verts:
        y, zz = v.co.y, v.co.z
        end = min(y, CAR_LENGTH - y)
        if end < TAPER_ZONE:  # 前後の端を上から見て丸める
            t = 1.0 - end / TAPER_ZONE
            v.co.x *= 1.0 - (1.0 - NOSE_TAPER) * t * t
        if zz > BELT:  # ベルトラインより上を屋根へすぼめる
            t = min((zz - BELT) / (ROOF_Z - BELT), 1.0)
            v.co.x *= 1.0 - (1.0 - ROOF_TAPER) * t ** 0.9
    # 面をふくらませる(本物の車の面は縦にも横にも曲がっていて、映り込みがゆがむ)
    for i in range(-8, 9):
        slice_plane(bm, (i * 0.1, 0, 0), (1, 0, 0))
    for v in bm.verts:
        x, y, zz = v.co
        along = math.sin(math.pi * min(max(y / CAR_LENGTH, 0.0), 1.0))
        if zz < BELT + 0.02:  # 横の面: 肩(ベルトラインの少し下)が一番外へ出て、下へ行くほど内側へ入る(タックアンダー)
            if zz > SHOULDER_Z:  # 肩より上は窓へ向かってまっすぐ入る(肩に折れ目のハイライトが出る)
                bulge = 0.026 * (1.0 - (zz - SHOULDER_Z) / (BELT + 0.02 - SHOULDER_Z)) ** 0.8
            else:
                u = (SHOULDER_Z - zz) / (SHOULDER_Z - 0.24)
                bulge = 0.026 - 0.070 * u ** 1.5
            v.co.x *= 1.0 + bulge * (0.4 + 0.6 * along)
        if zz > 0.75 and abs(x) < half * 0.9:  # 上の面(屋根・ボンネット・トランク): 真ん中が少し盛り上がる
            w = x / (half * 0.9)
            v.co.z += 0.025 * (1.0 - w * w) * (0.5 + 0.5 * along)
    for y in DOOR_SEAMS:
        for d in (-0.004, 0.004):
            slice_plane(bm, (0, y + d, 0), (0, 1, 0))
    # 顔(ヘッドライト・グリル・開口)は、窓と同じくボディの面を塗り分けて作る(箱を貼ると浮いて見える)
    for zz in (BELT + 0.005, 0.33, SHOULDER_Z):
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    for zz in FRONT_Z_CUTS:
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    for xx in FRONT_X_CUTS:
        for sx in (-1, 1):
            slice_plane(bm, (sx * xx, 0, 0), (1, 0, 0))
    # 窓の縁で切る(横の窓の前後・上下・Bピラー、前後の窓の左右)
    for low, high, inset in ((A_LOW, A_HIGH, -SIDE_WINDOW_INSET_A), (C_LOW, C_HIGH, SIDE_WINDOW_INSET_C)):
        co, no = line_plane((low[0] + inset, low[1]), (high[0] + inset, high[1]))
        slice_plane(bm, co, no)
    for zz in (SIDE_WINDOW_BOTTOM, SIDE_WINDOW_TOP):
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    for y in B_PILLAR:
        slice_plane(bm, (0, y, 0), (0, 1, 0))
    for sx in (-1, 1):  # 前後の窓の左右の縁: 上ほど内側へ入る斜めの線(台形)
        dx, dz = SCREEN_HALF_TOP - SCREEN_HALF, ROOF_Z - BELT
        slice_plane(bm, (sx * SCREEN_HALF, 0, BELT), (dz, 0, -sx * dx))
    bm.normal_update()
    for f in bm.faces:
        c = f.calc_center_median()
        n = f.normal
        glass = False
        if abs(n.x) > 0.55:  # 横の面
            glass = in_side_window(c.y, c.z)
        elif n.z > -0.2 and abs(c.x) < screen_half(c.z):  # フロントガラス・リアガラス(斜めの面、上が狭い台形)
            w = c.x / (half * 0.9)
            crown = 0.024 * max(0.0, 1.0 - w * w)  # 屋根の盛り上がりの分だけ上の縁も上げる(縁の線を水平にそろえる)
            on_front = A_HIGH[0] + 0.05 < c.y < A_LOW[0] - 0.04 and BELT + 0.03 < c.z < 1.40 + crown  # 上に屋根の縁を残す
            on_rear = C_LOW[0] + 0.05 < c.y < C_HIGH[0] - 0.05 and BELT + 0.03 < c.z < 1.38
            glass = (on_front or on_rear) and n.z < 0.97
        f.material_index = 1 if glass else 0
        if abs(n.x) > 0.55 and 0.27 < c.z < BELT - 0.01 and any(abs(c.y - y) < 0.004 for y in DOOR_SEAMS):
            f.material_index = 6  # ドアの隙間
        if abs(n.x) > 0.55 and BELT + 0.005 < c.z < SIDE_WINDOW_BOTTOM and \
                pillar_line_y(C_LOW, C_HIGH, c.z, SIDE_WINDOW_INSET_C) < c.y < pillar_line_y(A_LOW, A_HIGH, c.z, -SIDE_WINDOW_INSET_A):
            f.material_index = 4  # 窓の下のめっきの帯
        if abs(n.x) > 0.4 and c.z < 0.33:
            f.material_index = 2  # 黒いサイドスカート(車を低く見せる)
        face_mat = front_face_material(c, n)
        if face_mat is not None:
            f.material_index = face_mat
        if c.z < 0.26 and n.z < -0.5:
            f.material_index = 2  # 床下


def wheel_mesh(bm, side, y):
    """タイヤ(材質3)とホイール(材質4)。sideは-1(左)か+1(右)。"""
    x_out = side * (CAR_WIDTH / 2 - 0.035)  # タイヤの外の面はボディの面とほぼそろう
    rot = mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
    center = V((x_out - side * WHEEL_WIDTH / 2, y, WHEEL_RADIUS))
    before = set(bm.faces)
    ret = bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=WHEEL_RADIUS, radius2=WHEEL_RADIUS,
                                depth=WHEEL_WIDTH, matrix=mathutils.Matrix.Translation(center) @ rot)
    new_edges = list({e for v in ret['verts'] for e in v.link_edges})
    rim_edges = [e for e in new_edges if all(abs((v.co - center).length - math.hypot(WHEEL_RADIUS, WHEEL_WIDTH / 2)) < 1e-3
                                              for v in e.verts) and abs(e.verts[0].co.x - e.verts[1].co.x) < 1e-4]
    bmesh.ops.bevel(bm, geom=rim_edges, offset=0.05, segments=4, profile=0.5, affect='EDGES', clamp_overlap=True)
    for f in bm.faces:
        if f not in before:
            f.material_index = 3
    # ホイール: 外側の面に、少し引っ込んだ円盤と5本のスポーク
    face_x = x_out + side * 0.004
    disc_c = V((face_x - side * 0.025, y, WHEEL_RADIUS))
    before = set(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=0.245, radius2=0.235, depth=0.03,
                          matrix=mathutils.Matrix.Translation(disc_c) @ rot)
    for f in bm.faces:
        if f not in before:
            f.material_index = 6  # 奥は暗く
    for k in range(10):
        a = 2 * math.pi * k / 10
        before = set(bm.faces)
        m = (mathutils.Matrix.Translation((face_x - side * 0.012, y, WHEEL_RADIUS))
             @ mathutils.Matrix.Rotation(a, 4, 'X') @ mathutils.Matrix.Translation((0, 0, 0.125))
             @ mathutils.Matrix.Diagonal((0.022, 0.030, 0.235, 1.0)))
        bmesh.ops.create_cube(bm, size=1.0, matrix=m)
        for f in bm.faces:
            if f not in before:
                f.material_index = 4
    before = set(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=48, radius1=0.255, radius2=0.255, depth=0.02,
                          matrix=mathutils.Matrix.Translation((face_x - side * 0.01, y, WHEEL_RADIUS)) @ rot)
    ring = [f for f in bm.faces if f not in before]
    # 円盤の真ん中を抜いてリムの輪にする
    caps = [f for f in ring if len(f.verts) > 4]
    bmesh.ops.inset_region(bm, faces=caps, thickness=0.03, use_even_offset=True)
    inner = [f for f in caps]
    bmesh.ops.delete(bm, geom=inner, context='FACES')
    for f in bm.faces:
        if f not in before:
            f.material_index = 4
    rounded_box(bm, (face_x - side * 0.012, y, WHEEL_RADIUS), (0.03, 0.07, 0.07), 4, 0.01)  # センターキャップ


def stick(bm, bvh, origin, direction, size, mat_index, bevel, sink=0.4, up=(0, 0, 1), segments=3):
    """ボディの表面に部品を貼る: originからdirectionへ光線を飛ばして当たった点に、厚み方向を面の法線にそろえた箱を置く。
    size=(横, 厚み, 縦)。sinkは厚みのうちボディに埋める割合。"""
    loc, normal, _, _ = bvh.ray_cast(V(origin), V(direction).normalized())
    if loc is None:
        raise RuntimeError(f"stick: no hit from {origin}")
    n = normal.normalized()
    z = V(up) - n * n.dot(V(up))
    z = z.normalized() if z.length > 1e-6 else V((0, 0, 1))
    x = n.cross(z)
    basis = mathutils.Matrix((x, n, z)).transposed().to_4x4()
    center = loc + n * size[1] * (0.5 - sink)
    rounded_box(bm, center, size, mat_index, bevel, segments, matrix=basis)


def details_mesh(bm, bvh):
    """ボディのメッシュ(bvh)の表面に貼る部品。座標はボディのローカル(後端y=0)。"""
    half = CAR_WIDTH / 2
    front = (0, -1, 0)  # 前から後ろへ向けて光線を飛ばす
    for side in (-1, 1):
        rounded_box(bm, (side * (half + 0.07), 3.40, 1.07), (0.20, 0.10, 0.12), 0, 0.03)  # ミラー
        rounded_box(bm, (side * (half - 0.03), 3.44, 1.04), (0.10, 0.05, 0.04), 0, 0.01)
        rounded_box(bm, (side * 0.62, 0.01, 0.86), (0.40, 0.04, 0.10), 6, 0.015)  # テールランプ
        for y in (2.70, 1.40):  # ドアの取っ手
            stick(bm, bvh, (side * 2.0, y, 0.90), (-side, 0, 0), (0.17, 0.03, 0.035), 6, 0.012, sink=0.3)
    stick(bm, bvh, (0, 6.0, 0.4275), front, (0.33, 0.02, 0.165), 8, 0.008, sink=0.1)  # ナンバープレート(文字なし。グリルと下の開口の間)
    stick(bm, bvh, (0, 6.0, 0.245), front, (1.20, 0.05, 0.03), 2, 0.010)  # 下のリップ


def build_car(col):
    mats = car_materials()
    bm = bmesh.new()
    body_mesh(bm)
    bvh = BVHTree.FromBMesh(bm)  # 部品をボディの表面に貼るため
    smooth_shading(bm, 35.0)
    body = mesh_object("CarBody", bm, mats, col)
    # フェンダーの切り欠き: 円柱で抜く(抜いた内側の面は床下の色)
    cutters = []
    for y in AXLES_Y:
        bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=ARCH_RADIUS, depth=CAR_WIDTH + 0.6,
                                            location=(0, y, WHEEL_RADIUS), rotation=(0, math.radians(90), 0))
        cutter = bpy.context.active_object
        cutter.data.materials.append(mats[2])
        cutters.append(cutter)
    bpy.context.view_layer.objects.active = body
    for cutter in cutters:
        mod = body.modifiers.new("Arch", 'BOOLEAN')
        mod.operation = 'DIFFERENCE'
        mod.solver = 'EXACT'
        mod.object = cutter
        if hasattr(mod, "material_mode"):
            mod.material_mode = 'TRANSFER'
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(cutter)
    # 切り欠きの奥(ホイールハウス): 暗い半円筒
    bm = bmesh.new()
    for y in AXLES_Y:
        for side in (-1, 1):
            wheel_mesh(bm, side, y)
    details_mesh(bm, bvh)
    smooth_shading(bm, 40.0)
    parts = mesh_object("CarParts", bm, mats, col)
    car = link(bpy.data.objects.new("Car", None), col)
    for o in (body, parts):
        o.parent = car
        o.location = (0, -CAR_LENGTH / 2, 0)
    # 接地の影: 曇天では影がぼんやり車の下に溜まる。下ほど濃い、ぼかした楕円の板
    shadow = bpy.data.materials.new("ContactShadow")
    shadow.use_nodes = True
    nt = shadow.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[1])
    black = nt.nodes.new('ShaderNodeBsdfDiffuse')
    black.inputs['Color'].default_value = (0, 0, 0, 1)
    nt.links.new(black.outputs[0], mix.inputs[2])
    coord = nt.nodes.new('ShaderNodeTexCoord')
    grad = nt.nodes.new('ShaderNodeTexGradient')
    grad.gradient_type = 'SPHERICAL'
    nt.links.new(coord.outputs['Object'], grad.inputs['Vector'])
    fall = nt.nodes.new('ShaderNodeMath')
    fall.operation = 'POWER'
    fall.inputs[1].default_value = 1.6
    nt.links.new(grad.outputs['Fac'], fall.inputs[0])
    gain = nt.nodes.new('ShaderNodeMath')
    gain.operation = 'MULTIPLY'
    gain.inputs[1].default_value = 0.85
    nt.links.new(fall.outputs[0], gain.inputs[0])
    nt.links.new(gain.outputs[0], mix.inputs['Fac'])
    nt.links.new(mix.outputs[0], out.inputs[0])
    shadow.surface_render_method = 'BLENDED'
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0)
    blob = mesh_object("CarShadow", bm, [shadow], col)
    blob.scale = (1.25, 2.9, 1.0)
    blob.location = (0, 0, 0.008)
    blob.parent = car
    # 車内: 暗い座席の塊(窓越しにうっすら見える)
    bm = bmesh.new()
    rounded_box(bm, (0, 2.3, 0.75), (1.4, 2.2, 0.55), 2, 0.1)
    inner = mesh_object("CarInterior", bm, mats, col)
    inner.parent = car
    inner.location = (0, -CAR_LENGTH / 2, 0)
    return car


# ============================================================
# 地面・駐車枠・山・木立
# ============================================================
def asphalt_material():
    mat = bpy.data.materials.new("Asphalt")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    coord = nt.nodes.new('ShaderNodeTexCoord')
    mapping = nt.nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (0.3, 0.3, 0.3)  # テクスチャ1枚 ≒ 3.3m
    nt.links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    def tex(path, non_color):
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = bpy.data.images.load(path, check_existing=True)
        if non_color:
            t.image.colorspace_settings.name = 'Non-Color'
        nt.links.new(mapping.outputs['Vector'], t.inputs['Vector'])
        return t

    diff, rough, nor = tex(ASPHALT['diff'], False), tex(ASPHALT['rough'], True), tex(ASPHALT['nor_gl'], True)
    # 濡れて暗くなる
    dark = nt.nodes.new('ShaderNodeMix')
    dark.data_type = 'RGBA'
    dark.blend_type = 'MULTIPLY'
    dark.inputs['Factor'].default_value = 1.0
    dark.inputs['B'].default_value = (0.30, 0.30, 0.32, 1)
    nt.links.new(diff.outputs['Color'], dark.inputs['A'])
    nt.links.new(dark.outputs['Result'], bsdf.inputs['Base Color'])
    # 水たまり: ノイズで場所を決め、そこだけほぼ鏡にする
    puddle_noise = nt.nodes.new('ShaderNodeTexNoise')
    puddle_noise.inputs['Scale'].default_value = 0.12
    puddle_noise.inputs['Detail'].default_value = 4.0
    nt.links.new(coord.outputs['Object'], puddle_noise.inputs['Vector'])
    puddle = nt.nodes.new('ShaderNodeMapRange')
    puddle.inputs['From Min'].default_value = 0.44
    puddle.inputs['From Max'].default_value = 0.52
    nt.links.new(puddle_noise.outputs['Fac'], puddle.inputs['Value'])
    wet_rough = nt.nodes.new('ShaderNodeMapRange')  # 濡れたアスファルト全体のつや
    wet_rough.inputs['To Min'].default_value = 0.04
    wet_rough.inputs['To Max'].default_value = 0.22
    nt.links.new(rough.outputs['Color'], wet_rough.inputs['Value'])
    r_mix = nt.nodes.new('ShaderNodeMix')
    r_mix.inputs['B'].default_value = 0.02
    nt.links.new(puddle.outputs['Result'], r_mix.inputs['Factor'])
    nt.links.new(wet_rough.outputs['Result'], r_mix.inputs['A'])
    nt.links.new(r_mix.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(nor.outputs['Color'], nmap.inputs['Color'])
    n_strength = nt.nodes.new('ShaderNodeMapRange')  # 水たまりでは凹凸が消える
    n_strength.inputs['To Min'].default_value = 0.35
    n_strength.inputs['To Max'].default_value = 0.0
    nt.links.new(puddle.outputs['Result'], n_strength.inputs['Value'])
    nt.links.new(n_strength.outputs['Result'], nmap.inputs['Strength'])
    nt.links.new(nmap.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def build_ground(col):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0,
                          matrix=mathutils.Matrix.Diagonal((LOT_HALF[0], LOT_HALF[1], 1, 1)))
    lot = mesh_object("Lot", bm, [asphalt_material()], col)
    # 白線(濡れて少しつやがある)。車の枠を中心に、横へ並ぶ枠
    paint = principled("LinePaint", (0.75, 0.75, 0.72), roughness=0.25)
    bm = bmesh.new()
    y0, y1 = -SLOT_LENGTH / 2 - 0.2, SLOT_LENGTH / 2 - 0.2
    for i in range(-6, 7):
        x = (i + 0.5) * SLOT_WIDTH
        rounded_box(bm, (x, (y0 + y1) / 2, 0.003), (LINE_WIDTH, y1 - y0, 0.006), 0, 0.002, 1)
    rounded_box(bm, (0, y0, 0.003), (13 * SLOT_WIDTH, LINE_WIDTH, 0.006), 0, 0.002, 1)
    # 向かいの列
    for i in range(-6, 7):
        x = (i + 0.5) * SLOT_WIDTH
        rounded_box(bm, (x, y0 - SLOT_LENGTH / 2 - 7.0, 0.003), (LINE_WIDTH, SLOT_LENGTH, 0.006), 0, 0.002, 1)
    mesh_object("Lines", bm, [paint], col)
    return lot


def terrain_height(x, y):
    """谷の形: 駐車場のまわりは平ら。谷の軸(カメラの視線の向き)から横へ離れるほど山が高くなり、奥でも上がる。"""
    ax = V((-0.47, -0.88)).normalized()
    p = V((x, y))
    s = p.dot(ax)  # 谷の奥へ向かう距離
    lat = abs(p.x * ax.y - p.y * ax.x)  # 谷の軸からの横の距離
    flat = 120.0
    width = 260.0 + 0.10 * max(s, 0)  # 奥ほど谷が広がる(遠近で狭く見えすぎないように)
    side = max(0.0, (lat - width) / 700.0)
    end = max(0.0, (s - 2600.0) / 900.0)
    base = 520.0 * (min(side, 1.6) ** 1.2) + 600.0 * min(end, 1.0) ** 1.3
    n = noise.fractal(V((x / 1400.0, y / 1400.0, 0.3)), 1.0, 2.0, 4)  # なだらかな稜線(木に覆われた山)
    h = base * (0.80 + 0.30 * n)
    near = math.hypot(x, y)
    return 0.0 if near < flat else h * min(1.0, (near - flat) / 200.0) - 0.05


def build_terrain(col):
    size, n = 9000.0, 320
    bm = bmesh.new()
    verts = []
    for j in range(n + 1):
        row = []
        for i in range(n + 1):
            x = -size / 2 + size * i / n
            y = -size / 2 + size * j / n
            # 手前は細かく使いたいので、中心へ寄せる(二乗の配置)
            fx, fy = x / (size / 2), y / (size / 2)
            x = math.copysign(fx * fx, fx) * size / 2
            y = math.copysign(fy * fy, fy) * size / 2
            row.append(bm.verts.new((x, y, terrain_height(x, y))))
        verts.append(row)
    for j in range(n):
        for i in range(n):
            bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
    for f in bm.faces:
        f.smooth = True
    mat = bpy.data.materials.new("Forest")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(nd for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Roughness'].default_value = 0.9
    coord = nt.nodes.new('ShaderNodeTexCoord')
    tex = nt.nodes.new('ShaderNodeTexNoise')
    tex.inputs['Scale'].default_value = 0.02
    tex.inputs['Detail'].default_value = 10.0
    nt.links.new(coord.outputs['Object'], tex.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = (*FOREST, 1)
    ramp.color_ramp.elements[1].color = (FOREST[0] * 2.2, FOREST[1] * 2.0, FOREST[2] * 1.6, 1)
    nt.links.new(tex.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], bsdf.inputs['Base Color'])
    # 木の凹凸(細かいバンプ)
    bump_tex = nt.nodes.new('ShaderNodeTexVoronoi')
    bump_tex.inputs['Scale'].default_value = 0.25
    nt.links.new(coord.outputs['Object'], bump_tex.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.6
    nt.links.new(bump_tex.outputs['Distance'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    mesh_object("Terrain", bm, [mat], col)
    # 駐車場の外の平らなところ(草)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=1.0, matrix=mathutils.Matrix.Diagonal((400, 400, 1, 1)))
    for v in bm.verts:
        v.co.z = -0.02
    mesh_object("Grass", bm, [principled("Grass", GRASS, roughness=0.85)], col)


def build_trees(col, rng):
    """駐車場の外の針葉樹。円錐を2段重ねた形のリンク複製。"""
    mat = principled("Conifer", (0.012, 0.024, 0.014), roughness=0.9)
    bm = bmesh.new()
    for z0, r, h in ((0.15, 0.45, 0.55), (0.45, 0.33, 0.45), (0.70, 0.2, 0.30)):
        bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=r, radius2=0.0, depth=h,
                              matrix=mathutils.Matrix.Translation((0, 0, z0 + h / 2)))
    bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.03, radius2=0.03, depth=0.2,
                          matrix=mathutils.Matrix.Translation((0, 0, 0.1)))
    me = bpy.data.meshes.new("Conifer")
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    count = 0
    for _ in range(4000):
        r = rng.uniform(110.0, 700.0)
        a = rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(a), r * math.sin(a)
        if abs(x) < LOT_HALF[0] + 3 and abs(y) < LOT_HALF[1] + 3:
            continue
        if terrain_height(x, y) > 1.0:
            continue
        # 谷の奥(視線の先)は開けておく
        ang = math.degrees(math.atan2(y, x))
        if -125 < ang < -100 and r < 300:
            continue
        o = link(bpy.data.objects.new(f"Tree{count:04d}", me), col)
        s = rng.uniform(12.0, 22.0)
        o.scale = (s * rng.uniform(0.8, 1.1), s * rng.uniform(0.8, 1.1), s)
        o.location = (x, y, 0)
        o.rotation_euler = (0, 0, rng.uniform(0, 6.3))
        count += 1
        if count >= 1500:
            break
    print("[Stage1] trees:", count)


def build_rain(col, rng):
    """雨の筋: カメラの前の空間に、細長い板を散らす。遠くでも1画素ほどの幅は残す。少し風で傾ける。"""
    mat = bpy.data.materials.new("Rain")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    mix = nt.nodes.new('ShaderNodeMixShader')
    mix.inputs['Fac'].default_value = RAIN_OPACITY
    nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[1])
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (0.75, 0.78, 0.82, 1)
    em.inputs['Strength'].default_value = RAIN_BRIGHTNESS
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    mat.surface_render_method = 'BLENDED'
    cam = V(CAM_LOC)
    fwd = (V(CAM_TARGET) - cam).normalized()
    right = fwd.cross(V((0, 0, 1))).normalized()
    up = right.cross(fwd)
    tan_v = math.tan(math.atan(18.0 / CAM_LENS))
    tan_h = tan_v * 1080 / 1920
    px = 2 * tan_v / 1920  # 1mあたりの画素の大きさ(距離をかける)
    wind = mathutils.Matrix.Rotation(math.radians(8), 3, fwd)
    bm = bmesh.new()
    for _ in range(RAIN_COUNT):
        d = 4.0 + 50.0 * rng.random() ** 1.5  # 手前に寄せすぎると筋が太く長くなる
        sx, sy = rng.uniform(-1.1, 1.1) * tan_h * d, rng.uniform(-1.1, 1.1) * tan_v * d
        c = cam + fwd * d + right * sx + up * sy
        if c.z < 0.02:
            continue
        length = rng.uniform(0.25, 0.5)
        width = max(0.002, 0.9 * px * d)
        axis = wind @ V((0, 0, 1))
        side_dir = (cam - c).normalized().cross(axis).normalized()
        a, b = c - axis * length / 2, c + axis * length / 2
        vs = [bm.verts.new(p) for p in (a - side_dir * width / 2, a + side_dir * width / 2,
                                         b + side_dir * width / 2, b - side_dir * width / 2)]
        bm.faces.new(vs)
    obj = mesh_object("Rain", bm, [mat], col)
    obj.visible_shadow = False


def build_camera(col):
    cam_data = bpy.data.cameras.new("Camera")
    cam_data.lens = CAM_LENS
    cam_data.sensor_fit = 'VERTICAL'
    cam_data.sensor_height = 36.0
    cam_data.clip_end = 20000.0
    cam_data.dof.use_dof = True
    cam_data.dof.focus_distance = (V(CAM_LOC) - V((0, 0, 0.8))).length
    cam_data.dof.aperture_fstop = 8.0
    cam = link(bpy.data.objects.new("Camera", cam_data), col)
    cam.location = CAM_LOC
    d = (V(CAM_TARGET) - V(CAM_LOC)).normalized()
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    bpy.context.scene.camera = cam


def main():
    reset_scene()
    rng = random.Random(SEED)
    build_ground(collection("Ground"))
    build_terrain(collection("Terrain"))
    build_trees(collection("Trees"), rng)
    build_car(collection("Car"))
    build_camera(collection("Camera"))
    build_rain(collection("Rain"), rng)
    # 映り込み用のプローブ: 無いと車体の下半分にも空が映って白く飛ぶ(地面の暗さを拾わせる)
    probe = bpy.data.lightprobes.new("CarReflection", 'SPHERE')
    probe.influence_distance = 12.0
    link(bpy.data.objects.new("CarReflection", probe), collection("Probes")).location = (0, 0, 1.0)
    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print("[Stage1] saved:", WIP_BLEND)


if __name__ == "__main__":
    main()
