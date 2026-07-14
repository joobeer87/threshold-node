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
   - `GET /owner/status` (owner-auth) → bounded health, simulated interlock/display state,
     and active-grant count
   - `GET /owner/snapshot?ledger_limit=<n>` (owner-auth, `1..1000`) → one credential-free
     owner projection containing the current server housefile, public grants, owner status,
     and bounded newest-first ledger events
   - `POST /sim/interlock/trip` (owner-auth, explicit synthetic-demo gate) → exercise one
     latched software stop cycle and return bounded counters/nonclaims
   - `POST /sim/interlock/rearm` (owner-auth, explicit synthetic-demo gate) → clear only a
     process-local latch whose durable transition succeeded; never restore grants
   - `GET /health` → truthful pre-alpha capability state; ledger and grant-store paths are
     reported as configured, not probed; interlock state is process-local and always reports
     `physical_stop_verified:false`

Grant issue accepts `standing` or an RFC3339 `<start>/<end>` window and `revocable` or an
RFC3339 expiry. All timestamps require offsets. Both reads and commands evaluate the same
status/window/expiry decision before resource policy. Exact expiry or window end fails
closed with `403`. The decision clock is captured while holding the grant lock immediately
before evaluation. Any future adapter must recheck immediately before physical execution.
Grant credentials never appear in bodies, responses, events, or logs.

Grant metadata is authoritative across restart in a private revisioned envelope. The
envelope contains the complete bounded grant projection and credential digests, never raw
bearer credentials. Issue, revoke, observed expiry, and `suspend_all` transitions use the
same ledger-witnessed commit protocol described below. The suspend primitive is present for
the simulated interlock path. No physical E-stop input, NC loop, ESP32 bridge, adapter halt,
OLED, printer, or device stop is implemented or verified.

The command endpoint distinguishes a policy decision from physical execution. An allowed
request returns `503` with `policy_decision:allowed` and `relayed:false` while adapters are
unavailable. A no-go request returns `403` with `policy_decision:denied` and
`relayed:false`. `params` must remain empty until verb-specific parameter schemas are
implemented; non-empty parameters are denied.

Quiet hours gate commands only. While holding the grant lock, the server captures UTC once,
uses that value for the grant decision and ledger timestamps, converts it through
`zoneinfo.ZoneInfo` using the housefile's IANA timezone, and evaluates a start-inclusive,
end-exclusive interval. Overnight intervals wrap across midnight; equal start and end mean
quiet hours are active all day. Active quiet hours append and fsync DENY before returning
`403`. A missing/invalid timezone, unavailable timezone definition, or malformed start/end
appends DENY, relays nothing, and returns `503`. An invalid request clock returns `503`
before policy evaluation because no trustworthy receipt timestamp exists. Scoped reads do
not consult the quiet-hours gate.

2. **Simulated stop-interlock** — available only when owner authentication succeeds,
   `THS_DEMO_MODE=true`, and `ESP32_SERIAL` is exactly `SIMULATED`.
   - A new trip changes the in-memory state to `TRIPPED` before invoking any dependency.
   - It commits `suspend_all` plus one durable ESTOP ledger receipt even when zero grants
     are active, then attempts every injected adapter's `halt_all()` independently. One
     adapter exception cannot suppress later attempts or clear the latch.
   - Repeated calls during the same latch cycle return the first bounded report with
     `newly_tripped:false`; they do not repeat persistence, adapter, display, or receipt work.
   - If persistence fails, the current process still denies reads, commands, and new grant
     issue while TRIPPED, and the server refuses re-arm. No private exception detail is
     returned. After successful persistence, re-arm clears only the local latch and restores
     **no** grant; suspended status survives restart.
   - The latch is process-local and single-worker only. It is not shared across processes
     and does not survive restart. Every elapsed value is labeled
     `simulated_software_path_only`; `physical_stop_verified` is always false.
3. **Simulated terminal display states**: `ARMED n GRANTS` → `READ <agent>` (2 s) →
   `DENY <agent>` (4 s) → `TRIPPED` (latched). READ appears only after a durable READ
   ledger append; restrictive decisions drive DENY. Text is bounded and control-safe, and
   every rendered frame begins `THRESHOLD DISPLAY [SIMULATED]`.
4. **Synthetic receipt primitive** (fixed 384×256 grayscale PNG fallback):
```
THRESHOLD / SYNTHETIC DEMO
2026-07-18 14:02:03Z #000041
GRANT: SYNTHETIC UNIT 04
SCOPES: INVENTORY,LAYOUT,NAV
ZONES: KITCHEN,LIVING,OFFICE
TIER: GATED
SIMULATED SOFTWARE PATH
NOT A SAFETY SYSTEM
```
   Only GRANT, DENY, and ESTOP templates with fixed field allowlists are accepted through
   the factory; there is no credential, digest, arbitrary detail, or raw-payload input.
   Direct receipt construction is rejected and rendering rechecks factory integrity. PNG
   bytes are deterministic for exact inputs. The API exercises the ESTOP fallback in memory
   and discards it. An
   explicit optional sink accepts only a private `0700` directory and new `0600`, single-link,
   write-once PNG target; it rejects existing targets, symlinks, hardlinks, and public
   directories. No printer output is implemented.
5. **Owner console** — exact-pinned React/Vite/TypeScript application under `console/`.
   - Development origin is exactly `http://127.0.0.1:5173`; `/api` is proxied to the node
     at `http://127.0.0.1:8471`.
   - Owner routes accept no `Origin`, the request's exact same origin, or the fixed
     development origin. Foreign origins, excess preflight headers, and unsupported methods
     fail closed. `Access-Control-Allow-Origin: *` is prohibited.
   - Owner and new-grant tokens exist only in React component memory and request headers.
     They are excluded from URLs, cookies, browser storage, response bodies, screenshots,
     and build artifacts. Lock/reload clears page state; grant issue clears the distinct
     credential field after request construction.
   - The application implements locked, loading, ready, error, retry, refresh, and lock
     states; a canonical synthetic blueprint view; public grant list/issue/revoke; a bounded
     ledger table; and prominent ARMED/TRIPPED simulated-interlock presentation.
   - Snapshot and grant response traversal fails closed if a credential-like field appears.
     The API's `PublicGrant` schema omits credential material by construction.
   - Automated backend contract, frontend interaction, type/build, and accessibility checks
     are required. Human visual review remains a separate delivery gate.
6. **Vision proposal CLI** — `threshold.capture.openai_vision` operates only on a fixed
   private `data/capture/batch-<id>` created by THS-0020. `propose` requires the expected
   manifest SHA-256, an environment-only OpenAI API key, and explicit external-processing
   consent. `confirm|reject` prompts for owner authentication and requires the expected
   proposal SHA-256. The surface writes only private proposal/decision artifacts; it has no
   canonical housefile, adapter, grant, command, or hardware write capability.
7. **Deterministic geometry library** — `threshold.capture.geometry` accepts one explicit,
   ordered sequence of zone IDs, suggested names, proposal SHA-256 bindings, and locally
   assigned candidate IDs. Suggested names are trimmed printable Unicode, 1–80 characters.
   `ths/rectangular-strip-grid/0.1` maps order index `i` to
   `[(i % 8) * 400, (i // 8) * 300, 400, 300]` and emits canonical
   `ths/geometry-proposal/0.1` bytes plus their digest. It performs no model call,
   persistence, survey/spatial inference, or housefile write and has no access, no-go,
   restricted, outdoor, grant, command, or enforcement input. The caller supplies the
   proposal binding; this module does not open or authenticate proposal/decision artifacts.
8. **Owner-reviewed synthetic materialization library** —
   `materialize_housefile(path, geometry_bytes, review_payload)` is a separate explicit
   write boundary. The review must bind the exact geometry digest and each ordered proposal
   digest, declare `owner_reviewed:true` and `synthetic_fixture:true`, supply every zone's
   reviewed name/access/outdoor value, and match the current housefile revision. The
   implementation strictly parses the existing file, geometry, and review; validates the
   final THS-0.1 document; increments the revision; and commits under one private POSIX
   file lock with compare-and-swap, atomic replacement, directory fsync, and rollback on a
   failed final sync. The returned receipt contains only bounded digests, revisions, and a
   zone count. The review marker is declarative evidence, not owner authentication.

All checked-in housefile, receipt, and console data is fictional. Real dwelling exports,
camera frames, device identifiers, credentials, and printed receipts belong in ignored
local storage only.

Owner snapshot bodies are not publication-safe merely because credentials and digests are
absent. They can contain full housefile policy plus bounded activity context. The exact
origin policy is defense in depth alongside owner authentication, not authorization to
bind either process to a LAN, deploy the console, or claim transport security.

## Failure doctrine

Sensitive operations fail closed. API grant paths serialize through a process-local grant
lock; `GrantAuthority` also applies its own re-entrant lock and a private POSIX advisory
lock shared by local instances using the same paths. Every authority action reloads and
verifies the private envelope while that file lock is held, recovers any pending
transaction, and installs only a verified clean revision. Authenticated reads and commands
retain the authority lease through disclosure or the command decision and durable receipt,
so a concurrent revoke or suspension cannot overtake an allowed use.

Before recovering a pending transition, the store reconstructs its exact base snapshot by
restoring every recorded prior status and binds that snapshot to the previous clean target
hash. The authority also verifies the previous revision's exact ledger receipt before it
may append or finalize the pending receipt. An unrelated inserted grant or missing prior
receipt therefore makes recovery unavailable instead of becoming part of the next revision.

For a mutation, the authority prepares canonical ledger bytes against an exact ledger
offset and tail digest, then atomically saves a pending envelope containing the base and
target revisions, effective fail-safe grants, exact event, target digest, and receipt
digest. At that point the authority is unavailable to callers. The exact prepared ledger
line is then appended and fsynced; that append is the commit point. Finally the grant
envelope advances to the target revision with a minimal witness to that ledger line.

Recovery never guesses or performs an in-memory Python rollback across the two files. An
uncommitted pending issue is absent from the effective grant set and is aborted when its
exact ledger receipt is absent. Pending restrictive transitions already expose the target
revoked, expired, or suspended state; recovery appends a missing exact receipt and rolls
the transition forward. If the receipt is already present, recovery finalizes the witness.
A corrupt envelope, invalid pending record, witness mismatch, changed ledger precondition,
or ledger history with no grant store makes grant operations return `503`. Existing corrupt
or ambiguous state never falls back to demo seeds. First-boot seeds are created only in
explicit demo mode with a valid distinct demo credential, and are not usable before their
durable provisioning receipt.

Best-effort event-bus observers run only after the durable append and cannot change the
authority outcome. The store/ledger bindings detect torn or inconsistent local state but
are not a hash chain, tamper evidence, or protection from an attacker controlling both
files. The simulated coordinator isolates an injected adapter's exception and proceeds to
the next adapter. No adapter is configured by the server today, so this is control-flow
proof, not evidence of an adapter command or physical stop. The command API still reports
`relayed:false` and never upgrades an enforcement tier.

Health reports the ledger as configured, not probed. Missing storage reads as an empty
ledger; an unreadable or unsafe target returns `503` to the owner. Ledger inspection reads
only a fixed-size tail window so it cannot scan an ever-growing file while blocking policy
writes. Health likewise reports the grant store as configured, not available; grant use is
the authority probe.

The transaction lock coordinates local processes sharing the same paths and POSIX
filesystem semantics; non-POSIX hosts fail closed. It is not a distributed coordinator for
separate hosts or replicated storage. FastAPI currently performs synchronous locking,
private-file validation, and `fsync` work on its event loop, so slow storage can delay other
requests handled by that worker. This is a pre-alpha correctness path, not a throughput or
distributed-consensus design.

Geometry and materialization fail closed independently of the HTTP grant authority. An
invalid or noncanonical geometry document, changed geometry/proposal digest, reordered or
incomplete review, duplicate zone, stale revision, nonsynthetic target/review, unknown
field, schema violation, unsafe path, unavailable lock, write failure, or fsync failure
must not produce a successful receipt. The compare-and-swap is local to one filesystem and
one canonical target; it is neither a distributed transaction nor a claim of crash-proof
storage. Digest binding detects changed inputs but does not authenticate them or provide
tamper evidence.

The materializer is not invoked by vision confirmation or by the server. The running API
continues to serve the in-code synthetic seed, so a successfully materialized temporary
fixture is not live node state. Current writes are restricted to unmistakably synthetic
fixtures; real-dwelling materialization requires a separate security and workflow review.

The simulated latch is not a certified emergency-stop or life-safety system. Its software
timing does not prove physical response time, an NC loop, an ESP32 input, an OLED or printer,
adapter delivery, or device motion/stop.
