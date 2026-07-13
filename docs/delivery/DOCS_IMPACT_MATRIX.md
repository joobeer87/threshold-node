# Documentation impact matrix

| Surface | Impact | State |
|---|---|---|
| README | simulated trip/re-arm surface, durable suspension, display/receipt evidence, software-only nonclaims, remaining blockers | Updated through Wave 5 |
| AGENTS.md | public-repo, synthetic-only, validation, and operator boundaries | Reviewed; no change |
| SECURITY.md | demo-only owner-auth controls, latch-first denial, process-local limits, private receipt boundary, physical nonclaims | Updated for Wave 5 |
| HARDWARE.md | simulated interlock/display/receipt boundaries versus untested NC loop, ESP32, OLED, printer, and physical timing | Updated for Wave 5 |
| SPEC-NODE + SPEC-THS | owner-authenticated simulated controls, durable ESTOP/suspension, re-arm semantics, deterministic display and receipt contracts | Updated for THS-0041/0042/0043/0051 |
| ARCHITECTURE | simulated latch ordering, durable authority boundary, isolated adapter attempts, process-local state, in-memory PNG exercise | Updated for Wave 5 |
| PRIVACY | allowlisted synthetic receipt fields, no credential/digest rendering, explicit private write-only sink, no public runtime artifacts | Updated for Wave 5 |
| AURORA-EASTER-EGG | honest public Aurora framework signature | Replaced leak concept |
| REAL-FOOTAGE-CHECKLIST | staged-room, metadata, visual/audio review | Added |
| Media boundary | raw/review/export footage excluded from Git | Added |
| CONTRIBUTING + GitHub templates | public contribution and issue/PR hygiene | Added |
| KANBAN | THS-0041/0042/0043 capabilities and THS-0051 integration proof marked done with simulated-only evidence; hardware/demo blockers retained | Updated for Wave 5 |
| BUILD-WEEK | synthetic appliance proof separated from physical hardware, provider evaluation, geometry/materialization, and console work | Updated for Wave 5 |
| DEMO-SCRIPT | owner-authenticated simulated trip/re-arm flow, TRIPPED state, suspended non-restoration, and software-only timing language | Updated for Wave 5 |
| Config example | exact `ESP32_SERIAL=SIMULATED` plus demo-mode requirement for simulated control routes | Updated for Wave 5 |
| PUBLICATION-CHECKLIST | runtime receipt scan boundary and explicit no-device/no-physical-timing/no-certification claims | Updated for Wave 5 |
| Delivery records | F016/F017/F018 feature and QA mapping; THS-0051 recorded only as integration proof | Updated for Wave 5 |

PR #3 is merged at `a109b4d`, and Wave 4 is available on its separately authorized draft PR.
Wave 5 is prepared locally on `agent/wave5-sim-appliance` for a separate stacked draft PR.
These records reflect only the local gate; they do not claim draft-PR checks, review, merge,
deployment, provider evaluation, physical hardware operation, physical stop/latency, or
submission readiness.
