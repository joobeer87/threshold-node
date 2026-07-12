# QA matrix

| Feature | Proof | Result |
|---|---|---|
| THS-F001 | `tests/unit/test_scoped_view.py` | Pass |
| THS-F002 | ASGI issue/revoke/read auth tests in `test_api_server.py`; config tests | Pass |
| THS-F003 | allowed/not-relayed and no-go response-contract tests | Pass |
| THS-F004 | `test_public_release_check.py`, synthetic fixture validation | Pass |
| THS-F005 | `test_ledger.py`; API write-failure rollback and bounded-read tests | Pass |
| THS-F009 | public-safe signature assertions in `test_api_server.py` | Pass |
| THS-F010 | forbidden real-video test + media ignore policy | Pass |
| THS-F011 | `test_grant_manager.py`; API expiry/window/digest/revoke tests | Pass |
| THS-F012 | `test_mock_robot.py` exact flow + transport/contract/safety failures | Pass |
| Packaging | compile/import checks | Pass locally |
| Automated suite | `make check`: 109 tests | Pass locally |
| Loopback process proof | scoped `200` → allowed/unrelayed `503` → no-go `403` | Pass locally |
| Public-tree scan | 69 candidate files, 0 findings | Pass locally |
| Python 3.10 CI | GitHub Actions run 5 on implementation commit `3ae4894` | Pass |
| Python 3.12 CI | GitHub Actions run 5 on implementation commit `3ae4894` | Pass |
| Hardware | bench test with exact parts | Not run; do not claim |
| GPT-5.6 integration | structured-output evals | Not implemented |

The local Waves 1–2 gate passes. The product and Build Week submission remain incomplete;
command relay, model capture, hardware, and full demo claims stay blocked.
