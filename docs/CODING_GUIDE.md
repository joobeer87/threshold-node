# CODING GUIDE (delta from structured-coding-framework)
- Python 3.10+. Dataclasses + Enums in core/types.py are the lingua franca — no raw category strings.
- scoped_view stays PURE: no I/O, no clock, no globals. Ledger writes happen at the API boundary.
- Confidence rules: >80% requires passing tests; >90% requires edge cases tested.
- Hardware ships SIMULATED drivers first; real GPIO is a driver swap, not a refactor.
- Adapter tier comes from capabilities(); hand-asserted tiers fail T-ENF-01.
- `schema/ths-0.1.schema.json` is canonical; keep its packaged
  `src/threshold/housefile/ths-0.1.schema.json` projection byte-identical so installed
  materialization can validate without a repository checkout.
- Every kanban task touched gets Status+Conf+Notes updated same session. Receipts over claims.
