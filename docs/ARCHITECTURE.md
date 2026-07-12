# ARCHITECTURE

This is the target architecture. Today only the policy core, in-memory grants, authenticated
API boundary, and synthetic seed are runnable; adapters, durable ledger, console, capture,
and hardware modules are incomplete.

```
                   owner console (blueprint UI, P5: MVP.jsx → live API)
                                      │ HTTP :8471
 phone walk (P2) → capture/vision → housefile/store → housefile/scoped_view (PURE)
                                      │          ▲            │
                                      │    grants/manager ◄───┤ command gate
 ESP32 (USB) ◄─ hardware/{estop,display,receipt}              ▼
     E-stop trip → EVENT:ESTOP → adapters.halt_all()   core/events (bus)
                                      └──► adapters/{matter_rvc, home_assistant,
                                            valetudo_mqtt, automower, mock_agent}
                     ledger (append-only) subscribes to EVERYTHING
```
Import DAG: core ← housefile ← grants ← adapters ← api. Sideways talk = event bus only.
Handlers never crash the bus. Ledger is the last subscriber to detach, first to attach.
