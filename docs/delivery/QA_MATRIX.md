# QA matrix

| Feature | Proof | Result |
|---|---|---|
| THS-F001 | `tests/unit/test_scoped_view.py` | Pass |
| THS-F002 | ASGI issue/revoke/read auth tests in `test_api_server.py`; config tests | Pass |
| THS-F003 | allowed/not-relayed and no-go response-contract tests | Pass |
| THS-F004 | `test_public_release_check.py`: synthetic fixture validation and fail-closed tracked runtime-data, ledger, capture, and receipt rejection | Pass |
| THS-F005 | `test_ledger.py`: append/fsync, exact checkpoints, changed-tail refusal, witnesses, private-path checks, bounded reads; ESTOP commit coverage in grant-authority/API tests | Pass |
| THS-F006 | `test_vision_proposals.py`: batch binding, request shape, strict validation, private persistence, owner decision, no canonical write | Pass provider-free; live eval pending |
| THS-F009 | public-safe signature assertions in `test_api_server.py` | Pass |
| THS-F010 | forbidden real-video test + media ignore policy | Pass |
| THS-F011 | `test_grant_manager.py`; API durable expiry/window/digest/revoke/suspension tests; re-arm leaves grants suspended | Pass |
| THS-F012 | `test_mock_robot.py` exact flow + transport/contract/safety failures | Pass |
| THS-F013 | capture input-boundary, normalization, cleanup, receipt, and real JPEG/PNG/MP4 tool smoke tests | Pass locally |
| THS-F014 | `test_grant_store.py`, `test_grant_authority.py`: restart persistence, restrictive recovery, corruption and pending semantic tamper rejection, prior/target witnesses, stale/concurrent instances, authorization lease, zero-active ESTOP revision | Pass, 18 + 22 focused tests |
| THS-F015 | `test_quiet_hours.py`, ASGI command/read tests, schema/fixture projection checks, DST fold cases | Pass, 28 pure cases plus integration coverage |
| THS-F016 | `test_estop.py`: latch-first sequencing, zero-active persistence, duplicate/concurrent trip idempotence, isolated dependency failures, re-arm non-restoration; owner/API fail-closed coverage in `test_api_server.py` | Pass, 10 pure cases plus API coverage |
| THS-F017 | `test_display.py`: exact READ/DENY windows, TRIPPED precedence, deterministic rendering, bounded terminal-safe agents, invalid inputs; API observer coverage | Pass, 18 pure cases plus API coverage |
| THS-F018 | `test_receipt.py`: factory-only allowlisted templates, render-time integrity, fixed-bitmap deterministic PNG, private write-once modes, link/path rejection, partial-file cleanup; in-memory ESTOP API exercise | Pass, 20 focused cases plus API coverage |
| THS-0051 integration proof | `test_simulated_appliance.py`: grant → scoped read → no-go denial → simulated trip → suspended denial, then re-arm/restart non-restoration | Pass, 1 synthetic end-to-end case |
| Packaging | compile/import checks | Pass locally |
| Automated suite | Wave 5 `make check`: compile + 332 tests + release scan | Pass locally |
| Quiet-hours API proof | scoped reads unaffected; active/invalid/DST/receipt-failure command cases time-controlled | Pass locally |
| Loopback process proof | Prior scoped `200` → allowed/unrelayed `503` → no-go `403`; middle result is wall-clock dependent on quiet hours | Pass with documented limitation |
| Public-tree scan | 88 candidate files; scanner covers tracked runtime data and receipts without reflecting paths or contents | Pass locally, 0 findings |
| Capture force-track guard | scanner rejects files under `data/capture/` without reflecting paths or contents | Pass locally |
| Receipt force-track guard | scanner rejects files under `data/receipts/` without reflecting paths or contents | Pass locally |
| Python 3.10/3.12 CI | PR #3 merged baseline; Wave 5 local proof | Pending stacked draft PR #5 |
| Hardware | physical stop, adapter/device halt, NC loop, ESP32/OLED/printer, physical latency, and certification bench proof | Not run; do not claim |
| GPT-5.6 request contract | fixed Responses endpoint/model, multi-image data URLs, `detail:high`, `store:false`, strict `text.format`, no tools | Pass with fake transport |
| GPT-5.6 live synthetic eval | response quality, cost, latency, token use | Not run: no approved secret-safe credential injector is available in this session; do not claim |

The merged PR #3 baseline and the Wave 5 local gate pass. Wave 5 proof is synthetic and
software-path-only: adapter completion means only that an injected method returned, not that a
device halted. Delivery remains at `warn` because draft-PR CI, a live synthetic model evaluation,
and later product waves are incomplete. Geometry, owner-reviewed materialization, command relay,
physical hardware, console, and full demo claims stay blocked.
