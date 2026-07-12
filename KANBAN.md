# KANBAN — THRESHOLD NODE · build window 2026-07-13 → 07-21
Columns per structured-coding-framework. Tier: T1 essential / T2 important / T3 advanced / T4 future.
Day map: P0–P1→D1-2 · P2→D3-4 · P3→D4-6 · P4→D5+7 · P5→D6-8 · P6→D8.

| ID | P | Module | Title | Description | File | Deps | Tier | Est | Status | Conf | Notes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| THS-0001 | P0 | repo | Scaffold + pyproject + Makefile | Layout, deps, make targets | pyproject.toml | — | T1 | 20 | DONE | 90 | this repo |
| THS-0002 | P0 | core | Core types + enums + validation | Zone/System/Inventory/Grant/Policies dataclasses, post-init checks | src/threshold/core/types.py | 0001 | T1 | 40 | DONE | 85 | tested via scoped_view suite |
| THS-0003 | P0 | core | Error hierarchy | ThresholdError→Data/Validation/Config/Adapter | src/threshold/core/errors.py | 0001 | T1 | 15 | DONE | 85 | |
| THS-0004 | P0 | core | Event bus | on/emit, handler crash isolation | src/threshold/core/events.py | 0002 | T1 | 30 | DONE | 75 | sync bus; async upgrade THS-0042 |
| THS-0005 | P0 | core | Config loader | env + toml, LAN bind default | src/threshold/core/config.py | 0001 | T1 | 25 | DONE | 70 | minimal |
| THS-0006 | P0 | repo | Public release hygiene | gitignore, synthetic fixtures, sanitized scanner, privacy docs | scripts/public_release_check.py | 0001 | T1 | 45 | DONE | 90 | local scan + tests |
| THS-0010 | P1 | housefile | scoped_view pure function | SPEC-THS §3 rules 1–7 | src/threshold/housefile/scoped_view.py | 0002 | T1 | 45 | DONE | 90 | 8/8 tests pass |
| THS-0011 | P1 | housefile | scoped_view unit tests | happy, no-go-always, safety invariant, inactive, undisclosed, ungrantable | tests/unit/test_scoped_view.py | 0010 | T1 | 45 | DONE | 90 | pytest green |
| THS-0012 | P1 | housefile | JSON store + rev bump | load/save housefile, atomic write | src/threshold/housefile/store.py | 0002 | T1 | 30 | DONE | 75 | file-based; SQLite later |
| THS-0013 | P1 | grants | Grant manager | issue/revoke/suspend_all, ungrantable no-go check | src/threshold/grants/manager.py | 0002 | T1 | 40 | DONE | 80 | covered in tests |
| THS-0014 | P1 | api | FastAPI node v0 | /housefile /command /grants /ledger /health | src/threshold/api/server.py | 0010,0013 | T1 | 60 | WIP | 60 | skeleton written, needs auth+run |
| THS-0015 | P1 | api | Owner + per-grant auth | separate bearer boundaries, loopback default, explicit LAN opt-in | src/threshold/api/server.py | 0014 | T1 | 45 | WIP | 75 | expiry/window enforcement pending |
| THS-0016 | P1 | core | Ledger sink | append-only jsonl, subscribes all events | src/threshold/core/events.py | 0004 | T1 | 25 | TODO | 0 | |
| THS-0020 | P2 | capture | Room-walk intake CLI | phone video/photos → frames → per-room batches | src/threshold/capture/vision_intake.py | 0012 | T1 | 90 | TODO | 0 | |
| THS-0021 | P2 | capture | Vision → zones/inventory extraction | GPT-5.6 vision prompt → THS objects + flags, owner confirm step | src/threshold/capture/vision_intake.py | 0020 | T1 | 120 | TODO | 0 | human gate before write |
| THS-0022 | P2 | capture | Boundary sketcher | rough rect boundaries from walk order; manual nudge UI later | src/threshold/capture/vision_intake.py | 0021 | T2 | 60 | TODO | 0 | |
| THS-0030 | P3 | adapters | HA websocket client + gate | long-lived token, service-call relay through grant gate | src/threshold/adapters/home_assistant.py | 0013 | T1 | 90 | TODO | 0 | GATED tier |
| THS-0031 | P3 | adapters | Matter RVC via HA service-areas | THS zone↔ServiceArea map table, area-targeted clean → ENFORCED | src/threshold/adapters/matter_rvc.py | 0030 | T1 | 90 | TODO | 0 | HA 2026.3+ |
| THS-0032 | P3 | adapters | Virtual RVC demo rig | Matterbridge/matter.js virtual 1.4 RVC paired to HA | scripts/virtual_rvc.md | 0031 | T1 | 60 | TODO | 0 | $0 robot path |
| THS-0033 | P3 | adapters | Automower Connect adapter | OAuth2, WS state, stay-out zone switches, ParkUntilFurtherNotice halt | src/threshold/adapters/automower.py | 0013 | T2 | 120 | TODO | 0 | rate limits! cache+WS |
| THS-0034 | P3 | adapters | Valetudo MQTT adapter | segment-clean relay, halt | src/threshold/adapters/valetudo_mqtt.py | 0013 | T3 | 90 | TODO | 0 | |
| THS-0035 | P3 | adapters | Mock agent client | pulls scoped file, attempts workshop, obeys | scripts/mock_robot.py | 0014 | T1 | 40 | WIP | 50 | script stub in repo |
| THS-0040 | P4 | hardware | ESP32 firmware (bridge) | NC loop read, OLED, printer UART, serial JSON | firmware/bridge/bridge.ino | — | T1 | 90 | TODO | 0 | Arduino IDE |
| THS-0041 | P4 | hardware | stop interlock driver + SIM mode | serial listener → suspend_all + halt_all; measure latency | src/threshold/hardware/estop.py | 0004,0013 | T1 | 60 | TODO | 0 | prototype, not safety-rated |
| THS-0042 | P4 | hardware | display.py states | ARMED/READ/DENY/TRIPPED | src/threshold/hardware/display.py | 0040 | T2 | 45 | TODO | 0 | terminal fallback DONE-ish |
| THS-0043 | P4 | hardware | receipt.py printer | GRANT/DENY/ESTOP templates, PNG fallback | src/threshold/hardware/receipt.py | 0040 | T2 | 45 | TODO | 0 | |
| THS-0050 | P5 | console | MVP.jsx → live API | swap window.storage for node endpoints | console/ | 0014 | T1 | 120 | TODO | 0 | reference in /reference |
| THS-0051 | P5 | integration | E2E: grant→read→deny→estop | scripted run, ledger asserted | tests/integration/test_e2e.py | 0035,0041 | T1 | 90 | TODO | 0 | |
| THS-0052 | P5 | integration | T-ENF-01 tier honesty audit | adapter tier == capabilities, ADVISORY never upgraded | tests/integration/test_tiers.py | 0030 | T1 | 45 | TODO | 0 | spec violation gate |
| THS-0060 | P6 | docs | Demo video shoot + edit | DEMO-SCRIPT.md, 75s | media/ | 0051 | T1 | 180 | TODO | 0 | D8 |
| THS-0061 | P6 | docs | Submission pack | description, repo tidy, metrics | README.md | 0060 | T1 | 60 | TODO | 0 | |
| THS-0062 | P6 | polish | systemd unit + boot-to-armed | node autostarts on Jetson | scripts/threshold.service | 0041 | T2 | 30 | TODO | 0 | |
| THS-0070 | P6 | stretch | Receipt hash chain | each receipt carries prev-hash | hardware/receipt.py | 0043 | T3 | 45 | TODO | 0 | tamper-evident tape |
| THS-0071 | P6 | stretch | mDNS discovery `_threshold._tcp` | agents find the node | api/ | 0014 | T3 | 30 | TODO | 0 | |
| THS-0072 | P6 | stretch | Quiet-hours command gating | reject command:* inside quietHours | grants/manager.py | 0013 | T2 | 30 | TODO | 0 | |
| THS-0073 | P6 | polish | Aurora signature easter egg | hidden public-safe route, authority-before-autonomy receipt | docs/AURORA-EASTER-EGG.md | 0014 | T3 | 30 | DONE | 95 | signature only; private AuroraOS not embedded |
| THS-0074 | P6 | media | Real-footage privacy gate | staged-room checklist, metadata strip, frame/audio review, external publish | docs/REAL-FOOTAGE-CHECKLIST.md | 0060 | T1 | 45 | DONE | 90 | raw/review/export video stays out of Git |
