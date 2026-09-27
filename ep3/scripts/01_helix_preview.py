"""
00_orbital_parameters.pyで求めた伸び率(D/C比)をそのままピッチに反映した螺旋を描き、
Blender着手前に見た目の妥当性(密に巻いた渦になっていないか)を確認する。

出力: ep3/scripts/preview_helix.png (確認用、git管理対象外)
"""

import importlib.util
import math
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("orbital_parameters", HERE / "00_orbital_parameters.py")
orbital_parameters = importlib.util.module_from_spec(spec)
spec.loader.exec_module(orbital_parameters)

PLANETS = orbital_parameters.PLANETS
stretch_ratio = orbital_parameters.stretch_ratio

# 表示する惑星と色(内側=密、外側=疎のグラデーションが分かるように選定)
DISPLAY = ["Mercury", "Venus", "Earth", "Mars", "Jupiter", "Neptune"]
N_ORBITS = 3  # 各惑星につき描く周回数


def helix_points(a_au: float, ratio: float, n_orbits: float, n_points: int = 2000):
    """半径a_au、1周あたりの前進距離がa_auの円周のratio倍の螺旋を返す(x=前進方向, y, z=軌道面)。"""
    theta = np.linspace(0, 2 * math.pi * n_orbits, n_points)
    pitch = ratio * (2 * math.pi * a_au)  # 1周(2π)あたりの前進距離
    x = pitch * theta / (2 * math.pi)
    y = a_au * np.cos(theta)
    z = a_au * np.sin(theta)
    return x, y, z


def main():
    fig, axes = plt.subplots(len(DISPLAY), 1, figsize=(10, 2.2 * len(DISPLAY)), sharex=False)
    for ax, name in zip(axes, DISPLAY):
        a_au, period_years = PLANETS[name]
        ratio = stretch_ratio(a_au, period_years)
        x, y, _ = helix_points(a_au, ratio, N_ORBITS)
        ax.plot(x, y, lw=1)
        ax.set_aspect("equal")
        ax.set_title(f"{name}  a={a_au}AU  D/C比={ratio:.1f}")
        ax.set_yticks([])
    fig.tight_layout()
    out_path = HERE / "preview_helix.png"
    fig.savefig(out_path, dpi=120)
    print(f"saved: {out_path}")


if __name__ == "__main__":
    main()
