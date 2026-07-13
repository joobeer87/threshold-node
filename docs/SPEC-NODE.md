# SPEC — THRESHOLD NODE (the appliance)

## Surfaces
1. **HTTP API** (FastAPI, :8471, loopback default; explicit reviewed LAN opt-in)
   - `GET  /housefile?grant=<id>` + per-grant bearer header → scoped payload (SPEC-THS §3)
   - `POST /command {grant, verb, zone, params}` + per-grant bearer header → policy-checks the request; returns unavailable until a real adapter exists
   - `POST /grants` (owner header + separate new-grant credential header) → generated ID,
     digest-only credential registration, public grant projection
   - `POST /grants/{id}/revoke` (owner-auth) → active/suspended grants become revoked;
     already-revoked or expired grants return unchanged
   - `GET /ledger?limit=<n>` (owner-auth) → bounded newest-first local events
   - `GET /health` → truthful pre-alpha capability state

Grant issue accepts `standing` or an RFC3339 `<start>/<end>` window and `revocable` or an
RFC3339 expiry. All timestamps require offsets. Both reads and commands evaluate the same
status/window/expiry decision before resource policy. Exact expiry or window end fails
closed with `403`. The decision clock is captured while holding the grant lock immediately
before evaluation. Any future adapter must recheck immediately before physical execution.
Grant credentials never appear in bodies, responses, events, or logs.

The command endpoint distinguishes a policy decision from physical execution. An allowed
request returns `503` with `policy_decision:allowed` and `relayed:false` while adapters are
unavailable. A no-go request returns `403` with `policy_decision:denied` and
`relayed:false`. `params` must remain empty until verb-specific parameter schemas are
implemented; non-empty parameters are denied.
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
6. **Vision proposal CLI** — `threshold.capture.openai_vision` operates only on a fixed
   private `data/capture/batch-<id>` created by THS-0020. `propose` requires the expected
   manifest SHA-256, an environment-only OpenAI API key, and explicit external-processing
   consent. `confirm|reject` prompts for owner authentication and requires the expected
   proposal SHA-256. The surface writes only private proposal/decision artifacts; it has no
   canonical housefile, adapter, grant, command, or hardware write capability.

All checked-in housefile, receipt, and console data is fictional. Real dwelling exports,
camera frames, device identifiers, credentials, and printed receipts belong in ignored
local storage only.

## Failure doctrine

Sensitive operations fail closed. A required decision event is appended and fsynced
before disclosure or a successful grant state-change response; ledger write failure
returns `503` and rolls back grant issue/revoke state. Best-effort event-bus observers are
isolated after the durable append. Adapter calls remain unimplemented, so the API reports
`relayed:false` and never upgrades an enforcement tier.

Health reports the ledger as configured, not probed. Missing storage reads as an empty
ledger; an unreadable or unsafe target returns `503` to the owner. Ledger inspection reads
only a fixed-size tail window so it cannot scan an ever-growing file while blocking policy
writes.

This prototype interlock is not a certified emergency-stop or life-safety system.
