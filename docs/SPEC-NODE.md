# SPEC — THRESHOLD NODE (the appliance)

## Surfaces
1. **HTTP API** (FastAPI, :8471, loopback default; explicit reviewed LAN opt-in)
   - `GET  /housefile?grant=<id>` + per-grant bearer header → scoped payload (SPEC-THS §3)
   - `POST /command {grant, verb, zone, params}` + per-grant bearer header → policy-checks the request; returns unavailable until a real adapter exists
   - `POST /grants` · `POST /grants/{id}/revoke` (owner-auth)
   - `GET  /ledger` (owner-auth) · `GET /health` → truthful pre-alpha capability state
2. **E-stop** — NC loop (HARDWARE.md). On trip:
   (a) all active grants → `suspended` (latency target must be measured before a claim);
   (b) every adapter runs its native halt (RVC Pause/GoHome; Automower ParkUntilFurtherNotice);
   (c) ESTOP ledger entry; (d) display TRIPPED (latched); (e) receipt if printer present.
   Twist-release re-arm restores **nothing** automatically — owner re-issues from the console.
3. **Display states**: `ARMED n·grants` → `READ <agent>` (2 s) → `DENY <agent>` (inverse, 4 s) → `TRIPPED` (latched).
4. **Receipt** (58 mm, mono):
```
THRESHOLD · SYNTHETIC DEMO HOUSE
2026-07-18 14:02      #000041
GRANT  NEO UNIT 04
scopes: layout,inventory,nav
zones : kitchen,living,office
tier  : ENFORCED (matter-rvc)
-- boundary transmitted, interior withheld --
```
5. **Owner console** — reference/Threshold-MVP.jsx rebuilt against the live API (P5). Same blueprint UI, synthetic demo data.

All checked-in housefile, receipt, and console data is fictional. Real dwelling exports,
camera frames, device identifiers, credentials, and printed receipts belong in ignored
local storage only.

## Failure doctrine
The node never crashes. Adapter exceptions: catch, log, degrade that adapter to ADVISORY,
display the honest tier. Validation refusals are INFO-level, not errors.

This prototype interlock is not a certified emergency-stop or life-safety system.
