# -*- coding: utf-8 -*-
"""
交通流の計算(Blenderに依存しない。検証スクリプトとBlenderの両方から使う)。

モデル: Intelligent Driver Model (IDM, Treiber et al. 2000) に、人の反応の遅れを加えたもの。
ドライバーはREACTION_TIME秒前に見えた前の車との車間・速度差に反応する(Human Driver Modelの考え方)。
小さな減速が後ろへ行くほど増幅されるのは、主にこの遅れと、車間を詰めすぎることによる。

道路は周期境界(先頭と最後尾をつないだ円環と同じ条件)で計算する。2008年の円環コース実験と同じく、
合流・出口・先頭のない一様な道路で、渋滞が外的な原因なしに生まれるかを扱える。
画面にはその一部の区間だけを直線として映す。
"""
from dataclasses import dataclass, field

import numpy as np

KMH = 1 / 3.6
SAFE_GAP = 25.0  # m。渋滞吸収運転の車も、車間がこれより詰まったら通常の運転のブレーキに従う


@dataclass
class Driver:
    """IDMのパラメータ(高速道路の標準的な値: Treiber & Kesting『Traffic Flow Dynamics』表11.2付近)。"""
    v0: float = 120 * KMH  # 希望速度
    T: float = 1.5  # 希望車間時間(秒)
    s0: float = 2.0  # 停止時の最小車間(m)
    a: float = 1.0  # 加速度(m/s²)
    b: float = 1.5  # 心地よい減速度(m/s²)
    delta: float = 4.0
    reaction_time: float = 1.0  # 反応の遅れ(秒)
    length: float = 4.7  # 車長(m)
    look_two_ahead: bool = False  # 前の前の車まで見て、そちらの方が強いブレーキを要するならそれに従う(先読みの運転)


@dataclass
class Perturbation:
    """1台が少しだけブレーキを踏む(time秒からduration秒間、decelで減速)。"""
    car: int
    time: float
    duration: float
    decel: float


@dataclass
class Control:
    """1台の走り方を変える(4a、渋滞吸収運転): time秒から、前の車を追わずにhold_speedを保つ(ramp秒かけて
    ゆるやかに速度を合わせる)。前の渋滞に追いつかない速さで近づくので、着く頃には渋滞が解けていて止まらずに済む。
    安全のため、車間が詰まったら通常の運転(IDM)の方が強いブレーキならそちらに従う。release秒以降は通常の運転に戻る。"""
    car: int
    time: float
    hold_speed: float
    ramp: float = 10.0
    release: float = 1e9


@dataclass
class Sag:
    """緩い上り坂(サグ部)の区間 [start, end)(計算上の道路の位置)。ここではドライバーが坂に気づかずに加速が鈍り、
    車間も少し開く(希望車間時間がT倍、加速がa倍)。通れる台数が減り、混んでいると後ろに車列が伸びる。"""
    start: float
    end: float
    T_factor: float = 1.4
    a_factor: float = 0.6


@dataclass
class Result:
    t: np.ndarray  # (T,)
    x: np.ndarray  # (T, N) 位置(周期境界をほどいた累積値)
    v: np.ndarray  # (T, N)
    acc: np.ndarray  # (T, N)
    length: float  # 道路(周期)の長さ
    collisions: int = 0
    params: dict = field(default_factory=dict)


def idm_acceleration(v, dv, gap, d: Driver, T=None, a=None):
    """dv = 自分の速度 - 前の車の速度(近づいていると正)。T・aは車ごとの配列で上書きできる(サグ部)。"""
    T = d.T if T is None else T
    a = d.a if a is None else a
    s_star = d.s0 + np.maximum(0.0, v * T + v * dv / (2 * np.sqrt(a * d.b)))
    return a * (1 - (v / d.v0) ** d.delta - (s_star / np.maximum(gap, 0.1)) ** 2)


def simulate_ring(n_cars, road_length, driver: Driver, duration, dt=0.05, record_dt=1 / 30,
                  initial_speed=None, position_noise=0.0, perturbations=(), seed=0, max_decel=9.0,
                  initial_x=None, lengths=None, controls=(), accel_noise=0.0, noise_interval=1.0, sag=None):
    """周期境界の一車線を計算する。車iの前の車はi+1(最後の車の前は先頭の車)。xは車の後端の位置。
    lengthsを渡すと車ごとの長さ(トラック等)で車間を計算する。initial_xを渡すとその配置から始める。
    accel_noiseを渡すと、全員の加速度にnoise_interval秒ごとに変わる小さなゆらぎ(標準偏差、m/s²)を加える
    (実際の運転では、アクセルの踏み加減や車間の見積もりが常に少しずつぶれる)。"""
    rng = np.random.default_rng(seed)
    spacing = road_length / n_cars
    lengths = np.full(n_cars, driver.length) if lengths is None else np.asarray(lengths, dtype=float)
    if initial_x is None:
        x = np.arange(n_cars) * spacing + rng.normal(0, position_noise, n_cars)
    else:
        x = np.asarray(initial_x, dtype=float) + rng.normal(0, position_noise, n_cars)
    if initial_speed is None:
        initial_speed = equilibrium_speed(spacing - driver.length, driver)
    v = np.full(n_cars, float(initial_speed))

    delay_steps = max(1, int(round(driver.reaction_time / dt)))
    hist_x = np.repeat(x[None], delay_steps + 1, axis=0)
    hist_v = np.repeat(v[None], delay_steps + 1, axis=0)
    record_every = max(1, int(round(record_dt / dt)))

    ts, xs, vs, accs = [], [], [], []
    collisions = 0
    noise = np.zeros(n_cars)
    noise_every = max(1, int(round(noise_interval / dt)))
    steps = int(round(duration / dt))
    for step in range(steps + 1):
        t = step * dt
        # 反応の遅れ: delay_steps前に見えた状態で判断する。バッファには時刻step-delay_steps〜stepの状態が
        # 入っていて、今の状態はstep番目、一番古い状態は(step+1)番目の枠にある
        oldest = (step + 1) % (delay_steps + 1)
        px, pv = hist_x[oldest], hist_v[oldest]
        leader = np.roll(np.arange(n_cars), -1)
        gap_seen = (px[leader] - px) % road_length - lengths
        T_arr = a_arr = None
        if sag is not None:
            pos = px % road_length
            on_sag = (pos >= sag.start) & (pos < sag.end)
            T_arr = np.where(on_sag, driver.T * sag.T_factor, driver.T)
            a_arr = np.where(on_sag, driver.a * sag.a_factor, driver.a)
        acc = idm_acceleration(pv, pv - pv[leader], gap_seen, driver, T_arr, a_arr)
        if driver.look_two_ahead:
            # 前の前の車との間(前の車の長さを除く)に対しても車間を測り、二台ぶんの希望車間を見込んで判断する
            second = np.roll(leader, -1)
            gap2 = (px[second] - px) % road_length - lengths - lengths[leader]
            acc2 = idm_acceleration(pv, pv - pv[second], gap2 / 2.0, driver, T_arr, a_arr)
            acc = np.minimum(acc, acc2)
        if accel_noise > 0:
            if step % noise_every == 0:
                noise = rng.normal(0.0, accel_noise, n_cars)
            acc = acc + noise
        for c in controls:
            if c.time <= t < c.release:
                # 今の速度から目標の速度へ、ramp秒程度でゆるやかに近づく(加減速は0.5m/s²まで)
                hold = np.clip((c.hold_speed - pv[c.car]) / c.ramp * 2, -0.5, 0.5)
                acc[c.car] = min(hold, acc[c.car]) if gap_seen[c.car] < SAFE_GAP else hold
        for p in perturbations:
            if p.time <= t < p.time + p.duration:
                acc[p.car] = -p.decel
        acc = np.maximum(acc, -max_decel)

        if step % record_every == 0:
            ts.append(t)
            xs.append(x.copy())
            vs.append(v.copy())
            accs.append(acc.copy())

        new_v = np.maximum(0.0, v + acc * dt)
        x = x + (v + new_v) / 2 * dt
        v = new_v
        # 安全装置: 実際の車間が車長を割ったら止める(本来は起きない。起きたらパラメータの見直しが必要)
        gap_now = (x[leader] - x) % road_length - lengths
        crashed = gap_now < 0.3
        if crashed.any():
            collisions += int(crashed.sum())
            v[crashed] = 0.0
        hist_x[(step + 1) % (delay_steps + 1)] = x
        hist_v[(step + 1) % (delay_steps + 1)] = v

    return Result(np.array(ts), np.array(xs), np.array(vs), np.array(accs), road_length, collisions,
                  dict(n_cars=n_cars, road_length=road_length, driver=driver, dt=dt))


def equilibrium_gap(v, d: Driver):
    """速度vで一様に流れるときの車間(IDMの加速度が0になる車間)。"""
    s_star = d.s0 + v * d.T
    return s_star / np.sqrt(max(1e-9, 1 - (v / d.v0) ** d.delta))


def equilibrium_speed(gap, d: Driver):
    """一様な流れのときの速度(IDMで加速度0になる速度を二分法で求める)。"""
    lo, hi = 0.0, d.v0
    for _ in range(60):
        mid = (lo + hi) / 2
        if idm_acceleration(np.array(mid), np.array(0.0), np.array(gap), d) > 0:
            lo = mid
        else:
            hi = mid
    return lo


def brake_level(acc, light_on=0.3, full=3.0):
    """ブレーキランプの明るさ(0〜1)。エンジンブレーキ程度の減速(light_on未満)では点かない。"""
    return np.clip((-acc - light_on) / (full - light_on), 0.0, 1.0) * (-acc >= light_on)


def jam_front_speed(result: Result, t_from, t_to, slow=5 * KMH):
    """渋滞の波が進む速さ(m/s、後ろ向きなら負)。止まりかけの車の位置(=渋滞の中)を時刻ごとに追い、直線で当てはめる。
    止まりかけの車が何台もあるときは、前の時刻の位置に一番近い車を選ぶ(別の渋滞に飛び移らないように)。
    周期境界をまたぐので、位置は前の時刻から近い方の周回にほどく。"""
    sel = (result.t >= t_from) & (result.t <= t_to)
    times, positions = [], []
    prev = None
    for t, x, v in zip(result.t[sel], result.x[sel], result.v[sel]):
        candidates = x[v < slow] % result.length
        if candidates.size == 0:
            continue
        if prev is None:
            pos = x[np.argmin(v)] % result.length
        else:
            unwrapped = candidates + np.round((prev - candidates) / result.length) * result.length
            pos = unwrapped[np.argmin(np.abs(unwrapped - prev))]
        times.append(t)
        positions.append(pos)
        prev = pos
    if len(times) < 10:
        return None
    return np.polyfit(times, positions, 1)[0]
