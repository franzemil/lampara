"""Configuration: paths, project id and Edge Impulse API key resolution."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DATASET_DIR = REPO_ROOT / "dataset"
CACHE_DIR = REPO_ROOT / "tools" / ".cache"
ESC50_CACHE = CACHE_DIR / "hf" / "esc50"
TTS_CACHE = CACHE_DIR / "tts"
TTS_UNKNOWN_CACHE = CACHE_DIR / "tts_unk"
ENV_FILE = REPO_ROOT / ".env"
KEYFILE = CACHE_DIR / "ei_api_key"

DEFAULT_PROJECT_ID = 1127921
LABELS = ("enciende", "apaga", "noise")
CATEGORIES = ("training", "testing")


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    project_id: int
    api_key: str | None

    @property
    def base_url(self) -> str:
        return f"https://studio.edgeimpulse.com/v1/api/{self.project_id}"


def _read_env_key(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("EI_KEY="):
            return line.split("=", 1)[1].strip() or None
    return None


def load_settings(project_id: int | None = None) -> Settings:
    key = os.environ.get("EI_API_KEY") or _read_env_key(ENV_FILE)
    if not key and KEYFILE.is_file():
        key = KEYFILE.read_text().splitlines()[0].strip() or None
    return Settings(project_id=project_id or DEFAULT_PROJECT_ID, api_key=key)


def require_api_key(settings: Settings) -> str:
    if not settings.api_key:
        raise ConfigError(
            "No Edge Impulse API key found. Set one of:\n"
            "  export EI_API_KEY=ei_...\n"
            f"  EI_KEY=ei_... in {ENV_FILE} (gitignored)\n"
            f"  echo ei_... > {KEYFILE} (gitignored)"
        )
    return settings.api_key
