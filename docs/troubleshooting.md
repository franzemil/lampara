# Troubleshooting

- **Port not found / upload fails** — recheck `arduino-cli board list`; if still failing, hold **BOOT**, press **RESET**, release **BOOT** to enter bootloader mode and retry
- **Recorder silent after boot / stuck at `SD init...`** — the SD card failed to initialize: reseat the card, then press **RESET**. If the device also stops answering uploads ("No serial data received"), enter bootloader mode (BOOT + RESET) to recover
- **`ERR sd` on the recorder** — reseat the card, format FAT32 (max 32 GB), gold fingers facing inward
- **`Error sample buffer overrun`** — the DSP cannot keep up; reduce other load or re-export a smaller window model
- **False triggers** — see [lampara_light.md](lampara_light.md) "false positives" case; raise `LIGHT_TRIGGER_THRESHOLD`/`LIGHT_TRIGGER_MARGIN` or retrain with a noise class
- **Relay doesn't switch** — flash `relay_blink` (D7 blink) and bench-test: touch the IN wire directly to **GND** (should click ON on active-low modules) and to **3V3** (should release). If the manual test works but D7 doesn't, recheck the wire is on the bottom-left pad (D7/GPIO44); if the manual test fails, it's power: `VCC` must be 5V, `GND` shared with the XIAO, USB power connected
- **Relay always ON** — see [lampara_light.md](lampara_light.md) "relay always ON on 5V" case (open-drain output is the fix, already in the code)
- **Sketch totally silent after wire changes / uploads behave erratically** — a wire bridging the **BOOT pad/button** holds the chip in the bootloader; check the corners near the USB connector, then press **RESET**
- If a future Edge Impulse SDK export ever fails to compile on core 3.x, `arduino-cli core install esp32:esp32@2.0.17` provides the legacy core (the `wav_recorder` sketch requires 3.x, `lampara_light` would need its mic layer reverted to the legacy `driver/i2s.h` API from the stock EI example)
