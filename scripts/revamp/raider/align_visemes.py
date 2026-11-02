"""Align SAPI viseme times to the WAV they were spoken into.

SAPI's VisemeReached times ran about 1.4x long against the 22,050 Hz WAV it wrote (they assume another sample
rate), so the mouth fell behind the voice. The speech span is measured in the WAV (a 20 ms amplitude envelope
above 5% of its peak) and the non-silent visemes are rescaled linearly onto it.

  python align_visemes.py <speech_dir>      (reads line.wav and visemes.json; writes visemes-aligned.json)
"""
import json
import sys
import wave
from pathlib import Path

import numpy as np

d = Path(sys.argv[1])
w = wave.open(str(d / "line.wav"))
sr, n, ch, sw = w.getframerate(), w.getnframes(), w.getnchannels(), w.getsampwidth()
a = np.frombuffer(w.readframes(n), dtype=np.int16 if sw == 2 else np.uint8).astype(np.float32)
if ch > 1:
    a = a.reshape(-1, ch).mean(1)
win = int(sr * 0.02)
env = np.convolve(np.abs(a), np.ones(win) / win, mode="same")
on = np.nonzero(env > env.max() * 0.05)[0]
s0, s1 = on[0] / sr, on[-1] / sr
data = json.load(open(d / "visemes.json", encoding="utf-8-sig"))
V = data["visemes"]
spoken = [v for v in V if v["v"] != 0]
v0, v1 = spoken[0]["t"], spoken[-1]["t"] + spoken[-1]["d"]
k = (s1 - s0) / (v1 - v0)
for v in V:
    v["t"] = s0 + (v["t"] - v0) * k
    v["d"] = v["d"] * k
data["visemes"] = V
data["aligned"] = {"sample_rate": sr, "audio_speech_s": [round(s0, 3), round(s1, 3)],
                   "viseme_speech_s": [round(v0, 3), round(v1, 3)], "scale": round(k, 4)}
json.dump(data, open(d / "visemes-aligned.json", "w"), indent=1)
print("ALIGN_OK sample rate", sr, "speech", round(s0, 2), "-", round(s1, 2), "s, scale", round(k, 4))
