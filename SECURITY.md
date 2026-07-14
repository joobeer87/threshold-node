# Security policy

Threshold Node is pre-alpha software. Do not use it to control hazardous machinery, rely
on it as a certified safety function, expose it directly to the internet, or load a real
dwelling file without an independent security review.

## Reporting a vulnerability

When this repository is published, use GitHub's private vulnerability-reporting feature.
Do not put credentials, real house data, device identifiers, exploit payloads, or private
logs in a public issue. If private reporting is unavailable, open a minimal issue asking
the maintainers to enable a private channel; omit the sensitive details.

## Supported versions

No version is security-supported yet. The `0.1.x` line is a Build Week prototype.

## Public-demo boundaries

- Use only `schema/examples/synthetic-demo-house.json` and the in-code synthetic seed.
- Generate owner and grant tokens locally; never commit or print them.
- Treat the owner console as a local authenticated control surface, not a public dashboard.
  Its owner token and one-time new-grant token must remain only in page memory: never put
  either value in browser storage, cookies, URLs, screenshots, recordings, logs, or build
  artifacts. Lock or reload the page to clear its in-memory state.
- Owner routes accept an absent `Origin`, the request's exact same origin, or exactly
  `http://127.0.0.1:5173`. They reject foreign origins and unapproved preflight headers and
  never emit `Access-Control-Allow-Origin: *`. This origin check complements owner
  authentication; it does not replace it or make a LAN/internet deployment safe.
- `GET /owner/snapshot` and `GET /owner/status` expose owner-only projections. Snapshot
  responses may contain the complete current housefile and bounded activity data, so they
  remain sensitive even though their grant records omit credential digests and raw
  credentials. Never publish a response body or browser capture.
- Install console dependencies from the committed exact-pinned lockfile with `npm ci`.
  Review any dependency or lockfile update as a separate supply-chain change; do not use a
  floating install to reproduce this wave.
- Raw grant credentials must remain memory-only. The private store retains only credential
  digests, which are still sensitive and must never be published.
- Keep the default loopback bind. A network bind is an explicit, reviewed opt-in.
- Treat receipts, the ledger and grant-store pair, camera frames, and device integrations as
  sensitive local data. Keep the trust-state directory private and back up or restore both
  files together.
- Synthetic grants may seed only on a genuinely empty first boot with explicit demo mode.
  Missing, corrupt, mismatched, or ambiguous state after history exists returns unavailable;
  never delete one file to force a seed fallback.
- Quiet hours use the canonical policy's explicit IANA timezone and gate commands only.
  An active window is durably denied; an invalid schedule or timezone returns unavailable
  without relay. Reads do not bypass their existing grant/disclosure checks.
- The simulated trip/re-arm routes require owner authentication, explicit demo mode, and
  exact `ESP32_SERIAL=SIMULATED`. A new trip latches the serving process before persistence,
  records ESTOP even with zero active grants, and isolates each injected adapter attempt.
  Duplicate trip calls do not repeat effects. If persistence fails, keep that process
  TRIPPED and refuse re-arm; after success, re-arm must never restore grants.
- Treat the simulated latch as single-worker, process-local state. It resets on restart and
  is not coordinated across processes. Durable suspended grants survive; the latch does not.
- Synthetic receipt PNGs are local sensitive artifacts even when their fields are
  allowlisted. Use only the explicit private write-once sink, and never force-add its output.
- The GPT-5.6 adapter has provider-free contract evidence only. Do not claim live quality,
  latency, token use, or cost until a reviewed synthetic provider evaluation exists.
- The React console's automated contract, interaction, build/type, and accessibility
  checks are software evidence only. Human visual review remains required, and neither the
  console nor its `TRIPPED` presentation proves command relay, physical response, or
  certified safety.
- Use THS-0022/0023 only with unmistakably synthetic inputs and private temporary canonical
  targets. Geometry is a fixed ordered sketch, not inferred or measured floor-plan data;
  it must never assign access, no-go, or outdoor policy.
- Materialization must fail closed on a changed geometry/proposal digest, missing or
  duplicate owner choice, stale revision, unsafe path, invalid schema, lock failure, or
  failed write/sync. Its lock and compare-and-swap protect one local filesystem target;
  they are not distributed coordination, tamper evidence, or crash-proof storage.
- Treat `owner_reviewed:true` and `synthetic_fixture:true` as declarative workflow gates,
  not owner authentication or proof that arbitrary supplied data is fictional. The running
  API does not load materialized output, and real-house or automatic materialization is
  prohibited pending separate review.
- Run `make check` against the exact staged tree before any push.
- Do not represent `simulated_software_path_only` timing as a physical stop measurement.
  No current proof covers an NC loop, ESP32, serial transport, OLED, printer, configured
  adapter, device movement/stop, or certified safety. Do not use the prototype stop loop as
  an emergency-stop or life-safety system.
- Keep raw or review real-room footage out of Git and complete the footage privacy checklist
  before publishing a video link.
