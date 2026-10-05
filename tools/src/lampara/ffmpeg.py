"""Subprocess wrappers around ffmpeg / ffprobe / say."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path


class ToolError(RuntimeError):
    pass


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise ToolError(f"required executable not found: {name}")
    return path


def run(cmd: list[str], dry_run: bool = False) -> None:
    if dry_run:
        print("  " + " ".join(cmd))
        return
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ToolError(
            f"command failed ({result.returncode}): {' '.join(cmd)}\n{result.stderr.strip()[:500]}"
        )


def ffmpeg(args: list[str], dry_run: bool = False) -> None:
    run([require_executable("ffmpeg"), "-y", "-loglevel", "error", *args], dry_run=dry_run)


def probe_duration(path: Path) -> float:
    ffprobe = require_executable("ffprobe")
    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise ToolError(f"ffprobe failed for {path}: {result.stderr.strip()}")
    try:
        return float(result.stdout.strip())
    except ValueError:
        raise ToolError(f"could not parse duration for {path}: {result.stdout!r}") from None


def list_voices(locale_prefixes: tuple[str, ...] = ("es_",), max_voices: int | None = None) -> list[tuple[str, str]]:
    say = require_executable("say")
    result = subprocess.run([say, "-v", "?"], capture_output=True, text=True)
    voices: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        m = re.match(r"^(.*?)\s+([a-z]{2}_[A-Z]{2})\s", line)
        if not m:
            continue
        name, locale = m.group(1), m.group(2)
        if locale.startswith(locale_prefixes):
            voices.append((name, locale))
    if max_voices:
        voices = voices[:max_voices]
    return voices


def say_to_file(voice: str, rate: int, phrase: str, out: Path, dry_run: bool = False) -> None:
    run([require_executable("say"), "-v", voice, "-r", str(rate), "-o", str(out), phrase], dry_run=dry_run)
