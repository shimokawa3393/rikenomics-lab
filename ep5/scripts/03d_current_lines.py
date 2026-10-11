# -*- coding: utf-8 -*-
"""
電流の光の筋: 03b_car_current.py の電流の密度 J に沿って、落雷点から車輪のあたりまで流線をたどる。

- 筋の本数の分け方は計算どおり: 落雷点のまわりの小さな輪を通って流れ出る電流が等しくなるように、出発点の角度を決める
  (1本の筋が同じ量の電流を運ぶので、筋が集まるところ=電流が多いところ。ピラーに筋が集まって見える)
- 表面の上を、Jの向きへ少しずつ進み、そのたびに一番近い面へ戻す。タイヤハウスに着いたら止める
実行: .venv/bin/python ep5/scripts/03d_current_lines.py
出力: ep5/cache/current_lines.npz(筋ごとの点列)
"""
import os
import sys

import numpy as np
from scipy.spatial import cKDTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import ARCH_RADIUS, AXLES_Y, CAR_LENGTH, EP5, WHEEL_RADIUS

CACHE_IN = os.path.join(EP5, "cache", "car_current.npz")
CACHE_OUT = os.path.join(EP5, "cache", "current_lines.npz")
N_LINES = 48
RING = 0.12  # 出発点の輪の半径[m]
STEP = 0.012


def main():
    d = np.load(CACHE_IN)
    v, t, J, src = d["verts"], d["tris"], d["J"], int(d["src"])
    centers = v[t].mean(axis=1)
    tree = cKDTree(centers)
    # 頂点ごとのJ(まわりの三角形の平均)を、三角形の中心で引くための木
    n0 = np.cross(v[t[:, 1]] - v[t[:, 0]], v[t[:, 2]] - v[t[:, 0]])
    nrm = n0 / np.maximum(np.linalg.norm(n0, axis=1, keepdims=True), 1e-12)
    p_src = v[src]

    def j_at(p, k=3):
        dist, idx = tree.query(p, k=k)
        w = 1.0 / np.maximum(dist, 1e-4)
        return (J[idx] * w[:, None]).sum(0) / w.sum(), nrm[idx[0]], centers[idx[0]]

    # 輪の上の流れ出る電流(角度ごと)
    angles = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    flux = []
    for a in angles:
        dirv = np.array([np.cos(a), np.sin(a), 0.0])
        p = p_src + RING * dirv
        j, n, c = j_at(p)
        p = p - np.dot(p - c, n) * n
        r = p - p_src
        r -= np.dot(r, n) * n
        flux.append(max(np.dot(j, r / np.linalg.norm(r)), 0.0))
    cum = np.cumsum(flux)
    cum /= cum[-1]
    seeds_a = np.interp((np.arange(N_LINES) + 0.5) / N_LINES, cum, angles)
    sinks = [np.array([0.0, ay - CAR_LENGTH / 2, WHEEL_RADIUS]) for ay in AXLES_Y]
    lines = []
    for a in seeds_a:
        # 落雷点のすぐそばは電流が四方へ広がっていて向きが定まらないので、輪の上までまっすぐ出てから流れに乗せる
        p = p_src + RING * np.array([np.cos(a), np.sin(a), 0.0])
        _, n, c = j_at(p)
        p = p - np.dot(p - c, n) * n
        pts = [p_src + (p - p_src) * s for s in np.linspace(0, 1, 6)]
        for _ in range(3000):
            j, n, c = j_at(p)
            jt = j - np.dot(j, n) * n
            if np.linalg.norm(jt) < 1e-9:
                break
            p = p + STEP * jt / np.linalg.norm(jt)
            p = p - np.dot(p - c, n) * n  # 面へ戻す
            pts.append(p.copy())
            if any(np.hypot(p[1] - s[1], p[2] - s[2]) < ARCH_RADIUS + 0.03 for s in sinks):
                break
        lines.append(np.array(pts))
    lens = [len(l) for l in lines]
    print(f"{len(lines)} 本、点の数 {min(lens)}〜{max(lens)}、終点の高さ {np.round([l[-1][2] for l in lines][:8], 2)}...")
    np.savez(CACHE_OUT, *lines)
    print("保存:", CACHE_OUT)


if __name__ == "__main__":
    main()
