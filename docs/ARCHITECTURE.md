# ARCHITECTURE

This diagram includes both runnable and target surfaces. Today the policy core, in-memory
grant lifecycle, authenticated API, local append-only JSONL ledger, synthetic seed,
mock-agent client, and local capture normalization are implemented. The capture wave's
local unit, privacy, scanner, and synthetic FFmpeg proofs pass. The GPT-5.6 proposal adapter,
strict validator, and local owner-decision record are implemented with provider-free tests;
live model evaluation, geometry, adapters, console, and hardware remain incomplete.

```
                   owner console (blueprint UI, P5: MVP.jsx → live API)
                                      │ HTTP :8471
 phone walk → local intake → private frame batch ──explicit consent──► Responses API
                                      │                                      │
                                      │                         strict observation output
                                      │                                      ▼
                                      └────────► private proposal ──► owner decision artifact
                                                     │                       │
                                                     └─ no direct write ──────┘

 future THS-0022 geometry + reviewed materialization ─────────► housefile/store
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
calls a model.

The proposal boundary accepts only a batch ID plus the expected manifest digest. It
revalidates the private manifest and every normalized frame, selects at most eight bounded
frames, and requires explicit external-processing consent before constructing a fixed
OpenAI Responses API request. No user URL, tool, function call, model override, or path is
available. Structured output is revalidated into a deliberately incomplete observation
proposal: no boundary, access, policy, grant, command, or enforcement field exists.

The proposal file binds the batch, manifest, ordered frame hashes, prompt version, model,
and validator version. A separate owner-authenticated command records exactly one
digest-bound confirm/reject artifact. Neither path imports `housefile/store.py`. Content
hashes detect later changes but are not tamper evidence against an attacker controlling the
local filesystem. THS-0022 still owns geometry before any future canonical materialization.

The current descriptor-passing boundary is Linux-specific: inputs are opened with
`O_NOFOLLOW`, revalidated, and exposed to local tools through `/proc/self/fd`. Sources
inside the repository are refused unless they are under the ignored `media/raw/` boundary.

Import DAG: core ← housefile ← grants ← adapters ← api. Event-bus handlers are isolated,
but the bus is not the durability boundary: required API receipts use a synchronous ledger
append first, then notify in-process observers. The ledger contains only allowlisted event
fields in ignored local storage; it does not persist grant metadata and is not tamper-proof.
