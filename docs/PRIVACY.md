# Privacy and public-release policy

Threshold's useful data is unusually sensitive: floor-plan geometry, access windows,
systems, possessions, robot identifiers, camera frames, and audit events can describe a
real household. The public repository therefore ships only fictional data.

## What may be committed

- Source code, schemas, tests, and documentation.
- Fixtures explicitly labeled `synthetic: true`.
- Sanitized receipts containing counts, rule IDs, hashes, and pass/fail status.
- Screenshots or demo video frames created entirely from synthetic fixtures.
- A link to a final real-room video only after the footage checklist is complete.

## What stays local

- Populated environment files and bearer tokens.
- Real housefiles, room names, schedules, maps, inventory, quirks, and system details.
- Raw camera/audio frames and model prompts containing household context.
- Raw, review, and exported real-room media files; publish the approved video externally.
- Matter fabrics, Home Assistant tokens, device IDs, OAuth material, network captures,
  local paths, receipts, and ledger bodies.
- Every `*.jsonl` runtime ledger, including one written outside the default `data/` path.

## Model boundary

The planned capture flow sends the narrowest room batch needed for a structured proposal.
Model output is untrusted: validate it against THS-0.1, show an owner-visible diff, and
require confirmation before changing the canonical housefile. Deterministic policy—not a
model—decides disclosure and command authorization.

## Receipt boundary

The local decision ledger allowlists only `ts`, `type`, `agent`, `detail`, and optional
`tier`; API code writes fixed detail strings rather than request parameters. Checked-in
delivery receipts may contain counts, rule IDs, hashes, and pass/fail status. Neither form
contains prompts, tokens, raw payloads, URLs, device identifiers, private notes, or raw
ledger bodies.

## Pre-push gate

Run `make check`, inspect `git ls-files`, and review the staged diff. The scanner output is
sanitized by design and must report zero findings before publication.

Real-room video is allowed for the submission, but it does not make real dwelling data an
acceptable code fixture. Follow `docs/REAL-FOOTAGE-CHECKLIST.md` and keep the repo's visible
UI, receipts, actor names, and housefile synthetic.
