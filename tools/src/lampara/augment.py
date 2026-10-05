"""Audio augmentation: variant plan generation (pure, testable) and ffmpeg execution."""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path

from . import ffmpeg


@dataclass(frozen=True)
class Variant:
    index: int
    gain: float
    tempo: float | None
    pitch: float | None
    bg_mix: float | None
    bg_file: Path | None
    echo: bool

    def describe(self) -> str:
        parts = [f"gain={self.gain:.2f}"]
        if self.tempo is not None:
            parts.append(f"tempo={self.tempo:.2f}")
        if self.pitch is not None:
            parts.append(f"pitch=x{self.pitch:.2f}")
        if self.bg_mix is not None:
            parts.append(f"bg={self.bg_file.name if self.bg_file else '?'}@{self.bg_mix:.2f}")
        if self.echo:
            parts.append("echo")
        return " ".join(parts)


GAINS = (0.7, 0.85, 1.15, 1.3)
TEMPOS = (0.92, 1.08)
PITCHES = (0.94, 1.06)
BG_MIXES = (0.05, 0.10, 0.15)


def plan_variants(
    count: int,
    background_pool: list[Path],
    seed: int | None = None,
) -> list[Variant]:
    rng = random.Random(seed)
    variants: list[Variant] = []
    for i in range(count):
        transforms: dict[str, object] = {"echo": False}
        picks = ["gain"]
        extra = [c for c in ("tempo", "pitch", "bg") if rng.random() < 0.6][:1]
        picks += extra
        if "bg" in picks and background_pool:
            picks.append("bg")
        for pick in picks:
            if pick == "gain":
                transforms["gain"] = rng.choice(GAINS)
            elif pick == "tempo":
                transforms["tempo"] = rng.choice(TEMPOS)
            elif pick == "pitch":
                transforms["pitch"] = rng.choice(PITCHES)
            elif pick == "bg" and background_pool:
                transforms["bg_mix"] = rng.choice(BG_MIXES)
                transforms["bg_file"] = rng.choice(background_pool)
        if rng.random() < 0.2:
            transforms["echo"] = True
        variants.append(
            Variant(
                index=i + 1,
                gain=float(transforms.get("gain", 1.0)),
                tempo=transforms.get("tempo"),
                pitch=transforms.get("pitch"),
                bg_mix=transforms.get("bg_mix"),
                bg_file=transforms.get("bg_file"),
                echo=bool(transforms["echo"]),
            )
        )
    return variants


def _filters(variant: Variant, samplerate: int = 16000) -> list[str]:
    chain: list[str] = []
    if variant.pitch is not None:
        chain.append(f"asetrate={int(samplerate * variant.pitch)}")
        chain.append(f"aresample={samplerate}")
    if variant.tempo is not None:
        chain.append(f"atempo={variant.tempo:.2f}")
    chain.append(f"volume={variant.gain:.2f}")
    if variant.echo:
        chain.append("aecho=0.8:0.6:50:0.3")
    return chain


def augment_file(
    source: Path,
    out: Path,
    variant: Variant,
    dry_run: bool = False,
) -> Path:
    chain = _filters(variant)
    tail = "apad=whole_dur=1,atrim=0:1"
    if variant.bg_file is not None and variant.bg_mix is not None:
        mix_chain = ",".join([*chain, tail])
        ffmpeg.ffmpeg(
            [
                "-i",
                str(source),
                "-i",
                str(variant.bg_file),
                "-filter_complex",
                f"[1:a]volume={variant.bg_mix:.2f}[bg];[0:a][bg]amix=inputs=2:duration=first:normalize=0,{mix_chain}",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(out),
            ],
            dry_run=dry_run,
        )
    else:
        ffmpeg.ffmpeg(
            ["-i", str(source), "-af", ",".join([*chain, tail]), "-ar", "16000", "-ac", "1", str(out)],
            dry_run=dry_run,
        )
    return out


def augment_dataset(
    dataset_dir: Path,
    variants_per_file: int = 4,
    background_pool: list[Path] | None = None,
    seed: int | None = None,
    labels: tuple[str, ...] = ("enciende", "apaga", "noise"),
    dry_run: bool = False,
) -> list[Path]:
    pool = background_pool or []
    created: list[Path] = []
    counter = random.Random(seed)
    for label in labels:
        folder = dataset_dir / label
        if not folder.is_dir():
            continue
        for wav in sorted(folder.glob("*.wav")):
            if wav.stem.startswith("aug_"):
                continue
            plans = plan_variants(variants_per_file, pool, seed=counter.randrange(2**31))
            for variant in plans:
                out = folder / f"aug_{wav.stem}_{variant.index}.wav"
                augment_file(wav, out, variant, dry_run=dry_run)
                created.append(out)
    return created
