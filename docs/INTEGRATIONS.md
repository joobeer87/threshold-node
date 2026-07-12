# INTEGRATIONS — robot protocol landscape (researched 2026-07-11)

## 1. Matter RVC — the standards track (vacuums)
- RVC device type since **Matter 1.2** (Oct 2023): clusters `RVC Run Mode`, `RVC Clean Mode`, `RVC Operational State`.
- **Matter 1.4** (Nov 2024) added the **Service Area cluster**: list areas, select target rooms/zones,
  skip zones, track progress. Areas are defined in the vendor app. Certified 1.4 units on market
  (SwitchBot S20/K11+, recent Roborock & Ecovacs firmware; DJI certifying on 1.4.2).
- Home Assistant 2026.3+ issues Matter service-area commands → cheapest ENFORCED path:
  a **THS zone ↔ ServiceArea mapping table** (name-match with manual owner confirm).
- No robot on hand? **Matterbridge / matter.js ships a virtual Matter 1.4 RVC** — the $0 demo path.
  Caveat: Apple-Home-bridged RVCs are quirky; pair the virtual device to HA instead.
- Adapter: `adapters/matter_rvc.py` — via HA websocket first (THS-0030), native matter.js sidecar later (THS-0031).

## 2. Automower Connect — official mower API (tondeuse)
- Husqvarna developer portal (developer.husqvarnagroup.cloud), OAuth2 app key/secret,
  **REST commands + WebSocket pushed state**. Rate limits ≈ 10k req/month, 1 req/s → cache, subscribe, don't poll.
- Exposes **work areas** and **stay-out zones** as first-class objects; HA surfaces a switch per
  stay-out zone (ON = mower avoids it). That IS `access:no-go` for `outdoor:true` zones → **ENFORCED**.
- Halt verb for E-stop: `ParkUntilFurtherNotice`. Per-work-area schedule override supported.
- Caveats: cloud-dependent (print a residency exception on receipts); EPOS satellite-boundary mowers
  lack stay-out control via HA → degrade honestly to GATED. Mammotion / Bosch Indego: MQTT/unofficial → GATED via HA `lawn_mower`.

## 3. Home Assistant — the universal bridge
- `vacuum` + `lawn_mower` entity platforms cover hundreds of devices. Threshold connects as a
  websocket client (long-lived token) and filters every service call through the grant gate.
  Tier: GATED, or ENFORCED where the underlying integration exposes area/stay-out primitives.

## 4. Valetudo / MQTT — the ideological twin
- Cloud-free vacuum firmware; MQTT + HA autodiscovery; local segment (room) cleaning →
  GATED-to-ENFORCED by model. Belongs in the local-first demo narrative.

## 5. iRobot & friends (post-hackathon, T4)
- dorita980-class local protocols, python-miio for Xiaomi-family. Roomba Combo 10 Max gained Matter via firmware → route through §1.

## Adapter contract (`adapters/base.py`)
`capabilities() → {areas, stayout, halt}` · `sync_zones(housefile) → ZoneMap{ths_zone→native, tier}` ·
`relay(cmd) → Result` · `halt_all() → Result` (E-stop path: must never raise).
Tier is computed from capabilities, never asserted.
