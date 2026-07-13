# Demo script

## Runnable now — synthetic mock, no physical motion

Start the loopback node in synthetic demo mode with an empty private ledger+grant-store
pair, then run:

```bash
.venv/bin/python scripts/mock_robot.py --grant g-neo
```

The first empty demo boot provisions the synthetic grant. Later boots recover the same
digest-only grant state from the private store and its paired ledger; do not delete one file
to force re-seeding. To reproduce the exact three-request contract below, run outside the
synthetic fixture's `21:30–06:30` `Etc/UTC` quiet-hours window.

The client performs and validates exactly three requests:

1. A scoped housefile read proves the kitchen is disclosed while the workshop exposes only
   its no-go boundary.
2. Outside quiet hours, a kitchen navigation request passes policy but returns `503`,
   `policy_decision:allowed`, and `relayed:false` because no adapter is configured.
3. A workshop navigation request returns `403`, `policy_decision:denied`, and
   `relayed:false`.

The script prints bounded JSON Lines proof records, not the housefile, token, raw response,
URL, or exception details. Exit `0` means the exact contract passed; exits `2`–`5`
distinguish configuration, transport, API-contract, and safety failures. This sequence
demonstrates the permission boundary only—it does not claim robot movement or device-level
enforcement.

During the configured local quiet-hours window, the same authenticated kitchen command is
durably denied with `403`, `policy_decision:denied`, `relayed:false`, and
`reason:quiet_hours_active`. An invalid IANA timezone or malformed quiet-hours policy returns
`503` without relay. Scoped reads remain available under their normal grant and disclosure
checks. The focused API tests, rather than a wall-clock-dependent mock run, are the
deterministic evidence for this branch.

## Runnable now — synthetic simulated appliance, no hardware

The focused integration proof runs the complete THS-0051 sequence against temporary,
unmistakably synthetic trust state:

```bash
.venv/bin/python -m pytest -q tests/integration/test_simulated_appliance.py
```

It issues a grant, returns a scoped read, durably denies a no-go command, invokes the
owner-authenticated simulated trip route, and then denies the suspended grant. The trip
route is available only with explicit demo mode and `ESP32_SERIAL=SIMULATED`. It latches
the process before callbacks, persists one ESTOP event even when zero grants are active,
and attempts each injected adapter independently. Repeated trip calls while latched are
idempotent. The server currently configures zero adapters.

Re-arm clears the local latch only after its durable transition succeeded and never
restores a grant; the integration proof verifies that suspension survives re-arm and
authority restart. If persistence fails, the process stays TRIPPED, denies grant use and
issue, and refuses server re-arm. The latch itself is memory-only and single-worker; it
resets on process restart and is not coordinated across processes.

The terminal fallback has `READ <agent>` for two seconds, `DENY <agent>` for four seconds,
and latched `TRIPPED`. The synthetic receipt primitive deterministically renders allowlisted
GRANT/DENY/ESTOP text and PNG bytes; the API's ESTOP PNG is generated in memory and
discarded. Any elapsed field is labeled `simulated_software_path_only`, and
`physical_stop_verified` remains false. This proof contains no NC loop, ESP32, serial
bridge, OLED, printer, configured robot adapter, device movement/stop, or certified-safety
evidence.

## Runnable now — synthetic geometry/materialization, not a real floor plan

The focused provider-free proofs run against explicit synthetic bindings and private
temporary housefiles:

```bash
.venv/bin/python -m pytest -q \
  tests/unit/test_geometry.py \
  tests/unit/test_materialize.py \
  tests/integration/test_geometry_materialization.py
```

THS-0022 maps explicit room order to fixed 400×300 rectangles in an eight-column grid and
binds canonical output to exact proposal digests. It does not inspect frames or infer
physical dimensions, adjacency, access, no-go, or outdoor policy. THS-0023 then requires a
separate complete review with explicit names/access/outdoor values, the same digests, and
the expected synthetic housefile revision before a validated local atomic update.

This test output is suitable as software-path evidence only. Runtime geometry, review,
receipt, digest, and housefile artifacts stay private. Proposal confirmation does not call
the materializer, the API does not serve its output, and real-dwelling materialization is
not permitted by this proof. Keep blueprint-console footage in the target sequence until
PR #7 has frontend tests and a human visual review.

## Target submission sequence — 75 seconds

Target script only. Do not record or submit this sequence until each shown behavior has an
end-to-end test or captured local proof. Use synthetic house and actor data throughout.
Do not present the vision step as live-evaluated until a reviewed synthetic GPT-5.6 run has
recorded sanitized quality, latency, token-use, and cost evidence.

0–8s   Phone walks the hallway, frames stream into a terminal. VO: "Every robot maps your home for itself. This one maps it for you."
8–20s  Housefile plots on the blueprint console — title block, zones, shutoffs, flags.
20–35s Grant issued to the synthetic agent. Show a separately generated synthetic GRANT
receipt fallback; do not imply that the API printed it or operated a device.
35–48s Synthetic agent reads the granted room; the terminal shows READ. Show cleaning or
`ENFORCED` only if a real device-native area control has been separately proved. Workshop
stays hatched — boundary only.
48–58s Command aimed at the Workshop → 403; the simulated terminal shows DENY for four
seconds. A deterministic synthetic DENY PNG may be shown from a private temporary sink.
This must not be described as OLED or printer evidence.
58–68s Owner invokes the simulated trip route. Show TRIPPED and the grant becoming suspended;
label all timing `simulated_software_path_only` and show `physical_stop_verified:false`.
Do not imply a button press, adapter delivery, physical halt, OLED, or printed output.
68–75s Ledger scrolls. End card: "Your home's data belongs to the home. THRESHOLD."

Optional post-credit: reveal the public-safe Aurora signature from
`AURORA-EASTER-EGG.md`. Keep it out of the core 75 seconds unless the main permission loop
is already complete and legible.

Real-room footage must pass `REAL-FOOTAGE-CHECKLIST.md`; all visible housefile, receipt,
actor, and terminal data remains synthetic.
