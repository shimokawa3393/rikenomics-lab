# -*- coding: utf-8 -*-
"""
何回落ちたら何が壊れるか: 雷1回で屋根とピラーに起きること(IEC 62305-1:2010 付属書Dの式)を、回数に広げる。

出典
- 雷の値: IEC 62305-1:2010 表A.1(CIGRE Electra No.41/69、Bergerらの測定)
  負極性の雷1回(日本の夏の雷はほとんどこれ)の電荷 QFLASH: 50% 7.5 C、5% 40 C(20回に1回はこれ以上)。
  最初の雷撃の比エネルギー W/R: 50% 55 kJ/Ω、5% 550 kJ/Ω
- 落ちた点で溶ける量: 同 式(D.9) V = u·Q / (γ(Cw(θs−θu) + Cs))。uは陽極/陰極の電圧降下「数十V」(ここでは30 V)。
  落ちた点に入る熱を全部溶かすのに使う前提なので、多めに出る(規格もそう書いている)
- 導体の温度上昇: 同 式(D.7)(断熱、熱が逃げない前提)。鋼の値は 表D.2(軟鋼)
- 1回で壊れうるもの: 米国気象局「Lightning and Cars」(アンテナが溶ける、タイヤ、電装品、リアガラスの熱線で割れる、火災)
形: ボディの鋼板の厚さ0.8 mm(一般的な乗用車の外板)。屋根の面積と、Bピラーの電流の割合(03b)は本番の車から
実行: .venv/bin/python ep5/scripts/03e_damage_estimate.py
"""
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from shots import EP5, SIDE_WINDOW_TOP

# IEC 62305-1 表D.2(軟鋼)
RHO0, ALPHA, GAMMA, THETA_S, CS, CW = 120e-9, 6.5e-3, 7700.0, 1530.0, 272e3, 469.0
THETA_U = 20.0
U_AC = 30.0  # 陽極/陰極の電圧降下[V](規格「数十V」)
SHEET = 0.8e-3  # 外板の厚さ[m]
B_PILLAR_SHARE = 0.188  # 03b: 一番多いBピラーの電流の割合
B_PILLAR_WIDTH = 0.10  # 03b: Bピラーの断面の長さ[m]
STRIKES = {"ふつうの雷(半分の雷はこれ以下)": (7.5, 55e3), "強い雷(20回に1回はこれ以上)": (40.0, 550e3)}


def roof_area():
    d = np.load(os.path.join(EP5, "cache", "car_body.npz"))
    v, t = d["verts"], d["tris"][d["mat"] != 1]
    p = v[t]
    n = np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0])
    a = 0.5 * np.linalg.norm(n, axis=1)
    up = n[:, 2] / np.maximum(2 * a, 1e-12) > 0.7
    high = p[:, :, 2].mean(axis=1) > SIDE_WINDOW_TOP - 0.02
    return a[up & high].sum()


def melt_volume(q):
    return U_AC * q / (GAMMA * (CW * (THETA_S - THETA_U) + CS))


def temp_rise(w_r, area):
    return (math.exp(w_r * ALPHA * RHO0 / (area ** 2 * GAMMA * CW)) - 1) / ALPHA


def main():
    roof = roof_area()
    roof_vol = roof * SHEET
    print(f"屋根(窓より上の金属): {roof:.2f} m²、鋼板 {roof_vol * 1e6:.0f} cm³(厚さ {SHEET * 1e3} mm)")
    for name, (q, w_r) in STRIKES.items():
        v = melt_volume(q)
        hole = 2 * math.sqrt(v / SHEET / math.pi)
        dt = temp_rise(w_r * B_PILLAR_SHARE ** 2, B_PILLAR_WIDTH * SHEET)
        print(f"{name}: 電荷 {q} C")
        print(f"  落ちた点で溶ける鋼 {v * 1e6:.3f} cm³ → 厚さ{SHEET * 1e3}mmの屋根に直径 約{hole * 1e3:.0f} mm の穴(多めの見積もり)")
        print(f"  Bピラー(電流の{100 * B_PILLAR_SHARE:.0f}%、断面{B_PILLAR_WIDTH * 100:.0f}cm×{SHEET * 1e3}mm)の温度上昇 {dt:.3f} ℃")
        print(f"  屋根の鋼板が全部溶けるまで 約{roof_vol / v:,.0f} 回(毎回ちがう場所に落ちるとして)")
        print(f"  熱が逃げないまま続けて落ちて、Bピラーが溶ける温度に届くまで 約{(THETA_S - THETA_U) / dt:,.0f} 回")


if __name__ == "__main__":
    main()
