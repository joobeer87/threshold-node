# ARCHITECTURE

This diagram includes both runnable and target surfaces. Today the policy core, in-memory
grant lifecycle, authenticated API, local append-only JSONL ledger, synthetic seed, and
mock-agent client are runnable. Adapters, console, capture, and hardware modules remain
incomplete.

```
                   owner console (blueprint UI, P5: MVP.jsx → live API)
                                      │ HTTP :8471
 phone walk (P2) → capture/vision → housefile/store → housefile/scoped_view (PURE)
                                      │          ▲            │
                                      │    grants/manager ◄───┤ command gate
 ESP32 (USB) ◄─ hardware/{estop,display,receipt}              ▼
     E-stop trip → EVENT:ESTOP → adapters.halt_all()   core/events (best-effort bus)
                                      └──► adapters/{matter_rvc, home_assistant,
                                            valetudo_mqtt, automower}

 API policy boundary ── append + fsync ──► local JSONL ledger
 synthetic mock agent ── HTTP loopback ──► scoped read / command gate
```

Import DAG: core ← housefile ← grants ← adapters ← api. Event-bus handlers are isolated,
but the bus is not the durability boundary: required API receipts use a synchronous ledger
append first, then notify in-process observers. The ledger contains only allowlisted event
fields in ignored local storage; it does not persist grant metadata and is not tamper-proof.
