# Self-training: local model training with EI compatibility

The project can train its keyword-spotting model **locally** (no Edge Impulse Studio) while keeping full compatibility with the Edge Impulse C++ runtime the sketch uses.

## How it works

1. **Features**: `uv run lampara local features --out tools/.cache/features.npz`
   Dumps the **exact MFCC features the device computes** (13 × 50 = 650 values per 1 s clip) for every file in `dataset/` — extracted by the same C++ DSP that runs on the ESP32, so training features and device features can never diverge.
2. **Training**: `uv run tools/train/train_model.py <features.npz> <out.tflite>`
   Small Conv1D model (16/8 filters → Dense 16 → softmax), class-weighted, early-stopped; post-training **full-int8 quantization** with a representative dataset. Requires `tensorflow` (uv installs it on first run, ~200 MB, macOS arm64 wheels come from the unified `tensorflow` package).
3. **Injection**: `uv run lampara tflite inject <model.tflite> --version <ei-version> [--install] [--arena 32768]`
   Rewrites the Edge Impulse library to use the **non-EON TFLite-Micro engine**: swaps the EON graph config in `model_variables.h` for `ei_config_tflite_graph_t` (model bytes + arena), sets `EI_CLASSIFIER_COMPILED 0`, adds `trained_tflite.{h,cpp}` + a `tflite-resolver.h` stub. The sketch and its `run_classifier()` API are **unchanged**; ops resolve via `AllOpsResolver`.
   - without `--install`: patches `tools/.cache/ei/<version>/` (used by `local build`/`evaluate`)
   - with `--install`: also patches `~/Documents/Arduino/libraries/Lampara_inferencing/`
4. **Verify locally**: `uv run lampara local evaluate` (the harness rebuild picks up the injected model)
5. **Deploy**: `arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light` and smoke-test via the monitor

## The training script (`tools/train/train_model.py`)

Single-file uv script (deps declared inline: `tensorflow`, `numpy` — uv installs them on first run):

```sh
uv run tools/train/train_model.py tools/.cache/features.npz tools/.cache/lampara_local_int8.tflite
```

What it does, in order:

1. **Load** the `.npz` (features, labels, file paths) and reshape each 650-vector to a `(50, 13)` time × coefficient sequence
2. **Split**: stratified 90/10 train/val, seeded with `rng(42)` — reproducible runs
3. **Model** (fits the ESP32's TFLM easily):

   ```
   Input (50, 13)
   Conv1D(16, kernel 3, relu) -> MaxPooling1D(2)
   Conv1D(8,  kernel 3, relu) -> GlobalAveragePooling1D()
   Dense(16, relu) -> Dense(3, softmax)
   ```

   ~8.4 KB as int8; output order matches the EI label array (`apaga`, `enciende`, `noise`)
4. **Fit**: Adam(1e-3), `sparse_categorical_crossentropy`, up to 300 epochs with EarlyStopping (patience 30, restore best weights), batch 16, **class weights** to compensate label imbalance
5. **Quantize**: post-training **full-int8** (`TFLITE_BUILTINS_INT8`, int8 in/out) using the training features as the representative dataset
6. **Self-check**: runs the int8 flatbuffer in the Python interpreter over the val split and reports its accuracy (must match the float model before deployment)

## The training data (`tools/.cache/features.npz`)

Produced by `lampara local features` from `dataset/` — one row per WAV, **features computed by EI's own C++ DSP** (`extract_mfcc_features`), so they are byte-identical to what the device extracts at inference.

Snapshot used for the current model (2026-10-05): **275 samples × 650 features**, float32, zero NaN (all inputs DC-fixed via `dataset dcfix`):

| Label | Total | Originals (real recordings) | ffmpeg augments |
|---|---|---|---|
| enciende | 120 | 24 | 96 |
| apaga | 125 | 25 | 100 |
| noise | 30 | 6 | 24 |
| **total** | **275** | **55** | **220** |

- **Originals** = `wav_recorder` recordings (Studio `.sN` splits of `enciende_2`, `apaga_1`, `apaga_2`, `noise`, plus 3 CLI-uploaded clips), DC-offset removed
- **Augments** = 4 seeded ffmpeg variants per original (gain 0.7–1.3, tempo 0.92–1.08, pitch ±6%, ESC-50 background mix, occasional echo) — see `lampara augment plan`
- Feature ranges are consistent across labels (≈ −6.2 … +4.2) and match the int8 input quantization range

### Honest accuracy caveat

The val split is drawn from the same 275 clips the model trains on (in augmented form), so 100% val accuracy measures **memorization + augmentation coverage**, not generalization to brand-new voices or rooms. The most reliable accuracy check is `lampara local evaluate` after recording a *fresh* batch of clips that never entered training. The biggest quality lever is still **more original recordings** (`wav_recorder` → `ei upload`) — especially `noise` (only 6 originals) and additional speakers.

## Important caveats

- **The installed library no longer matches any Edge Impulse zip.** Installing a new EI zip (`lib install --zip-path`) overwrites the local model — re-run `tflite inject --install` after any EI library update. This is also why `local build` never re-extracts the zip over an injected copy.
- The current model outputs int8-quantized softmax scores (multiples of 1/255); confident predictions saturate at 0.996 — thresholds/margins still work as tuned.
- Retraining after new data: `lampara ei download` → `dataset dcfix` (if needed) → `augment run` → `local features` → `train_model.py` → `tflite inject` → `local evaluate`.
- **Changelog**: a locally-trained model deployment is a model change — add a `CHANGELOG.md` entry (see `AGENTS.md`).
