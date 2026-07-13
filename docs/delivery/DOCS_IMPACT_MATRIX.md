# Documentation impact matrix

| Surface | Impact | State |
|---|---|---|
| README | fixed digest-bound geometry, explicit reviewed synthetic materialization, standalone/live-API boundary, privacy and real-use nonclaims | Updated through Wave 6 |
| AGENTS.md | public-repo, synthetic-only, validation, and operator boundaries | Reviewed; no change |
| CODING-GUIDE | canonical public schema and byte-identical installed package-data projection | Updated for Wave 6 |
| SECURITY.md | fail-closed geometry/materialization digest, schema, synthetic, lock/CAS boundaries; no authentication/tamper/real-use claims | Updated for Wave 6 |
| HARDWARE.md | simulated interlock/display/receipt boundaries versus untested NC loop, ESP32, OLED, printer, and physical timing | Updated for Wave 5 |
| SPEC-NODE + SPEC-THS | THS-0022 fixed geometry schema/algorithm and THS-0023 exact declarative review, strict synthetic materialization, local atomicity/failure doctrine | Updated for THS-0022/0023 |
| ARCHITECTURE | caller-supplied proposal digest → explicit order → geometry binding → explicit review → synthetic revision CAS; server remains seed-backed | Updated for Wave 6 |
| PRIVACY | geometry/review/receipt/housefile artifacts stay local; hashes can fingerprint layouts; explicit choices prevent model policy assignment | Updated for Wave 6 |
| AURORA-EASTER-EGG | honest public Aurora framework signature | Replaced leak concept |
| REAL-FOOTAGE-CHECKLIST | staged-room, metadata, visual/audio review | Added |
| Media boundary | raw/review/export footage excluded from Git | Added |
| CONTRIBUTING + GitHub templates | public contribution and issue/PR hygiene | Added |
| KANBAN | THS-0022/0023 complete; THS-0012 hardened; THS-0050 owner-auth and THS-0060 conditional-hardware dependencies corrected | Updated for Wave 6 |
| BUILD-WEEK | provider-free fixed geometry and synthetic materialization proof separated from live model, real dwelling, console, and hardware work | Updated for Wave 6 |
| DEMO-SCRIPT | runnable synthetic geometry/materialization proof and explicit no-survey/no-live-API/no-real-house language | Updated for Wave 6 |
| Config example | exact `ESP32_SERIAL=SIMULATED` plus demo-mode requirement for simulated control routes | Updated for Wave 5 |
| PUBLICATION-CHECKLIST | exact allowed fixed-grid/local-CAS claims and prohibited inferred/real/automatic/tamper/live-server claims | Updated for Wave 6 |
| Delivery records | F019/F020 feature and QA mapping; Wave 6 remains synthetic-only and standalone | Updated for Wave 6 |

PR #3 is merged at `a109b4d`; draft PR #4 contains Wave 4 and stacked draft PR #5 contains
Wave 5. Wave 6 is prepared on `agent/wave6-geometry-materialization` for a separate stacked
draft PR. These records reflect only the local gate; they do not claim draft-PR checks,
review, merge, deployment, provider evaluation, real-dwelling materialization, physical
hardware operation, physical stop/latency, or submission readiness.
