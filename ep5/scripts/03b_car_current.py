# -*- coding: utf-8 -*-
"""
本番の車の形で、屋根に落ちた雷の電流がボディの表面をどう流れて地面へ抜けるかを解く(01_surface_current_check.py の本番版)。

- 形は 03_export_car_mesh.py で書き出したレンダーの車そのもの。ガラス(材質1)の三角形は電気を通さないので抜く
- ボディは一様な薄い金属板とみなし、表面の電位Vのラプラス方程式を有限要素(三角形の余接の重み)で解く
- 屋根の落雷点(shots.STRIKE_POINT)の一番近い頂点から電流 I=1 を入れ、4つのタイヤハウス(アーチの内側の面)から地面へ抜ける(電位0)
- 直流の計算。実際の雷(1000分の1秒より短い)では分かれ方の細かい数字は変わりうる。「窓を通れないのでピラーを通る」は変わらない
実行: .venv/bin/python ep5/scripts/03b_car_current.py
出力: ep5/cache/car_current.npz(頂点の電位、三角形ごとの電流の密度ベクトル。光の線を描くのに使う)
"""
import os
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.csgraph as csg
import scipy.sparse.linalg as spla

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import (A_PILLAR_Y_MIN, ARCH_RADIUS, AXLES_Y, B_PILLAR_WORLD, CAR_LENGTH, EP5, SIDE_WINDOW_BOTTOM,
                   SIDE_WINDOW_TOP, STRIKE_POINT, WHEEL_RADIUS)

CACHE_IN = os.path.join(EP5, "cache", "car_body.npz")
CACHE_OUT = os.path.join(EP5, "cache", "car_current.npz")
Z_WINDOW = (SIDE_WINDOW_BOTTOM + SIDE_WINDOW_TOP) / 2 + 0.02  # 窓の高さの真ん中(ここを横切る電流はピラーしか通れない)
Z_SIDE = 0.65  # ドアの真ん中の高さ(側面の電流の密度を測る)


def load_metal():
    d = np.load(CACHE_IN)
    verts, tris, mat = d["verts"], d["tris"], d["mat"]
    tris = tris[mat != 1]
    used = np.unique(tris)
    remap = -np.ones(len(verts), int)
    remap[used] = np.arange(len(used))
    return verts[used], remap[tris]


def cotan_laplacian(v, t):
    rows, cols, w = [], [], []
    for k in range(3):
        i, j, o = t[:, (k + 1) % 3], t[:, (k + 2) % 3], t[:, k]  # 辺 i-j の向かいの角 o
        a, b = v[i] - v[o], v[j] - v[o]
        cross = np.linalg.norm(np.cross(a, b), axis=1)
        cot = np.einsum('ij,ij->i', a, b) / np.maximum(cross, 1e-12)
        rows += [i, j]
        cols += [j, i]
        w += [0.5 * cot, 0.5 * cot]
    W = sp.coo_matrix((np.concatenate(w), (np.concatenate(rows), np.concatenate(cols))), shape=(len(v),) * 2).tocsr()
    return W  # 辺の重み(導電率1のシートのコンダクタンス)


def main(strike=STRIKE_POINT, save=True):
    v, t = load_metal()
    W = cotan_laplacian(v, t)
    src = int(np.argmin(np.linalg.norm(v - np.array(strike), axis=1)))
    # 落雷点とつながっている部分だけで解く(ミラーの付け根などの浮いた小片を除く)
    _, comp = csg.connected_components(W != 0, directed=False)
    keep = comp == comp[src]
    # 出口: 4つのタイヤハウス(車軸からアーチの半径+3cm以内の頂点)
    sinks = []
    for ay in AXLES_Y:
        y = ay - CAR_LENGTH / 2
        for sx in (-1, 1):
            r = np.hypot(v[:, 1] - y, v[:, 2] - WHEEL_RADIUS)
            sinks.append(np.where(keep & (r < ARCH_RADIUS + 0.03) & (np.sign(v[:, 0]) == sx))[0])
    n = len(v)
    L = sp.diags(np.asarray(W.sum(axis=1)).ravel()) - W
    fixed = np.zeros(n, bool)
    fixed[np.concatenate(sinks)] = True
    fixed |= ~keep
    free = ~fixed
    rhs = np.zeros(n)
    rhs[src] = 1.0
    V = np.zeros(n)
    V[free] = spla.spsolve(L[free][:, free].tocsc(), rhs[free])
    # 辺の電流 I_ij = W_ij (V_i - V_j)
    Wc = W.tocoo()
    I = Wc.data * (V[Wc.row] - V[Wc.col])
    zi, zj = v[Wc.row, 2], v[Wc.col, 2]

    def down_through(z, region):  # 高さzの水平面を、上から下へ横切る電流(regionで場所を選ぶ)
        m = (zi > z) & (zj <= z) & region
        return I[m].sum()

    mid = (v[Wc.row] + v[Wc.col]) / 2
    yx = mid[:, 1], mid[:, 0]
    regions = {
        "A": yx[0] > A_PILLAR_Y_MIN, "B": (yx[0] > B_PILLAR_WORLD[0] - 0.15) & (yx[0] < B_PILLAR_WORLD[1] + 0.15),
        "C": yx[0] < -1.0,
    }
    total = down_through(Z_WINDOW, np.ones_like(zi, bool))
    shares = {f"{k}{side}": down_through(Z_WINDOW, r & (np.sign(yx[1]) == sx))
              for k, r in regions.items() for side, sx in (("左", -1), ("右", 1))}
    wheel_out = []
    for s in sinks:
        ins = np.isin(Wc.col, s) & ~np.isin(Wc.row, s)
        wheel_out.append(I[ins].sum())

    def cut_length(z, region_fn):  # 高さzで切った金属の断面の長さ
        tot = 0.0
        for tri in t:
            p = v[tri]
            above = p[:, 2] > z
            if above.all() or (~above).all():
                continue
            pts = []
            for a, b in ((0, 1), (1, 2), (2, 0)):
                if above[a] != above[b]:
                    s_ = (z - p[a, 2]) / (p[b, 2] - p[a, 2])
                    pts.append(p[a] + s_ * (p[b] - p[a]))
            if len(pts) == 2 and region_fn((pts[0] + pts[1]) / 2):
                tot += np.linalg.norm(pts[1] - pts[0])
        return tot
    best = max(shares, key=shares.get)
    k, sx = best[0], -1 if best[1] == "左" else 1
    rk = {"A": lambda q: q[1] > A_PILLAR_Y_MIN,
          "B": lambda q: B_PILLAR_WORLD[0] - 0.15 < q[1] < B_PILLAR_WORLD[1] + 0.15,
          "C": lambda q: q[1] < -1.0}[k]
    pillar_w = cut_length(Z_WINDOW, lambda q: rk(q) and np.sign(q[0]) == sx)
    # ドアの面(前後のタイヤハウスのあいだの横の面)を流れ下る電流の密度
    door_y = (AXLES_Y[0] - CAR_LENGTH / 2 + ARCH_RADIUS + 0.1, AXLES_Y[1] - CAR_LENGTH / 2 - ARCH_RADIUS - 0.1)
    on_door = (yx[0] > door_y[0]) & (yx[0] < door_y[1]) & (np.abs(yx[1]) > 0.7)
    door_len = cut_length(Z_SIDE, lambda q: door_y[0] < q[1] < door_y[1] and abs(q[0]) > 0.7)
    door_total = down_through(Z_SIDE, on_door)
    ratio = (shares[best] / pillar_w) / (door_total / door_len)
    print(f"頂点 {n}(金属)、三角形 {len(t)}、落雷点 {np.round(v[src], 2)}")
    print(f"  窓の高さ(z={Z_WINDOW:.2f})を流れ下る電流の合計 {100 * total:.1f}%")
    print("  ピラーごと: " + "  ".join(f"{k} {100 * s:.1f}%" for k, s in shares.items()))
    print("  タイヤハウスごと(後左・後右・前左・前右): " + "  ".join(f"{100 * o:.1f}%" for o in wheel_out))
    print(f"  一番多い{best}ピラーの断面 {100 * pillar_w:.0f}cm。電流の密度は、ドアの面(z={Z_SIDE}、左右{100 * door_len:.0f}cmを{100 * door_total:.1f}%が流れ下る)の {ratio:.1f} 倍")
    # 三角形ごとの電流の密度ベクトル J = -grad V(光の線を描く用)
    p0, p1, p2 = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    nrm = np.cross(p1 - p0, p2 - p0)
    area2 = np.linalg.norm(nrm, axis=1, keepdims=True)
    nh = nrm / np.maximum(area2, 1e-12)
    grad = (np.cross(nh, p2 - p1) * V[t[:, 0], None] + np.cross(nh, p0 - p2) * V[t[:, 1], None]
            + np.cross(nh, p1 - p0) * V[t[:, 2], None]) / np.maximum(area2, 1e-12)
    if save:
        np.savez(CACHE_OUT, verts=v, tris=t, V=V, J=-grad, src=src)
        print("  保存:", CACHE_OUT)


if __name__ == "__main__":
    main()
    main((0.35, -0.9, 1.45), save=False)  # 落ちる場所を後ろ寄り・片側寄りにずらしたとき
