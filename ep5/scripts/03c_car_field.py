# -*- coding: utf-8 -*-
"""
本番の車の形で、雷雲の下の電場の中に車を置いたとき、車内の電場が外の何%になるかを解く(00_field_check.py の本番版)。

- 形は 03_export_car_mesh.py で書き出したレンダーの車そのもの。金属の三角形(ガラス以外)が通る格子の箱を電位0(地面とつながった金属)にする
- ガラスは電気を通さないので穴(ガラスの誘電率は静電場の遮蔽にほぼ効かない)
- 地面(z=0)は電位0、上と横の境界は一様な電場 E0=1 の電位(雷雲の下の電場。比率だけ見る)
- ラプラス方程式を赤黒のSORで解く。粗い格子で解いてから細かい格子に移す
- 比べる条件: 金属の車 / 屋根なし(ベルトラインより上の金属を外す=オープンカー) / 樹脂ボディ(金属なし)
実行: .venv/bin/python ep5/scripts/03c_car_field.py [格子の幅m(既定0.05)]
出力: ep5/cache/car_field_<条件>.npz(電位。光の線を描くのに使う)
"""
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import BELT, EP5, STRIKE_POINT

CACHE_IN = os.path.join(EP5, "cache", "car_body.npz")
H_FINE = float(sys.argv[1]) if len(sys.argv) > 1 else 0.05
BOX = ((-4.0, 4.0), (-6.0, 6.0), (0.0, 6.0))  # 計算の範囲(車の中心が原点)
# 測る点(右ハンドル: 運転席は右(+x))。車内の平均は、座席のあたりの箱
POINTS = {"運転席の頭": (0.38, 0.0, 1.12), "後席の頭": (0.38, -0.95, 1.10), "運転席の胸": (0.38, 0.1, 0.82),
          "足もと": (0.38, 0.9, 0.45), "車内の真ん中": (0.0, -0.4, 0.9), "ダッシュボードの上": (0.3, 0.9, 1.05),
          "屋根のすぐ上": (STRIKE_POINT[0], STRIKE_POINT[1], STRIKE_POINT[2] + 0.2)}
CABIN = ((-0.55, 0.55), (-1.1, 0.9), (0.5, 1.15))


def grid(h):
    return [np.arange(lo, hi + h / 2, h) for lo, hi in BOX]


def metal_mask(h, kind):
    xs, ys, zs = grid(h)
    m = np.zeros((len(xs), len(ys), len(zs)), bool)
    if kind == "resin":
        return m
    d = np.load(CACHE_IN)
    v, t = d["verts"], d["tris"][d["mat"] != 1]
    if kind == "convertible":
        t = t[v[t][:, :, 2].max(axis=1) <= BELT + 0.02]  # ベルトラインより上(屋根・ピラー・窓枠)の金属を外す
    # 三角形の上に点を細かく打って、その点が入る格子の箱を金属にする(殻に隙間ができないように、格子の1/3間隔)
    p0, p1, p2 = v[t[:, 0]], v[t[:, 1]], v[t[:, 2]]
    edge = np.maximum(np.linalg.norm(p1 - p0, axis=1), np.linalg.norm(p2 - p0, axis=1))
    nmax = int(np.ceil(edge.max() / (h / 3))) + 1
    for a in range(nmax + 1):
        for b in range(nmax + 1 - a):
            u, w = a / nmax, b / nmax
            q = p0 + u * (p1 - p0) + w * (p2 - p0)
            idx = np.round((q - np.array([BOX[0][0], BOX[1][0], BOX[2][0]])) / h).astype(int)
            m[idx[:, 0], idx[:, 1], idx[:, 2]] = True
    return m


def solve(mask, h, phi0=None, tol=1e-5, max_iter=20000):
    xs, ys, zs = grid(h)
    phi = np.broadcast_to(zs, mask.shape).astype(np.float64).copy() if phi0 is None else phi0.copy()
    phi[mask] = 0.0
    fixed = mask.copy()
    fixed[0, :, :] = fixed[-1, :, :] = fixed[:, 0, :] = fixed[:, -1, :] = fixed[:, :, 0] = fixed[:, :, -1] = True
    ii, jj, kk = np.indices(mask.shape)
    free = ~fixed
    colors = [free & ((ii + jj + kk) % 2 == c) for c in (0, 1)]
    w = 2 / (1 + np.sin(np.pi / max(mask.shape)))
    for it in range(max_iter):
        delta = 0.0
        for color in colors:
            avg = np.zeros_like(phi)
            avg[1:-1, 1:-1, 1:-1] = (phi[2:, 1:-1, 1:-1] + phi[:-2, 1:-1, 1:-1] + phi[1:-1, 2:, 1:-1]
                                    + phi[1:-1, :-2, 1:-1] + phi[1:-1, 1:-1, 2:] + phi[1:-1, 1:-1, :-2]) / 6
            d = (avg - phi)[color]
            phi[color] += w * d
            delta = max(delta, float(np.abs(d).max()))
        if delta < tol:
            break
    return phi, it


def refine(phi_c, shape):
    """粗い格子の解を、細かい格子の初期値に(2倍に引きのばす)"""
    f = np.repeat(np.repeat(np.repeat(phi_c, 2, 0), 2, 1), 2, 2)
    return f[:shape[0], :shape[1], :shape[2]]


def field_mag(phi, h):
    gx, gy, gz = np.gradient(phi, h)
    return np.sqrt(gx * gx + gy * gy + gz * gz)


def at(arr, h, p):
    i = [int(round((p[a] - BOX[a][0]) / h)) for a in range(3)]
    return float(arr[i[0], i[1], i[2]])


def main():
    hc = H_FINE * 2
    print(f"格子 {H_FINE} m(粗い格子 {hc} m で解いてから移す)。値は、車が無いときの電場(E0)に対する%")
    for kind in ("metal", "convertible", "resin"):
        t0 = time.time()
        phi_c, _ = solve(metal_mask(hc, kind), hc)
        mask = metal_mask(H_FINE, kind)
        phi, it = solve(mask, H_FINE, refine(phi_c, mask.shape))
        E = 100 * field_mag(phi, H_FINE)
        xs, ys, zs = grid(H_FINE)
        X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')
        cab = ((X > CABIN[0][0]) & (X < CABIN[0][1]) & (Y > CABIN[1][0]) & (Y < CABIN[1][1])
               & (Z > CABIN[2][0]) & (Z < CABIN[2][1]) & ~mask)
        vals = {k: at(E, H_FINE, p) for k, p in POINTS.items()}
        print(f"{kind:12s} (反復{it}, {time.time() - t0:.0f}s): " + "  ".join(f"{k} {v:5.1f}%" for k, v in vals.items())
              + f"  車内の平均 {E[cab].mean():5.1f}%(最大 {E[cab].max():5.1f}%)")
        np.savez_compressed(os.path.join(EP5, "cache", f"car_field_{kind}.npz"), phi=phi.astype(np.float32), h=H_FINE,
                            origin=np.array([BOX[0][0], BOX[1][0], BOX[2][0]]))


if __name__ == "__main__":
    main()
