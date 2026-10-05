# wav_recorder — training data collector

Sends `rec {label}` over serial -> records 10 s of audio to a WAV file on the microSD card. This is how the training samples for Edge Impulse are gathered.

## Requirements

- microSD card, FAT32, up to 32 GB, inserted in the expansion board
- **PSRAM must be enabled** (`:PSRAM=opi`, or Tools > PSRAM > OPI PSRAM in the IDE) because the 10 s audio buffer lives in PSRAM
- Requires ESP32 core 3.x (the legacy 2.x core does not support this sketch's I2S API)

## Serial commands (newline-terminated)

| Command | Response |
|---|---|
| `rec test1` | `REC /test1.wav` ... `DONE /test1.wav 320044 bytes` |
| anything while recording | `ERR busy` |
| malformed | `ERR usage: rec {label}` |

Files are 16 kHz / 16-bit mono WAV, ~320 KB per 10 s, exactly what Edge Impulse expects for this model.

## SD card handling

- **`ERR sd`** — reseat the card, format FAT32 (max 32 GB), gold fingers facing inward
- **Stuck at `SD init...` / silent after boot** — the SD card failed to initialize: reseat the card, then press **RESET**. If the device also stops answering uploads ("No serial data received"), enter bootloader mode (BOOT + RESET) to recover
- **Each label must be unique — the same label overwrites its file**
- To get the files off the card: power off, take the microSD out, copy the WAVs with a card reader
