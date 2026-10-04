# -*- coding: utf-8 -*-
"""
ep4の交通の筋書き: 3車線の交通流の計算、動画のフレーム→計算上の時刻の対応(早送り)、車種。
Blenderに依存しない(Blender内のnumpyでも.venvでも動く)。計算結果はep4/cacheにキャッシュする。

筋書き: 緩い上り坂(サグ部)から大渋滞が育っていく。
- 1車線あたり30台/km、時速約61kmの流れ。車間は平均の±8%でばらつかせる(等間隔だと車が格子模様に並んで見える。
  ばらつきを大きくすると、坂と関係なくあちこちで渋滞が生まれてしまう)
- 坂ではドライバーが坂に気づかずに加速が鈍り(加速×0.6)、車間も少し開く(車間時間×1.5)。通れる台数が減り、
  坂の入口から渋滞が後ろへ一続きに伸びていく(計算の20秒で約60m、40秒で約160m、80秒で約350m)。
  坂の上の車はアクセルを緩めて遅くなるだけで、ブレーキを踏むのはその後ろの車
- 1つの計算を最後まで流し、映像のスピードだけを等速→2倍→3倍に上げる(途中で別の計算に切り替えない)

試して使わなかったもの(lessons/LESSONS_4.md): 平らな道の1台のブレーキ(10台前後の塊にしかならない)・
運転のゆらぎ・左右/上下2分割の比較・昼の図解。

計算上の道路は周期境界(円環と同じ条件)。画面の道路にはその一部を直線として映す。
"""
import os
import random

import numpy as np
from shots import FPS, OUR_LANE_X, ROAD_END, ROAD_START, SAG_START, TOTAL_FRAMES
from traffic_sim import KMH, Driver, Sag, equilibrium_speed, simulate_ring

CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache", "traffic.npz")
CACHE_VERSION = 11  # 筋書きやパラメータを変えたら上げる(古いキャッシュを使わないため)

DRIVER = Driver()  # 車間時間1.5秒・反応の遅れ1秒(高速道路の標準的な値)
RING_LENGTH = 5000.0  # 計算上の道路の1周(m)
CARS_PER_LANE = 150  # 1kmあたり30台
GAP_SPREAD = 0.08  # 車間のばらつき(平均の±8%)
SAG_RING = (2000.0, 2400.0)  # 計算上の道路での坂の区間(画面の道路の上り坂の始まりSAG_STARTに合わせる)
SAG_FACTORS = (1.5, 0.6)  # 坂での車間時間・加速の倍率
SEED = 7

CAR_LENGTH = {"sedan": 4.6, "van": 4.7, "truck": 8.9}
TRUCK_RATIO = 0.12
VAN_RATIO = 0.18

# 映像のスピード: (フレーム, 倍率)。キーの間はなめらかにつなぐ。倍率は画面に表示する(04_encode_video.py)
SPEED_KEYS = [(1, 1.0), (120, 1.0), (205, 2.0), (420, 2.0), (450, 3.0), (TOTAL_FRAMES, 3.0)]

ONCOMING_SPEED = 95 * KMH
ONCOMING_HEADWAY = (35.0, 90.0)


def car_kinds(lane):
    rng = random.Random(SEED * 10 + lane)
    kinds = []
    for _ in range(CARS_PER_LANE):
        r = rng.random()
        kinds.append("truck" if r < TRUCK_RATIO else "van" if r < TRUCK_RATIO + VAN_RATIO else "sedan")
    return kinds


def _lane_layout(lane):
    """車間を平均の±GAP_SPREADでばらつかせた配置(車線ごとに乱数を変える)。"""
    kinds = car_kinds(lane)
    lengths = np.array([CAR_LENGTH[k] for k in kinds])
    rng = np.random.default_rng(SEED + lane)
    mean_gap = (RING_LENGTH - lengths.sum()) / len(kinds)
    gaps = mean_gap * (1 + rng.uniform(-GAP_SPREAD, GAP_SPREAD, len(kinds)))
    gaps *= (RING_LENGTH - lengths.sum()) / gaps.sum()
    x = np.concatenate([[0.0], np.cumsum(lengths[:-1] + gaps[:-1])]) + rng.uniform(0, mean_gap)
    return kinds, lengths, x, mean_gap


def _simulate(duration):
    lanes = []
    for lane in range(len(OUR_LANE_X)):
        kinds, lengths, x0, mean_gap = _lane_layout(lane)
        r = simulate_ring(len(kinds), RING_LENGTH, DRIVER, duration, initial_speed=equilibrium_speed(mean_gap, DRIVER),
                          initial_x=x0, lengths=lengths, sag=Sag(*SAG_RING, *SAG_FACTORS))
        if r.collisions:
            raise RuntimeError(f"lane {lane}: {r.collisions} collisions")
        lanes.append(dict(t=r.t, x=r.x, v=r.v, acc=r.acc, length=RING_LENGTH, offset=SAG_START - SAG_RING[0]))
    return lanes


def load():
    """3車線ぶんの計算結果。"""
    if os.path.exists(CACHE_PATH):
        data = np.load(CACHE_PATH, allow_pickle=True)
        if int(data["version"]) == CACHE_VERSION:
            return list(data["lanes"])
    lanes = _simulate(sim_time(TOTAL_FRAMES) + 5)
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    np.savez_compressed(CACHE_PATH, version=CACHE_VERSION, lanes=np.array(lanes, dtype=object))
    return lanes


# ============================================================
# フレーム → 計算上の時刻
# ============================================================
def speed_factor(frame):
    for (f0, s0), (f1, s1) in zip(SPEED_KEYS, SPEED_KEYS[1:]):
        if f0 <= frame <= f1:
            u = (frame - f0) / (f1 - f0)
            return s0 + (s1 - s0) * u * u * (3 - 2 * u)
    return SPEED_KEYS[-1][1]


def _cumulative_sim_time():
    """フレーム1からの計算上の経過時間(倍率を積分)。"""
    t = np.zeros(TOTAL_FRAMES + 2)
    for f in range(2, TOTAL_FRAMES + 2):
        t[f] = t[f - 1] + (speed_factor(f - 1) + speed_factor(f)) / 2 / FPS
    return t


_CUM = _cumulative_sim_time()


def sim_time(frame):
    """計算上の時刻(計算の始まりがフレーム1)。"""
    f = min(max(frame, 1), TOTAL_FRAMES + 1)
    return _CUM[int(f)]


# ============================================================
# フレームごとの車の状態
# ============================================================
def lane_state(lane_data, t):
    """計算上の時刻tでの、各車の画面上のy・速度・加速度(記録の間は線形補間)。"""
    ts = lane_data["t"]
    i = int(np.clip(np.searchsorted(ts, t) - 1, 0, len(ts) - 2))
    u = float(np.clip((t - ts[i]) / (ts[i + 1] - ts[i]), 0.0, 1.0))
    x = lane_data["x"][i] * (1 - u) + lane_data["x"][i + 1] * u
    v = lane_data["v"][i] * (1 - u) + lane_data["v"][i + 1] * u
    acc = lane_data["acc"][i] * (1 - u) + lane_data["acc"][i + 1] * u
    y = (x + lane_data["offset"] - ROAD_START) % lane_data["length"] + ROAD_START
    return y, v, acc


def visible(y, length):
    return ROAD_START + 5.0 < y < ROAD_END - length


def oncoming_layout():
    rng = random.Random(SEED + 99)
    cars = []
    for lane in range(3):
        y = ROAD_START + rng.uniform(0, 40)
        while y < ROAD_END:
            r = rng.random()
            kind = "truck" if r < TRUCK_RATIO else "van" if r < TRUCK_RATIO + VAN_RATIO else "sedan"
            cars.append((lane, y, kind))
            y += rng.uniform(*ONCOMING_HEADWAY)
    return cars


def oncoming_y(y0, t):
    """対向車(-Y方向へ一定速度)。道路の範囲で周期的に回す。"""
    span = ROAD_END - ROAD_START
    return (y0 - ONCOMING_SPEED * t - ROAD_START) % span + ROAD_START


# ============================================================
# ノロノロ運転の車の台数(画面に数字で出す)
# ============================================================
# 最初は渋滞の「長さ」を出したが、見た目より長く感じた(「実際の列より数値が大きく感じる」)。時速40km以下だと、ほぼ白に
# 見える薄いオレンジの点まで数えていた。基準を下げると、一番赤い塊は渋滞の波として坂から後ろへ離れていくので、
# 「どこからどこまでを列と呼ぶか」で長さがいくらでも変わる。画面で赤〜オレンジに見える点そのものの台数にした
SLOW_SPEED = 20 * KMH  # 光の点の色で赤〜オレンジに見える速さ(DOT_COLORS: 0km/hで赤、12km/hでオレンジ、40km/hでほぼ白)
SLOW_SMOOTH = 4.0  # 計算上の秒。前後の平均で、1台ずつの出入りによる数字のちらつきをならす(この筋書きでは一度も減らない)
_SLOW_STEP = 0.25
_slow_curve = None


def slow_car_count(lanes, t):
    """道路の上の、時速SLOW_SPEEDより遅い車の台数(3車線の合計)。"""
    global _slow_curve
    if _slow_curve is None:
        ts = np.arange(0.0, sim_time(TOTAL_FRAMES) + _SLOW_STEP, _SLOW_STEP)
        raw = []
        for x in ts:
            n = 0
            for lane in lanes:
                y, v, _ = lane_state(lane, x)
                n += int(((v < SLOW_SPEED) & (y > ROAD_START) & (y < ROAD_END)).sum())
            raw.append(n)
        raw = np.array(raw, float)
        k = int(SLOW_SMOOTH / _SLOW_STEP) // 2
        _slow_curve = (ts, np.array([raw[max(0, i - k):i + k + 1].mean() for i in range(len(raw))]))
    ts, curve = _slow_curve
    return float(np.interp(t, ts, curve))
