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
   - `GET /health` → truthful pre-alpha capability state; ledger and grant-store paths are
     reported as configured, not probed

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
the later interlock wave; this version still does not claim that an E-stop input or adapter
halt is implemented.

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

Sensitive operations fail closed. API grant paths serialize through a process-local grant
lock; `GrantAuthority` also applies its own re-entrant lock and a private POSIX advisory
lock shared by local instances using the same paths. Every authority action reloads and
verifies the private envelope while that file lock is held, recovers any pending
transaction, and installs only a verified clean revision. Authenticated reads and commands
retain the authority lease through disclosure or the command decision and durable receipt,
so a concurrent revoke or suspension cannot overtake an allowed use.

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
files. Adapter calls remain unimplemented, so the API reports `relayed:false` and never
upgrades an enforcement tier.

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

This prototype interlock is not a certified emergency-stop or life-safety system.
