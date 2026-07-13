# QA matrix

| Feature | Proof | Result |
|---|---|---|
| THS-F001 | `tests/unit/test_scoped_view.py` | Pass |
| THS-F002 | ASGI issue/revoke/read auth tests in `test_api_server.py`; config tests | Pass |
| THS-F003 | allowed/not-relayed and no-go response-contract tests | Pass |
| THS-F004 | `test_public_release_check.py`, synthetic fixture validation | Pass |
| THS-F005 | `test_ledger.py`; API write-failure rollback and bounded-read tests | Pass |
| THS-F006 | `test_vision_proposals.py`: batch binding, request shape, strict validation, private persistence, owner decision, no canonical write | Pass provider-free; live eval pending |
| THS-F009 | public-safe signature assertions in `test_api_server.py` | Pass |
| THS-F010 | forbidden real-video test + media ignore policy | Pass |
| THS-F011 | `test_grant_manager.py`; API expiry/window/digest/revoke tests | Pass |
| THS-F012 | `test_mock_robot.py` exact flow + transport/contract/safety failures | Pass |
| THS-F013 | capture input-boundary, normalization, cleanup, receipt, and real JPEG/PNG/MP4 tool smoke tests | Pass locally |
| Packaging | compile/import checks | Pass locally |
| Automated suite | Prior merged baseline: `make check` 151 tests | Pass locally |
| THS-0021 full suite | Current-wave `make check`: compile + 190 tests + release scan | Pass locally |
| Loopback process proof | scoped `200` → allowed/unrelayed `503` → no-go `403` | Pass locally |
| Public-tree scan | 75 candidate files, 0 findings | Pass locally |
| Capture force-track guard | scanner rejects files under `data/capture/` without reflecting paths or contents | Pass locally |
| Python 3.10 CI | GitHub Actions push + PR checks for draft PR #2 | Pass |
| Python 3.12 CI | GitHub Actions push + PR checks for draft PR #2 | Pass |
| Hardware | bench test with exact parts | Not run; do not claim |
| GPT-5.6 request contract | fixed Responses endpoint/model, multi-image data URLs, `detail:high`, `store:false`, strict `text.format`, no tools | Pass with fake transport |
| GPT-5.6 live synthetic eval | response quality, cost, and latency | Not run; do not claim |

The merged Waves 1–3 gate and THS-0021 local full suite pass. THS-0021 remains at `warn`
until a live synthetic model evaluation is recorded. The product and Build Week submission
remain incomplete; geometry, canonical proposal application, command relay, hardware, and
full demo claims stay blocked.
