# ARCHITECTURE

This diagram includes both runnable and target surfaces. Today the policy core, in-memory
grant lifecycle, authenticated API, local append-only JSONL ledger, synthetic seed,
mock-agent client, and local capture normalization are implemented. The capture wave's
local unit, privacy, scanner, and synthetic FFmpeg proofs pass. Model extraction, adapters,
console, and hardware modules remain incomplete.

```
                   owner console (blueprint UI, P5: MVP.jsx → live API)
                                      │ HTTP :8471
 phone walk (P2) → local intake → private frame batch     model proposal (planned)
                                      │                              │ owner confirm
                                      └─ no direct write ─────────────► housefile/store
                                                                     │
                                                        housefile/scoped_view (PURE)
                                                                     │
                                                        grants/manager ◄───┤ command gate
 ESP32 (USB) ◄─ hardware/{estop,display,receipt}              ▼
     E-stop trip → EVENT:ESTOP → adapters.halt_all()   core/events (best-effort bus)
                                      └──► adapters/{matter_rvc, home_assistant,
                                            valetudo_mqtt, automower}

 API policy boundary ── append + fsync ──► local JSONL ledger
 synthetic mock agent ── HTTP loopback ──► scoped read / command gate
```

The intake boundary accepts one local room source, invokes local `ffprobe`/`ffmpeg` with
bounded formats and frame counts, strips media metadata from normalized JPEGs, and stores
the batch only under ignored `data/capture/`. It neither imports the housefile store nor
calls a model. A later extraction wave must treat the private batch as untrusted input and
retain an explicit owner-confirmation gate before any canonical write.

The current descriptor-passing boundary is Linux-specific: inputs are opened with
`O_NOFOLLOW`, revalidated, and exposed to local tools through `/proc/self/fd`. Sources
inside the repository are refused unless they are under the ignored `media/raw/` boundary.

Import DAG: core ← housefile ← grants ← adapters ← api. Event-bus handlers are isolated,
but the bus is not the durability boundary: required API receipts use a synchronous ledger
append first, then notify in-process observers. The ledger contains only allowlisted event
fields in ignored local storage; it does not persist grant metadata and is not tamper-proof.
