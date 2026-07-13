# QA matrix

| Feature | Proof | Result |
|---|---|---|
| THS-F001 | `tests/unit/test_scoped_view.py` | Pass |
| THS-F002 | ASGI issue/revoke/read auth tests in `test_api_server.py`; config tests | Pass |
| THS-F003 | allowed/not-relayed and no-go response-contract tests | Pass |
| THS-F004 | `test_public_release_check.py`, synthetic fixture validation | Pass |
| THS-F005 | `test_ledger.py`: append/fsync, exact checkpoints, changed-tail refusal, witnesses, private-path checks, bounded reads | Pass, 25 tests |
| THS-F006 | `test_vision_proposals.py`: batch binding, request shape, strict validation, private persistence, owner decision, no canonical write | Pass provider-free; live eval pending |
| THS-F009 | public-safe signature assertions in `test_api_server.py` | Pass |
| THS-F010 | forbidden real-video test + media ignore policy | Pass |
| THS-F011 | `test_grant_manager.py`; API durable expiry/window/digest/revoke tests | Pass |
| THS-F012 | `test_mock_robot.py` exact flow + transport/contract/safety failures | Pass |
| THS-F013 | capture input-boundary, normalization, cleanup, receipt, and real JPEG/PNG/MP4 tool smoke tests | Pass locally |
| THS-F014 | `test_grant_store.py`, `test_grant_authority.py`: restart persistence, restrictive recovery, corruption, target witness, stale/concurrent instances, authorization lease | Pass, 18 + 17 focused tests |
| THS-F015 | `test_quiet_hours.py`, ASGI command/read tests, schema/fixture projection checks, DST fold cases | Pass, 28 pure cases plus integration coverage |
| Packaging | compile/import checks | Pass locally |
| Automated suite | Wave 4 `make check`: compile + 267 tests + release scan | Pass locally |
| Quiet-hours API proof | scoped reads unaffected; active/invalid/DST/receipt-failure command cases time-controlled | Pass locally |
| Loopback process proof | Prior scoped `200` → allowed/unrelayed `503` → no-go `403`; middle result is wall-clock dependent on quiet hours | Pass with documented limitation |
| Public-tree scan | 81 candidate files, 0 findings | Pass locally |
| Capture force-track guard | scanner rejects files under `data/capture/` without reflecting paths or contents | Pass locally |
| Python 3.10/3.12 CI | PR #3 merged baseline; Wave 4 PR checks | Pending draft PR #4 |
| Hardware | bench test with exact parts | Not run; do not claim |
| GPT-5.6 request contract | fixed Responses endpoint/model, multi-image data URLs, `detail:high`, `store:false`, strict `text.format`, no tools | Pass with fake transport |
| GPT-5.6 live synthetic eval | response quality, cost, latency, token use | Not run: no approved secret-safe credential injector is available in this session; do not claim |

The merged PR #3 baseline and Wave 4 local gate pass. Delivery remains at `warn` because a
live synthetic model evaluation and later product waves are incomplete. Geometry,
owner-reviewed materialization, command relay, hardware, console, and full demo claims stay
blocked.
