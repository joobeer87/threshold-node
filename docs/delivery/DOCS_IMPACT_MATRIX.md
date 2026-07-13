# Documentation impact matrix

| Surface | Impact | State |
|---|---|---|
| README | authoritative restart persistence, paired private state, IANA quiet-hours claims, live-eval warning | Updated for THS-0017/THS-0072 |
| AGENTS.md | public-repo, synthetic-only, validation, and operator boundaries | Reviewed; no change |
| SECURITY.md | private grant metadata, paired recovery, quiet-hours and live-eval boundaries | Updated for Wave 4 |
| HARDWARE.md | prototype warning and later-wave hardware boundary | Reviewed; no change |
| SPEC-NODE + SPEC-THS | grant transaction/recovery authority, persistent states, IANA command-only quiet hours | Updated for THS-0017/THS-0072 |
| ARCHITECTURE | store/ledger commit point, target witness, cross-instance lock and authorization lease | Updated for Wave 4 |
| PRIVACY | digest sensitivity, store/ledger pair, recovery and timezone privacy | Updated for Wave 4 |
| AURORA-EASTER-EGG | honest public Aurora framework signature | Replaced leak concept |
| REAL-FOOTAGE-CHECKLIST | staged-room, metadata, visual/audio review | Added |
| Media boundary | raw/review/export footage excluded from Git | Added |
| CONTRIBUTING + GitHub templates | public contribution and issue/PR hygiene | Added |
| KANBAN | THS-0017 and THS-0023 added; THS-0021/0072 states and downstream dependencies corrected | Updated for Wave 4 |
| BUILD-WEEK | durable grant/quiet-hours evidence separated from later waves and live model proof | Updated for Wave 4 |
| DEMO-SCRIPT | restart seeding and wall-clock quiet-hours behavior documented | Updated for Wave 4 |
| Config example | paired private paths, first-boot seeding, canonical timezone location | Updated for Wave 4 |
| PUBLICATION-CHECKLIST | private authority files, bounded claims, live-eval gate | Updated for Wave 4 |
| Delivery records | F014/F015 feature, QA, docs-impact, and scoped receipt | Updated for Wave 4 |

PR #3 is merged at `a109b4d`. Wave 4 is prepared on
`agent/wave4-trust-foundation` for its separately authorized draft PR. This receipt does not
claim draft-PR checks, review, merge, deployment, provider mutation, hardware operation, or
submission readiness.
