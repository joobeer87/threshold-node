# Feature index

| ID | Feature | Current state | Public claim |
|---|---|---|---|
| THS-F001 | Scoped housefile disclosure | Implemented and unit-tested | Runnable |
| THS-F002 | Owner/per-grant auth separation | Issue/revoke/read routes covered by ASGI tests | Pre-alpha |
| THS-F003 | Command policy gate | Distinguishes allowed/not-relayed from denied | Runnable |
| THS-F004 | Public-release hygiene | Synthetic fixtures, ignore rules, scan | Runnable |
| THS-F005 | Persistent append-only ledger | JSONL append+fsync, bounded reads, allowlisted fields, prepared checkpoints, exact receipt witnesses | Runnable local durability |
| THS-F006 | GPT-5.6 observation proposal | Merged provider-free adapter, strict validator, private artifact, digest-bound owner decision; live eval pending | Runnable provider-free; not demo-proven |
| THS-F007 | Owner console | JSX visual reference only | Planned |
| THS-F008 | Prototype physical stop loop | Hardware plan only | Planned |
| THS-F009 | Aurora public signature | Hidden static route + safety test | Runnable |
| THS-F010 | Real-footage privacy workflow | Checklist + Git/scanner boundary | Runnable |
| THS-F011 | Grant lifecycle and time policy | Issue/revoke, digest-only auth, durable expiry, one-time windows, restart persistence | Runnable pre-alpha |
| THS-F012 | Synthetic mock-agent permission loop | Scoped read → allowed/not-relayed → no-go denial | Runnable |
| THS-F013 | Privacy-first local capture intake | JPEG/PNG or MOV/MP4/M4V → bounded private JPEG batch; local proofs pass | Runnable locally; not a model integration |
| THS-F014 | Authoritative persistent grant state | Revisioned digest-only store, cross-instance transaction lock, pending recovery, ledger/target witness, fail-closed corruption handling | Runnable local authority |
| THS-F015 | IANA quiet-hours command gate | One locked UTC capture, `ZoneInfo` conversion, durable command-only denial, invalid-policy `503` | Runnable pre-alpha |

Wave 4 impacts THS-F005, THS-F011, THS-F014, and THS-F015. PR #3 merged the provider-free
THS-0021 path; a live synthetic GPT-5.6 quality/cost/latency evaluation is still not run.
The private proposal remains separate from canonical THS-0.1 policy: THS-0022 geometry and
THS-0023 owner-reviewed materialization are still required.
