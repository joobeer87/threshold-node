# ARCHITECTURE

This diagram includes both runnable and target surfaces. Today the policy core,
authenticated API, revisioned private grant authority, local append-only JSONL ledger,
explicit first-boot synthetic seed, IANA quiet-hours command gate, mock-agent client, and
local capture normalization are implemented. The capture wave's local unit, privacy,
scanner, and synthetic FFmpeg proofs pass. The GPT-5.6 proposal adapter, strict validator,
and local owner-decision record are implemented with provider-free tests; live model
evaluation, geometry, canonical materialization, adapters, console, and physical hardware
remain incomplete. The simulated appliance adds a process-local latched stop coordinator,
deterministic terminal frames, and a synthetic PNG receipt fallback; it proves only the
software path.

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
                                                                     ▲
 synthetic mock agent ── HTTP loopback ──► API grant lock ──► grants/authority
                                                │                    │
                                      UTC once + ZoneInfo             ├── pending/final
                                      command-only gate               │   private grant envelope
                                                                     └── prepared/committed
                                                                         JSONL ledger receipt

 owner-auth /sim/interlock/trip ── explicit demo + exact SIMULATED gate
                  │
                  ├─ latch process TRIPPED first
                  ├─ durable authority.suspend_all() + ESTOP (including zero active)
                  ├─ independent adapters[].halt_all() attempts (none configured)
                  └─ terminal TRIPPED + deterministic in-memory ESTOP PNG

 future NC loop/ESP32/OLED/printer ── not connected or verified

 durable append ──► core/events observers (best effort only)
```

`GrantAuthority` is the only integrated owner of usable grant state. The private envelope
contains complete bounded metadata and credential digests, never raw bearer values. Grant
manager decisions remain independently testable; the authority copies their target state
and commits it rather than exposing an in-place mutation before durability.

Each authority action is serialized under the API grant lock where applicable, the
authority's re-entrant lock, and a private POSIX advisory lock shared by local instances.
It reloads and verifies the store inside that file lock before use. Authenticated reads and
commands retain an authority lease through disclosure or the command decision plus its
durable receipt, so a concurrent revoke or suspension cannot land in between.
The authority prepares canonical ledger bytes at an exact offset/tail checkpoint, saves a
revisioned pending envelope, marks itself unavailable, appends and fsyncs that exact ledger
line as the commit point, then replaces the pending envelope with a clean target revision
and minimal ledger witness. On restart—or on the next request after an I/O failure—the
authority reloads the envelope before serving any grant. It aborts an uncommitted issue,
rolls a missing restrictive receipt forward while the restrictive target remains effective,
or finalizes a receipt already proven at the expected offset. Before doing so, it
reconstructs the base snapshot, compares it with the prior clean target hash, and verifies
the prior revision's exact ledger receipt. A mismatch, unrelated inserted grant, missing
prior receipt, or ambiguous pair fails closed with `503`; it never silently installs the
synthetic seed over existing state.

This recovery protocol protects against interrupted local writes, not malicious control of
both files. The store is not a database, the witness is not a hash chain, and neither file
is tamper-evident. Health reports both paths as configured rather than probing them; the
first grant operation performs authority loading and recovery.

The command path captures UTC once inside the grant lock, reuses it for grant and receipt
decisions, converts it with `zoneinfo.ZoneInfo`, and evaluates quiet hours before any relay.
An active interval produces a durable DENY and `403`; an invalid IANA timezone or malformed
policy produces a durable DENY and `503`. Scoped reads remain available outside this
command-only gate and include the timezone in their policy projection.

The simulated appliance surface is owner-authenticated and exists only when demo mode is
enabled and `ESP32_SERIAL` equals `SIMULATED` exactly. The interlock latches its current
process before calling display, persistence, adapters, or receipt code. Persistence uses
the same authority transaction as other restrictive grant transitions and records ESTOP
even when zero active grants exist. Adapter calls are isolated so one failure does not skip
later attempts. Duplicate trip requests reuse the first report without repeating effects.

The serving process denies grant use and issue whenever its latch is TRIPPED. A failed
durable transition therefore remains locally restrictive and makes the server re-arm route
return unavailable. A successful re-arm clears only that local latch; suspended grants
remain suspended across restart. The latch is not in the shared store, is not coordinated
between workers, and resets on process restart. Run the simulated appliance with one
worker. All reported elapsed values are explicitly `simulated_software_path_only`, never a
physical response-time or safety target.

The immutable display state renders control-safe `ARMED`, two-second `READ`, four-second
`DENY`, and latched `TRIPPED` terminal frames with a simulation banner. Receipt generation
accepts only allowlisted GRANT/DENY/ESTOP fields and produces deterministic 384×256
grayscale PNG bytes. The API generates its ESTOP fallback in memory and discards it; the
separate optional sink is private, single-link, and write-once. There is no ESP32, NC-loop,
OLED, printer, configured adapter, device actuation, or certified-safety evidence.

The file lock coordinates local processes only when they share the same private paths and
POSIX filesystem semantics; non-POSIX hosts fail closed. It is not a distributed lock and
does not coordinate separate hosts or replicated storage. The async API also performs
synchronous private-file validation and `fsync` while holding its request lock, so slow
storage blocks that worker's event loop. Non-blocking persistence and distributed
coordination are later work, not implicit properties of this design.

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
but the bus is not the durability boundary: the authority commits the ledger synchronously
and only then notifies in-process observers. The ledger contains allowlisted events plus
paired transaction/revision metadata; the separate private envelope persists grant
metadata. Neither surface is tamper-proof.
