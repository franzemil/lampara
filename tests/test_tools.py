from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from lampara.augment import plan_variants
from lampara.config import REPO_ROOT, load_settings, _read_env_key
from lampara.dataset import stats, write_wav


def test_env_key_parsing(tmp_path: Path) -> None:
    env = tmp_path / ".env"
    env.write_text("EI_KEY=ei_test123\nOTHER=x\n")
    assert _read_env_key(env) == "ei_test123"
    assert _read_env_key(tmp_path / "missing.env") is None


def test_settings_defaults_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EI_API_KEY", raising=False)
    settings = load_settings()
    assert settings.project_id == 1127921
    assert settings.base_url.endswith("/v1/api/1127921")


def test_variant_plan_deterministic() -> None:
    a = plan_variants(4, [Path("bg1.wav"), Path("bg2.wav")], seed=42)
    b = plan_variants(4, [Path("bg1.wav"), Path("bg2.wav")], seed=42)
    assert a == b
    assert len(a) == 4
    assert all(v.gain > 0 for v in a)


def test_variant_plan_respects_count() -> None:
    plans = plan_variants(3, [], seed=1)
    assert [v.index for v in plans] == [1, 2, 3]
    assert all(v.bg_file is None for v in plans)


def test_wav_roundtrip_and_stats(tmp_path: Path) -> None:
    ds = tmp_path / "dataset"
    label_dir = ds / "enciende"
    label_dir.mkdir(parents=True)
    write_wav(label_dir / "one.wav", [0, 100, -100, 32767, -32768])
    write_wav(label_dir / "two.wav", [0] * 16000)
    (ds / "noise").mkdir()
    results = {s.label: s for s in stats(ds)}
    assert results["noise"].total == 0
    assert results["enciende"].total == 2
    assert results["enciende"].format_ok == 2
    assert results["enciende"].duration_ok == 1  # 4 samples = 0.25 s, only the 1 s file passes
    data, sr = sf.read(str(label_dir / "one.wav"), dtype="int16")
    assert sr == 16000
    assert list(data) == [0, 100, -100, 32767, -32768]
