# Threshold Node

**The permission slip robots read before entering your home.**

Threshold Node is a local-first permission appliance for domestic robots and agents. It
keeps a machine-readable *housefile* under the owner's control, returns only the zones and
capabilities granted to a caller, refuses no-go actions, and records access decisions.

> Pre-alpha scaffold: the scoped-view policy core, authenticated grant lifecycle API,
> crash-recoverable private grant state, timezone-aware command policy, durable local
> decision ledger, synthetic mock-agent proof run, privacy-first local capture intake, and
> a guarded GPT-5.6 observation-proposal adapter. A simulated, process-local stop-interlock,
> deterministic terminal states, and a synthetic PNG receipt fallback are implemented with
> software-path tests. Deterministic digest-bound geometry and a separate synthetic-only,
> owner-reviewed housefile materializer are implemented as local library boundaries. An
> owner-authenticated loopback snapshot API and React/Vite/TypeScript console provide
> credential-free housefile, grant, interlock, and bounded-ledger views plus grant
> issue/revoke controls. Live model quality has not been evaluated, and real-dwelling
> materialization, live loading of materialized housefiles, robot adapters, ESP32/NC-loop
> input, OLED/printer output, and physical stopping are not implemented. The owner accepted
> the corrected console visual review on 2026-07-14.
> This is not a life-safety system.

## Why this exists

Robots commonly build separate proprietary maps and permission models. Threshold inverts
that relationship: the home owns one local policy model, while each robot receives a
scoped, revocable view. No-go boundaries transmit; their interiors do not.

The checked-in house, seed grants, tests, and UI reference are unmistakably synthetic.
Real dwelling exports, camera frames, device identifiers, credentials, and receipts must
stay in ignored local storage.

## Current proof

- Pure `scoped_view` policy function with defense-in-depth around no-go zones.
- Per-grant bearer authentication for robot reads and commands.
- Separate owner authentication for grant issue/revoke and ledger access.
- Owner-authenticated `GET /owner/snapshot` and `GET /owner/status` projections. The
  snapshot returns the server's current canonical housefile, public grant projections,
  bounded newest-first ledger data, and truthful simulated interlock/health state without
  credential digests. Both owner projections durably persist any exact-boundary grant
  expiry they first observe before reporting grant status or the active-grant count.
- A loopback React/Vite/TypeScript owner console with explicit loading, error, retry, and
  lock states; blueprint, grants, bounded-ledger, and prominent `TRIPPED` views; and grant
  issue/revoke controls. Owner and new-grant tokens remain in page memory only and are
  never placed in browser storage, cookies, URLs, response bodies, or build artifacts.
- An exact owner-route origin policy: no `Origin`, the request's same origin, or exactly
  `http://127.0.0.1:5173` is accepted. Foreign origins and unapproved preflight headers
  fail closed, and wildcard CORS is never emitted.
- Server-generated grant IDs, digest-only credential storage, revocation, RFC3339 expiry,
  and start-inclusive/end-exclusive access windows.
- An authoritative, revisioned private grant envelope: complete grant metadata persists
  across restart, while raw bearer credentials never do. Issue, revoke, observed expiry,
  and the suspend transition use one ledger-witnessed recovery protocol.
- Pending issues are never usable before their exact durable ledger receipt. Pending
  restrictive transitions remain denied; corrupt, missing-with-history, or ambiguous
  authority state makes grant operations fail closed with `503` rather than loading seeds.
- Explicit first-boot synthetic seeding only when demo mode and a distinct valid demo
  credential are configured.
- Append-only local JSONL decision records with allowlisted fields, fsync-before-response,
  and bounded owner reads. This is durability, not tamper evidence.
- Command-only quiet-hours gating in an explicit IANA timezone. Active quiet hours produce
  a durable denial and `403`; an invalid timezone or policy produces no relay and `503`.
  Scoped reads are unaffected.
- Owner-authenticated simulated trip and re-arm routes enabled only when demo mode is on
  and `ESP32_SERIAL` is exactly `SIMULATED`. Trip latches first, commits grant suspension
  plus an ESTOP receipt even with zero active grants, then attempts every injected adapter
  independently. Repeated trip calls while latched do not repeat those effects.
- Fail-closed simulated latch handling: if durable suspension fails, that server process
  remains TRIPPED, denies grant use and issue, and refuses re-arm. After a successful trip,
  re-arm clears only the process-local latch and never restores suspended grants.
- Deterministic terminal frames for `ARMED`, two-second `READ`, four-second `DENY`, and
  latched `TRIPPED`, plus allowlisted GRANT/DENY/ESTOP text and fixed-bitmap PNG generation.
  The optional PNG sink is private and write-once; the API's ESTOP fallback is generated in
  memory and discarded.
- Loopback-only default; non-loopback binding requires an explicit opt-in.
- Strict command schema that refuses unsupported verbs and non-empty parameters until
  verb-specific schemas exist, and never claims a stub adapter relayed an action.
- An exit-coded mock agent that proves scoped read → policy-allowed but not relayed →
  no-go denial without printing the housefile or credentials.
- A bounded, local-only intake that normalizes one room's JPEG/PNG photos or MOV/MP4/M4V
  video into private JPEG frames without calling a model or changing the housefile.
- An explicit-consent OpenAI Responses API adapter that sends only verified normalized
  frames, requires strict structured output, revalidates it locally, and records a
  digest-bound owner decision without creating policy or writing the housefile.
- A deterministic rectangular geometry proposal built only from explicit room order and
  exact proposal digests. It is a fixed sketch—not model, survey, or spatial inference—and
  contains no access, no-go, outdoor, grant, or command policy.
- A separate synthetic-only materializer that requires the exact geometry and per-zone
  proposal digests, explicit owner-reviewed names/access/outdoor choices, and the expected
  housefile revision. It validates THS-0.1, increments the revision under a private POSIX
  lock, and atomically replaces one local canonical fixture with rollback on a failed
  directory sync. Its receipt contains no room names or policy values.
  The synthetic markers are a fail-closed workflow gate, not proof that arbitrary supplied
  content is fictional.
- Simulator-first fixtures and a sanitized public-release scanner that rejects tracked
  runtime data, including capture and receipt artifacts, even if force-added to Git.

## Framework

The current core is Python 3.10+ with FastAPI and Pydantic. That is a good fit for a Jetson
or other edge host and keeps the policy layer easy to test. The recommended product stack
is:

- FastAPI for the local policy/API node;
- Vite + React + TypeScript for the loopback owner console;
- Arduino/PlatformIO for the ESP32 bridge;
- Matterbridge/matter.js only where the virtual Matter RVC demo needs it;
- OpenAI Responses API with GPT-5.6 structured outputs for vision-to-housefile proposals,
  always behind deterministic validation and explicit owner confirmation.

The model adapter and provider-free contract tests are implemented. A live synthetic
GPT-5.6 quality/cost evaluation is still required before calling the extraction flow
demo-proven. The geometry/materialization proof uses only unmistakably synthetic temporary
fixtures, does not make model-quality claims, and is not wired into the live API. The
simulated appliance proof likewise proves no physical hardware behavior. The console has
automated backend contract, frontend interaction, type/build, and accessibility coverage,
and its final human visual recheck is complete. The accepted recheck covered the loading
dwell, gold/crimson semantic separation, and blueprint label containment. The implemented
loopback-console delivery gate is `pass`; this is not broad browser/device validation and
does not make the broader prototype deployed, submission-ready, or physically proven.
A read-only review found a reusable AuroraOS local-Vault runner pattern, but there is no
Threshold-specific approved credential injector. Building that narrow runner and approving
its Vault path/read and one direct Responses call remain a separate operator-gated wave;
headless Codex may orchestrate work but is not the evaluation transport.
See [`docs/BUILD-WEEK.md`](docs/BUILD-WEEK.md).

## Quickstart (synthetic demo only)

```bash
make install
```

Generate two different random values locally (for example with Python's `secrets` module),
export them as `THS_OWNER_TOKEN` and `THS_DEMO_GRANT_TOKEN`, then enable the synthetic demo:

```bash
export THS_DEMO_MODE=true
make run
```

On a first boot with no grant-store file and no ledger history, explicit demo mode creates
only the synthetic `g-neo` grant and durably records that provisioning. An existing store
is authoritative. Corrupt state, or ledger history with no matching store, returns `503`;
it never falls back to demo seeds.

In another shell with the same demo grant token exported:

```bash
.venv/bin/python scripts/mock_robot.py --grant g-neo
```

The script emits three bounded JSON Lines proof records. Outside the fixture's configured
quiet hours, the middle request returns `503` because policy allows it but no adapter
exists; `relayed` remains `false`. During quiet hours the command is durably denied with
`403` instead. The final workshop request returns `403`. No robot movement is performed or
claimed.

### Owner grant workflow

For API-created grants, generate a third distinct local token and retain it as
`THS_NEW_GRANT_TOKEN`; the server receives it only in a dedicated request header from a
masked input, stores its digest, and never returns the credential. Issue a synthetic grant
with:

```bash
curl --fail-with-body -X POST http://127.0.0.1:8471/grants \
  -H "X-Threshold-Owner-Token: ${THS_OWNER_TOKEN}" \
  -H "X-Threshold-New-Grant-Token: ${THS_NEW_GRANT_TOKEN}" \
  -H "Content-Type: application/json" \
  --data '{"name":"Synthetic Demo Agent","kind":"agent","scopes":["read:layout","command:navigate"],"zones":["kitchen"],"window":"standing","expires":"revocable"}'
```

Retain the returned grant ID as `RETURNED_GRANT_ID`. Revocation and bounded ledger
inspection use owner auth:

```bash
curl --fail-with-body -X POST \
  -H "X-Threshold-Owner-Token: ${THS_OWNER_TOKEN}" \
  "http://127.0.0.1:8471/grants/${RETURNED_GRANT_ID}/revoke"

curl --fail-with-body \
  -H "X-Threshold-Owner-Token: ${THS_OWNER_TOKEN}" \
  'http://127.0.0.1:8471/ledger?limit=20'
```

With demo mode enabled and `ESP32_SERIAL=SIMULATED`, the owner can exercise the bounded
software-only latch:

```bash
curl --fail-with-body -X POST \
  -H "X-Threshold-Owner-Token: ${THS_OWNER_TOKEN}" \
  http://127.0.0.1:8471/sim/interlock/trip

curl --fail-with-body -X POST \
  -H "X-Threshold-Owner-Token: ${THS_OWNER_TOKEN}" \
  http://127.0.0.1:8471/sim/interlock/rearm
```

The trip response labels its elapsed value `simulated_software_path_only` and always says
`physical_stop_verified:false`. A successful first trip durably suspends active grants and
records one ESTOP event; the duplicate call is idempotent. Re-arm restores no grant. If the
durable transition fails, the process keeps denying while TRIPPED and the server refuses
re-arm. The latch itself is in memory and is not coordinated across workers or processes;
the persisted suspended grant state is the only restart proof. Run this pre-alpha API with
one worker.

### Owner console (loopback development only)

With Node.js 22.13 or newer, install the console's exact committed dependency graph and
start the fixed loopback Vite server:

```bash
cd console
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`. Vite proxies `/api` to the node at
`http://127.0.0.1:8471`; the backend accepts that one development origin plus same-origin
or origin-less owner requests. It never emits wildcard CORS. Enter the owner token only in
the password field. It is held in React memory for the page lifetime and cleared by
**Lock** or reload; do not use browser storage, URL parameters, screenshots, or recordings
for credentials.

The console loads a credential-free snapshot, renders the server's current synthetic
housefile blueprint, public grant projections, bounded ledger events, and truthful
interlock/display state. Issue sends a separately generated grant credential once in the
dedicated request header from a masked input and clears the field; the API persists only
its digest. `TRIPPED` remains a simulated software state, re-arm never restores suspended
grants, and no console action proves relay, motion, physical stopping, or certified safety.

The node listens on `127.0.0.1:8471` by default. It writes its private ledger and grant
envelope under ignored `data/` storage unless `THS_LEDGER_PATH` and
`THS_GRANT_STORE_PATH` are set. These files are one recovery pair: do not delete, copy, or
replace only one side and expect the other to be accepted. For an intentionally fresh
synthetic demo, select a fresh pair of local paths. Never use that reset procedure for real
household state.

The authority uses a private POSIX advisory lock to serialize reload, recovery, mutation,
and authenticated use across local instances that share the same store/ledger pair. An
authorization lease remains held through disclosure or the command decision and its
receipt, so a concurrent revoke or suspension cannot overtake protected use. This is local
file coordination, not distributed consensus, and non-POSIX hosts fail the transaction
lock closed. Synchronous private-file validation and `fsync` still run on the server event
loop, so this pre-alpha path is not a high-throughput service. Do not expose the node to a
LAN or the internet until the threat model, transport security, and hardware behavior have
been reviewed.

Owner and demo grant tokens must be different, 32–512-character visible-ASCII values.
The grant store contains credential digests and private grant metadata, not raw bearer
values. All runtime grant stores and `*.jsonl` files stay local because custom paths can
still contain private household state and activity data.

### Local capture intake

Wave 3 accepts exactly one local room source per invocation: one JPEG/PNG image, one
MOV/MP4/M4V video, or one flat directory containing only JPEG/PNG images. `ffmpeg` and
`ffprobe` must be available on `PATH`. This hardened intake currently requires Linux with
`/proc/self/fd` support (including the target Jetson environment). Keep the source outside
the repository checkout, or place it under ignored `media/raw/`; any other in-repository
source is refused. Choose a local-only room label and do not add it to committed fixtures
or documentation.

```bash
export LOCAL_ROOM_CAPTURE=/path/to/local-room-capture
.venv/bin/python -m threshold.capture.vision_intake \
  --room room-01 \
  --max-frames 8 \
  "${LOCAL_ROOM_CAPTURE}"
```

`--max-frames` accepts 1–12. The command writes a bounded normalized JPEG batch under
ignored `data/capture/` storage and emits one sanitized JSON receipt. The receipt contains
counts and hashes, not the source path, original filenames, room label, or tool output.
Capture batches and their runtime receipts can still describe or fingerprint a real home:
keep both local and never force-add them to Git.

This command performs intake only. It makes no network or model call and cannot write the
canonical housefile.

### Private vision proposal

The next command is a separate privacy boundary: selected normalized frames leave the
device for OpenAI processing. Review the batch first, set `OPENAI_API_KEY` only in the local
process environment, and pass the explicit consent flag with the batch ID and manifest
digest from the intake receipt:

```bash
.venv/bin/python -m threshold.capture.openai_vision propose "${BATCH_ID}" \
  --manifest-sha256 "${MANIFEST_SHA256}" \
  --allow-external-processing
```

The Responses API request uses GPT-5.6, Base64 image inputs, `detail: high`, `store: false`,
no tools, and strict JSON Schema output. Threshold then performs a second deterministic
validation pass and saves a private proposal under a write-once filename beside the batch.
The proposal is digest-bound and revalidated before an owner decision; it is not described
as immutable or tamper-evident. Image text and QR codes are treated as observations, never
instructions. Provider errors and refusals are reduced to fixed receipts that do not
reflect response bodies, paths, prompts, or keys.

Inspect the private proposal locally. To record an owner decision, use the proposal ID and
digest from the receipt; the command prompts securely for `THS_OWNER_TOKEN`:

```bash
.venv/bin/python -m threshold.capture.openai_vision confirm \
  "${BATCH_ID}" "${PROPOSAL_ID}" \
  --proposal-sha256 "${PROPOSAL_SHA256}"
```

Use `reject` instead of `confirm` to reject it. Either action writes only a terminal private
decision artifact. Confirmation means “owner-approved proposal,” not “policy applied”: it
does not produce boundaries, assign access, or write the canonical housefile. Proposal,
decision, and runtime receipt files remain private even when their output shape is
sanitized.

### Synthetic geometry and reviewed materialization

THS-0022 and THS-0023 are deliberately separate local library boundaries. Geometry takes
an explicit ordered list of room bindings and produces fixed 400×300 rectangles in an
eight-column strip/grid. Every room binds a proposal SHA-256 and locally assigned candidate
ID; reordering or changing a binding changes the geometry digest. The algorithm does not
read pixels, infer dimensions, choose policy, or open a proposal/decision artifact. The
caller remains responsible for selecting the caller-asserted confirmed private proposal
digests; the geometry module does not verify that confirmation.

Materialization accepts only canonical geometry bytes plus an exact review record. The
review must be marked owner-reviewed and synthetic, cover every geometry room in order,
repeat each proposal digest exactly, explicitly name each zone, choose its
`open|restricted|no-go` access, choose `outdoor` true or false, and match the current
housefile revision. The canonical target must be an unmistakably synthetic fixture in a
private local directory. A stale revision, changed digest, unsafe path, invalid schema, or
ambiguous file state fails without a successful write.

The focused end-to-end proof is local and synthetic:

```bash
.venv/bin/python -m pytest -q tests/integration/test_geometry_materialization.py
```

This is a materialization primitive, not an automatic pipeline. The vision `confirm`
command still cannot write a housefile. A target without the required explicit synthetic
markers is rejected, but those declarative markers cannot prove supplied content is
fictional; using real dwelling data remains prohibited. The FastAPI server still serves its
in-code synthetic seed rather than loading this canonical file. Digest binding detects
mismatches; it is not tamper evidence. Geometry bytes, review records, receipts, digests,
and resulting runtime housefiles remain private.

## Validation

```bash
make check
```

This compiles the Python sources, runs the tests, and scans the candidate public tree. The
scanner reports only file, line, and rule identifiers; it never echoes matching values.

## Integration paths

| Target | Protocol | Intended enforcement |
|---|---|---|
| Modern robot vacuums | Matter 1.4 RVC + Service Area | Enforced by area selection |
| Robot lawn mowers | Automower Connect | Enforced by work/stay-out areas |
| Existing home robots | Home Assistant or Valetudo MQTT | Gated by Threshold |
| Future agents/humanoids | THS-0.1 scoped-read API | Gated + auditable |

These adapters are stubs today; the command API reports them as unavailable rather than
upgrading their enforcement tier. The simulated trip coordinator can isolate injected
`halt_all()` failures, but no configured adapter or physical device stop is currently
proved.

## Repository map

```text
docs/          architecture, specs, privacy, demo, and Build Week plan
schema/        canonical THS-0.1, private vision-proposal, and geometry JSON Schemas
src/threshold/ policy core, grants, API, adapters, hardware, and capture modules
tests/         unit/API/security tests
scripts/       mock robot and public-release scan
console/       exact-pinned React/Vite/TypeScript loopback owner console
reference/     non-runnable JSX visual reference retained for provenance
```

## Safety and disclosure

The current stop path is a process-local simulation, not evidence for the physical loop
described in [`HARDWARE.md`](HARDWARE.md), and neither is a certified emergency-stop. It
does not prove an NC loop, ESP32, OLED, printer, adapter, device stop, or physical timing.
Keep manufacturer controls and a physical power-isolation path. For vulnerability handling
and public-demo rules, see [`SECURITY.md`](SECURITY.md) and
[`docs/PRIVACY.md`](docs/PRIVACY.md). Real-room video follows the separate
[`footage checklist`](docs/REAL-FOOTAGE-CHECKLIST.md) and stays out of Git.

Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md). The first-publish metadata and
verification sequence is recorded in
[`docs/PUBLICATION-CHECKLIST.md`](docs/PUBLICATION-CHECKLIST.md).

Licensed under the MIT License.

<!-- Curious operators: GET /.well-known/aurora -->
