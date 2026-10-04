# lampara-aliz

Voice-controlled lamp using TinyML on a **Seeed XIAO ESP32S3 Sense**, plus a serial-triggered WAV recorder for gathering training data.

| Sketch | Purpose |
|---|---|
| `lampara_light/` | Always-listening keyword spotter: says *"enciende"* -> light on, *"apaga"* -> light off (Edge Impulse model) |
| `wav_recorder/` | Sends `rec {label}` over serial -> records 10 s WAV to microSD |

## Hardware

- Seeed XIAO ESP32S3 Sense with expansion board (PDM microphone: CLK = GPIO42, DATA = GPIO41)
- Light: onboard user LED on **GPIO21, active-LOW** (pin LOW = LED on)
  - GPIO21 is also the SD card chip-select on the expansion board, so the LED and the SD card cannot be used at the same time (that is why `lampara_light` is inference-only)
- microSD card, FAT32, up to 32 GB (only needed by `wav_recorder`)
- Model: Edge Impulse impulse "Lampara" v1.0.1 — 1 s window @ 16 kHz, 16-bit mono, labels `apaga` / `enciende`, int8 TFLite (EON)

## Toolchain setup (arduino-cli)

```sh
arduino-cli core update-index
arduino-cli core install esp32:esp32        # tested with 3.3.12
```

Arduino IDE alternative: add the ESP32 boards URL in Preferences and install "esp32 by Espressif Systems" (2.0.8+).

## Installing the Edge Impulse library

The model ships as an Arduino library zip (`ei-lampara-arduino-1.0.1-impulse-#1.zip`).

arduino-cli blocks zip installs by default, so enable it once:

```sh
arduino-cli config set library.enable_unsafe_install true
```

Then install and verify:

```sh
arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.1-impulse-#1.zip"
arduino-cli lib list | grep Lampara
# Lampara_inferencing 1.0.1 ... user
```

The library lands in `~/Documents/Arduino/libraries/Lampara_inferencing`.

Arduino IDE alternative: **Sketch > Include Library > Add .ZIP Library...**

## lampara_light — voice-controlled light

### Build and flash

```sh
PORT=/dev/cu.usbmodem1101   # check with: arduino-cli board list
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light
```

### Monitor

```sh
arduino-cli monitor -p $PORT -c baudrate=115200
```

After boot it prints the model settings and `Listening...`, then one prediction line per second:

```
Predictions (DSP: 145 ms., Classification: 3 ms.): apaga: 0.013 enciende: 0.021
Predictions (DSP: 141 ms., Classification: 3 ms.): apaga: 0.948 enciende: 0.011
>> LIGHT OFF (apaga: 0.948)
```

Say *"enciende"* -> `>> LIGHT ON`, *"apaga"* -> `>> LIGHT OFF`.

### Tuning (defines at the top of `lampara_light.ino`)

| Define | Default | Meaning |
|---|---|---|
| `LIGHT_PIN` | `21` | Onboard user LED; change when wiring a relay/MOSFET |
| `LIGHT_ACTIVE_LOW` | `1` | `1` = pin LOW turns light on (onboard LED, many relay boards); `0` = active-high |
| `LIGHT_TRIGGER_THRESHOLD` | `0.9` | Minimum confidence to trigger (raised from the model's 0.6 default, see below) |
| `LIGHT_TRIGGER_MARGIN` | `0.15` | Winner must also beat the other class by at least this much |
| `LIGHT_COOLDOWN_MS` | `1500` | Ignore new triggers for this long after one fires |
| `AUDIO_GAIN` | `4` | Mic input gain. Training WAVs were recorded with x4 gain, keep in sync |

### Case: false positives with a 2-class model

Observed on the first flash, with the model's default 0.6 threshold and no margin:

- Ambient noise scored >0.6 on `apaga` almost every second (`>> LIGHT OFF` spam — harmless but noisy logs)
- One random noise spike scored `enciende: 0.886` and falsely turned the light **ON**

Why: the model has only the two word classes, and the classifier's softmax always produces a winner. Silence, music or speech that is neither "enciende" nor "apaga" still gets pushed toward one of them.

Mitigations, in order of effectiveness:

1. **Retrain with negative samples (best fix)** — collect 1-2 minutes of ambient noise, silence and random speech/words with `wav_recorder` (`rec noise`, `rec unknown`, ...) and add them to Edge Impulse Studio as an extra class (or use the Studio's built-in noise handling). The sketch keeps working unchanged: it looks labels up by name (`enciende`/`apaga`), so a third `noise` class simply lowers the other two scores.
2. **High threshold + margin (applied by default)** — `LIGHT_TRIGGER_THRESHOLD 0.9` and `LIGHT_TRIGGER_MARGIN 0.15` block mid-confidence noise like the `0.886` false ON above.
3. **Cooldown** — `LIGHT_COOLDOWN_MS` limits how often a trigger can fire at all.

If real utterances start getting missed (model not confident enough on your voice), lower the threshold to 0.8 or the margin to 0.1 and retest.

## wav_recorder — training data collector

```sh
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" wav_recorder
arduino-cli monitor -p $PORT -c baudrate=115200
```

PSRAM must be enabled (`:PSRAM=opi`, or Tools > PSRAM > OPI PSRAM in the IDE) because the 10 s audio buffer lives in PSRAM.

Serial commands (newline-terminated):

| Command | Response |
|---|---|
| `rec test1` | `REC /test1.wav` ... `DONE /test1.wav 320044 bytes` |
| anything while recording | `ERR busy` |
| malformed | `ERR usage: rec {label}` |

Files are 16 kHz / 16-bit mono WAV, ~320 KB per 10 s, exactly what Edge Impulse expects for this model.

## Retraining workflow

### 1. Collect samples with `wav_recorder`

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

### 2. Upload, retrain, redeploy

1. Power off, take the microSD out, and copy the WAVs to your computer (card reader)
2. Upload them to Edge Impulse Studio (project "Lampara") under the matching labels — noise/unknown clips go to a new class (e.g. `noise`)
3. Retrain and export the **Arduino library** zip
4. Install the new zip (uninstall first, arduino-cli refuses to overwrite):
   ```sh
   arduino-cli lib uninstall Lampara_inferencing
   arduino-cli lib install --zip-path "ei-lampara-arduino-X.Y.Z-impulse-N.zip"
   ```
5. Flash the light sketch again and test:
   ```sh
   arduino-cli compile -u -p /dev/cu.usbmodem1101 --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light
   ```

The sketch needs no code changes for a third class: it looks labels up by name, so a `noise` class simply lowers the `enciende`/`apaga` scores on non-command audio.

## Troubleshooting

- **Port not found / upload fails** — recheck `arduino-cli board list`; if still failing, hold **BOOT**, press **RESET**, release **BOOT** to enter bootloader mode and retry
- **Recorder silent after boot / stuck at `SD init...`** — the SD card failed to initialize: reseat the card, then press **RESET**. If the device also stops answering uploads ("No serial data received"), enter bootloader mode (BOOT + RESET) to recover
- **`ERR sd` on the recorder** — reseat the card, format FAT32 (max 32 GB), gold fingers facing inward
- **`Error sample buffer overrun`** — the DSP cannot keep up; reduce other load or re-export a smaller window model
- **False triggers** — see "Case: false positives with a 2-class model" above; raise `LIGHT_TRIGGER_THRESHOLD`/`LIGHT_TRIGGER_MARGIN` or retrain with a noise class
- **Light stays off** — remember the onboard LED is active-LOW and shares GPIO21 with SD-CS
- If a future Edge Impulse SDK export ever fails to compile on core 3.x, `arduino-cli core install esp32:esp32@2.0.17` provides the legacy core (the `wav_recorder` sketch requires 3.x, `lampara_light` would need its mic layer reverted to the legacy `driver/i2s.h` API from the stock EI example)
