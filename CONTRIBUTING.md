# Contributing

Threshold Node welcomes focused improvements to its policy core, local API, simulator,
privacy controls, adapters, console, and documentation.

## Before opening a change

1. Create a focused branch from `main`.
2. Keep examples synthetic and remove private paths, identifiers, logs, credentials, and
   real-world media.
3. Add or update tests for behavior changes.
4. Run `make check` and review the staged file list.
5. Keep claims evidence-based: stubs are unavailable, not "working" or "enforced."

Do not report vulnerabilities or attach sensitive logs in a public issue. Follow
[`SECURITY.md`](SECURITY.md) instead.

## Pull requests

Explain the user impact, list the checks run, and call out any skipped hardware, model,
adapter, or hosted validation. Small, reviewable changes are preferred.
