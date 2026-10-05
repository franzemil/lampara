# Model (Edge Impulse)

The model ships as an Arduino library zip (`ei-lampara-arduino-<version>-impulse-#1.zip`, e.g. `1.0.8`).

- Impulse "Lampara": 1 s window @ 16 kHz, 16-bit mono
- Labels: `apaga` / `enciende` / `noise` — int8 TFLite, EON compiled
- The `noise` class absorbs everything that is neither command: when it wins, nothing happens

## Installing the library

arduino-cli blocks zip installs by default, so enable it once:

```sh
arduino-cli config set library.enable_unsafe_install true
```

Then install and verify:

```sh
arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.8-impulse-#1.zip"
arduino-cli lib list | grep Lampara
# Lampara_inferencing 1.0.8 ... user
```

The library lands in `~/Documents/Arduino/libraries/Lampara_inferencing`.

Arduino IDE alternative: **Sketch > Include Library > Add .ZIP Library...**

## Updating the model (new impulse version)

When you retrain in Edge Impulse Studio and export a new zip (e.g. `ei-lampara-arduino-1.0.8-impulse-#1.zip`), three steps put it on the device. **No sketch changes are needed** as long as the new model keeps the same labels (`apaga`, `enciende`, `noise`) and 1 s @ 16 kHz window — check before installing:

```sh
unzip -p "ei-lampara-arduino-1.0.8-impulse-#1.zip" \
  "Lampara_inferencing/src/model-parameters/model_variables.h" | grep categories
# expect: ... = { "apaga", "enciende", "noise" };
```

1. Swap the library (arduino-cli refuses to overwrite, so uninstall first):

   ```sh
   arduino-cli lib uninstall Lampara_inferencing
   arduino-cli lib install --zip-path "ei-lampara-arduino-1.0.8-impulse-#1.zip"
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
