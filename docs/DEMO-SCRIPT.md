# Demo script

## Runnable now — synthetic mock, no physical motion

Start the loopback node in synthetic demo mode, then run:

```bash
.venv/bin/python scripts/mock_robot.py --grant g-neo
```

The client performs and validates exactly three requests:

1. A scoped housefile read proves the kitchen is disclosed while the workshop exposes only
   its no-go boundary.
2. A kitchen navigation request passes policy but returns `503`,
   `policy_decision:allowed`, and `relayed:false` because no adapter is configured.
3. A workshop navigation request returns `403`, `policy_decision:denied`, and
   `relayed:false`.

The script prints bounded JSON Lines proof records, not the housefile, token, raw response,
URL, or exception details. Exit `0` means the exact contract passed; exits `2`–`5`
distinguish configuration, transport, API-contract, and safety failures. This sequence
demonstrates the permission boundary only—it does not claim robot movement or device-level
enforcement.

## Target submission sequence — 75 seconds

Target script only. Do not record or submit this sequence until each shown behavior has an
end-to-end test or captured local proof. Use synthetic house and actor data throughout.

0–8s   Phone walks the hallway, frames stream into a terminal. VO: "Every robot maps your home for itself. This one maps it for you."
8–20s  Housefile plots on the blueprint console — title block, zones, shutoffs, flags.
20–35s Grant issued to the robot (real Matter 1.4 RVC, virtual RVC, or Automower). Printer: GRANT receipt.
35–48s Robot cleans the granted room; console shows READ. Show `ENFORCED` only if a real
device-native area control has been proven. Workshop stays hatched — boundary only.
48–58s Command aimed at the Workshop → 403, DENY flashes on the OLED, printer: DENY receipt.
58–68s Operator presses the mushroom interlock. The demo robot parks. Display: TRIPPED. Printer: STOP. Two seconds of silence.
68–75s Ledger scrolls. End card: "Your home's data belongs to the home. THRESHOLD."

Optional post-credit: reveal the public-safe Aurora signature from
`AURORA-EASTER-EGG.md`. Keep it out of the core 75 seconds unless the main permission loop
is already complete and legible.

Real-room footage must pass `REAL-FOOTAGE-CHECKLIST.md`; all visible housefile, receipt,
actor, and terminal data remains synthetic.
