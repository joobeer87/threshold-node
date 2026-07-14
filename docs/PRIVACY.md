# Privacy and public-release policy

Threshold's useful data is unusually sensitive: floor-plan geometry, access windows,
systems, possessions, robot identifiers, camera frames, and audit events can describe a
real household. The public repository therefore ships only fictional data.

## What may be committed

- Source code, schemas, tests, and documentation.
- Fixtures explicitly labeled `synthetic: true`.
- Delivery or test receipts produced only from synthetic fixtures, containing bounded
  counts, rule IDs, hashes, and pass/fail status.
- Screenshots or demo video frames created entirely from synthetic fixtures.
- A link to a final real-room video only after the footage checklist is complete.

## What stays local

- Populated environment files and bearer tokens.
- Owner-console snapshots, screenshots, recordings, browser diagnostics, and network
  captures. A credential-free response still contains a complete owner view of the current
  housefile and bounded activity history.
- The private digest-only grant metadata store. Credential digests are still sensitive
  authentication material even though raw grant credentials are never persisted.
- Real housefiles, room names, schedules, maps, inventory, quirks, and system details.
- Raw camera/audio frames and model prompts containing household context.
- Normalized frame batches and capture manifests under `data/capture/`; derived media is
  still household data.
- Vision proposals, owner decisions, model response identifiers, batch/proposal hashes,
  and every real-run provider receipt stored beside a private capture batch.
- Geometry bytes and digests, materialization review records and receipts, and generated
  runtime housefiles. A digest can still fingerprint a private layout even when names are
  absent.
- Raw, review, and exported real-room media files; publish the approved video externally.
- Matter fabrics, Home Assistant tokens, device IDs, OAuth material, network captures,
  local paths, receipts, and ledger bodies.
- Every runtime synthetic receipt PNG, including output from the optional private write-once
  sink. An allowlisted template does not make a local activity artifact publication-safe.
- Every real-capture runtime receipt, including its batch ID and manifest hash; omission of
  paths and room labels does not make a real-household receipt publication-safe.
- Every `*.jsonl` runtime ledger, including one written outside the default `data/` path.

## Local trust-state boundary

The grant metadata snapshot and decision ledger are one private recovery boundary. The
snapshot stores bounded grant metadata and credential digests, never raw credentials; the
ledger stores the durable receipts that commit grant revisions. Keep both files under
ignored owner-controlled storage with private directory/file permissions, and back up,
move, or restore them together. Neither file is publication-safe or tamper-evident.

On a genuinely empty first boot, Threshold creates no grants unless explicit synthetic demo
mode is enabled with a separate demo grant credential. Once either trust-state file has
history, missing, corrupt, mismatched, or ambiguous recovery state fails closed. The node
must return an unavailable response rather than silently rebuilding grants from synthetic
seeds. Pending grant issue is not usable until its durable ledger receipt exists; pending
revoke, expiry, and suspension transitions remain restrictive during recovery.

Quiet-hours schedules and their IANA timezone can disclose occupancy patterns and location
context, so they remain part of the private canonical housefile. The command gate captures
one UTC instant, converts it to that policy timezone, and denies commands during the local
window. A malformed schedule or unresolvable timezone fails the command closed; scoped
reads remain governed by the ordinary grant and disclosure policy.

## Owner-console boundary

The console is a loopback owner surface, not a public status page. Its
`GET /owner/snapshot` response intentionally includes the full current server housefile,
public grant projections, bounded newest-first ledger events, and health/interlock/display
state. `GET /owner/status` returns only bounded state and the active-grant count. Neither
schema can contain raw credentials or credential digests, but names, geometry, policies,
grant scopes, schedules, and activity events remain private household context.

The owner token and the distinct new-grant token live only in React component state. They
are sent only in request headers, never in URLs, response bodies, browser storage, cookies,
or build artifacts. The issue field is cleared after the request is formed, and Lock or a
page reload clears the owner token. Operators must also keep tokens out of screenshots,
recordings, developer-tool exports, crash reports, and copied browser diagnostics; an
in-memory UI cannot prevent deliberate inspection by a user or same-user process.

Owner API requests accept an absent Origin, the request's exact same origin, or exactly
`http://127.0.0.1:5173`. Foreign origins and excess preflight headers fail closed, and the
server never emits wildcard CORS. This limits accidental browser exposure but is not
transport encryption, process isolation, authorization for LAN use, or a defense against a
compromised local browser, extension, or host. Keep both node and console on loopback.

## Model boundary

The current intake flow is local preprocessing only. It accepts one bounded room source,
uses local media tools to normalize selected JPEG frames, writes only to ignored
`data/capture/`, and emits a receipt that omits source paths, filenames, room labels, and
tool output. It makes no model call and cannot change the canonical housefile.
Input must stay outside the repository checkout or under ignored `media/raw/`; the CLI
refuses other in-repository sources before invoking a media tool.

The GPT-5.6 proposal command is a separate external-processing boundary. It is disabled
without `--allow-external-processing`, reads `OPENAI_API_KEY` only from the process
environment, and sends at most eight verified normalized frames using Base64 data URLs.
The fixed Responses API request uses `store:false`, no tools, no user URL, and no room
label, path, manifest, credential, or source filename. Pixels, visible text, and QR codes
are untrusted data and never instructions.

Strict structured output is necessary but not sufficient. Threshold parses a bounded
response, handles refusals and incomplete responses, rejects duplicate keys and unknown
fields, then applies deterministic count, string, flag, evidence-reference, and uniqueness
checks. The result is an incomplete private observation proposal—not THS-0.1 policy. It
cannot assign access, boundaries, policies, grants, commands, or enforcement.

Owner confirmation is a second invocation that prompts for the configured owner token and
requires the exact proposal digest. It rechecks the proposal, manifest, and frame hashes,
then writes one confirm/reject artifact under a write-once filename. It does not call a
provider or the housefile store. Hash binding detects changes but is not tamper evidence
against an attacker who controls the local filesystem. Deterministic policy—not a
model—decides disclosure and command authorization.

THS-0021's provider adapter and provider-free validation are implemented, but no reviewed
live synthetic GPT-5.6 run yet proves response quality, latency, token use, or cost.
THS-0022 geometry is implemented as a fixed deterministic strip/grid bound to explicit room
order and proposal digests; it cannot infer dimensions, access, no-go, or outdoor policy.
THS-0023 is a separate synthetic-only materializer that binds exact proposal and geometry
digests, requires explicit owner-reviewed names/access/outdoor choices and the expected
housefile revision, validates the schema, and performs a local locked compare-and-swap.

These runtime artifacts all remain private. The `owner_reviewed:true` and
`synthetic_fixture:true` markers are workflow gates, not authentication or proof that
arbitrary input is fictional. The current materializer refuses nonsynthetic targets and
is not called by proposal confirmation or the API. It must never apply a real dwelling
proposal automatically. Digest binding detects mismatch but is not tamper evidence.

## Receipt boundary

The local decision ledger allowlists only `ts`, `type`, `agent`, `detail`, optional `tier`,
and a validated transaction/revision pair for grant commits; API code writes fixed detail
strings rather than request parameters. Checked-in delivery receipts must be derived only
from synthetic fixtures and may contain bounded counts, rule IDs, hashes, and pass/fail
status. Real capture and proposal receipts stay local even though their output shape is
sanitized. Neither checked-in form contains prompts, tokens, raw payloads, URLs, device
identifiers, private notes, or raw ledger bodies.

The simulated-appliance receipt primitive is narrower still: only GRANT, DENY, and ESTOP
templates are accepted through its factory, and its function signature has no credential,
digest, arbitrary detail, or raw-payload field. Direct construction is rejected, and the
renderer rechecks the factory-created receipt's integrity before emitting bytes. Exact
validated inputs produce deterministic 384×256 grayscale PNG bytes. The API renders the
ESTOP fallback in memory and discards it. An
explicit optional sink creates only a private `0700` directory and new, single-link `0600`
write-once PNG; existing files, symlinks, hardlinks, and non-private directories fail
closed. Those controls reduce accidental disclosure but do not make a runtime PNG suitable
for Git.

Simulated trip responses expose only bounded outcome counters and explicit nonclaims. They
do not return adapter exceptions, ledger bodies, grant metadata, credentials, or receipt
bytes. The process-local latch denies use after a persistence failure without reflecting
the private error. `simulated_software_path_only` latency is not household, device, or
physical-safety evidence.

## Pre-push gate

Run `make check`, inspect `git ls-files`, and review the staged diff. The scanner output is
sanitized by design and must report zero findings before publication. It treats
all tracked runtime paths under `data/`, including capture and receipt artifacts, and the
legacy root `receipts/` path as private even when a file there was force-added. Such
artifacts cannot become acceptable merely by bypassing `.gitignore`.

Real-room video is allowed for the submission, but it does not make real dwelling data an
acceptable code fixture. Follow `docs/REAL-FOOTAGE-CHECKLIST.md` and keep the repo's visible
UI, receipts, actor names, and housefile synthetic.
