# Threshold Node

**The permission slip robots read before entering your home.**

Threshold Node is a local-first permission appliance for domestic robots and agents. It
keeps a machine-readable *housefile* under the owner's control, returns only the zones and
capabilities granted to a caller, refuses no-go actions, and records access decisions.

> Pre-alpha scaffold: the scoped-view policy core and authenticated API boundary run;
> robot adapters, persistent ledger, capture flow, owner console, and hardware interlock
> are not implemented yet. This is not a life-safety system.

## Why this exists

Robots commonly build separate proprietary maps and permission models. Threshold inverts
that relationship: the home owns one local policy model, while each robot receives a
scoped, revocable view. No-go boundaries transmit; their interiors do not.

The checked-in house, grants, ledger entries, and UI reference are unmistakably synthetic.
Real dwelling exports, camera frames, device identifiers, credentials, and receipts must
stay in ignored local storage.

## Current proof

- Pure `scoped_view` policy function with defense-in-depth around no-go zones.
- Per-grant bearer authentication for robot reads and commands.
- Separate owner authentication for the ledger/admin boundary.
- Loopback-only default; non-loopback binding requires an explicit opt-in.
- Strict command schema that refuses unsupported verbs and never claims a stub adapter
  relayed an action.
- Simulator-first path, synthetic fixtures, and a sanitized public-release scanner.

## Framework

The current core is Python 3.10+ with FastAPI and Pydantic. That is a good fit for a Jetson
or other edge host and keeps the policy layer easy to test. The recommended product stack
is:

- FastAPI for the local policy/API node;
- Vite + React + TypeScript for the offline-capable owner console;
- Arduino/PlatformIO for the ESP32 bridge;
- Matterbridge/matter.js only where the virtual Matter RVC demo needs it;
- OpenAI Responses API with GPT-5.6 structured outputs for vision-to-housefile proposals,
  always behind deterministic validation and explicit owner confirmation.

The OpenAI runtime integration is planned, not yet implemented. See
[`docs/BUILD-WEEK.md`](docs/BUILD-WEEK.md).

## Quickstart (synthetic demo only)

```bash
make install
```

Generate two different random values locally (for example with Python's `secrets` module),
export them as `THS_OWNER_TOKEN` and `THS_DEMO_GRANT_TOKEN`, then enable the synthetic demo:

```bash
export THS_DEMO_MODE=true
make run
```

In another shell with the same demo grant token exported:

```bash
python3 scripts/mock_robot.py --grant g-neo
```

The node listens on `127.0.0.1:8471` by default. Do not expose it to a LAN or the internet
until the threat model, persistent grant store, transport security, and hardware behavior
have been reviewed.

## Validation

```bash
make check
```

This compiles the Python sources, runs the tests, and scans the candidate public tree. The
scanner reports only file, line, and rule identifiers; it never echoes matching values.

## Integration paths

| Target | Protocol | Intended enforcement |
|---|---|---|
| Modern robot vacuums | Matter 1.4 RVC + Service Area | Enforced by area selection |
| Robot lawn mowers | Automower Connect | Enforced by work/stay-out areas |
| Existing home robots | Home Assistant or Valetudo MQTT | Gated by Threshold |
| Future agents/humanoids | THS-0.1 scoped-read API | Gated + auditable |

These adapters are stubs today; the API reports them as unavailable rather than upgrading
their enforcement tier.

## Repository map

```text
docs/          architecture, specs, privacy, demo, and Build Week plan
schema/        THS-0.1 JSON Schema and a synthetic fixture
src/threshold/ policy core, grants, API, adapters, hardware, and capture modules
tests/         unit/API/security tests
scripts/       mock robot and public-release scan
reference/     non-runnable JSX visual reference for the future console
```

## Safety and disclosure

The physical stop loop described in [`HARDWARE.md`](HARDWARE.md) is a prototype interlock,
not a certified emergency-stop. Keep manufacturer controls and a physical power-isolation
path. For vulnerability handling and public-demo rules, see [`SECURITY.md`](SECURITY.md)
and [`docs/PRIVACY.md`](docs/PRIVACY.md).

Licensed under the MIT License.
