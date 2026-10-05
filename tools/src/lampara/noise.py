"""Synthetic noise generation (ffmpeg anoisesrc / sine) and ESC-50 windowing."""

from __future__ import annotations

import random
from pathlib import Path

from . import ffmpeg

COLORS = ("white", "pink", "brown")
AMPS = (0.05, 0.10, 0.15, 0.20, 0.25, 0.30)


def build_synthetic(noise_dir: Path, seed: int | None = None, dry_run: bool = False) -> dict[str, int]:
    rng = random.Random(seed)
    noise_dir.mkdir(parents=True, exist_ok=True)
    counts = {"color": 0, "burst": 0, "hum": 0, "rumble": 0}

    for color in COLORS:
        for i in range(1, 21):
            amp = AMPS[(i - 1) % len(AMPS)]
            out = noise_dir / f"syn_color_{color}_{i:02d}.wav"
            ffmpeg.ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"anoisesrc=color={color}:duration=1:amplitude={amp}:seed={rng.randrange(2**31)}",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(out),
                ],
                dry_run=dry_run,
            )
            counts["color"] += 1

    n = 0
    for color in COLORS:
        for freq in (1, 2, 3):
            for depth in (0.7, 0.9):
                for amp in (0.15, 0.30):
                    n += 1
                    out = noise_dir / f"syn_burst_{n:02d}.wav"
                    ffmpeg.ffmpeg(
                        [
                            "-f",
                            "lavfi",
                            "-i",
                            f"anoisesrc=color={color}:duration=1:amplitude={amp}:seed={rng.randrange(2**31)}",
                            "-af",
                            f"tremolo=f={freq}:d={depth}",
                            "-ar",
                            "16000",
                            "-ac",
                            "1",
                            str(out),
                        ],
                        dry_run=dry_run,
                    )
                    counts["burst"] += 1

    n = 0
    for freq in (50, 100, 120):
        for gain in (0.02, 0.05):
            n += 1
            out = noise_dir / f"syn_hum_{n:02d}.wav"
            ffmpeg.ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"sine=frequency={freq}:duration=1",
                    "-f",
                    "lavfi",
                    "-i",
                    f"anoisesrc=color=white:duration=1:amplitude=0.1:seed={rng.randrange(2**31)}",
                    "-filter_complex",
                    "amix=inputs=2:duration=first,volume=3.0",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(out),
                ],
                dry_run=dry_run,
            )
            counts["hum"] += 1

    n = 0
    for cutoff in (200, 500, 1000):
        for _ in range(4):
            n += 1
            out = noise_dir / f"syn_rumble_{n:02d}.wav"
            ffmpeg.ffmpeg(
                [
                    "-f",
                    "lavfi",
                    "-i",
                    f"anoisesrc=color=white:duration=1:amplitude=0.4:seed={rng.randrange(2**31)}",
                    "-af",
                    f"lowpass=f={cutoff}",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(out),
                ],
                dry_run=dry_run,
            )
            counts["rumble"] += 1
    return counts


def build_esc50_windows(esc50_cache: Path, noise_dir: Path, dry_run: bool = False) -> int:
    if not esc50_cache.is_dir():
        return 0
    noise_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for f in sorted(esc50_cache.iterdir()):
        if not f.is_file():
            continue
        for start in (0.5, 2.0, 3.5):
            out = noise_dir / f"esc_{f.stem}_{str(start).replace('.', '-')}.wav"
            ffmpeg.ffmpeg(
                ["-i", str(f), "-ss", str(start), "-t", "1", "-ar", "16000", "-ac", "1", str(out)],
                dry_run=dry_run,
            )
            count += 1
    return count
