# -*- coding: utf-8 -*-
"""
着手前の計算チェック: 屋根に落ちた雷の電流が、車のボディの表面をどう流れて地面へ抜けるかを解く。

- ボディは一様な薄い金属板(シート)とみなし、箱を2段重ねた簡単な形の外側の面を格子に切る(00_field_check.py と同じ形)
- 窓のガラスは電気を通さないので、面から抜く(屋根から下へは、ピラー(窓の間の柱)しか通り道がない)
- 屋根の1点から電流 I を入れ、4つの車輪の位置(ボディの下の縁)から地面へ抜ける(電位0)
- 各面は、自分の4辺にコンダクタンス 1/2 ずつを足す(平らなところの辺は2面ぶんで1)。キルヒホッフの式を疎行列で解く
- 直流の計算。実際の雷は速い電流なので、表皮効果で鋼板の外側の薄い層を流れる(厚さ方向の話。面の上の分かれ方はここで見る)
実行: .venv/bin/python ep5/scripts/01_surface_current_check.py [格子の幅m]
"""
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

H = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05

# 形(m)。車の中心を x=0, y=0、地面を z=0
BODY = (-2.2, 2.2, -0.9, 0.9, 0.3, 1.0)  # 下の箱: x0, x1, y0, y1, z0, z1
CABIN = (-1.3, 1.0, -0.9, 0.9, 1.0, 1.5)  # 上の箱(キャビン)
PILLAR_W = 0.10  # ピラーの幅
PILLARS = {"A": (-1.3, -1.3 + PILLAR_W), "B": (-0.2, -0.2 + PILLAR_W), "C": (1.0 - PILLAR_W, 1.0)}
SILL = 0.05  # 窓の下と上に残す金属の縁
STRIKE = (-0.2, 0.0)  # 屋根の落雷点(x, y)
WHEELS = [(-1.4, -0.9), (-1.4, 0.9), (1.4, -0.9), (1.4, 0.9)]  # 車輪の位置(ボディの下の縁)


def cells(lo, hi):
    return np.arange(int(round(lo / H)), int(round(hi / H)))


def solid_set():
    s = set()
    for (x0, x1, y0, y1, z0, z1) in (BODY, CABIN):
        for i in cells(x0, x1):
            for j in cells(y0, y1):
                for k in cells(z0, z1):
                    s.add((i, j, k))
    return s


def in_window(face_center, normal_axis):
    """キャビンの側面・前・後ろの面のうち、ガラスの部分か"""
    x, y, z = face_center
    cx0, cx1, _, _, cz0, cz1 = CABIN
    if not (cz0 + SILL < z < cz1 - SILL):
        return False
    if normal_axis == 1:  # 横の面: ピラー以外の窓
        if not (cx0 < x < cx1):
            return False
        return not any(a <= x <= b for a, b in PILLARS.values())
    if normal_axis == 0:  # 前の窓(フロントガラス)と後ろの窓
        return abs(y) < 0.9 - PILLAR_W and (abs(x - cx0) < H or abs(x - cx1) < H)
    return False


def build_faces():
    solid = solid_set()
    faces = []
    for (i, j, k) in solid:
        for axis in range(3):
            for sgn in (-1, 1):
                n = [i, j, k]
                n[axis] += sgn
                if tuple(n) in solid:
                    continue
                # 面の4頂点(格子点の整数座標)
                base = [i, j, k]
                if sgn == 1:
                    base[axis] += 1
                a1, a2 = [ax for ax in range(3) if ax != axis]
                quad = []
                for d1, d2 in ((0, 0), (1, 0), (1, 1), (0, 1)):
                    p = list(base)
                    p[a1] += d1
                    p[a2] += d2
                    quad.append(tuple(p))
                center = [(i + 0.5) * H, (j + 0.5) * H, (k + 0.5) * H]
                center[axis] = base[axis] * H
                if in_window(center, axis):
                    continue
                faces.append((quad, axis, center))
    return faces


def solve(strike=STRIKE):
    faces = build_faces()
    verts = {}
    for quad, _, _ in faces:
        for p in quad:
            verts.setdefault(p, len(verts))
    g = {}
    for quad, _, _ in faces:
        for m in range(4):
            a, b = verts[quad[m]], verts[quad[(m + 1) % 4]]
            key = (min(a, b), max(a, b))
            g[key] = g.get(key, 0.0) + 0.5
    pos = np.zeros((len(verts), 3))
    for p, n in verts.items():
        pos[n] = np.array(p) * H
    # 落雷点: 屋根の上で一番近い頂点。出口: 車輪の位置で、ボディの下の縁の一番近い頂点
    roof = np.where(np.abs(pos[:, 2] - CABIN[5]) < 1e-9)[0]
    src = roof[np.argmin(np.hypot(pos[roof, 0] - strike[0], pos[roof, 1] - strike[1]))]
    bottom = np.where(np.abs(pos[:, 2] - BODY[4]) < 1e-9)[0]
    sinks = [bottom[np.argmin(np.hypot(pos[bottom, 0] - wx, pos[bottom, 1] - wy))] for wx, wy in WHEELS]
    n = len(verts)
    edges = np.array(list(g.keys()))
    cond = np.array(list(g.values()))
    L = sp.coo_matrix((np.r_[cond, cond, -cond, -cond],
                       (np.r_[edges[:, 0], edges[:, 1], edges[:, 0], edges[:, 1]],
                        np.r_[edges[:, 0], edges[:, 1], edges[:, 1], edges[:, 0]])), shape=(n, n)).tocsr()
    free = np.ones(n, bool)
    free[sinks] = False
    rhs = np.zeros(n)
    rhs[src] = 1.0  # I = 1
    V = np.zeros(n)
    V[free] = spla.spsolve(L[free][:, free].tocsc(), rhs[free])
    cur = cond * (V[edges[:, 0]] - V[edges[:, 1]])  # 辺の電流(頂点0→1の向き)
    return pos, edges, cur, V, src, sinks


def report(strike=STRIKE):
    pos, edges, cur, V, src, sinks = solve(strike)
    p0, p1 = pos[edges[:, 0]], pos[edges[:, 1]]
    # 窓の高さの真ん中で、縦の辺を流れ下る電流を、ピラーごとに足す
    zc = (CABIN[4] + CABIN[5]) / 2
    zc = np.round(zc / H) * H
    vert = (np.abs(p0[:, 0] - p1[:, 0]) < 1e-9) & (np.abs(p0[:, 1] - p1[:, 1]) < 1e-9)
    cut = vert & (np.minimum(p0[:, 2], p1[:, 2]) < zc - 1e-9) & (np.maximum(p0[:, 2], p1[:, 2]) > zc - 1e-9) \
        & (np.maximum(p0[:, 2], p1[:, 2]) <= zc + H / 2)
    down = np.where(p0[:, 2] > p1[:, 2], cur, -cur)
    shares = {}
    for name, (a, b) in PILLARS.items():
        for side, sy in (("左", -1), ("右", 1)):
            m = cut & (p0[:, 0] >= a - 1e-9) & (p0[:, 0] <= b + 1e-9) & (np.sign(p0[:, 1]) == sy)
            shares[f"{name}{side}"] = down[m].sum()
    total_cut = down[cut].sum()
    # 車輪ごとの出口の電流
    out = []
    for s in sinks:
        m0, m1 = edges[:, 0] == s, edges[:, 1] == s
        out.append(cur[m1].sum() - cur[m0].sum())
    # 電流の密度(1mあたり): ピラーと、下の箱の側面の真ん中(z=0.65)
    pillar_density = max(shares.values()) / PILLAR_W
    zs = np.round(0.65 / H) * H
    cut2 = vert & (np.minimum(p0[:, 2], p1[:, 2]) < zs - 1e-9) & (np.maximum(p0[:, 2], p1[:, 2]) > zs - 1e-9) \
        & (np.maximum(p0[:, 2], p1[:, 2]) <= zs + H / 2) & (np.abs(np.abs(p0[:, 1]) - 0.9) < 1e-9)
    side_density = np.abs(down[cut2]).sum() / (2 * (BODY[1] - BODY[0]))
    print(f"格子 {H} m, 頂点 {len(pos)}, 落雷点 x={strike[0]} y={strike[1]}")
    print(f"  窓の高さを流れ下る電流の合計 {100 * total_cut:.1f}%(屋根から下へはピラーしか通れない)")
    print("  ピラーごと: " + "  ".join(f"{k} {100 * v:.1f}%" for k, v in shares.items()))
    print("  車輪ごと(前左・前右・後左・後右): " + "  ".join(f"{100 * o:.1f}%" for o in out))
    print(f"  一番多いピラーの電流の密度は、下の側面の平均の {pillar_density / side_density:.1f} 倍")


if __name__ == "__main__":
    report()
    report((0.4, 0.3))  # 落ちる場所を後ろ寄り・片側寄りにずらしたとき
