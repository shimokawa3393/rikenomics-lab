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
    CAR_WIDTH, GRASS_TEX, LIGHTNING_TOP, LINE_WIDTH, STRIKE_POINT, SOIL_TEX, LOT_HALF, NOSE_TAPER, ROOF_TAPER, SCREEN_HALF, SIDE_WINDOW_BOTTOM,
    SIDE_WINDOW_INSET_A, SIDE_WINDOW_INSET_C, SIDE_WINDOW_TOP, WINDOW_KICK, SLOT_LENGTH, SLOT_WIDTH, TAPER_ZONE,
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
    rim = principled("Rim", (0.20, 0.205, 0.215), roughness=0.3, metallic=1.0)  # 暗いガンメタ(参考画像)
    lamp = principled("HeadLamp", (0.06, 0.065, 0.07), roughness=0.05, metallic=0.8, coat=1.0)
    drl = bpy.data.materials.new("DRL")  # デイライト(細い白い光の線)
    drl.use_nodes = True
    em = next(n for n in drl.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    em.inputs['Emission Color'].default_value = (1.0, 0.97, 0.92, 1)
    em.inputs['Emission Strength'].default_value = 6.0
    grille = principled("Grille", (0.01, 0.01, 0.01), roughness=0.35, coat=0.5)
    plate = principled("Plate", (0.75, 0.75, 0.72), roughness=0.35)
    tail = principled("TailLamp", (0.20, 0.006, 0.006), roughness=0.05, coat=1.0)  # 点いていない赤いレンズ(暗い中でも赤と分かる程度に光らせる)
    bsdf = next(n for n in tail.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Emission Color'].default_value = (1.0, 0.03, 0.02, 1)
    bsdf.inputs['Emission Strength'].default_value = 0.06
    return [paint, glass, under, tire, rim, lamp, grille, drl, plate, tail]


def line_plane(p1, p2):
    """横から見た(y,z)の線分p1→p2を含み、x方向に伸びる平面。"""
    dy, dz = p2[0] - p1[0], p2[1] - p1[1]
    no = V((0.0, -dz, dy)).normalized()
    return V((0.0, p1[0], p1[1])), no


def pillar_line_y(p_low, p_high, z, inset):
    """窓の斜めの縁(ピラーの線)の、高さzでのy。p_low→p_highの線を水平にinsetだけ窓側へずらす。"""
    t = (z - p_low[1]) / (p_high[1] - p_low[1])
    return p_low[0] + (p_high[0] - p_low[0]) * t + inset


GRILLE_SLATS = (0.585, 0.630)  # グリルの横の桟(めっき)。真っ黒な四角だと箱に見える
FRONT_Z_CUTS = (0.27, 0.28, 0.30, 0.36, 0.40, 0.680, 0.693) + tuple(z + d for z in GRILLE_SLATS for d in (0.0, 0.008))
FRONT_X_CUTS = (0.38, 0.42, 0.50, 0.55, 0.72)
LAMP_INNER = 0.40  # ヘッドライトの内側の端(|x|)
LAMP_Z0, LAMP_SLOPE = 0.645, 0.07  # ヘッドライトの下の縁: 内側でz=LAMP_Z0、外へ行くほどゆるく上がる(急だとシャープすぎる)
LAMP_HEIGHT, DRL_HEIGHT = 0.085, 0.012  # ライトに縦の厚みを持たせる(細い線だけだと鋭く見える)
GRILLE_TOP, GRILLE_BOTTOM = 0.68, 0.40
GRILLE_HALF_TOP, GRILLE_HALF_BOTTOM = 0.44, 0.41  # グリルはほぼ長方形(下をすぼめると鋭く見える)


def screen_half(z):
    """前後の窓の横幅の半分。ベルトラインでSCREEN_HALF、屋根でSCREEN_HALF_TOP(車体のすぼまりに合わせた台形)。"""
    t = min(max((z - BELT) / (ROOF_Z - BELT), 0.0), 1.0)
    return SCREEN_HALF + (SCREEN_HALF_TOP - SCREEN_HALF) * t


def lamp_low(ax):
    return LAMP_Z0 + LAMP_SLOPE * (ax - LAMP_INNER)


def front_slices(bm):
    """顔の斜めの線(吊り目のライト、台形のグリル)で切る。"""
    for sx in (-1, 1):
        for dz in (0.0, DRL_HEIGHT, LAMP_HEIGHT):  # ライトの下の縁・光の線の上・ライトの上の縁
            slice_plane(bm, (sx * LAMP_INNER, 0, LAMP_Z0 + dz), (-sx * LAMP_SLOPE, 0, 1))
        dx, dz = GRILLE_HALF_TOP - GRILLE_HALF_BOTTOM, GRILLE_TOP - GRILLE_BOTTOM
        slice_plane(bm, (sx * GRILLE_HALF_BOTTOM, 0, GRILLE_BOTTOM), (dz, 0, -sx * dx))


def front_face_material(c, n):
    """前の面(と角)のどこを何色に塗るか。c=面の中心、n=法線。材質: 4めっき 5ライトのレンズ 6黒い開口 7デイライト"""
    facing = (c.y > 4.30 and n.y > 0.2) or (c.y > 4.15 and abs(n.x) > 0.3 and n.y > 0.02)
    if not facing:
        return None
    ax, z = abs(c.x), c.z
    low = lamp_low(min(ax, 0.95))
    if ax > LAMP_INNER and low < z < low + LAMP_HEIGHT:
        return 7 if z < low + DRL_HEIGHT else 5
    if ax < LAMP_INNER + 0.02 and 0.680 < z < 0.693:  # グリルの上のめっきの帯(左右のライトをつなぐ)
        return 4
    half = GRILLE_HALF_BOTTOM + (GRILLE_HALF_TOP - GRILLE_HALF_BOTTOM) * (z - GRILLE_BOTTOM) / (GRILLE_TOP - GRILLE_BOTTOM)
    if GRILLE_BOTTOM < z < GRILLE_TOP and ax < half:
        return 4 if any(zs < z < zs + 0.008 for zs in GRILLE_SLATS) and ax < half - 0.03 else 6
    if ax < 0.50 and z < 0.30:  # 下の開口
        return 6
    if 0.50 < ax < 0.72 and 0.28 < z < 0.36:  # 左右の細い開口
        return 6
    return None


REAR_Z_CUTS = (0.33, 0.36, 0.40, 0.740, 0.746, 0.80, 0.825, 0.84, 0.88)
REAR_X_CUTS = (0.36, 0.55, 0.620, 0.626, 0.70)


def rear_face_material(c, n):
    """後ろの面(と角)の塗り分け。材質: 2黒い下まわり 6隙間 9テールランプ"""
    ax, z = abs(c.x), c.z
    facing = (c.y < 0.30 and n.y < -0.25) or (c.y < 0.40 and abs(n.x) > 0.3 and n.y < -0.05)
    wrap = c.y < 0.24 and abs(n.x) > 0.3  # テールランプは横の面へ少し回り込む
    if 0.80 < z < 0.88 and ((facing and ax > 0.36) or wrap):
        return 9
    if not facing:
        if n.z > 0.5 and c.y < C_LOW[0] + 0.02 and 0.620 < ax < 0.626:  # トランクの蓋の横の隙間(上の面)
            return 6
        return None
    if 0.825 < z < 0.84:  # 左右のランプをつなぐ細い光の帯
        return 9
    if 0.620 < ax < 0.626 and z > 0.740:  # トランクの蓋の横の隙間
        return 6
    if 0.740 < z < 0.746 and ax < 0.626:  # トランクの蓋の下の隙間
        return 6
    if 0.55 < ax < 0.70 and 0.36 < z < 0.40:  # 反射板
        return 9
    if z < 0.33:  # 黒い下まわり(サイドスカートとつなげる)
        return 2
    return None


SHOULDER_Z = 0.90  # 肩のキャラクターライン
DOOR_SEAMS = (3.30, 2.03, 0.98)  # 前のドアの前端、前後のドアの境、後ろのドアの後端(後端からの距離)
A_LOW, A_HIGH = (3.45, 1.04), (2.55, 1.45)  # フロントガラスの下端・上端(横から見た線)
C_LOW, C_HIGH = (0.45, 1.05), (1.45, 1.41)  # リアガラス


def window_bottom(y):
    """横の窓の下の縁の高さ。後ろで跳ね上がる。"""
    y0, rise = WINDOW_KICK
    return SIDE_WINDOW_BOTTOM + rise * max(0.0, y0 - y) / (y0 - C_LOW[0])


def in_side_window(y, z):
    if not (window_bottom(y) < z < SIDE_WINDOW_TOP):
        return False
    front = pillar_line_y(A_LOW, A_HIGH, z, -SIDE_WINDOW_INSET_A)
    rear = pillar_line_y(C_LOW, C_HIGH, z, SIDE_WINDOW_INSET_C)
    return rear < y < front and not (B_PILLAR[0] < y < B_PILLAR[1])


def catmull_clark(bm, levels):
    """bmeshをサブディビジョン(Catmull-Clark)でなめらかにする。塗り分けの切れ目を入れる前に使う(後だと境目が波打つ)。"""
    me = bpy.data.meshes.new("_round")
    bm.to_mesh(me)
    obj = bpy.data.objects.new("_round", me)
    bpy.context.scene.collection.objects.link(obj)
    sub = obj.modifiers.new("Round", 'SUBSURF')
    sub.levels = sub.render_levels = levels
    sub.boundary_smooth = 'PRESERVE_CORNERS'
    ev = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bm.clear()
    bm.from_mesh(ev.to_mesh())
    ev.to_mesh_clear()
    bpy.data.objects.remove(obj)
    bpy.data.meshes.remove(me)


LENGTH_CROWNS = (  # (y0, y1, 盛り上がり[m]): ボンネット・屋根・トランクの前後方向のふくらみ
    (A_LOW[0], CAR_LENGTH - 0.15, 0.025),
    (C_HIGH[0], A_HIGH[0], 0.012),
    (0.10, C_LOW[0], 0.008),
)
FACE_DEPTH = 0.30  # 前後の端からこの範囲を、真ん中が張り出すように曲げる


CHAR_LINE = (0.80, 0.74)  # キャラクターラインの高さ(後端, 前端)。後ろへ向かって上がる
HOOD_LINE_X = 0.42  # ボンネットの盛り上がった線の位置(|x|)


def char_line_z(y):
    return CHAR_LINE[0] + (CHAR_LINE[1] - CHAR_LINE[0]) * y / CAR_LENGTH


def local_relief(bm):
    """局所的な凹凸: キャラクターライン、フェンダーのふくらみ、ドアの下のへこみ、ボンネットの線、トランクの跳ね上がり。"""
    half = CAR_WIDTH / 2
    # 線をきれいに出すための切れ目(キャラクターラインに沿った斜めの線、ボンネットの線の両側)
    for d in (-0.035, -0.012, 0.0, 0.012, 0.035):
        co, no = line_plane((0.0, CHAR_LINE[0] + d), (CAR_LENGTH, CHAR_LINE[1] + d))
        slice_plane(bm, co, no)
    for sx in (-1, 1):
        for d in (-0.05, -0.015, 0.0, 0.015, 0.05):
            slice_plane(bm, (sx * (HOOD_LINE_X + d), 0, 0), (1, 0, 0))
    for v in bm.verts:
        x, y, z = v.co
        sx = 1.0 if x > 0 else -1.0
        ax = abs(x)
        # 横の面だけにかける。範囲の境目でいきなり0にするとしわが寄るので、なめらかに弱める
        w_side = min(max((ax - half * 0.70) / (half * 0.15), 0.0), 1.0)
        w_side *= min(max((BELT - 0.02 - z) / 0.12, 0.0), 1.0) * min(max((z - 0.24) / 0.06, 0.0), 1.0)
        if w_side > 0:
            out = 0.0
            # キャラクターライン: 幅7cmの山形の稜線(映り込みに細いハイライトの線が出る)
            d = abs(z - char_line_z(y))
            fade = min(1.0, min(y - 0.3, CAR_LENGTH - 0.3 - y) / 0.4) if 0.3 < y < CAR_LENGTH - 0.3 else 0.0
            out += 0.006 * max(0.0, 1.0 - d / 0.035) * max(fade, 0.0)
            # フェンダーのふくらみ: タイヤのアーチのまわりを外へ
            for ay in AXLES_Y:
                r = math.hypot(y - ay, z - WHEEL_RADIUS)
                # アーチの内側(あとで円柱で抜く所)も同じだけ動かす。動かさないと、抜いた縁で面がねじれてしわになる
                t = min(max((r - ARCH_RADIUS) / 0.28, 0.0), 1.0)
                out += 0.014 * 0.5 * (1.0 + math.cos(math.pi * t))
            # ドアの下のへこみ: アーチとアーチのあいだ、ラインの下をゆるくへこませる
            y0, y1 = AXLES_Y[0] + ARCH_RADIUS + 0.10, AXLES_Y[1] - ARCH_RADIUS - 0.10
            top = char_line_z(y) - 0.06
            if y0 < y < y1 and 0.36 < z < top:
                u = (z - 0.36) / (top - 0.36)
                along = math.sin(math.pi * (y - y0) / (y1 - y0)) ** 0.5
                out -= 0.007 * math.sin(math.pi * u) * along
            v.co.x += sx * out * w_side
        # ボンネットの2本の線: 幅10cmの盛り上がり。フロントガラスの根元から鼻先へ消えていく
        if z > 0.80 and A_LOW[0] + 0.05 < y < CAR_LENGTH - 0.10:
            d = abs(ax - HOOD_LINE_X)
            t = (y - A_LOW[0]) / (CAR_LENGTH - A_LOW[0])
            v.co.z += 0.007 * max(0.0, 1.0 - d / 0.05) * (1.0 - 0.6 * t)
        # トランクの後ろの端の小さな跳ね上がり(ダックテール)
        if z > 0.90 and y < 0.30:
            v.co.z += 0.012 * max(0.0, 1.0 - y / 0.30) * (1.0 - (ax / half) ** 4)


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
    # 細かい角を丸める: 面取りの段差と、短い線分で面取りしきれなかった折れ目(鼻先・トランクの角)をなめらかに。
    # 平らな横の面(大きな多角形)は外しておき、後で張り直す(丸めると中心から放射状の細い面になり、映り込みがまだらになる)
    bm.normal_update()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if abs(f.normal.x) > 0.999], context='FACES_ONLY')
    catmull_clark(bm, 2)
    bmesh.ops.holes_fill(bm, edges=[e for e in bm.edges if e.is_boundary], sides=0)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    # すぼめる・曲げるための切れ目(yは8cmごと、zは4cmごと。切れ目が少ないと横の面が平らな板のまま残る)
    for i in range(1, int(CAR_LENGTH / 0.08)):
        slice_plane(bm, (0, i * 0.08, 0), (0, 1, 0))
    z = 0.28
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
        if zz > 0.80 and abs(x) < half * 0.9:  # 上の面(屋根・ボンネット・トランク): 真ん中が少し盛り上がる
            w = x / (half * 0.9)
            v.co.z += 0.025 * (1.0 - w * w) * (0.5 + 0.5 * along)
            for y0, y1, amp in LENGTH_CROWNS:  # 前後方向にも盛り上げる(上の面がまっすぐな板に見えないように)
                if y0 < y < y1:
                    v.co.z += amp * math.sin(math.pi * (y - y0) / (y1 - y0)) * (1.0 - 0.5 * w * w)
        v.co.x *= 1.0 + 0.018 * along  # 上から見て真ん中が少しふくらむ弓なり(ドアの面が前後にも曲がる)
        w = min(abs(x) / half, 1.0)
        front = (y - (CAR_LENGTH - FACE_DEPTH)) / FACE_DEPTH
        if front > 0:  # 前の面の真ん中を前へ張り出す
            v.co.y += 0.035 * (1.0 - w * w) * front
        rear = (FACE_DEPTH - y) / FACE_DEPTH
        if rear > 0:  # 後ろの面も同じく
            v.co.y -= 0.025 * (1.0 - w * w) * rear
    local_relief(bm)
    for y in DOOR_SEAMS:
        for d in (-0.004, 0.004):
            slice_plane(bm, (0, y + d, 0), (0, 1, 0))
    # 顔(ヘッドライト・グリル・開口)は、窓と同じくボディの面を塗り分けて作る(箱を貼ると浮いて見える)
    for zz in (BELT + 0.005, 0.33, SHOULDER_Z):
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    for zz in FRONT_Z_CUTS + REAR_Z_CUTS:
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    for xx in FRONT_X_CUTS + REAR_X_CUTS:
        for sx in (-1, 1):
            slice_plane(bm, (sx * xx, 0, 0), (1, 0, 0))
    # 窓の縁で切る(横の窓の前後・上下・Bピラー、前後の窓の左右)
    for low, high, inset in ((A_LOW, A_HIGH, -SIDE_WINDOW_INSET_A), (C_LOW, C_HIGH, SIDE_WINDOW_INSET_C)):
        co, no = line_plane((low[0] + inset, low[1]), (high[0] + inset, high[1]))
        slice_plane(bm, co, no)
    for zz in (SIDE_WINDOW_BOTTOM, SIDE_WINDOW_TOP):
        slice_plane(bm, (0, 0, zz), (0, 0, 1))
    co, no = line_plane((WINDOW_KICK[0], SIDE_WINDOW_BOTTOM), (C_LOW[0], SIDE_WINDOW_BOTTOM + WINDOW_KICK[1]))
    slice_plane(bm, co, no)
    front_slices(bm)
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
            on_front = A_HIGH[0] + 0.05 < c.y < A_LOW[0] - 0.04 and BELT + 0.03 < c.z < A_HIGH[1] - 0.04 + crown  # 上に屋根の縁を残す
            on_rear = C_LOW[0] + 0.05 < c.y < C_HIGH[0] - 0.05 and C_LOW[1] + 0.03 < c.z < C_HIGH[1] - 0.02
            glass = (on_front or on_rear) and n.z < 0.97
        f.material_index = 1 if glass else 0
        if abs(n.x) > 0.55 and 0.27 < c.z < BELT - 0.01 and any(abs(c.y - y) < 0.004 for y in DOOR_SEAMS):
            f.material_index = 6  # ドアの隙間
        if abs(n.x) > 0.55 and B_PILLAR[0] < c.y < B_PILLAR[1] and window_bottom(c.y) < c.z < SIDE_WINDOW_TOP:
            f.material_index = 6  # 黒いBピラー(窓が1枚につながって見え、屋根が浮いて見える)。下は金属
        if abs(n.x) > 0.4 and c.z < 0.33:
            f.material_index = 2  # 黒いサイドスカート(車を低く見せる)
        if c.y > 4.35 and n.y > 0.25 and c.z < 0.27:
            f.material_index = 2  # 前の下の黒い縁(リップ)。箱で貼ると角ではみ出す
        face_mat = front_face_material(c, n)
        if face_mat is None:
            face_mat = rear_face_material(c, n)
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
    for k in range(10):  # 5本のダブルスポーク
        a = 2 * math.pi * (k // 2) / 5 + (1 if k % 2 else -1) * math.radians(7)
        before = set(bm.faces)
        m = (mathutils.Matrix.Translation((face_x - side * 0.012, y, WHEEL_RADIUS))
             @ mathutils.Matrix.Rotation(a, 4, 'X') @ mathutils.Matrix.Translation((0, 0, 0.125))
             @ mathutils.Matrix.Diagonal((0.026, 0.026, 0.235, 1.0)))
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
    before = set(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.04, radius2=0.035, depth=0.02,  # センターキャップ
                          matrix=mathutils.Matrix.Translation((face_x - side * 0.008, y, WHEEL_RADIUS)) @ rot)
    for f in bm.faces:
        if f not in before:
            f.material_index = 4


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
        rounded_box(bm, (side * (half + 0.03), 3.18, 1.14), (0.19, 0.09, 0.11), 0, 0.04, 4)  # ミラー(ドアに付く、丸い)
        rounded_box(bm, (side * (half - 0.04), 3.20, 1.09), (0.08, 0.06, 0.03), 6, 0.01)  # ミラーの付け根(黒)
        for y in (2.62, 1.36):  # ドアの取っ手
            stick(bm, bvh, (side * 2.0, y, 0.94), (-side, 0, 0), (0.17, 0.03, 0.035), 6, 0.012, sink=0.3)
    stick(bm, bvh, (0, 6.0, 0.47), front, (0.33, 0.02, 0.165), 8, 0.008, sink=0.1)  # ナンバープレート(文字なし。グリルの下の方に重ねる)
    stick(bm, bvh, (0, -2.0, 0.57), (0, 1, 0), (0.33, 0.02, 0.165), 8, 0.008, sink=0.1)  # 後ろのナンバープレート


def build_car(col):
    mats = car_materials()
    bm = bmesh.new()
    body_mesh(bm)
    smooth_shading(bm, 35.0)
    body = mesh_object("CarBody", bm, mats, col)
    bm = bmesh.new()
    bm.from_mesh(body.data)
    bvh = BVHTree.FromBMesh(bm)  # 部品をボディの表面に貼るため
    bm.free()
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
    wet_rough.inputs['To Min'].default_value = 0.03  # EEVEEは粗いと映り込みが消える(Cyclesより低めに)
    wet_rough.inputs['To Max'].default_value = 0.10
    nt.links.new(rough.outputs['Color'], wet_rough.inputs['Value'])
    r_mix = nt.nodes.new('ShaderNodeMix')
    r_mix.inputs['B'].default_value = 0.02
    nt.links.new(puddle.outputs['Result'], r_mix.inputs['Factor'])
    nt.links.new(wet_rough.outputs['Result'], r_mix.inputs['A'])
    nt.links.new(r_mix.outputs['Result'], bsdf.inputs['Roughness'])
    nmap = nt.nodes.new('ShaderNodeNormalMap')
    nt.links.new(nor.outputs['Color'], nmap.inputs['Color'])
    n_strength = nt.nodes.new('ShaderNodeMapRange')  # 水たまりでは凹凸が消える
    n_strength.inputs['To Min'].default_value = 0.12  # 凹凸が強いとEEVEEでは路面の映り込みが崩れて消える
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


GROUND_TINT = (0.26, 0.40, 0.25, 1.0)  # 草地・土の写真にかける色(濡れて暗く、曇天で彩度が落ちる)
ROLL_AMP = 9.0  # 谷底の起伏の大きさ[m]


def rolling_height(x, y):
    """谷底のゆるい起伏: 駐車場のすぐ外は平らで、離れるほど数mの丘やくぼみが出る。"""
    d = max(abs(x) - LOT_HALF[0], abs(y) - LOT_HALF[1], 0.0)  # 駐車場の縁からの距離
    t = min(max((d - 8.0) / 180.0, 0.0), 1.0)
    amp = ROLL_AMP * t * t * (3 - 2 * t)
    n = noise.fractal(V((x / 140.0, y / 140.0, 2.7)), 1.0, 2.0, 3)
    return amp * (0.6 + n)


def terrain_height(x, y):
    return mountain_height(x, y) + rolling_height(x, y) - 0.03  # 駐車場の面(z=0)と重ならないよう少し下げる


def mountain_height(x, y):
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


def forest_material():
    """木に覆われた山肌: 遠目に見える樹冠の粒(明るい梢と暗いすき間)、大きな色むら、急な所は岩っぽく。"""
    mat = bpy.data.materials.new("Forest")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(nd for nd in nt.nodes if nd.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Roughness'].default_value = 0.9
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    # 樹冠の粒(1本 ≒ 6m)
    crown = nt.nodes.new('ShaderNodeTexVoronoi')
    crown.feature = 'DISTANCE_TO_EDGE'
    crown.inputs['Scale'].default_value = 1.0 / 14.0  # 遠目に見える木の塊(数本ずつ)
    nt.links.new(geo.outputs['Position'], crown.inputs['Vector'])
    gap = nt.nodes.new('ShaderNodeMapRange')  # 縁(すき間)ほど暗い
    gap.inputs['From Max'].default_value = 0.30
    gap.inputs['To Min'].default_value = 0.25
    gap.inputs['To Max'].default_value = 1.0
    nt.links.new(crown.outputs['Distance'], gap.inputs['Value'])
    # 大きな色むら(針葉樹の濃い緑と、広葉樹の明るい緑のまだら)
    patch = nt.nodes.new('ShaderNodeTexNoise')
    patch.inputs['Scale'].default_value = 1.0 / 120.0
    patch.inputs['Detail'].default_value = 6.0
    nt.links.new(geo.outputs['Position'], patch.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (FOREST[0], FOREST[1], FOREST[2], 1)
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[1].color = (FOREST[0] * 2.6, FOREST[1] * 2.1, FOREST[2] * 1.4, 1)
    nt.links.new(patch.outputs['Fac'], ramp.inputs['Fac'])
    col = nt.nodes.new('ShaderNodeMix')
    col.data_type = 'RGBA'
    col.blend_type = 'MULTIPLY'
    col.inputs['Factor'].default_value = 1.0
    nt.links.new(ramp.outputs['Color'], col.inputs['A'])
    nt.links.new(gap.outputs['Result'], col.inputs['B'])
    # 急な斜面は木がまばらで岩が見える
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Normal'], sep.inputs['Vector'])
    steep = nt.nodes.new('ShaderNodeMapRange')
    steep.inputs['From Min'].default_value = 0.80
    steep.inputs['From Max'].default_value = 0.62
    nt.links.new(sep.outputs['Z'], steep.inputs['Value'])
    rock = nt.nodes.new('ShaderNodeMix')
    rock.data_type = 'RGBA'
    rock.inputs['B'].default_value = (0.045, 0.045, 0.042, 1)
    nt.links.new(steep.outputs['Result'], rock.inputs['Factor'])
    nt.links.new(col.outputs['Result'], rock.inputs['A'])
    # 谷底(低い所)は草地。起伏のある谷底から山の木の色へなめらかに移る
    sepp = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(geo.outputs['Position'], sepp.inputs['Vector'])
    low = nt.nodes.new('ShaderNodeMapRange')
    low.inputs['From Min'].default_value = 10.0
    low.inputs['From Max'].default_value = 25.0
    low.inputs['To Min'].default_value = 1.0
    low.inputs['To Max'].default_value = 0.0
    nt.links.new(sepp.outputs['Z'], low.inputs['Value'])
    # 草地と土の写真(Poly Haven)をワールド座標で貼り、ノイズで土のまだらを混ぜる
    def photo(paths, tile):
        mapping = nt.nodes.new('ShaderNodeMapping')
        mapping.inputs['Scale'].default_value = (1.0 / tile, 1.0 / tile, 1.0)
        nt.links.new(geo.outputs['Position'], mapping.inputs['Vector'])
        out = {}
        for k in ("diff", "rough", "nor_gl"):
            t = nt.nodes.new('ShaderNodeTexImage')
            t.image = bpy.data.images.load(paths[k], check_existing=True)
            if k != "diff":
                t.image.colorspace_settings.name = 'Non-Color'
            nt.links.new(mapping.outputs['Vector'], t.inputs['Vector'])
            out[k] = t
        return out
    g, d = photo(GRASS_TEX, 14.0), photo(SOIL_TEX, 5.0)
    soil_noise = nt.nodes.new('ShaderNodeTexNoise')
    soil_noise.inputs['Scale'].default_value = 1.0 / 35.0
    soil_noise.inputs['Detail'].default_value = 5.0
    nt.links.new(geo.outputs['Position'], soil_noise.inputs['Vector'])
    soil = nt.nodes.new('ShaderNodeMapRange')  # 土が出ている所(2割ほど)
    soil.inputs['From Min'].default_value = 0.58
    soil.inputs['From Max'].default_value = 0.64
    nt.links.new(soil_noise.outputs['Fac'], soil.inputs['Value'])

    def mix(kind, a, b):
        m = nt.nodes.new('ShaderNodeMix')
        m.data_type = kind
        nt.links.new(soil.outputs['Result'], m.inputs['Factor'])
        nt.links.new(a, m.inputs['A'])
        nt.links.new(b, m.inputs['B'])
        return m.outputs['Result']
    ground = mix('RGBA', g['diff'].outputs['Color'], d['diff'].outputs['Color'])
    wet = nt.nodes.new('ShaderNodeMix')  # 雨で濡れて暗く、曇天で彩度も落ちる
    wet.data_type = 'RGBA'
    wet.blend_type = 'MULTIPLY'
    wet.inputs['Factor'].default_value = 1.0
    wet.inputs['B'].default_value = GROUND_TINT
    nt.links.new(ground, wet.inputs['A'])
    grass = nt.nodes.new('ShaderNodeMix')
    grass.data_type = 'RGBA'
    nt.links.new(low.outputs['Result'], grass.inputs['Factor'])
    nt.links.new(rock.outputs['Result'], grass.inputs['A'])
    nt.links.new(wet.outputs['Result'], grass.inputs['B'])
    nt.links.new(grass.outputs['Result'], bsdf.inputs['Base Color'])
    rough = mix('FLOAT', g['rough'].outputs['Color'], d['rough'].outputs['Color'])
    r_low = nt.nodes.new('ShaderNodeMix')
    r_low.inputs['A'].default_value = 0.9
    nt.links.new(low.outputs['Result'], r_low.inputs['Factor'])
    nt.links.new(rough, r_low.inputs['B'])
    nt.links.new(r_low.outputs['Result'], bsdf.inputs['Roughness'])
    bump = nt.nodes.new('ShaderNodeBump')  # 樹冠の凹凸
    bump.inputs['Strength'].default_value = 0.7
    nt.links.new(crown.outputs['Distance'], bump.inputs['Height'])
    nmap = nt.nodes.new('ShaderNodeNormalMap')  # 谷底は草地・土の写真の凹凸
    nmap.inputs['Strength'].default_value = 0.8
    nt.links.new(mix('RGBA', g['nor_gl'].outputs['Color'], d['nor_gl'].outputs['Color']), nmap.inputs['Color'])
    n_mix = nt.nodes.new('ShaderNodeMix')
    n_mix.data_type = 'VECTOR'
    nt.links.new(low.outputs['Result'], n_mix.inputs['Factor'])
    nt.links.new(bump.outputs['Normal'], n_mix.inputs['A'])
    nt.links.new(nmap.outputs['Normal'], n_mix.inputs['B'])
    nt.links.new(n_mix.outputs['Result'], bsdf.inputs['Normal'])
    return mat


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
    mat = forest_material()
    mesh_object("Terrain", bm, [mat], col)


TRUNK_CLEAR = 0.20  # 下の枝が始まる高さ(木の高さに対する割合)。根元まで葉があると幹が見えず、のっぺりする


def conifer_mesh():
    """後ろの森の針葉樹(高さ1)。ギザギザの枝の段を7段重ね、縁を垂らして、ノイズで形を崩す。"""
    bm = bmesh.new()
    tiers = 7
    for k in range(tiers):
        t = k / tiers
        z0 = TRUNK_CLEAR + (0.92 - TRUNK_CLEAR) * t
        r = 0.34 * (1.0 - t) ** 0.9 + 0.04
        h = 0.26 * (1.0 - 0.5 * t)
        n = 24
        ring = []
        for i in range(n):
            a = 2 * math.pi * (i + 0.5 * (k % 2)) / n
            rr = r * (1.0 if i % 2 == 0 else 0.62)  # 枝先と枝のあいだ(星形)
            ring.append(bm.verts.new((rr * math.cos(a), rr * math.sin(a), z0 - (0.04 if i % 2 == 0 else 0.0))))
        tip = bm.verts.new((0, 0, z0 + h))
        for i in range(n):
            bm.faces.new((ring[i], ring[(i + 1) % n], tip))
        bm.faces.new(list(reversed(ring)))
    for v in bm.verts:
        d = noise.noise_vector(v.co * 6.0)
        v.co += d * 0.025 * (0.3 + v.co.length)
    for f in bm.faces:
        f.smooth = True  # 近くで面の角が目立たないように
    before = set(bm.faces)
    bmesh.ops.create_cone(bm, cap_ends=True, segments=10, radius1=0.022, radius2=0.012, depth=TRUNK_CLEAR + 0.08,
                          matrix=mathutils.Matrix.Translation((0, 0, (TRUNK_CLEAR + 0.08) / 2)))
    for f in bm.faces:
        if f not in before:
            f.material_index = 1  # 幹
    me = bpy.data.meshes.new("Conifer")
    bm.to_mesh(me)
    bm.free()
    return me


def conifer_material():
    """後ろの森の葉: 木ごとに色を少し変え、葉の塊のまだらを入れる。"""
    mat = bpy.data.materials.new("Conifer")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
    bsdf.inputs['Roughness'].default_value = 0.85
    info = nt.nodes.new('ShaderNodeObjectInfo')
    ramp = nt.nodes.new('ShaderNodeValToRGB')  # 木ごとの色(濃い緑〜少し青みの緑〜少し黄みの緑)
    ramp.color_ramp.elements[0].color = (0.010, 0.022, 0.013, 1)
    ramp.color_ramp.elements[1].color = (0.022, 0.036, 0.018, 1)
    ramp.color_ramp.elements.new(0.5).color = (0.012, 0.030, 0.022, 1)
    nt.links.new(info.outputs['Random'], ramp.inputs['Fac'])
    coord = nt.nodes.new('ShaderNodeTexCoord')
    vor = nt.nodes.new('ShaderNodeTexVoronoi')  # 葉の塊
    vor.inputs['Scale'].default_value = 9.0
    nt.links.new(coord.outputs['Object'], vor.inputs['Vector'])
    shade = nt.nodes.new('ShaderNodeMapRange')
    shade.inputs['To Min'].default_value = 1.0
    shade.inputs['To Max'].default_value = 0.45
    nt.links.new(vor.outputs['Distance'], shade.inputs['Value'])
    mul = nt.nodes.new('ShaderNodeMix')
    mul.data_type = 'RGBA'
    mul.blend_type = 'MULTIPLY'
    mul.inputs['Factor'].default_value = 1.0
    nt.links.new(ramp.outputs['Color'], mul.inputs['A'])
    nt.links.new(shade.outputs['Result'], mul.inputs['B'])
    nt.links.new(mul.outputs['Result'], bsdf.inputs['Base Color'])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.8
    nt.links.new(vor.outputs['Distance'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def in_camera_view(x, y, margin_deg=6.0):
    cam = V(CAM_LOC)
    fwd = (V(CAM_TARGET) - cam).to_2d().normalized()
    d = V((x, y)) - cam.to_2d()
    half_h = math.degrees(math.atan(math.tan(math.atan(18.0 / CAM_LENS)) * 1080 / 1920))
    return math.degrees(fwd.angle(d.normalized())) < half_h + margin_deg


NEAR_TREE = 75.0  # 木を植える一番近い距離(駐車場のすぐ外。遠すぎると手前に何もない草地が広がる)
GROVES = 26  # カメラに映る範囲に足す木立の数(1つ5本ほど)


def build_trees(col, rng):
    """駐車場の外の針葉樹(自作の木のリンク複製)。壁にならないよう、木立のあいだに奥が見えるすき間を残す。"""
    me = conifer_mesh()
    me.materials.append(conifer_material())
    me.materials.append(principled("ConiferTrunk", (0.022, 0.020, 0.018), roughness=0.9))
    count = 0
    for _ in range(4000):
        r = rng.uniform(NEAR_TREE, 700.0)
        a = rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(a), r * math.sin(a)
        if abs(x) < LOT_HALF[0] + 3 and abs(y) < LOT_HALF[1] + 3:
            continue
        if mountain_height(x, y) > 1.0:
            continue
        # 谷の奥(視線の先)は開けておく
        ang = math.degrees(math.atan2(y, x))
        if -125 < ang < -100 and r < 300:
            continue
        o = link(bpy.data.objects.new(f"Tree{count:04d}", me), col)
        s = rng.uniform(12.0, 22.0)
        o.scale = (s * rng.uniform(0.8, 1.1), s * rng.uniform(0.8, 1.1), s)
        o.location = (x, y, terrain_height(x, y) - 0.5)
        o.rotation_euler = (0, 0, rng.uniform(0, 6.3))
        count += 1
        if count >= 1000:
            break
    # カメラに映る範囲に木立を足す。数本ずつの塊にして、塊のあいだから奥が見えるようにする(密に植えると壁になる)
    dense = 0
    groves = []
    for _ in range(20000):
        r = NEAR_TREE + 520.0 * rng.random() ** 1.6
        a = rng.uniform(0, 2 * math.pi)
        x, y = r * math.cos(a), r * math.sin(a)
        if in_camera_view(x, y, 10.0) and terrain_height(x, y) < 60.0:
            groves.append((x, y))
        if len(groves) >= GROVES:
            break
    for _ in range(20000):
        gx, gy = groves[rng.randrange(len(groves))]
        x, y = gx + rng.gauss(0, 7.0), gy + rng.gauss(0, 7.0)
        h = terrain_height(x, y)
        if (abs(x) < LOT_HALF[0] + 4 and abs(y) < LOT_HALF[1] + 4) or h > 60.0:
            continue
        ang = math.degrees(math.atan2(y, x))
        if -125 < ang < -100 and r < 300:
            continue
        o = link(bpy.data.objects.new(f"TreeDense{dense:04d}", me), col)
        s = rng.uniform(13.0, 24.0) * min(1.0, 0.6 + 0.4 * (math.hypot(x, y) - NEAR_TREE) / 60.0)  # 近いほど低い木(大きく映りすぎない)
        o.scale = (s * rng.uniform(0.8, 1.1), s * rng.uniform(0.8, 1.1), s)
        o.location = (x, y, max(h, 0.0) - 0.5)
        o.rotation_euler = (0, 0, rng.uniform(0, 6.3))
        dense += 1
        if dense >= GROVES * 5:
            break
    print("[Stage1] trees:", count, "groves:", dense)


def bolt_path(rng, start, end, segments, jitter):
    """startからendへのギザギザの道(中点を横へずらしていく)。jitterは長さに対するずれの割合。"""
    pts = [V(start), V(end)]
    for _ in range(segments):
        new = [pts[0]]
        for a, b in zip(pts, pts[1:]):
            d = b - a
            side = d.cross(V((0, 0, 1)))
            side = side.normalized() if side.length > 1e-6 else V((1, 0, 0))
            up = side.cross(d).normalized()
            m = (a + b) / 2 + (side * rng.gauss(0, 1) + up * rng.gauss(0, 0.5)) * d.length * jitter
            new += [m, b]
        pts = new
    return pts


def bolt_curve(name, pts, radius_fn, mat, col):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 1
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (*p, 1.0)
        sp.points[i].radius = radius_fn(i / (len(pts) - 1), p)
    cu.materials.append(mat)
    obj = link(bpy.data.objects.new(name, cu), col)
    obj.visible_shadow = False
    return obj


def build_lightning(col, rng):
    """雷: 雲から屋根の真ん中へ下りる主の道と、途中から分かれて空中で消える枝。光る管(太さは遠いほど太く、画面で数画素)。
    画面全体を照らす光は、道の途中に置いた点光源(frame_stateで落ちるフレームだけ点ける)。"""
    mat = bpy.data.materials.new("Lightning")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = (0.82, 0.80, 1.0, 1)  # 青紫がかった白
    em.inputs['Strength'].default_value = 120.0
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    nt.links.new(em.outputs[0], out.inputs[0])
    top, hit = V(LIGHTNING_TOP), V(STRIKE_POINT)
    # 手前(カメラの近く)ほど画面で大きく見えるので、区間を分けてそれぞれギザギザにする(3Dで均等に分けると、手前がまっすぐな棒になる)
    toward = (top - hit).normalized()
    p80, p12, p1 = (hit + toward * d for d in (80.0, 12.0, 0.6))
    main = (bolt_path(rng, top, p80, 8, 0.035) + bolt_path(rng, p80, p12, 6, 0.07)[1:]
            + bolt_path(rng, p12, p1, 5, 0.10)[1:] + [hit])

    def width(p):
        return 0.02 + 0.0005 * (p - V(CAM_LOC)).length  # 遠くても画面で同じくらいの太さ(1画素≒距離の0.0006倍)
    bolt_curve("LightningMain", main, lambda t, p: width(p), mat, col)
    for k in range(9):  # 枝: 上の方ほど多く長い
        i = int(len(main) * rng.uniform(0.03, 0.45))
        a = main[i]
        down = (main[min(i + 8, len(main) - 1)] - a).normalized()
        side = down.cross(V((0, 0, 1))).normalized() * rng.choice((-1, 1))
        length = (a - hit).length * rng.uniform(0.12, 0.30)
        end = a + (down * 0.6 + side * rng.uniform(0.5, 1.1) + V((0, 0, -0.3))).normalized() * length
        pts = bolt_path(rng, a, end, 6, 0.16)
        bolt_curve(f"LightningBranch{k}", pts, lambda t, p: width(p) * 0.45 * (1.0 - 0.8 * t), mat, col)
    glow = bpy.data.lights.new("LightningGlow", 'POINT')  # 雷の道のすぐ上の光(はっきりした影を落とす)
    glow.energy = 0.0
    glow.shadow_soft_size = 0.5
    glow.color = (0.85, 0.85, 1.0)
    link(bpy.data.objects.new("LightningGlow", glow), col).location = hit + (top - hit).normalized() * 25.0
    col.hide_render = True


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
    build_lightning(collection("Lightning"), rng)
    # 映り込み用のプローブ: 無いと車体の下半分にも空が映って白く飛ぶ(地面の暗さを拾わせる)
    probe = bpy.data.lightprobes.new("CarReflection", 'SPHERE')
    probe.influence_distance = 12.0
    link(bpy.data.objects.new("CarReflection", probe), collection("Probes")).location = (0, 0, 2.2)  # 車の屋根の上(車の中に置くと、中の暗さを路面や車体に映してしまう)
    os.makedirs(os.path.dirname(WIP_BLEND), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=WIP_BLEND)
    print("[Stage1] saved:", WIP_BLEND)


if __name__ == "__main__":
    main()
