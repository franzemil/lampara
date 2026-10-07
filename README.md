# lampara-aliz

Voice-controlled lamp using TinyML on a **Seeed XIAO ESP32S3 Sense**: says *"enciende"* -> light on, *"apaga"* -> light off. Includes a serial-triggered WAV recorder for gathering training data.

| Sketch | Purpose |
|---|---|
| `lampara_light/` | Voice-controlled light (Edge Impulse model) |
| `wav_recorder/` | Records 10 s WAVs to microSD for training data |
| `relay_blink/` | Hardware test: blinks the relay pin D7 (GPIO44) |

## Tools

| Tool | What it's for | Install |
|---|---|---|
| **arduino-cli** | Compile, flash and monitor | `brew install arduino-cli` |
| **ESP32 core** (`esp32:esp32`) | Board support for the XIAO ESP32S3 | see below |
| **Edge Impulse model zip** | The trained model as an Arduino library (`ei-lampara-arduino-*-impulse-#1.zip`, in this repo) | see [docs/model.md](docs/model.md) |
| **`lampara` CLI** (Python + Typer, uv-managed) | Dataset building, augmentation, Edge Impulse data management | `uv sync` then `uv run lampara --help` |
| microSD card (FAT32, ≤32 GB) | Only for `wav_recorder` | — |

One-time toolchain setup:

```sh
arduino-cli core update-index
arduino-cli core install esp32:esp32        # tested with 3.3.12
arduino-cli config set library.enable_unsafe_install true   # allows zip installs
```

Arduino IDE alternative: add the ESP32 boards URL in Preferences and install "esp32 by Espressif Systems" (2.0.8+). Board: **XIAO_ESP32S3**.

Set your port once (check with `arduino-cli board list`):

```sh
PORT=/dev/cu.usbmodem1101
```

## The two main workflows

### 1. Record training WAVs (`wav_recorder`)

Compile with **PSRAM enabled** (required), then open the serial monitor and type one `rec {label}` line per clip:

```sh
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3:PSRAM=opi" wav_recorder
arduino-cli monitor -p $PORT -c baudrate=115200
```

```
rec noise1        <- 10 s of ambient noise
rec enciende1     <- a real "enciende" utterance
```

Each command records 10 s to the microSD and answers `DONE /noiseX.wav 320044 bytes` when finished (16 kHz / 16-bit mono WAV, ready for Edge Impulse). Labels must be unique — reusing one overwrites its file. Details and error handling: [docs/wav_recorder.md](docs/wav_recorder.md), full loop incl. augmentation: [docs/retraining.md](docs/retraining.md).

### 2. Download the model, compile and flash (`lampara_light`)

The model comes as an Arduino library zip from Edge Impulse (project "Lampara") — or as a **locally-trained model** injected into the library ([docs/self-training.md](docs/self-training.md)). Install it, then compile and send to the board:

```sh
arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.8-impulse-#1.zip"
arduino-cli compile -u -p $PORT --fqbn "esp32:esp32:XIAO_ESP32S3" lampara_light
arduino-cli monitor -p $PORT -c baudrate=115200
```

The monitor prints one prediction line per second; say *"enciende"* -> `>> LIGHT ON`, *"apaga"* -> `>> LIGHT OFF`. To update to a retrained model, see [docs/model.md](docs/model.md).

## Documentation

| Doc | Contents |
|---|---|
| [docs/hardware.md](docs/hardware.md) | Board, wiring diagrams, relay (D7/GPIO44, open-drain), SD card |
| [docs/model.md](docs/model.md) | Model install & update (Edge Impulse zip, label checks, library swap) |
| [docs/lampara_light.md](docs/lampara_light.md) | Monitor output, tuning defines, resolved hardware/model cases |
| [docs/wav_recorder.md](docs/wav_recorder.md) | Recorder serial commands, PSRAM requirement, SD handling |
| [docs/retraining.md](docs/retraining.md) | Full retraining loop: record -> upload -> retrain -> reflash |
| [docs/self-training.md](docs/self-training.md) | Local model training (EI-compatible, no Studio needed) |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Ports, SD errors, relay issues, bootloader recovery |
