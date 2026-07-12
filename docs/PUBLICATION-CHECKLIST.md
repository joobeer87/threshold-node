# Public GitHub publication checklist

Target repository: `joobeer87/threshold-node`.

The public repository and `main` branch now exist. Wave work is reviewed through a feature
branch and draft pull request before merge. Repeat the safety checks below for every push.

## Before a push

- Working tree and staged diff are understood and clean.
- Test suite, compile check, public-tree scan, and independent secret scan pass.
- `git ls-files` contains no environment files, credentials, archives, raw/review media,
  runtime data, or generated caches.
- Commit metadata uses a public noreply email.
- README, MIT license, security policy, contribution guide, CI, and issue/PR templates are
  present.
- The approved Git/PR authentication path targets the intended account and repository.
- The branch, commit scope, and remote action have been explicitly reviewed.

## Repository metadata

- Visibility: public
- Default branch: `main`
- Description: `Owner-held permission and disclosure boundary for domestic robots and agents.`
- Topics: `codex`, `edge-ai`, `fastapi`, `home-automation`, `privacy`, `robotics`
- Issues: enabled
- Wiki: disabled
- Private vulnerability reporting: enabled

Do not add a GPT-5.6 topic or runtime claim until that integration is implemented and
tested.

## After a public push

1. Open the repository in a logged-out browser and inspect README, files, commit author,
   license, and links as a stranger would see them.
2. Confirm GitHub Actions starts on Python 3.10 and 3.12 and fix only evidence-backed
   failures.
3. Enable private vulnerability reporting and verify `SECURITY.md` is discoverable.
4. Confirm no unexpected remote, branch, release, package, Pages site, or deployment was
   created.
5. After the first green CI run, add branch protection without blocking the owner's
   emergency ability to repair the Build Week branch.

The final real-room video remains external. Add its reviewed link only after
`REAL-FOOTAGE-CHECKLIST.md` passes.
