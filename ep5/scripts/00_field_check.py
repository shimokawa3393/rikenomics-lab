# -*- coding: utf-8 -*-
"""
着手前の計算チェック: 雷雲の下の電場の中に車を置いて、車内の電場が外の何%になるかをラプラス方程式で解く。

- 地面(z=0)は電位0、上の境界は一様な電場 E0 になる電位(雷雲の下の電場を模したもの。値は比率だけ見るので1)
- 金属のボディは電位0(タイヤ越しでも、ゆっくりした電場では地面とつながっている扱い)
- 窓のガラスは電気を通さないので「穴」として扱う(ガラスの誘電率は静電場の遮蔽にほぼ効かない)
- 比べる条件: 金属の車 / 屋根なし(オープンカー) / 樹脂ボディ(金属なし)
実行: .venv/bin/python ep5/scripts/00_field_check.py [格子の幅m]
"""
import sys

import numpy as np

H = float(sys.argv[1]) if len(sys.argv) > 1 else 0.1
NX, NY, NZ = int(12 / H), int(8 / H), int(6 / H)
X0, Y0 = 6.0, 4.0  # 車の中心


def idx(v, o=0.0):
    return int(round((v + o) / H))


def car_mask(kind):
    m = np.zeros((NX, NY, NZ), bool)
    if kind == "resin":
        return m
    x0, x1 = idx(X0 - 2.2), idx(X0 + 2.2)
    y0, y1 = idx(Y0 - 0.9), idx(Y0 + 0.9)
    z0, zb, zr = idx(0.3), idx(1.0), idx(1.5)  # 床、窓の下端(ベルトライン)、屋根
    # 下半分の箱(床・側面・前後)
    m[x0:x1 + 1, y0:y1 + 1, z0] = True
    m[x0, y0:y1 + 1, z0:zb + 1] = m[x1, y0:y1 + 1, z0:zb + 1] = True
    m[x0:x1 + 1, y0, z0:zb + 1] = m[x0:x1 + 1, y1, z0:zb + 1] = True
    m[x0:x1 + 1, y0:y1 + 1, zb] |= False
    # 上半分(キャビン): 前後を少し絞る。窓は穴、ピラー(柱)だけ金属
    cx0, cx1 = idx(X0 - 1.3), idx(X0 + 1.0)
    for x in (cx0, idx(X0 - 0.15), cx1):  # Aピラー・Bピラー・Cピラー
        for y in (y0, y1):
            m[x, y, zb:zr + 1] = True
    m[cx0, y0:y1 + 1, zb:zr + 1] |= False  # 前の窓は穴
    # ボンネット・トランクの上面(キャビンの外側)
    m[x0:cx0 + 1, y0:y1 + 1, zb] = True
    m[cx1:x1 + 1, y0:y1 + 1, zb] = True
    for y in (y0, y1):  # 窓の下の縁
        m[cx0:cx1 + 1, y, zb] = True
    m[cx0, y0:y1 + 1, zb] = m[cx1, y0:y1 + 1, zb] = True
    if kind == "metal":
        m[cx0:cx1 + 1, y0:y1 + 1, zr] = True  # 屋根
        for y in (y0, y1):
            m[cx0:cx1 + 1, y, zr] = True
    return m


def solve(mask, iters=20000, tol=1e-6):
    z = np.arange(NZ) * H
    phi = np.broadcast_to(z, (NX, NY, NZ)).copy()  # 一様な電場 E0=1 の電位
    phi[mask] = 0.0
    fixed = mask.copy()
    fixed[:, :, 0] = fixed[:, :, -1] = True
    ii, jj, kk = np.indices((NX, NY, NZ))
    inner = np.zeros_like(fixed)
    inner[1:-1, 1:-1, 1:-1] = True
    free = inner & ~fixed
    red, black = free & ((ii + jj + kk) % 2 == 0), free & ((ii + jj + kk) % 2 == 1)
    w = 2 / (1 + np.sin(np.pi / max(NX, NY, NZ)))
    for it in range(iters):
        delta = 0.0
        for color in (red, black):
            avg = np.zeros_like(phi)
            avg[1:-1, 1:-1, 1:-1] = (phi[2:, 1:-1, 1:-1] + phi[:-2, 1:-1, 1:-1] + phi[1:-1, 2:, 1:-1]
                                    + phi[1:-1, :-2, 1:-1] + phi[1:-1, 1:-1, 2:] + phi[1:-1, 1:-1, :-2]) / 6
            d = (avg - phi)[color]
            phi[color] += w * d
            delta = max(delta, np.abs(d).max())
        # 横の境界は一様な電場のまま(遠方)
        if delta < tol:
            break
    return phi, it


def field_at(phi, x, y, z):
    i, j, k = idx(x), idx(y), idx(z)
    gx = (phi[i + 1, j, k] - phi[i - 1, j, k]) / (2 * H)
    gy = (phi[i, j + 1, k] - phi[i, j - 1, k]) / (2 * H)
    gz = (phi[i, j, k + 1] - phi[i, j, k - 1]) / (2 * H)
    return float(np.sqrt(gx * gx + gy * gy + gz * gz))


points = {"頭(運転席)": (X0 - 0.4, Y0 - 0.4, 1.25), "胸": (X0 - 0.4, Y0 - 0.4, 0.85),
          "足もと": (X0 - 0.9, Y0 - 0.4, 0.45), "車内の真ん中": (X0, Y0, 1.1), "屋根のすぐ上": (X0 - 0.2, Y0, 1.7)}
print(f"格子 {H} m ({NX}x{NY}x{NZ})。値は、車が無いときの電場(E0)に対する%")
for kind in ("metal", "convertible", "resin"):
    phi, it = solve(car_mask(kind))
    vals = {k: 100 * field_at(phi, *p) for k, p in points.items()}
    print(f"{kind:12s} (反復{it}): " + "  ".join(f"{k} {v:6.2f}%" for k, v in vals.items()))
