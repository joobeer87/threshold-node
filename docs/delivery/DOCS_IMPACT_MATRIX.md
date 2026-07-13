# Documentation impact matrix

| Surface | Impact | State |
|---|---|---|
| README | pre-alpha status, private proposal/decision workflow, external-processing warning, claims | Updated for THS-0021 |
| AGENTS.md | durable public-repo and validation rules | Added |
| SECURITY.md | disclosure and demo boundaries | Added |
| HARDWARE.md | GPIO correction and prototype warning | Updated |
| SPEC-NODE + SPEC-THS | private proposal schema, authority exclusions, digest-bound owner decision | Updated for THS-0021 |
| ARCHITECTURE | external model boundary, strict validator, private decision, no canonical write | Updated for THS-0021 |
| PRIVACY | upload consent, provider request, proposal/decision storage, receipt boundaries | Updated for THS-0021 |
| AURORA-EASTER-EGG | honest public Aurora framework signature | Replaced leak concept |
| REAL-FOOTAGE-CHECKLIST | staged-room, metadata, visual/audio review | Added |
| Media boundary | raw/review/export footage excluded from Git | Added |
| CONTRIBUTING + GitHub templates | public contribution and issue/PR hygiene | Added |
| KANBAN | THS-0021 implementation and live-eval boundary | Updated for THS-0021 |
| BUILD-WEEK | provider-free proposal evidence separated from live model/demo proof | Updated for THS-0021 |
| DEMO-SCRIPT | exact no-motion mock proof separated from target hardware video | Updated |
| PUBLICATION-CHECKLIST | exact GPT-5.6 adapter claim versus blocked live-eval claim | Updated for THS-0021 |
| Delivery records | THS-0021 feature, QA, docs-impact, and scoped delivery receipt | Updated for THS-0021 |

PR #2 is merged. THS-0021 changes remain local on `agent/ths-0021-vision-proposals` while
the final local gate and review are in progress. Current-branch push, pull request, merge,
deployment, and submission remain separate delivery states.
