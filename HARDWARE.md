# HARDWARE — parts, wiring, fallbacks

Links are **search-stable** (product listings churn; these queries don't). Pick the
top-rated hit. Prices in CAD, July 2026 ballpark. Everything has a software fallback —
a late package can delay a feature, never the build.

## Prototype BOM (prices checked July 2026)
| # | Part | ~CAD | Link | Fallback if late |
|---|---|---|---|---|
| 1 | 22 mm mushroom **stop/interlock**, twist-release, **1×NC + 1×NO** contact blocks | $15–25 | https://www.amazon.ca/s?k=22mm+emergency+stop+mushroom+push+button+NC+NO | keyboard key `e` (simulated driver) |
| 2 | 0.96" **SSD1306 OLED**, I2C, 2-pack (or 2.13" Waveshare e-ink if you want the drafting look) | $12–30 | https://www.amazon.ca/s?k=ssd1306+0.96+oled+i2c | terminal status pane |
| 3 | **ESP32 DevKit** (USB serial↔GPIO bridge for button + display) | $12–18 | https://www.amazon.ca/s?k=esp32+devkit+development+board | any ESP32/Arduino in the drawer; or J401 header (verify pinout first) |
| 4 | **TTL embedded thermal printer**, 58 mm, 5–9 V + paper rolls | $45–70 | https://www.amazon.ca/s?k=ttl+embedded+thermal+printer+58mm — canonical ref: https://www.adafruit.com/?q=thermal+printer | receipts render to PNG + display |
| 5 | 5 V ≥2 A supply for printer (printers brown-out USB) | $12 | https://www.amazon.ca/s?k=5v+3a+power+supply+barrel | bench supply |
| 6 | Dupont/JST jumpers, heat-shrink | $10 | drawer | drawer |
| 7 | Enclosure: panel-mount box ≥ button depth (~60 mm) | $15 | hardware store / 3D print | cardboard for demo, proudly |

**Estimated new spend ≈ CA$110–170.** Candidate host: Jetson Orin NX reComputer J4012
or another Python-capable edge computer. A webcam or phone is required for capture work.

## Robot for the live demo — $0 path exists
- **Own a Matter 1.4 vacuum or Automower?** Use it (see INTEGRATIONS.md).
- **Own neither?** Run a **virtual Matter RVC** via Matterbridge/matter.js (Matter 1.4 RVC
  with Service Area is implemented there) or a Valetudo/HA demo instance. The judges see
  a real protocol exchange either way. Buying a robot is OPTIONAL.

## Wiring (ESP32 bridge path — recommended)
```
STOP LOOP (NC)   ── GPIO27 ── external pull-up to 3V3 ── loop to GND
                    trip condition: GPIO reads HIGH (loop OPEN)
STOP LOOP (NO)   ── GPIO26 (redundant confirm, optional; bias explicitly)
SSD1306          ── I2C: SDA GPIO21, SCL GPIO22, 3V3, GND
Thermal printer  ── UART2: TX GPIO17 → printer RX, GND common, OWN 5V supply
ESP32 ↔ Jetson   ── USB (serial JSON lines, 115200)
```
**Semantics (do not soften):** NC loop, pull-up, **trip on open**. Wire break = stop.
Latching twist-release = deliberate re-arm. Re-arm does NOT restore grants — the owner
re-issues from the ledger screen. (SPEC-NODE §E-stop.)

Classic ESP32 GPIO34/35 are input-only and do not provide internal pull-ups. The
recommended GPIO27 path above therefore uses an external pull-up (10 kΩ is a reasonable
bench starting point; validate it for cable length and electrical noise). Confirm 3.3 V
logic levels, printer baud, and printer peak current against the exact parts before wiring.

> Prototype warning: this is a demo interlock, not a certified emergency-stop or
> life-safety circuit. Keep manufacturer controls and a physical power-isolation path.

## Bench test order (30 min, day parts arrive)
1. ESP32 blink → serial echo
2. Button loop reads: closed=LOW, open=HIGH, unplugged lead=HIGH (trip ✓)
3. OLED "THRESHOLD / ARMED"
4. Printer self-test page (hold feed on power-up), then serial "RECEIPT 000 TEST"
