#!/usr/bin/env python3
"""Generate the battery "locate me" clip: device/termux/assets/battery-colors/locate.mp3,
plus the copy stayturgid-agent plays (app/src/main/res/raw/locate.mp3, 2026-10-08).

Design (2026-10-05): broadband sounds with sharp onsets are much easier to locate than
pure tones, which the ear localizes worst between 1 and 4 kHz (IRSST / University of
Ottawa reverse-alarm studies: broadband alarms gave markedly better localization and far
fewer front-back confusions). To keep it pleasant rather than a hiss, each note is a
rising major-triad marimba-like strike (rich, inharmonic partials spread across the
spectrum) with a short filtered-noise "tick" on the attack, repeated with gaps so every
onset is a fresh localization cue. 4.0 s long; the player loops it.

    python3 control/tools/gen_locate_sound.py   # needs numpy + ffmpeg (libmp3lame)
"""

import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
CLIP_SEC = 4.0  # keep in sync with SOUND_CLIP_SEC in stayturgid_battery_alarm.py
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "device/termux/assets/battery-colors/locate.mp3"
AGENT_COPY = ROOT / "device/native-agent/app/src/main/res/raw/locate.mp3"
NOTES = [659.25, 830.61, 987.77, 1318.5]  # E5 G#5 B5 E6
PARTIALS = [(1.0, 1.0, 0.9), (2.0, 0.5, 0.5), (3.0, 0.35, 0.35), (4.07, 0.3, 0.22), (6.8, 0.2, 0.12)]


RNG = np.random.default_rng(7)  # fixed seed: regenerating gives the same file


def strike(freq, dur=0.6):
    t = np.arange(int(SR * dur)) / SR
    tone = sum(a * np.sin(2 * np.pi * freq * k * t) * np.exp(-t / d) for k, a, d in PARTIALS)
    noise = RNG.standard_normal(t.size) * np.exp(-t / 0.025)
    noise = np.convolve(noise, [1, -0.6], mode="same")  # tilt toward highs for a crisp tick
    attack = np.minimum(1.0, t / 0.002)
    return attack * (0.75 * tone / 2.5 + 0.35 * noise)


def main():
    clip = np.zeros(int(SR * CLIP_SEC))
    for start in (0.0, 1.9):  # two phrases per clip, with a breath between them
        for i, f in enumerate(NOTES):
            s = strike(f)
            at = int(SR * (start + 0.16 * i))
            clip[at : at + s.size] += s[: clip.size - at]
    clip = np.tanh(1.6 * clip)  # gentle saturation: louder on a phone speaker, no clipping
    clip *= 0.95 / np.max(np.abs(clip))
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "locate.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes((clip * 32767).astype("<i2").tobytes())
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "128k", str(OUT)],
            check=True,
        )
    shutil.copyfile(OUT, AGENT_COPY)
    print(OUT, AGENT_COPY)


if __name__ == "__main__":
    main()
