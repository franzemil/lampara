# Changelog

All notable changes to the lampara-aliz project are documented in this file.

**Rule**: every time the model is updated or tweaked (new Edge Impulse zip, retrain, threshold/margin/dataset change, sketch inference change), add an entry here and bump the version references in `README.md` and `docs/model.md`. See `AGENTS.md`.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [2026-10-05] Data-quality overhaul, local evaluation harness, model 1.0.8

### Added
- `lampara` production CLI (Python + Typer, uv-managed, root `pyproject.toml` + `uv.lock`): consolidates all tooling
  - `dataset stats|split|dcfix`, `noise build`, `tts keywords|unknown`
  - `ei count|list|info|delete [--prefix|--yes]|download|upload|prune-failing` (REST API client with retries; API key from gitignored `.env` `EI_KEY=...`)
  - `local build|classify|evaluate|features` — native on-Mac inference of the Edge Impulse model
  - `augment plan|run` — seeded ffmpeg augmentation (gain/tempo/pitch/ESC-50 background mix/echo)
- Native inference harness (`tools/native/`): compiles the Edge Impulse C++ SDK from the model zip natively on macOS; exact DSP/weights parity with the ESP32 at ~1 ms per clip
- `tests/` pytest suite (config, variant determinism, WAV round-trip)
- `docs/` split (hardware, model, lampara_light, wav_recorder, retraining, troubleshooting)

### Changed
- **Root cause of poor model quality found and fixed**: 56 of 57 project samples carried a large DC offset (recorder mic bias) and silent splits produced NaN features (`DSP error -5`) — Studio was training on broken features. Fixed with DC-removal + dither (`dataset dcfix`), broken samples deleted from Studio, clean re-uploads.
- Trigger logic in `lampara_light`: requires confidence ≥ `LIGHT_TRIGGER_THRESHOLD` **and** margin over every other class (incl. `noise`); threshold 0.6 → 0.8
- Relay moved to **D7 = GPIO44, driven open-drain** (fixes "relay always ON" with 5 V modules and 3.3 V logic)
- All previous bash tools (`*.sh`, `dataset_stats.py`) removed — replaced by the `lampara` CLI
- All synthetic/TTS training data (714 samples) removed from the project; strategy is real recordings + Studio splits + ffmpeg augments

### Fixed
- Model 1.0.7 produced all-zero outputs (`CALIBRATION_ENABLED=1` export bug) — resolved in 1.0.8 (`CALIBRATION_ENABLED=0`), verified on-device

## [2026-10-04] Noise class, relay control, arduino-cli workflow

### Added
- `wav_recorder` sketch: `rec {label}` over serial records 10 s WAVs to microSD
- `relay_blink` sketch: relay hardware test
- Edge Impulse library management via arduino-cli (`enable_unsafe_install` + `lib install --zip-path`)
- Serial protocol on `lampara_light`: prediction lines + `>> LIGHT ON/OFF` events

### Changed
- Model 1.0.1 → 1.0.3: added `noise` class (2-class model had softmax-forced false triggers; ambient noise scored >0.6 on `apaga` every second and one spike hit `enciende: 0.886` → false ON)
- Model 1.0.3 → 1.0.5: retrain on expanded data
- Light output: onboard user LED (GPIO21, active-low) → external relay module

### Fixed
- EI SDK 1.95.x compile verified on ESP32 core 3.3.12 (EI examples only documented 2.0.x)

## [2026-10-03] Project start

### Added
- Initial `wav_recorder` and `lampara_light` sketches for the XIAO ESP32S3 Sense (PDM mic CLK=42/DATA=41 via `ESP_I2S`, microSD CS=21)
- First Edge Impulse model (1.0.1, 2 classes, 1 s @ 16 kHz MFCC + int8 TFLite/EON)
- Baseline workflow: record → Studio train → Arduino zip → flash

## [Unreleased] Locally-trained model deployed (self-training pipeline)

### Added
- **Self-training pipeline** (`docs/self-training.md`): the deployed model is now trained locally instead of in Edge Impulse Studio
  - `lampara local features` — dumps EI's exact MFCC features to `.npz` (training features = device features, by construction)
  - `tools/train/train_model.py` — small Conv1D classifier, class-weighted, full-int8 quantized (8,440 bytes, 100% val accuracy on the clean dataset)
  - `lampara tflite inject [--install]` — swaps the EI library to the non-EON TFLite-Micro engine and injects the local model; sketch unchanged
- Native harness hardening: object-cache busting on `--force` (header changes now trigger recompiles), zip never re-extracted over an injected library copy

### Changed
- Model on device: Edge Impulse 1.0.8 (EON) → **locally-trained int8 model** (TFLM engine, `EI_CLASSIFIER_COMPILED 0`), trained on the clean 273-sample real-recording dataset; verified on-device (17 ms DSP / 3 ms classification, ambient noise → `noise: 0.996`, zero false triggers)
- Installed Arduino library now carries the local model: re-installing any EI zip overwrites it — re-run `lampara tflite inject --install` after EI library updates

### Fixed
- `local evaluate` previously could report stale results: native build cached objects without header-dependency tracking (masking injected-model changes) and re-extracted the zip over injections on `--force`
- Changelog and AGENTS.md conventions introduced
