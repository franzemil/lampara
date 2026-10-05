# lampara_light — voice-controlled light

Always-listening keyword spotter: says *"enciende"* -> light on, *"apaga"* -> light off, using the Edge Impulse model installed as the `Lampara_inferencing` library (see [model.md](model.md)).

## Monitor output

After boot it prints the model settings and `Listening...`, then one prediction line per second:

```
Predictions (DSP: 145 ms., Classification: 3 ms.): apaga: 0.013 enciende: 0.021
Predictions (DSP: 141 ms., Classification: 3 ms.): apaga: 0.948 enciende: 0.011
>> LIGHT OFF (apaga: 0.948)
```

Say *"enciende"* -> `>> LIGHT ON`, *"apaga"* -> `>> LIGHT OFF`.

## Tuning (defines at the top of `lampara_light.ino`)

| Define | Default | Meaning |
|---|---|---|
| `LIGHT_PIN` | `44` | Relay IN pin, header pin D7 (GPIO44), open-drain |
| `LIGHT_ACTIVE_LOW` | `1` | `1` = pin LOW energizes the relay; `0` = active-high |
| `LIGHT_TRIGGER_THRESHOLD` | `0.8` | Minimum confidence to trigger |
| `LIGHT_TRIGGER_MARGIN` | `0.15` | Winner must also beat **every** other class (including `noise`) by at least this much |
| `LIGHT_COOLDOWN_MS` | `1500` | Ignore new triggers for this long after one fires |
| `AUDIO_GAIN` | `4` | Mic input gain. Training WAVs were recorded with x4 gain, keep in sync |

## Case: relay always ON when powered from 5V (RESOLVED)

Symptom: with the relay module's VCC on the **3V3** pin, the relay toggled correctly; with VCC on **5V/VBUS**, it stayed energized permanently regardless of the GPIO state.

Why: the module's input is an optocoupler LED between **VCC and IN**, triggered active-LOW. A 3.3V GPIO driving HIGH against a 5V VCC still leaves 5 − 3.3 = **1.7V across the input** — enough current to keep the optocoupler (and the relay) on. On 3V3 the difference is 0V, which is why it worked there — but the relay coil is a 5V coil and is under-driven at 3V3.

Resolution: the GPIO is configured as **open-drain** (`OUTPUT_OPEN_DRAIN`). LOW = pin pulled to GND → relay solidly ON; HIGH = pin floats → no voltage difference at all → relay truly OFF. VCC stays on 5V, so the coil always gets its full rated voltage. Applied to both `lampara_light` and `relay_blink`.

If you ever swap to an active-HIGH module or a logic-level MOSFET board, change the `pinMode()` back to plain `OUTPUT`.

## Case: false positives with a 2-class model (RESOLVED)

Observed on the first flash (model v1.0.1, only `apaga`/`enciende`, 0.6 threshold, no margin):

- Ambient noise scored >0.6 on `apaga` almost every second (`>> LIGHT OFF` spam — harmless but noisy logs)
- One random noise spike scored `enciende: 0.886` and falsely turned the light **ON**

Why: with only the two word classes, the classifier's softmax always produces a winner. Silence, music or speech that is neither "enciende" nor "apaga" still gets pushed toward one of them.

Resolution (model v1.0.3 + current code): the model was retrained with a third `noise` class (samples collected with `wav_recorder`, see [retraining.md](retraining.md)), and the trigger logic now requires a command to clear the threshold **and** beat every other class — `noise` included — by `LIGHT_TRIGGER_MARGIN`. Verified on-device: ambient noise scores `noise: 0.95+` and produces zero light events.

Remaining tuning knobs if false triggers ever come back:

1. **Retrain with more negative samples** — collect 1-2 minutes more of ambient noise, silence and random speech with `wav_recorder` and add them to the `noise` class
2. **Raise threshold/margin** — e.g. `LIGHT_TRIGGER_THRESHOLD 0.9`, `LIGHT_TRIGGER_MARGIN 0.2`
3. **Cooldown** — `LIGHT_COOLDOWN_MS` limits how often a trigger can fire at all

If real utterances start getting missed (model not confident enough on your voice), lower the threshold to 0.7 or the margin to 0.1 and retest.
