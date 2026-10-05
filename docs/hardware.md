# Hardware

## Board

- Seeed XIAO ESP32S3 Sense with expansion board
- PDM microphone: CLK = GPIO42, DATA = GPIO41
- microSD card, FAT32, up to 32 GB (only needed by `wav_recorder`)

## Relay (the light switch)

Relay module on header pin **D7 = GPIO44**, driven **open-drain**, active-LOW (IN pulled to GND = relay energized).

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

Notes:

- Power the module from the **5V** pin — most 5 V relay coils will not energize from 3V3
- The XIAO's 5V pin is only live when powered via **USB** (dead on battery)
- If the relay clicks inverted (enciende turns it off), set `LIGHT_ACTIVE_LOW` to `0`
- **NO** = normally open (load on when the relay energizes); **NC** behaves inverted

See [troubleshooting.md](troubleshooting.md) for the "relay always ON on 5V" case (open-drain fix, already in the code).
