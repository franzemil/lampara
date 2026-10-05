# Retraining workflow

End-to-end: manage/augment data with the `lampara` CLI + collect samples with `wav_recorder` -> upload to Edge Impulse -> retrain -> install the new model zip -> reflash.

## 0. Data strategy

The project is trained on **real recordings only** — `wav_recorder` clips uploaded to Studio (including Studio's `.s1`–`.s9` split copies), expanded locally with ffmpeg-based augmentation (`aug_*.wav` files). The synthetic/TTS data (714 samples) was removed from the project on 2026-10-05.

## The `lampara` CLI (Python + Typer, uv-managed)

All tooling lives in one production CLI — run from the repo root:

```sh
uv run lampara --help
```

| Command | What it does |
|---|---|
| `uv run lampara dataset stats` | Validate every WAV (16 kHz / mono / PCM16 / ~1 s) |
| `uv run lampara dataset split <file.wav> <label>` | Chop a 10 s `wav_recorder` file into 1 s clips under `dataset/<label>/` |
| `uv run lampara noise build [--seed N]` | Regenerate synthetic noise (colors/bursts/hum/rumble + ESC-50 cache windows) |
| `uv run lampara tts keywords` / `tts unknown` | Regenerate TTS keyword / unknown-word samples (macOS `say`) |
| `uv run lampara ei count / list / info` | Inspect the Edge Impulse project (counts, samples, metadata) |
| `uv run lampara ei delete <id>` / `ei delete --prefix tts_ --yes` | Delete one sample or every sample matching a filename prefix |
| `uv run lampara ei download` | Download all project recordings into `dataset/<label>/` (skips files already present) |
| `uv run lampara ei upload <label> [--category training]` | Upload `dataset/<label>/aug_*.wav` (or `--all`) via `edge-impulse-uploader` |
| `uv run lampara augment plan -n 4` | Preview augmentation variants (no files written) |
| `uv run lampara augment run -n 4 --seed 42` | Generate `aug_<name>_<k>.wav` variants (gain/tempo/pitch/ESC-50 bg/echo), all exactly 1 s |

The Edge Impulse API key is read from `.env` (`EI_KEY=ei_...`, gitignored), `EI_API_KEY` env var, or `tools/.cache/ei_api_key`. Tests: `uv run pytest`.

## 1. Collect samples with `wav_recorder`

Flash the recorder (note the `:PSRAM=opi` option — required for this sketch):

```sh
arduino-cli compile -u -p /dev/cu.usbmodem1101 --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" wav_recorder
```

Open the monitor and record 10 s clips by typing one line per sample (**each label must be unique — the same label overwrites its file**):

```sh
arduino-cli monitor -p /dev/cu.usbmodem1101 -c baudrate=115200
```

```
rec noise1        <- 10 s of ambient noise
rec noise2        <- another 10 s, vary conditions (silence, music, talking)
...
rec unknown1      <- random words that are neither enciende nor apaga
rec enciende1     <- real "enciende" utterances
rec apaga1        <- real "apaga" utterances
```

Wait for `DONE /noiseX.wav 320044 bytes` before the next command; anything sent during a recording gets `ERR busy`. Expect `ERR sd` if no card is inserted.

## 2. Upload, augment, retrain, redeploy

1. Power off, take the microSD out, and copy the WAVs to your computer (card reader)
2. Bring them into the local dataset and upload:

   ```sh
   uv run lampara dataset split ~/Downloads/enciende01.wav enciende   # 10 s -> 1 s clips
   uv run lampara ei upload enciende --all        # originals + augments
   uv run lampara ei count                        # verify
   ```

3. Or augment what is already in the project:

   ```sh
   uv run lampara ei download                     # project -> dataset/<label>/
   uv run lampara augment run -n 4 --seed 42      # 4 ffmpeg variants per clip
   uv run lampara dataset stats                   # validate
   uv run lampara ei upload enciende              # uploads aug_*.wav
   uv run lampara ei upload apaga
   uv run lampara ei upload noise
   ```

4. Keep some real (non-augmented) recordings as **testing** samples in Studio — the model-testing page needs them
5. Retrain and export the **Arduino library** zip
6. Follow [model.md](model.md) ("Updating the model") to install it and reflash

The sketch expects the labels by name (`enciende`, `apaga`, `noise`); the `noise` class must exist in the model — when it wins a window, no action is taken.
