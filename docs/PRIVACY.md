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
- Real housefiles, room names, schedules, maps, inventory, quirks, and system details.
- Raw camera/audio frames and model prompts containing household context.
- Normalized frame batches and capture manifests under `data/capture/`; derived media is
  still household data.
- Raw, review, and exported real-room media files; publish the approved video externally.
- Matter fabrics, Home Assistant tokens, device IDs, OAuth material, network captures,
  local paths, receipts, and ledger bodies.
- Every real-capture runtime receipt, including its batch ID and manifest hash; omission of
  paths and room labels does not make a real-household receipt publication-safe.
- Every `*.jsonl` runtime ledger, including one written outside the default `data/` path.

## Model boundary

The current intake flow is local preprocessing only. It accepts one bounded room source,
uses local media tools to normalize selected JPEG frames, writes only to ignored
`data/capture/`, and emits a receipt that omits source paths, filenames, room labels, and
tool output. It makes no model call and cannot change the canonical housefile.
Input must stay outside the repository checkout or under ignored `media/raw/`; the CLI
refuses other in-repository sources before invoking a media tool.

A later model flow may send only the narrowest room batch needed for a structured
proposal. Model output remains untrusted: validate it against THS-0.1, show an
owner-visible diff, and require confirmation before changing the canonical housefile.
Deterministic policy—not a model—decides disclosure and command authorization.

## Receipt boundary

The local decision ledger allowlists only `ts`, `type`, `agent`, `detail`, and optional
`tier`; API code writes fixed detail strings rather than request parameters. Checked-in
delivery receipts must be derived only from synthetic fixtures and may contain bounded
counts, rule IDs, hashes, and pass/fail status. Real capture receipts stay local even though
their output shape is sanitized. Neither checked-in form contains prompts, tokens, raw
payloads, URLs, device identifiers, private notes, or raw ledger bodies.

## Pre-push gate

Run `make check`, inspect `git ls-files`, and review the staged diff. The scanner output is
sanitized by design and must report zero findings before publication. It treats
`data/capture/` as private even when a file there was force-added, so capture artifacts
cannot become acceptable merely by bypassing `.gitignore`.

Real-room video is allowed for the submission, but it does not make real dwelling data an
acceptable code fixture. Follow `docs/REAL-FOOTAGE-CHECKLIST.md` and keep the repo's visible
UI, receipts, actor names, and housefile synthetic.
