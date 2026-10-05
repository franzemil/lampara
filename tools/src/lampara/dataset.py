"""Dataset utilities: validation stats and 10 s -> 1 s splitting."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import soundfile as sf


@dataclass
class FolderStats:
    label: str
    total: int
    format_ok: int
    duration_ok: int
    duration_range: tuple[float, float] | None

    @property
    def issues(self) -> int:
        return (self.total - self.format_ok) + (self.total - self.duration_ok)


def stats(dataset_dir: Path) -> list[FolderStats]:
    results: list[FolderStats] = []
    for label_dir in sorted(d for d in dataset_dir.iterdir() if d.is_dir()):
        files = sorted(label_dir.glob("*.wav"))
        if not files:
            results.append(FolderStats(label_dir.name, 0, 0, 0, None))
            continue
        fmt_ok = dur_ok = 0
        durations: list[float] = []
        for f in files:
            info = sf.info(str(f))
            if info.samplerate == 16000 and info.channels == 1 and info.subtype == "PCM_16":
                fmt_ok += 1
            dur = info.frames / info.samplerate
            durations.append(dur)
            if 0.95 <= dur <= 1.05:
                dur_ok += 1
        results.append(
            FolderStats(
                label=label_dir.name,
                total=len(files),
                format_ok=fmt_ok,
                duration_ok=dur_ok,
                duration_range=(min(durations), max(durations)),
            )
        )
    return results


def split_recording(recording: Path, label: str, dataset_dir: Path, dry_run: bool = False) -> list[Path]:
    from . import ffmpeg

    out_dir = dataset_dir / label
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = out_dir / f"{recording.stem}_%02d.wav"
    ffmpeg.ffmpeg(
        [
            "-i",
            str(recording),
            "-f",
            "segment",
            "-segment_time",
            "1",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(pattern),
        ],
        dry_run=dry_run,
    )
    if dry_run:
        return []
    return sorted(out_dir.glob(f"{recording.stem}_*.wav"))


def write_wav(path: Path, values: list[int], samplerate: int = 16000) -> Path:
    import numpy as np

    path.parent.mkdir(parents=True, exist_ok=True)
    data = np.clip(np.asarray(values, dtype=np.int32), -32768, 32767).astype("<i2")
    sf.write(str(path), data, samplerate, subtype="PCM_16")
    return path
