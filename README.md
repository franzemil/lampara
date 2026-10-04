# lampara-aliz

Voice-controlled lamp using TinyML on a **Seeed XIAO ESP32S3 Sense**, plus a serial-triggered WAV recorder for gathering training data.

| Sketch | Purpose |
|---|---|
| `lampara_light/` | Always-listening keyword spotter: says *"enciende"* -> light on, *"apaga"* -> light off (Edge Impulse model) |
| `wav_recorder/` | Sends `rec {label}` over serial -> records 10 s WAV to microSD |
| `relay_blink/` | Hardware test: blinks the relay pin D7 (GPIO44) open-drain, LOW 2 s (ON) / HIGH-float 2 s (OFF) |

## Hardware

- Seeed XIAO ESP32S3 Sense with expansion board (PDM microphone: CLK = GPIO42, DATA = GPIO41)
- Light: relay module on header pin **D7 = GPIO44**, driven **open-drain**, active-LOW (IN pulled to GND = relay energized)

  ```
  XIAO ESP32S3 — top view (USB-C at the top)

        ┌─────────────────┐
        │    ( USB-C )    │   5V pin is only live
        │                 │   when USB is plugged
  5V ──►│5V            D0 │
  GND ─►│GND           D1 │
        │3V3           D2 │
        │D4            D3 │
        │D5               │
        │D6            D8 │
  IN ◄──┤D7            D9 │    D7 = bottom pad, left edge
        │              D10│
        └─────────────────┘
  ```

  Control-side wiring (3 wires):

  ```
  XIAO                     RELAY MODULE
  ────                     ────────────
  5V  ───────────────────►  VCC   (5V! NOT the 3V3 pin)
  GND ───────────────────►  GND   (must share ground with XIAO)
  D7  ───────────────────►  IN    (signal, open-drain)
  ```

  Load side (the circuit the relay switches) — use **COM + NO**:

  ```
            relay screw terminals

          ┌────────────────────────┐
          │    COM     NO     NC   │
          └────┬──────┬──────┬─────┘
               │      │      └── unused (closed when relay is OFF)
   supply + ───┘      └─────── to load +
                          (lamp/device)
   supply - ───────────────────── to load -
  ```

  - Power the module from the **5V** pin — most 5 V relay coils will not energize from 3V3
  - The XIAO's 5V pin is only live when powered via **USB** (dead on battery)
  - If the relay clicks inverted (enciende turns it off), set `LIGHT_ACTIVE_LOW` to `0`
  - **NO** = normally open (load on when the relay energizes); **NC** behaves inverted
- microSD card, FAT32, up to 32 GB (only needed by `wav_recorder`)
- Model: Edge Impulse impulse "Lampara" v1.0.5 — 1 s window @ 16 kHz, 16-bit mono, labels `apaga` / `enciende` / `noise` (int8 TFLite, EON). The `noise` class absorbs everything that is neither command: when it wins, nothing happens.

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
arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.5-impulse-#1.zip"
arduino-cli lib list | grep Lampara
# Lampara_inferencing 1.0.5 ... user
```

The library lands in `~/Documents/Arduino/libraries/Lampara_inferencing`.

Arduino IDE alternative: **Sketch > Include Library > Add .ZIP Library...**

## Updating the model (new impulse version)

When you retrain in Edge Impulse Studio and export a new zip (e.g. `ei-lampara-arduino-1.0.7-impulse-#1.zip`), three steps put it on the device. **No sketch changes are needed** as long as the new model keeps the same labels (`apaga`, `enciende`, `noise`) and 1 s @ 16 kHz window — check before installing:

```sh
unzip -p "ei-lampara-arduino-1.0.7-impulse-#1.zip" \
  "Lampara_inferencing/src/model-parameters/model_variables.h" | grep categories
# expect: ... = { "apaga", "enciende", "noise" };
```

1. Swap the library (arduino-cli refuses to overwrite, so uninstall first):

   ```sh
   arduino-cli lib uninstall Lampara_inferencing
   arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.7-impulse-#1.zip"
   arduino-cli lib list | grep Lampara
   ```

2. Rebuild and flash (the sketch compiles against whatever library version is installed):

   ```sh
   arduino-cli compile -u -p /dev/cu.usbmodem1101 --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light
   ```

3. Verify in the monitor — you should see three-label predictions and no false light events on ambient noise:

   ```sh
   arduino-cli monitor -p /dev/cu.usbmodem1101 -c baudrate=115200
   ```

If the new model renames or adds labels, also update the label lookups (`strcmp(..., "enciende")` etc.) in `lampara_light/lampara_light.ino`.

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
| `LIGHT_PIN` | `44` | Relay IN pin, header pin D7 (GPIO44), open-drain |
| `LIGHT_ACTIVE_LOW` | `1` | `1` = pin LOW energizes the relay; `0` = active-high |
| `LIGHT_TRIGGER_THRESHOLD` | `0.8` | Minimum confidence to trigger |
| `LIGHT_TRIGGER_MARGIN` | `0.15` | Winner must also beat **every** other class (including `noise`) by at least this much |
| `LIGHT_COOLDOWN_MS` | `1500` | Ignore new triggers for this long after one fires |
| `AUDIO_GAIN` | `4` | Mic input gain. Training WAVs were recorded with x4 gain, keep in sync |

### Case: relay always ON when powered from 5V (RESOLVED)

Symptom: with the relay module's VCC on the **3V3** pin, the relay toggled correctly; with VCC on **5V/VBUS**, it stayed energized permanently regardless of the GPIO state.

Why: the module's input is an optocoupler LED between **VCC and IN**, triggered active-LOW. A 3.3V GPIO driving HIGH against a 5V VCC still leaves 5 − 3.3 = **1.7V across the input** — enough current to keep the optocoupler (and the relay) on. On 3V3 the difference is 0V, which is why it worked there — but the relay coil is a 5V coil and is under-driven at 3V3.

Resolution: the GPIO is configured as **open-drain** (`OUTPUT_OPEN_DRAIN`). LOW = pin pulled to GND → relay solidly ON; HIGH = pin floats → no voltage difference at all → relay truly OFF. VCC stays on 5V, so the coil always gets its full rated voltage. Applied to both `lampara_light` and `relay_blink`.

If you ever swap to an active-HIGH module or a logic-level MOSFET board, change the `pinMode()` back to plain `OUTPUT`.

### Case: false positives with a 2-class model (RESOLVED)

Observed on the first flash (model v1.0.1, only `apaga`/`enciende`, 0.6 threshold, no margin):

- Ambient noise scored >0.6 on `apaga` almost every second (`>> LIGHT OFF` spam — harmless but noisy logs)
- One random noise spike scored `enciende: 0.886` and falsely turned the light **ON**

Why: with only the two word classes, the classifier's softmax always produces a winner. Silence, music or speech that is neither "enciende" nor "apaga" still gets pushed toward one of them.

Resolution (model v1.0.3 + current code): the model was retrained with a third `noise` class (samples collected with `wav_recorder`, see the retraining workflow below), and the trigger logic now requires a command to clear the threshold **and** beat every other class — `noise` included — by `LIGHT_TRIGGER_MARGIN`. Verified on-device: ambient noise scores `noise: 0.95+` and produces zero light events.

Remaining tuning knobs if false triggers ever come back:

1. **Retrain with more negative samples** — collect 1-2 minutes more of ambient noise, silence and random speech with `wav_recorder` and add them to the `noise` class
2. **Raise threshold/margin** — e.g. `LIGHT_TRIGGER_THRESHOLD 0.9`, `LIGHT_TRIGGER_MARGIN 0.2`
3. **Cooldown** — `LIGHT_COOLDOWN_MS` limits how often a trigger can fire at all

If real utterances start getting missed (model not confident enough on your voice), lower the threshold to 0.7 or the margin to 0.1 and retest.

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
2. Upload them to Edge Impulse Studio (project "Lampara") under the matching labels — noise/unknown clips go to the `noise` class
3. Retrain and export the **Arduino library** zip
4. Follow **"Updating the model (new impulse version)"** above to install it and reflash

The sketch expects the labels by name (`enciende`, `apaga`, `noise`); the `noise` class must exist in the model — when it wins a window, no action is taken.

## Troubleshooting

- **Port not found / upload fails** — recheck `arduino-cli board list`; if still failing, hold **BOOT**, press **RESET**, release **BOOT** to enter bootloader mode and retry
- **Recorder silent after boot / stuck at `SD init...`** — the SD card failed to initialize: reseat the card, then press **RESET**. If the device also stops answering uploads ("No serial data received"), enter bootloader mode (BOOT + RESET) to recover
- **`ERR sd` on the recorder** — reseat the card, format FAT32 (max 32 GB), gold fingers facing inward
- **`Error sample buffer overrun`** — the DSP cannot keep up; reduce other load or re-export a smaller window model
- **False triggers** — see "Case: false positives with a 2-class model" above; raise `LIGHT_TRIGGER_THRESHOLD`/`LIGHT_TRIGGER_MARGIN` or retrain with a noise class
- **Relay doesn't switch** — flash `relay_blink` (D7 blink) and bench-test: touch the IN wire directly to **GND** (should click ON on active-low modules) and to **3V3** (should release). If the manual test works but D7 doesn't, recheck the wire is on the bottom-left pad (D7/GPIO44); if the manual test fails, it's power: `VCC` must be 5V, `GND` shared with the XIAO, USB power connected
- **Relay always ON** — see "Case: relay always ON when powered from 5V" above (open-drain output is the fix, already in the code)
- **Sketch totally silent after wire changes / uploads behave erratically** — a wire bridging the **BOOT pad/button** holds the chip in the bootloader; check the corners near the USB connector, then press **RESET**
- If a future Edge Impulse SDK export ever fails to compile on core 3.x, `arduino-cli core install esp32:esp32@2.0.17` provides the legacy core (the `wav_recorder` sketch requires 3.x, `lampara_light` would need its mic layer reverted to the legacy `driver/i2s.h` API from the stock EI example)
