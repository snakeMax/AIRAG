"""Builds AIRAG's default sound effects (short, soft tones) into web/sounds/.

They're generated here rather than downloaded, so there are no licence questions.
Run: python tools/make_sounds.py
"""
import math
import struct
import wave
from pathlib import Path

RATE = 22050
OUT = Path(__file__).resolve().parent.parent / "web" / "sounds"


def tone(freq, dur, vol=0.5, attack=0.008, release=None, freq_end=None, harmonics=((1, 1.0), (2, 0.18), (3, 0.06))):
    n = int(RATE * dur)
    release = release if release is not None else dur * 0.85
    out, phase = [], 0.0
    for i in range(n):
        t = i / RATE
        f = freq if freq_end is None else freq + (freq_end - freq) * (t / dur)
        phase += 2 * math.pi * f / RATE
        env = min(1.0, t / attack) * math.exp(-max(0.0, t - attack) / (release / 4.5))
        s = sum(a * math.sin(phase * k) for k, a in harmonics) / sum(a for _, a in harmonics)
        out.append(s * env * vol)
    return out


def silence(dur):
    return [0.0] * int(RATE * dur)


def mix(*parts_at):
    """parts_at: (start_seconds, samples)"""
    end = max(int(st * RATE) + len(p) for st, p in parts_at)
    buf = [0.0] * end
    for st, p in parts_at:
        o = int(st * RATE)
        for i, v in enumerate(p):
            buf[o + i] += v
    peak = max(1e-9, max(abs(v) for v in buf))
    return [v / peak * 0.8 for v in buf] if peak > 0.8 else buf


def write(name, samples):
    OUT.mkdir(parents=True, exist_ok=True)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(max(-1, min(1, v)) * 32767)) for v in samples))


# mic starts listening: quick rising two-note "bip"
write("mic-start.wav", mix((0, tone(660, 0.09, 0.45)), (0.07, tone(990, 0.14, 0.45))))
# mic stops: the same two notes falling
write("mic-stop.wav", mix((0, tone(990, 0.09, 0.4)), (0.07, tone(660, 0.16, 0.4))))
# search finished: soft three-note major chime
write("search-done.wav", mix((0, tone(784, 0.5, 0.35)), (0.09, tone(988, 0.5, 0.33)), (0.18, tone(1175, 0.7, 0.33))))
# explainer finished: playful sparkle (quick glide up + bell)
write("explainer-done.wav", mix((0, tone(523, 0.18, 0.3, freq_end=1046)), (0.16, tone(1568, 0.6, 0.3, harmonics=((1, 1), (2.76, 0.3), (5.4, 0.1)))),
                                (0.26, tone(2093, 0.5, 0.18, harmonics=((1, 1), (2.76, 0.25))))))
# a task failed or was stopped: low, short two-tone
write("task-failed.wav", mix((0, tone(440, 0.16, 0.38)), (0.13, tone(330, 0.3, 0.38))))
print("sounds written to", OUT)
