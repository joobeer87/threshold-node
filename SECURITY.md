# Security policy

Threshold Node is pre-alpha software. Do not use it to control hazardous machinery, rely
on it as a certified safety function, expose it directly to the internet, or load a real
dwelling file without an independent security review.

## Reporting a vulnerability

When this repository is published, use GitHub's private vulnerability-reporting feature.
Do not put credentials, real house data, device identifiers, exploit payloads, or private
logs in a public issue. If private reporting is unavailable, open a minimal issue asking
the maintainers to enable a private channel; omit the sensitive details.

## Supported versions

No version is security-supported yet. The `0.1.x` line is a Build Week prototype.

## Public-demo boundaries

- Use only `schema/examples/synthetic-demo-house.json` and the in-code synthetic seed.
- Generate owner and grant tokens locally; never commit or print them.
- Keep the default loopback bind. A network bind is an explicit, reviewed opt-in.
- Treat receipts, ledgers, camera frames, and device integrations as sensitive local data.
- Run `make check` against the exact staged tree before any push.
- Do not use the prototype stop loop as an emergency-stop or life-safety system.
- Keep raw or review real-room footage out of Git and complete the footage privacy checklist
  before publishing a video link.
