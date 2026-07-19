# Documentation impact matrix

| Surface | Impact | State |
|---|---|---|
| README | loopback owner-console quickstart, snapshot/status surface, first-observer expiry persistence, exact origin policy, memory-only token boundary, UI capabilities and nonclaims | Updated through selected PR #7 review fix |
| AGENTS.md | public-repo, synthetic-only, validation, and operator boundaries | Reviewed; no change |
| CODING-GUIDE | canonical public schema and byte-identical installed package-data projection | Updated for Wave 6 |
| SECURITY.md | owner snapshot sensitivity, exact-origin/no-wildcard policy, memory-only tokens, exact-lockfile install, visual/safety nonclaims | Updated for Wave 7 |
| HARDWARE.md | simulated interlock/display/receipt boundaries versus untested NC loop, ESP32, OLED, printer, and physical timing | Updated for Wave 5 |
| SPEC-NODE + SPEC-THS | existing first-observer exact expiry/window-end contract already governs owner requests; THS schema is unchanged | Reviewed; no change needed for PR #7 fix |
| ARCHITECTURE | Vite loopback proxy → exact-origin owner API → expiry-persisting credential-free projections; token and completed visual-review boundaries | Updated for selected PR #7 review fix |
| PRIVACY | snapshots remain private; stale-active projection fails closed; token/browser-storage/screenshot restrictions; local-origin limitations and threat nonclaims | Updated for selected PR #7 review fix |
| AURORA-EASTER-EGG | honest public Aurora framework signature | Replaced leak concept |
| REAL-FOOTAGE-CHECKLIST | staged-room, metadata, visual/audio review | Added |
| Media boundary | raw/review/export footage excluded from Git | Added |
| CONTRIBUTING + GitHub templates | public contribution and issue/PR hygiene | Added |
| KANBAN | THS-0050 complete with owner-first expiry proof and accepted visual recheck; THS-0024 records the separate Vault-gated live-eval wave | Updated for selected PR #7 review fix |
| Console design contract | Reference-derived tokens, perceptible loading dwell, distinct semantic colors, contained blueprint labels, responsive layout, interaction, accessibility, credential, and visual-review boundaries | Updated for Wave 7 closeout |
| BUILD-WEEK | implemented owner API/console proof with accepted visual review, separated from deployment, real dwelling, provider, and hardware claims | Updated for Wave 7 closeout |
| DEMO-SCRIPT | loopback console run path, safe token handling, shown states, accepted human visual recheck, and footage boundaries | Updated for Wave 7 closeout |
| Config example | exact `ESP32_SERIAL=SIMULATED` plus demo-mode requirement for simulated control routes | Updated for Wave 5 |
| PUBLICATION-CHECKLIST | exact owner-console claims, pinned dependency/public-tree gates, private snapshot boundaries, and completed visual-review evidence | Updated for Wave 7 closeout |
| Delivery records | F007/F011/F014 feature/QA mapping; implemented loopback-console gate is locally PASS after owner visual acceptance and selected expiry review fix | Updated for selected PR #7 review fix |

Wave 7 remains on `agent/wave7-owner-console` as a separately reviewable change. These
records reflect the local automated gate, the owner's accepted corrected visual review, and
the locally addressed first-observer expiry thread. They do not claim a pushed correction,
thread resolution, PR merge, deployment, provider evaluation, real-dwelling materialization,
physical hardware operation, physical stop/latency, or submission readiness.
