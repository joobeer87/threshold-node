# Privacy and public-release policy

Threshold's useful data is unusually sensitive: floor-plan geometry, access windows,
systems, possessions, robot identifiers, camera frames, and audit events can describe a
real household. The public repository therefore ships only fictional data.

## What may be committed

- Source code, schemas, tests, and documentation.
- Fixtures explicitly labeled `synthetic: true`.
- Sanitized receipts containing counts, rule IDs, hashes, and pass/fail status.
- Screenshots or demo video frames created entirely from synthetic fixtures.

## What stays local

- Populated environment files and bearer tokens.
- Real housefiles, room names, schedules, maps, inventory, quirks, and system details.
- Raw camera/audio frames and model prompts containing household context.
- Matter fabrics, Home Assistant tokens, device IDs, OAuth material, network captures,
  local paths, receipts, and ledger bodies.

## Model boundary

The planned capture flow sends the narrowest room batch needed for a structured proposal.
Model output is untrusted: validate it against THS-0.1, show an owner-visible diff, and
require confirmation before changing the canonical housefile. Deterministic policy—not a
model—decides disclosure and command authorization.

## Receipt boundary

Receipts use an allowlist: event type, synthetic actor label, policy result, coarse zone
label, timestamp, and a one-way content fingerprint. They do not print prompts, tokens,
raw payloads, URLs, device identifiers, or private notes.

## Pre-push gate

Run `make check`, inspect `git ls-files`, and review the staged diff. The scanner output is
sanitized by design and must report zero findings before publication.
