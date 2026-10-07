# AGENTS.md — guidance for AI agents working on this repo

Voice-controlled lamp (TinyML) on a Seeed XIAO ESP32S3 Sense: Edge Impulse model runs on-device; a relay on D7 (GPIO44, open-drain) switches the light. Training data comes from the `wav_recorder` sketch; all tooling is the `lampara` Python CLI.

## Mandatory rules

1. **Changelog discipline**: every time the model is updated or tweaked — new Edge Impulse zip installed, retrain, threshold/margin/trigger-logic change, dataset change (add/remove/augment samples), or any inference-affecting sketch edit — **add an entry to `CHANGELOG.md`** and bump the version references in `README.md` and `docs/model.md`. Never leave a model change undocumented.
2. Never commit secrets: `.env` (`EI_KEY=...`), `tools/.cache/`, `dataset/`, `.venv/`, `*.tar.gz` are gitignored — keep it that way.
3. Never run `dataset dcfix`, `noise build`, `tts ...` or `augment run` without checking with the user first: they rewrite `dataset/` contents, and the project deliberately trains on real recordings only.
4. Destructive Edge Impulse operations (`ei delete`, `prune-failing`) require `--yes` and a printed target list first.

## Commands

```sh
uv run lampara --help                     # all tooling (dataset/noise/tts/ei/augment/local)
uv run lampara ei count                   # samples per label/category (needs .env EI_KEY)
uv run lampara local evaluate             # accuracy, confusion matrix, threshold sweep
uv run lampara ei download                # project recordings -> dataset/<label>/
uv run lampara augment run -n 4 --seed 42 # ffmpeg variants of local originals
uv run lampara ei upload <label>          # upload aug_*.wav (see --all)

uv run pytest                             # tests

# firmware
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" wav_recorder
arduino-cli monitor -p $PORT -c baudrate=115200
```

`PORT` can change after replug/bootloader — always check `arduino-cli board list`.

## Model update checklist (new `ei-lampara-arduino-*-impulse-#1.zip`)

1. Verify compatibility: `unzip -p <zip> "Lampara_inferencing/src/model-parameters/model_variables.h" | grep categories` → must be `{ "apaga", "enciende", "noise" }`; also check `RAW_SAMPLE_COUNT 16000`, `FREQUENCY 16000`, and `CALIBRATION_ENABLED 0` in `model_metadata.h`
2. `arduino-cli lib uninstall Lampara_inferencing && arduino-cli lib install --zip-path <zip>`
3. Compile + flash `lampara_light`, then smoke-test via `arduino-cli monitor`
4. **Add the `CHANGELOG.md` entry** (see rule 1) and bump versions in `README.md` / `docs/model.md`

## Known hardware/software gotchas

- GPIO21 = SD-CS on the expansion board; the user LED shares it — do not mix LED + SD usage
- Relay modules need VCC on **5V**; the D7 driver is open-drain on purpose (3.3 V logic + 5 V module otherwise stays ON)
- A wire bridging the **BOOT pad/button** parks the chip in the bootloader (silent sketches, flaky uploads): clear it, then BOOT+RESET to recover
- `wav_recorder` requires `PSRAM=opi`; uploads that look silent/DC-biased break EI's MFCC (NaN → `DSP error -5`) — run `lampara dataset dcfix` and re-upload, then `local evaluate`
