# Feature index

| ID | Feature | Current state | Public claim |
|---|---|---|---|
| THS-F001 | Scoped housefile disclosure | Implemented and unit-tested | Runnable |
| THS-F002 | Owner/per-grant auth separation | Issue/revoke/read routes covered by ASGI tests | Pre-alpha |
| THS-F003 | Command policy gate | Distinguishes allowed/not-relayed from denied | Runnable |
| THS-F004 | Public-release hygiene | Synthetic fixtures, ignore rules, and fail-closed scans for tracked runtime data, ledgers, capture inputs, and receipts | Runnable |
| THS-F005 | Persistent append-only ledger | JSONL append+fsync, bounded reads, allowlisted fields, prepared checkpoints, exact receipt witnesses, and durable ESTOP events | Runnable local durability |
| THS-F006 | GPT-5.6 observation proposal | Merged provider-free adapter, strict validator, private artifact, digest-bound owner decision; live eval pending | Runnable provider-free; not demo-proven |
| THS-F007 | Owner console | JSX visual reference only | Planned |
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

Wave 5 adds THS-F016 through THS-F018 and also impacts THS-F004, THS-F005, THS-F011,
and THS-F014. THS-0051 is integration proof across existing features, not a separate
feature. Its timing evidence is limited to the simulated software path; it does not prove a
physical stop, physical latency, device halt, or hardware certification. PR #3 merged the
provider-free THS-0021 path, but a live synthetic GPT-5.6 quality/cost/latency evaluation is
still not run. THS-0022 geometry and THS-0023 owner-reviewed materialization are also still
required.
