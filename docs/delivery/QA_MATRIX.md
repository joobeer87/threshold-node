# QA matrix

| Feature | Proof | Result |
|---|---|---|
| THS-F001 | `tests/unit/test_scoped_view.py` | Pass |
| THS-F002 | `tests/unit/test_api_server.py`, `test_config.py` | Pass |
| THS-F003 | strict model, no-go, wrong-scope, no-adapter tests | Pass |
| THS-F004 | `test_public_release_check.py`, synthetic fixture validation | Pass |
| Packaging | compile/import checks | Pass locally |
| Automated suite | 27 tests | Pass locally |
| Python 3.10 CI | `.github/workflows/ci.yml` | Pending first hosted run |
| Python 3.12 CI | `.github/workflows/ci.yml` | Pending first hosted run |
| Hardware | bench test with exact parts | Not run; do not claim |
| GPT-5.6 integration | structured-output evals | Not implemented |

The delivery gate remains `warn`: the initial repository is safe to continue locally, but
the product and Build Week submission are incomplete.
