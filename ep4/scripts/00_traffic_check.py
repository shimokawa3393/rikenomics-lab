# -*- coding: utf-8 -*-
"""
Stage 0: 交通流の計算を、既知の観測事実と照らし合わせる(Blender不要。.venvのPythonで実行)

1. 2008年の円環コース実験(Sugiyama et al., New J. Phys. 10, 033001): 22台・1周230mで、きっかけなしに
   渋滞が自然発生し、渋滞の波が後ろへ時速約20kmで進んだ。同じ条件で再現できるか。
2. ep4の高速道路(一車線・周期境界): 1台の小さなブレーキが後ろへ増幅されて止まる車が出るか。
   車の密度を変えて、波ができるまでの時間・波の速さを比べる(実際の高速道路の渋滞波は後ろ向きに時速約15〜20km)。

実行:
  .venv/bin/python ep4/scripts/00_traffic_check.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from traffic_sim import KMH, Driver, Perturbation, jam_front_speed, simulate_ring

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "analysis")


def first_stop_time(result, slow=5 * KMH):
    stopped = (result.v < slow).any(axis=1)
    return result.t[np.argmax(stopped)] if stopped.any() else None


def space_time_plot(result, path, title, window=None, t_max=None):
    """横軸が時間、縦軸が位置。1台ずつの軌跡を速度で色分け(赤=遅い)。渋滞の波は右下がりの赤い帯になる。"""
    fig, ax = plt.subplots(figsize=(10, 6), dpi=110)
    x = result.x % result.length
    sel = slice(None) if t_max is None else result.t <= t_max
    t = result.t[sel]
    for i in range(x.shape[1]):
        xi, vi = x[sel, i], result.v[sel, i]
        jumps = np.where(np.diff(xi) < 0)[0] + 1  # 周期境界で折り返す所で線を切る
        for seg_t, seg_x, seg_v in zip(np.split(t, jumps), np.split(xi, jumps), np.split(vi, jumps)):
            ax.scatter(seg_t, seg_x, c=seg_v / KMH, cmap="RdYlGn", vmin=0, vmax=60 if result.length < 500 else 110,
                       s=0.3, linewidths=0)
    if window:
        ax.set_ylim(*window)
    ax.set_xlabel("time [s]")
    ax.set_ylabel("position [m]")
    ax.set_title(title)
    sm = plt.cm.ScalarMappable(cmap="RdYlGn", norm=plt.Normalize(0, 60 if result.length < 500 else 110))
    fig.colorbar(sm, ax=ax, label="speed [km/h]")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def sugiyama():
    # 実験のドライバーは時速約30kmで車間10m強(車間時間0.7秒前後)まで詰めていたが、IDMに反応の遅れを入れて
    # そこまで詰めると衝突する。衝突しない範囲(車間時間1.2秒・反応0.5秒)では走り出しが時速約11kmと遅いが、
    # 「小さな揺らぎだけから渋滞が自然に生まれ、波が後ろへ時速約20kmで進む」ことは再現できる
    driver = Driver(v0=60 * KMH, T=1.2, s0=2.0, a=1.2, b=1.5, reaction_time=0.5, length=4.7)
    r = simulate_ring(22, 230.0, driver, duration=600, position_noise=0.3, seed=1)
    stop = first_stop_time(r)
    speed = jam_front_speed(r, (stop or 0) + 60, 600)
    print(f"[円環実験] 初速 {r.v[0].mean() / KMH:.1f} km/h, 最初に止まる車が出た時刻: {stop}, "
          f"渋滞の波の速さ: {None if speed is None else round(speed / KMH, 1)} km/h, 衝突: {r.collisions}")
    space_time_plot(r, os.path.join(OUT_DIR, "sugiyama_ring.png"),
                    "Ring experiment (22 cars, 230 m): jam emerges without any cause")
    return r


def highway(density_per_km, plot=False):
    driver = Driver()  # 高速道路の標準的な値
    length = 4000.0
    n = int(round(density_per_km * length / 1000))
    r = simulate_ring(n, length, driver, duration=600, position_noise=0.0, seed=2,
                      perturbations=[Perturbation(car=0, time=20.0, duration=2.0, decel=2.0)])
    stop = first_stop_time(r)
    speed = jam_front_speed(r, (stop or 0) + 30, 600) if stop else None
    min_v = r.v[r.t > 20].min() / KMH
    print(f"[高速 {density_per_km:>2} 台/km] 初速 {r.v[0].mean() / KMH:5.1f} km/h, 最低速度 {min_v:5.1f} km/h, "
          f"最初に止まる車: {stop}, 波の速さ: {None if speed is None else round(speed / KMH, 1)} km/h, 衝突: {r.collisions}")
    if plot:
        space_time_plot(r, os.path.join(OUT_DIR, f"highway_{density_per_km}perkm.png"),
                        f"Highway lane, {density_per_km} cars/km: one car brakes lightly at t=20 s",
                        window=(0, 1500), t_max=300)
    return r


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    sugiyama()
    for density in (20, 25, 30, 35, 40, 45):
        highway(density, plot=density in (25, 35))


if __name__ == "__main__":
    main()
