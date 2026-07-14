# Public GitHub publication checklist

Target repository: `joobeer87/threshold-node`.

The public repository and `main` branch now exist. Wave work is reviewed through a feature
branch and draft pull request before merge. Repeat the safety checks below for every push.

## Before a push

- Working tree and staged diff are understood and clean.
- Test suite, compile check, public-tree scan, and independent secret scan pass.
- Console install uses `npm ci`; `package.json` contains exact dependency versions and the
  committed lockfile matches. Frontend tests, typecheck/build, and accessibility checks
  pass without adding generated `node_modules/`, coverage, or `dist/` output to Git.
- `git ls-files` contains no environment files, credentials, archives, raw/review media,
  runtime data, private grant snapshots, ledgers, receipts, or generated caches.
- The configured grant store and ledger remain outside the candidate public tree. Treat them
  as one private recovery pair; never publish either file, its backup, or a recovery copy.
- Commit metadata uses a public noreply email.
- README, MIT license, security policy, contribution guide, CI, and issue/PR templates are
  present.
- The approved Git/PR authentication path targets the intended account and repository.
- The branch, commit scope, and remote action have been explicitly reviewed.

## Repository metadata

- Visibility: public
- Default branch: `main`
- Description: `Owner-held permission and disclosure boundary for domestic robots and agents.`
- Topics: `codex`, `edge-ai`, `fastapi`, `home-automation`, `privacy`, `robotics`
- Issues: enabled
- Wiki: disabled
- Private vulnerability reporting: enabled

The GPT-5.6 request adapter and provider-free contract tests may be described precisely.
Do not claim live model quality, cost, or end-to-end extraction evidence until a reviewed
synthetic provider run exists. Never publish a real capture request, response, proposal,
decision, batch/proposal digest, or runtime receipt.

THS-0022 may be described as the exact provider-free
`ths/rectangular-strip-grid/0.1` algorithm: explicit order, eight columns, fixed 400×300
rectangles, canonical JSON, and digest binding. THS-0023 may be described as a
synthetic-only reviewed materializer with exact proposal/geometry bindings, explicit
name/access/outdoor choices, strict validation, local revision compare-and-swap, and atomic
replacement. Runtime geometry, reviews, receipts, digests, and resulting housefiles must
stay out of Git.

Do not describe those primitives as inferred or surveyed floor plans, model-assigned
policy, real-dwelling support, owner authentication, automatic materialization, tamper
evidence, distributed/crash-proof authority, or live API state. Proposal confirmation
still writes no geometry or housefile, and the API still serves its in-code synthetic seed.

The grant authority may be described as a local digest-only store with ledger-bound,
fail-closed restart recovery only after the focused recovery tests and full gate pass. Do
not call it tamper-evident, distributed, or crash-proof. State explicitly that raw grant
credentials are never persisted, synthetic seeding is limited to an empty first boot in
explicit demo mode, and corrupt or ambiguous existing state returns unavailable rather than
falling back to seeds.

Quiet-hours evidence may claim command-only gating against an explicit IANA timezone: one
UTC instant is converted to policy-local time, an active window is durably denied, and an
invalid policy or timezone returns unavailable without relay. Do not imply that reads are
quiet-hours blocked, that a command was physically stopped, or that this prototype is a
certified safety control.

The simulated-appliance wave may claim only its tested software behavior: owner-authenticated
routes gated by explicit demo mode and exact `ESP32_SERIAL=SIMULATED`; latch-first handling;
one durable ESTOP transition even with zero active grants; isolated adapter-call attempts;
idempotent duplicate trip; refusal to re-arm after failed persistence; and no grant restore
on successful re-arm. State that the latch is process-local, resets on restart, is not
shared across workers, and should be demonstrated with one worker. Suspended grant state,
not the latch, is the durable restart evidence.

Terminal claims are limited to deterministic simulated `ARMED`, two-second `READ`,
four-second `DENY`, and latched `TRIPPED` frames. Receipt claims are limited to allowlisted,
deterministic synthetic text/PNG generation and an optional private write-once sink. Never
commit a generated PNG or imply that the in-memory API fallback was printed. Every latency
value must remain labeled `simulated_software_path_only` beside
`physical_stop_verified:false`.

The owner-console wave may claim owner-authenticated `GET /owner/status` and
`GET /owner/snapshot`, credential-free public grant projections, the current server
housefile blueprint, bounded ledger display, grant issue/revoke controls, and explicit
loading/error/retry/TRIPPED UI states after the automated gates pass. State that owner and
new-grant tokens are memory-only and header-only, that operator captures must never include
them, and that owner-route origins are limited to no Origin, exact same-origin, or exactly
`http://127.0.0.1:5173`. Check that no wildcard CORS header or policy appears.

Do not describe the console as a deployment, transport-secure remote administration,
credential vault, real-dwelling UI, physical safety control, or proof that a command/device
was relayed or stopped. A credential-free snapshot is still private household/activity
data and must never be committed or published. Automated interaction and accessibility
checks do not substitute for the required human visual review.

Do not claim an NC loop, ESP32/serial bridge, OLED, printer, configured adapter invocation,
device movement/stop, physical stop timing, or certified-safety result. Those remain later
hardware/adapter proof gates. The live synthetic GPT-5.6 evaluation, real-dwelling
materialization review, and final human owner-console visual recheck also remain outstanding.

## After a public push

1. Open the repository in a logged-out browser and inspect README, files, commit author,
   license, and links as a stranger would see them.
2. Confirm GitHub Actions starts on Python 3.10 and 3.12 and fix only evidence-backed
   failures.
3. Enable private vulnerability reporting and verify `SECURITY.md` is discoverable.
4. Confirm no unexpected remote, branch, release, package, Pages site, or deployment was
   created.
5. After the first green CI run, add branch protection without blocking the owner's
   emergency ability to repair the Build Week branch.

The final real-room video remains external. Add its reviewed link only after
`REAL-FOOTAGE-CHECKLIST.md` passes.
