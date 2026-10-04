# -*- coding: utf-8 -*-
"""
Stage 5: 走行音とBGMを30秒の音声に組む(このマシンにffmpegは無いので、mp3はmacOSのafconvertでwavにしてnumpyで混ぜる)

- 走行音: 生成した10秒のうち、1台の通過音が入っていない一定の区間(TRAFFIC_STEADY)を、つなぎ目をクロスフェードして
  繰り返し、映像の0〜4秒に置く。上昇の始まり(4秒)から小さくして7秒で消す
- BGM: 曲は26.2秒でぶつっと止まる(その後2秒ほど余韻)。止まる位置を映像の終わりに合わせるため、曲の頭を
  BGM_OFFSET秒ずらして置き、上昇の始まり(4秒)のあたりで入れる。最後は映像の終わりで短くフェードして切る

実行:
  .venv/bin/python ep4/scripts/05_mix_audio.py
出力の wav を 04_encode_video.py の AUDIO_PATH に指定する。
"""
import os
import subprocess
import tempfile
import wave

import numpy as np

EP4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRAFFIC_PATH = os.path.join(EP4, "constant-highway-traffic-noise-as_100426.mp3")
BGM_PATH = os.path.join(EP4, "instrumental-electronic-track-exactly-30_100426.mp3")  # 1曲目(minimal-...)は盛り上がらず不採用
OUTPUT_PATH = os.path.join(EP4, "Rikenomics_Episode04_mix.wav")

SR = 44100
DURATION = 30.0
TRAFFIC_STEADY = (5.5, 9.5)  # 秒。2〜5秒には1台の通過音(音量の山)が入っているので使わない
TRAFFIC_LEVEL_DB = -20.0  # 走行音の大きさ(RMS)
TRAFFIC_FADE = (4.0, 7.0)  # この間に走行音を消す
BGM_OFFSET = 3.5  # 曲の頭を置く映像の秒数(曲が止まる26.2秒が映像の29.7秒になる)
BGM_RISE = (3.5, 5.0)  # この間にBGMを0から本来の大きさへ上げる
END_FADE = (29.8, 30.0)  # 余韻を映像の終わりで切る
CROSSFADE = 0.5  # 走行音を繰り返すつなぎ目(秒)
PEAK_DB = -1.0


def load(path):
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = os.path.join(tmp, "a.wav")
        subprocess.run(["afconvert", "-f", "WAVE", "-d", f"LEI16@{SR}", "-c", "2", path, wav_path], check=True)
        with wave.open(wav_path) as w:
            x = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, 2) / 32768.0
    return x


def db(v):
    return 10 ** (v / 20)


def ramp(t, t0, t1, a, b):
    """t0→t1でaからbへ(音量が自然に聞こえるよう、なめらかに)。"""
    u = np.clip((t - t0) / (t1 - t0), 0, 1)
    return a + (b - a) * (0.5 - 0.5 * np.cos(np.pi * u))


def traffic_bed(src, n):
    """一定の区間を、つなぎ目をクロスフェードしながらn サンプルぶん繰り返す。"""
    seg = src[int(TRAFFIC_STEADY[0] * SR):int(TRAFFIC_STEADY[1] * SR)]
    xf = int(CROSSFADE * SR)
    fade = np.sqrt(np.linspace(0, 1, xf))[:, None]  # 等パワー
    out = seg.copy()
    while len(out) < n:
        out = np.concatenate([out[:-xf], out[-xf:] * fade[::-1] + seg[:xf] * fade, seg[xf:]])
    return out[:n]


def main():
    n = int(DURATION * SR)
    t = np.arange(n)[:, None] / SR

    traffic = traffic_bed(load(TRAFFIC_PATH), n)
    traffic *= db(TRAFFIC_LEVEL_DB) / np.sqrt((traffic ** 2).mean())
    traffic *= ramp(t, 0.0, 0.3, 0.0, 1.0) * ramp(t, *TRAFFIC_FADE, 1.0, 0.0)

    off = int(BGM_OFFSET * SR)
    bgm = load(BGM_PATH)[:n - off]
    bgm = np.pad(bgm, ((off, n - off - len(bgm)), (0, 0)))
    bgm *= ramp(t, *BGM_RISE, 0.0, 1.0) * ramp(t, *END_FADE, 1.0, 0.0)

    mix = traffic + bgm
    mix *= db(PEAK_DB) / np.abs(mix).max()
    with wave.open(OUTPUT_PATH, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((mix * 32767).astype(np.int16).tobytes())
    for s in (0, 2, 4, 5, 6, 7, 10, 20, 27, 29, 29.5):
        seg = mix[int(s * SR):int((s + 0.5) * SR)]
        print(f"[Stage5] {s:4.1f}s  {20 * np.log10(np.sqrt((seg ** 2).mean()) + 1e-9):6.1f} dB")
    print("[Stage5] written:", OUTPUT_PATH)


if __name__ == "__main__":
    main()
