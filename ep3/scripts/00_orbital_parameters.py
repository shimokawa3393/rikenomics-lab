"""
第3話「太陽系の螺旋」着手前の実測計算。

太陽の銀河公転速度(約220km/s)を基準に、各惑星の軌道を1周する間に
銀河基準でどれだけ前進するか(D)と、その軌道の円周(C)の比率(D/C)を求める。
この比率が大きいほど、螺旋は「密に巻いた渦」ではなく「引き伸ばされた緩いバネ」に近づく。

Blender側のジオメトリ生成(Stage1)は、この比率を使って各惑星の螺旋の
ピッチ(1周あたりの前進距離)を実際の速度比通りに描くこと。感覚的な
「きりのいい数字」を使わない(ep2 LESSONSの教訓と同根)。
"""

import math

AU_KM = 1.495978707e8  # 1天文単位(km)
YEAR_S = 3.15576e7  # 1年(秒)
SUN_GALACTIC_VELOCITY_KMS = 220.0  # 太陽の銀河公転速度(秒速約220km)

# 惑星: (軌道長半径[AU], 公転周期[年])
PLANETS = {
    "Mercury": (0.387, 0.241),
    "Venus": (0.723, 0.615),
    "Earth": (1.000, 1.000),
    "Mars": (1.524, 1.881),
    "Jupiter": (5.203, 11.86),
    "Saturn": (9.537, 29.46),
    "Uranus": (19.191, 84.01),
    "Neptune": (30.069, 164.8),
}


def stretch_ratio(a_au: float, period_years: float) -> float:
    """1周の間に銀河基準で前進する距離(D)と軌道円周(C)の比率 D/C を返す。"""
    period_s = period_years * YEAR_S
    advance_km = SUN_GALACTIC_VELOCITY_KMS * period_s
    circumference_km = 2 * math.pi * a_au * AU_KM
    return advance_km / circumference_km


def main():
    print(f"{'Planet':<10}{'a[AU]':>8}{'T[yr]':>8}{'D/C比':>10}")
    for name, (a_au, period_years) in PLANETS.items():
        ratio = stretch_ratio(a_au, period_years)
        print(f"{name:<10}{a_au:>8.3f}{period_years:>8.2f}{ratio:>10.2f}")


if __name__ == "__main__":
    main()
