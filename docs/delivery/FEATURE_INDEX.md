# Feature index

| ID | Feature | Current state | Public claim |
|---|---|---|---|
| THS-F001 | Scoped housefile disclosure | Implemented and unit-tested | Runnable |
| THS-F002 | Owner/per-grant auth separation | Issue/revoke/read routes covered by ASGI tests | Pre-alpha |
| THS-F003 | Command policy gate | Distinguishes allowed/not-relayed from denied | Runnable |
| THS-F004 | Public-release hygiene | Synthetic fixtures, ignore rules, and fail-closed scans for tracked runtime data, ledgers, capture inputs, and receipts | Runnable |
| THS-F005 | Persistent append-only ledger | JSONL append+fsync, bounded reads, allowlisted fields, prepared checkpoints, exact receipt witnesses, and durable ESTOP events | Runnable local durability |
| THS-F006 | GPT-5.6 observation proposal | Merged provider-free adapter, strict validator, private artifact, digest-bound owner decision; live eval pending | Runnable provider-free; not demo-proven |
| THS-F007 | Owner console | Owner-auth snapshot/status API; credential-free housefile/grant/interlock/bounded-ledger projections; exact-origin React/Vite/TypeScript blueprint, issue/revoke, perceptible loading/error/retry, contained labels, and TRIPPED UI; exact-pinned lockfile | Runnable loopback pre-alpha; visual fixes implemented, final human recheck pending |
| THS-F008 | Prototype physical stop loop | Hardware plan only | Planned |
| THS-F009 | Aurora public signature | Hidden static route + safety test | Runnable |
| THS-F010 | Real-footage privacy workflow | Checklist + Git/scanner boundary | Runnable |
| THS-F011 | Grant lifecycle and time policy | Issue/revoke, digest-only auth, durable expiry/suspension, one-time windows, restart persistence, and no grant restoration on simulated re-arm | Runnable pre-alpha |
| THS-F012 | Synthetic mock-agent permission loop | Scoped read → allowed/not-relayed → no-go denial | Runnable |
| THS-F013 | Privacy-first local capture intake | JPEG/PNG or MOV/MP4/M4V → bounded private JPEG batch; local proofs pass | Runnable locally; not a model integration |
| THS-F014 | Authoritative persistent grant state | Revisioned digest-only store, cross-instance transaction lock, pending recovery, ledger/target witness, fail-closed corruption handling, and durable all-grant suspension | Runnable local authority |
| THS-F015 | IANA quiet-hours command gate | One locked UTC capture, `ZoneInfo` conversion, durable command-only denial, invalid-policy `503` | Runnable pre-alpha |
| THS-F016 | Simulated latched interlock | Owner-authenticated demo-only trip/re-arm, latch-first denial, durable ESTOP/suspension, idempotence, and isolated adapter attempts | Runnable simulated software path only; no physical stop proof |
| THS-F017 | Deterministic simulated terminal display | Pure ARMED count, two-second READ, four-second DENY, and latched TRIPPED state rendering | Runnable terminal simulation only; no OLED/device proof |
| THS-F018 | Synthetic receipt/PNG fallback | Allowlisted GRANT/DENY/ESTOP text, deterministic fixed-bitmap PNG, and optional private write-once sink | Runnable synthetic-only primitive; no printer/device proof |
| THS-F019 | Deterministic digest-bound rectangular geometry | Explicit ordered proposal bindings → canonical fixed 8-column 400×300 strip/grid + digest; no persistence or policy fields | Runnable provider-free synthetic sketch only; no model/spatial/survey/policy inference |
| THS-F020 | Owner-reviewed synthetic housefile materialization | Exact geometry/proposal bindings, explicit reviewed name/access/outdoor choices, strict THS validation, local revision CAS, and rollback-capable atomic replace | Runnable synthetic temporary-fixture primitive; no authentication, live API, real, or automatic materialization |

Wave 6 adds THS-F019 and THS-F020 as standalone caller-supplied digest boundaries. Geometry
does not load or authenticate THS-F006 proposal/decision artifacts, make a model call, or
infer a floor plan. Materialization consumes a separate exact declarative review and writes
only a local fixture carrying the required synthetic markers; it is not invoked by proposal
confirmation or the running API. Those markers do not prove arbitrary content is fictional,
and digests are change bindings, not tamper evidence.

Wave 7 implements THS-F007 without changing those materialization boundaries. The console
reads the server's current housefile through owner-authenticated projections; it does not
load THS-0023 output. Owner/new-grant tokens stay in page memory and headers only, owner
routes accept no Origin, exact same-origin, or exactly `http://127.0.0.1:5173`, and no
wildcard CORS is emitted. Automated backend/frontend contract, interaction, build/type, and
accessibility proof is present. Delivery remains `warn` pending final human recheck of the
changes-requested visual fixes. A live
synthetic GPT-5.6 quality/cost/latency evaluation and real-dwelling workflow are still not
run.
