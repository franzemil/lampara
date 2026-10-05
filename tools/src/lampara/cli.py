"""Typer CLI entry point: sub-apps for dataset, noise, tts, ei and augment."""

from __future__ import annotations

from pathlib import Path

import typer

from . import config, dataset, ffmpeg, noise, tts
from .augment import augment_dataset, plan_variants
from .ei_api import EdgeImpulseClient

app = typer.Typer(help="Tooling for the lampara-aliz voice-controlled lamp.", no_args_is_help=True)
dataset_app = typer.Typer(help="Local dataset utilities.", no_args_is_help=True)
noise_app = typer.Typer(help="Synthetic noise generation.", no_args_is_help=True)
tts_app = typer.Typer(help="TTS sample generation (macOS say).", no_args_is_help=True)
ei_app = typer.Typer(help="Edge Impulse Studio data management.", no_args_is_help=True)
augment_app = typer.Typer(help="Audio augmentation pipeline.", no_args_is_help=True)

app.add_typer(dataset_app, name="dataset")
app.add_typer(noise_app, name="noise")
app.add_typer(tts_app, name="tts")
app.add_typer(ei_app, name="ei")
app.add_typer(augment_app, name="augment")


def _client(project_id: int | None) -> EdgeImpulseClient:
    return EdgeImpulseClient(config.load_settings(project_id))


@dataset_app.command("stats")
def dataset_stats(path: Path = typer.Option(config.DATASET_DIR, "--path", "-p")) -> None:
    """Validate every WAV: 16 kHz / mono / PCM16 / ~1 s."""
    if not path.is_dir():
        typer.secho(f"no dataset directory at {path}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    total_issues = 0
    for stat in dataset.stats(path):
        rng = (
            f"{stat.duration_range[0]:.2f}-{stat.duration_range[1]:.2f}s"
            if stat.duration_range
            else "-"
        )
        print(f"{stat.label}: {stat.total} files | fmt ok: {stat.format_ok} | dur ok: {stat.duration_ok} | range: {rng}")
        total_issues += stat.issues
    print("ISSUES:", total_issues)
    if total_issues:
        raise typer.Exit(1)


@dataset_app.command("split")
def dataset_split(
    recording: Path = typer.Argument(..., exists=True, readable=True),
    label: str = typer.Argument(...),
) -> None:
    """Split a 10 s wav_recorder file into 1 s clips under dataset/<label>/."""
    clips = dataset.split_recording(recording, label, config.DATASET_DIR)
    print(f"wrote {len(clips)} clips to dataset/{label}/")


@noise_app.command("build")
def noise_build(
    seed: int = typer.Option(None, "--seed"),
    esc50: Path = typer.Option(config.ESC50_CACHE, "--esc50-cache"),
) -> None:
    """Build dataset/noise: synthetic clips + ESC-50 windows (if cache present)."""
    noise_dir = config.DATASET_DIR / "noise"
    counts = noise.build_synthetic(noise_dir, seed=seed)
    esc = noise.build_esc50_windows(esc50, noise_dir)
    for kind, n in counts.items():
        print(f"synthetic {kind}: {n}")
    print(f"esc50 windows: {esc}")
    print(f"total noise clips: {len(list(noise_dir.glob('*.wav')))}")


@tts_app.command("keywords")
def tts_keywords_cmd(
    max_voices: int = typer.Option(6, "--max-voices"),
) -> None:
    """Generate enciende/apaga samples from Spanish voices."""
    counts = tts.tts_keywords(config.DATASET_DIR, config.TTS_CACHE, max_voices=max_voices)
    for label, n in counts.items():
        print(f"{label} tts: {n}")


@tts_app.command("unknown")
def tts_unknown_cmd() -> None:
    """Generate unknown-word negatives into dataset/noise/."""
    n = tts.tts_unknown(config.DATASET_DIR / "noise", config.TTS_UNKNOWN_CACHE)
    print(f"unknown-word tts clips: {n}")
    print(f"total noise clips: {len(list((config.DATASET_DIR / 'noise').glob('*.wav')))}")


@ei_app.command("info")
def ei_info(project_id: int = typer.Option(None, "--project")) -> None:
    """Show Edge Impulse project info."""
    info = _client(project_id).info()
    project = info.get("project", {})
    print(f"id: {project.get('id')}  name: {project.get('name')}")
    print(f"owner: {project.get('owner', {}).get('name', '?') if isinstance(project.get('owner'), dict) else '?'}")
    print(f"last modified: {project.get('lastModified')}")


@ei_app.command("count")
def ei_count(project_id: int = typer.Option(None, "--project")) -> None:
    """Count samples per label/category."""
    client = _client(project_id)
    for category in config.CATEGORIES:
        samples = client.list_samples(category)
        row = "  ".join(f"{label}={sum(1 for s in samples if s.label == label)}" for label in config.LABELS)
        print(f"{category}: {row}")


@ei_app.command("list")
def ei_list(
    label: str = typer.Option("", "--label", "-l"),
    category: str = typer.Option("training", "--category", "-c"),
    project_id: int = typer.Option(None, "--project"),
) -> None:
    """List samples (id, label, filename, length)."""
    samples = _client(project_id).list_samples(category)
    rows = [s for s in samples if not label or s.label == label]
    for s in rows:
        print(f"{s.id:<10} {s.label:<9} {s.filename:<40} {s.total_length_ms}ms")
    print(f"-- {len(rows)} samples (category={category})")


@ei_app.command("delete")
def ei_delete(
    sample_id: int = typer.Argument(None),
    prefix: str = typer.Option("", "--prefix", help="delete every sample whose filename starts with this"),
    yes: bool = typer.Option(False, "--yes", help="skip confirmation"),
    project_id: int = typer.Option(None, "--project"),
) -> None:
    """Delete one sample by id, or many by filename prefix."""
    client = _client(project_id)
    if sample_id is not None:
        client.delete_sample(sample_id)
        print(f"deleted {sample_id}")
        return
    if not prefix:
        typer.secho("provide a sample id or --prefix PREFIX", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    targets = [s for s in client.iter_all_samples() if s.filename.startswith(prefix)]
    if not targets:
        print("no matching samples")
        return
    for s in targets:
        print(f"{s.id:<10} {s.label:<9} {s.filename}")
    if not yes:
        if not typer.confirm(f"delete {len(targets)} samples?"):
            raise typer.Abort()
    for s in targets:
        client.delete_sample(s.id)
    print(f"deleted {len(targets)} samples")


@ei_app.command("download")
def ei_download(
    skip_splits: bool = typer.Option(False, "--skip-splits", help="skip .sN split copies"),
    project_id: int = typer.Option(None, "--project"),
) -> None:
    """Download all recordings (including .sN splits) into dataset/<label>/."""
    import re

    client = _client(project_id)
    split_re = re.compile(r"\.s\d+$")
    saved = skipped = 0
    for sample in client.iter_all_samples():
        if skip_splits and split_re.search(sample.filename):
            skipped += 1
            continue
        out = config.DATASET_DIR / sample.label / f"{sample.filename}.wav"
        if out.exists():
            skipped += 1
            continue
        values, freq = client.fetch_sample_values(sample.id)
        dataset.write_wav(out, values, freq)
        saved += 1
        print(f"{sample.label:<9} {sample.filename}.wav")
    print(f"downloaded: {saved} | skipped ({'splits/' if skip_splits else ''}existing): {skipped}")


@ei_app.command("upload")
def ei_upload(
    label: str = typer.Argument(...),
    category: str = typer.Option("training", "--category", "-c"),
    augments_only: bool = typer.Option(True, "--augments-only/--all"),
    project_id: int = typer.Option(None, "--project"),
) -> None:
    """Upload dataset/<label>/*.wav to Edge Impulse via the CLI uploader."""
    import glob
    import subprocess

    from .config import require_api_key

    folder = config.DATASET_DIR / label
    pattern = "aug_*.wav" if augments_only else "*.wav"
    files = sorted(glob.glob(str(folder / pattern)))
    if not files:
        typer.secho(f"no {pattern} in {folder}", fg=typer.colors.RED, err=True)
        raise typer.Exit(1)
    settings = config.load_settings(project_id)
    cmd = ["edge-impulse-uploader", "--api-key", require_api_key(settings), "--label", label, "--category", category]
    print(f"uploading {len(files)} files to label={label} category={category}")
    result = subprocess.run([*cmd, *files])
    raise typer.Exit(result.returncode)


@augment_app.command("plan")
def augment_plan(
    variants: int = typer.Option(4, "--variants", "-n"),
    seed: int = typer.Option(None, "--seed"),
) -> None:
    """Preview the augmentation variant plan (no files touched)."""
    pool = [p for p in config.ESC50_CACHE.glob("*.wav")] if config.ESC50_CACHE.is_dir() else []
    for v in plan_variants(variants, pool, seed=seed):
        print(f"#{v.index}: {v.describe()}")


@augment_app.command("run")
def augment_run(
    variants: int = typer.Option(4, "--variants", "-n"),
    seed: int = typer.Option(None, "--seed"),
    labels: list[str] = typer.Option(["enciende", "apaga", "noise"], "--label", "-l"),
    no_background: bool = typer.Option(False, "--no-background", help="disable ESC-50 background mixing"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Generate aug_<name>_<k>.wav variants for every original in dataset/."""
    pool = [] if no_background else (
        [p for p in config.ESC50_CACHE.glob("*.wav")] if config.ESC50_CACHE.is_dir() else []
    )
    created = augment_dataset(
        config.DATASET_DIR,
        variants_per_file=variants,
        background_pool=pool,
        seed=seed,
        labels=tuple(labels),
        dry_run=dry_run,
    )
    suffix = " (dry-run)" if dry_run else ""
    print(f"created {len(created)} augmented clips{suffix}")


if __name__ == "__main__":
    app()
