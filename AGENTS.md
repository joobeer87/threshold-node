# Threshold Node agent instructions

This repository is intended to become public. Treat all edits as publication candidates.

## Boundaries

- Never add real credentials, populated environment files, private URLs, home-directory
  paths, real dwelling data, raw/review video, camera frames, device identifiers, receipts,
  or ledgers.
- Use only fixtures labeled synthetic. Never make a fake credential resemble a provider
  token.
- Keep owner authentication separate from per-grant authentication.
- Default to loopback and fail closed when authentication is absent.
- Never claim that a command was relayed, a device was stopped, a ledger was persistent,
  or a safety target was met without local evidence.
- Treat hardware controls as prototype interlocks, not certified safety systems.

## Workflow

1. Inspect `git status` and the relevant spec before editing.
2. Keep policy decisions in pure/testable functions where possible.
3. Update README/spec/privacy guidance when behavior or public assumptions change.
4. Run focused tests, then `make check` before a commit.
5. Review `git diff --cached` and `git ls-files` before any push.

This file does not authorize a hosted deploy, provider write, secret access, hardware
actuation, or public push. Those require an explicit user request plus the applicable
operator approval gate.
