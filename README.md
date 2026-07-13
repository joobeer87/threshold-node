# Threshold Node

**The permission slip robots read before entering your home.**

Threshold Node is a local-first permission appliance for domestic robots and agents. It
keeps a machine-readable *housefile* under the owner's control, returns only the zones and
capabilities granted to a caller, refuses no-go actions, and records access decisions.

> Pre-alpha scaffold: the scoped-view policy core, authenticated grant lifecycle API,
> time-policy enforcement, durable local decision ledger, synthetic mock-agent proof run,
> privacy-first local capture intake, and a guarded GPT-5.6 observation-proposal adapter.
> Grant metadata still resets on restart; live model quality has not been evaluated, and
> boundaries, robot adapters, owner console, and hardware interlock are not implemented.
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
- Server-generated grant IDs, digest-only credential storage, revocation, RFC3339 expiry,
  and start-inclusive/end-exclusive access windows.
- Append-only local JSONL decision records with allowlisted fields, fsync-before-response,
  and bounded owner reads. This is durability, not tamper evidence.
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
- Simulator-first fixtures and a sanitized public-release scanner that rejects capture
  artifacts even if they are force-added to Git.

## Framework

The current core is Python 3.10+ with FastAPI and Pydantic. That is a good fit for a Jetson
or other edge host and keeps the policy layer easy to test. The recommended product stack
is:

- FastAPI for the local policy/API node;
- Vite + React + TypeScript for the offline-capable owner console;
- Arduino/PlatformIO for the ESP32 bridge;
- Matterbridge/matter.js only where the virtual Matter RVC demo needs it;
- OpenAI Responses API with GPT-5.6 structured outputs for vision-to-housefile proposals,
  always behind deterministic validation and explicit owner confirmation.

The adapter and provider-free contract tests are implemented. A live synthetic GPT-5.6
quality/cost evaluation is still required before calling the extraction flow demo-proven.
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

In another shell with the same demo grant token exported:

```bash
.venv/bin/python scripts/mock_robot.py --grant g-neo
```

The script emits three bounded JSON Lines proof records. The middle request returns `503`
because the policy gate allows it but no adapter exists; `relayed` remains `false`. The
final workshop request returns `403`. No robot movement is performed or claimed.

### Owner grant workflow

For API-created grants, generate a third distinct local token and retain it as
`THS_NEW_GRANT_TOKEN`; the server receives it only in a masked header, stores its digest,
and never returns the credential. Issue a synthetic grant with:

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

The node listens on `127.0.0.1:8471` by default and writes its local ledger under ignored
`data/` storage unless `THS_LEDGER_PATH` is set. Issued grant metadata is currently
in-memory and resets on restart. Do not expose the node to a LAN or the internet until the
threat model, persistent grant store, transport security, and hardware behavior have been
reviewed.

Owner and demo grant tokens must be different, 32–512-character visible-ASCII values.
All `*.jsonl` files are excluded from the public tree because a custom ledger path may
still contain private activity data.

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

These adapters are stubs today; the API reports them as unavailable rather than upgrading
their enforcement tier.

## Repository map

```text
docs/          architecture, specs, privacy, demo, and Build Week plan
schema/        canonical THS-0.1 and private vision-proposal JSON Schemas
src/threshold/ policy core, grants, API, adapters, hardware, and capture modules
tests/         unit/API/security tests
scripts/       mock robot and public-release scan
reference/     non-runnable JSX visual reference for the future console
```

## Safety and disclosure

The physical stop loop described in [`HARDWARE.md`](HARDWARE.md) is a prototype interlock,
not a certified emergency-stop. Keep manufacturer controls and a physical power-isolation
path. For vulnerability handling and public-demo rules, see [`SECURITY.md`](SECURITY.md)
and [`docs/PRIVACY.md`](docs/PRIVACY.md). Real-room video follows the separate
[`footage checklist`](docs/REAL-FOOTAGE-CHECKLIST.md) and stays out of Git.

Contributions follow [`CONTRIBUTING.md`](CONTRIBUTING.md). The first-publish metadata and
verification sequence is recorded in
[`docs/PUBLICATION-CHECKLIST.md`](docs/PUBLICATION-CHECKLIST.md).

Licensed under the MIT License.

<!-- Curious operators: GET /.well-known/aurora -->
