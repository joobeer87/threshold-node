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
| THS-F019 | `test_geometry.py`: canonical determinism, explicit-order coordinates, unique digest binding, strict parser/schema, bounded fields, and absence/rejection of policy fields | Pass, 51 focused cases |
| THS-F020 | `test_materialize.py`: exact review coverage/bindings, explicit policy choices, strict schema, synthetic gate, revision CAS/exhaustion, private path/lock checks, atomic replace and rollback | Pass, 45 focused synthetic cases |
| THS-0022/0023 integration proof | `test_geometry_materialization.py`: explicit bindings → fixed geometry → reviewed synthetic canonical revision, then stale retry denial | Pass, 1 synthetic end-to-end case |
| THS-0051 integration proof | `test_simulated_appliance.py`: grant → scoped read → no-go denial → simulated trip → suspended denial, then re-arm/restart non-restoration | Pass, 1 synthetic end-to-end case |
| Packaging | compile/import checks; wheel contains byte-identical THS schema package data and isolated resource read succeeds | Pass locally |
| Automated suite | Wave 6 `make check`: compile + 429 tests + release scan | Pass locally |
| Quiet-hours API proof | scoped reads unaffected; active/invalid/DST/receipt-failure command cases time-controlled | Pass locally |
| Loopback process proof | Prior scoped `200` → allowed/unrelayed `503` → no-go `403`; middle result is wall-clock dependent on quiet hours | Pass with documented limitation |
| Public-tree scan | 95 candidate files; scanner covers tracked runtime data and receipts without reflecting paths or contents | Pass locally, 0 findings |
| Capture force-track guard | scanner rejects files under `data/capture/` without reflecting paths or contents | Pass locally |
| Receipt force-track guard | scanner rejects files under `data/receipts/` without reflecting paths or contents | Pass locally |
| Python 3.10/3.12 CI | PR #3 merged baseline; Waves 4–6 local proof | Pending stacked draft PR #6 |
| Hardware | physical stop, adapter/device halt, NC loop, ESP32/OLED/printer, physical latency, and certification bench proof | Not run; do not claim |
| GPT-5.6 request contract | fixed Responses endpoint/model, multi-image data URLs, `detail:high`, `store:false`, strict `text.format`, no tools | Pass with fake transport |
| GPT-5.6 live synthetic eval | response quality, cost, latency, token use | Not run: no approved secret-safe credential injector is available in this session; do not claim |
| Real-dwelling materialization | real canonical input or policy | Not run and prohibited by the current synthetic-only boundary |

The merged PR #3 baseline and local Wave 5 proof remain green. Wave 6 adds only
provider-free fixed geometry and a synthetic temporary-fixture materialization primitive.
Delivery remains at `warn` because draft-PR CI, a live synthetic model evaluation, a
real-dwelling review, and later product waves are incomplete. Model/spatial inference,
automatic/live-server materialization, command relay, physical hardware, console, and full
demo claims stay blocked.
