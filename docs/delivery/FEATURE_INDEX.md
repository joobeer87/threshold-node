# Feature index

| ID | Feature | Current state | Public claim |
|---|---|---|---|
| THS-F001 | Scoped housefile disclosure | Implemented and unit-tested | Runnable |
| THS-F002 | Owner/per-grant auth separation | Issue/revoke/read routes covered by ASGI tests | Pre-alpha |
| THS-F003 | Command policy gate | Distinguishes allowed/not-relayed from denied | Runnable |
| THS-F004 | Public-release hygiene | Synthetic fixtures, ignore rules, scan | Runnable |
| THS-F005 | Persistent append-only ledger | JSONL append+fsync, bounded reads, allowlisted fields | Runnable local durability |
| THS-F006 | GPT-5.6 observation proposal | Responses adapter, strict local validator, private artifact, digest-bound owner decision; live eval pending | Implemented locally; not demo-proven |
| THS-F007 | Owner console | JSX visual reference only | Planned |
| THS-F008 | Prototype physical stop loop | Hardware plan only | Planned |
| THS-F009 | Aurora public signature | Hidden static route + safety test | Runnable |
| THS-F010 | Real-footage privacy workflow | Checklist + Git/scanner boundary | Runnable |
| THS-F011 | Grant lifecycle and time policy | Issue/revoke, digest-only auth, expiry and one-time windows | Runnable pre-alpha |
| THS-F012 | Synthetic mock-agent permission loop | Scoped read → allowed/not-relayed → no-go denial | Runnable |
| THS-F013 | Privacy-first local capture intake | JPEG/PNG or MOV/MP4/M4V → bounded private JPEG batch; local proofs pass | Runnable locally; not a model integration |

Current THS-0021 impact: THS-F006 and THS-F010. The private proposal remains deliberately
separate from canonical THS-0.1 policy: THS-0022 geometry and a future reviewed
materialization step are still required.
