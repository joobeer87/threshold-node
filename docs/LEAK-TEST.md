# Optional leak-test easter egg

A leak-themed easter egg can strengthen the submission if it proves the product thesis
instead of pretending to expose something.

## Safe scene

1. A red-team robot asks for a field hidden inside a no-go synthetic zone.
2. The model may propose the request, but the deterministic scoped-view gate removes it.
3. The console flashes `LEAK TEST: BLOCKED` and `0 bytes disclosed`.
4. The ledger records only the deny rule and a short one-way fingerprint.
5. The thermal receipt ends with: `THE BEST SECRET NEVER CROSSED THE THRESHOLD.`

Use a plainly fictional marker such as `THRESHOLD-DEMO-CANARY`; do not use a value shaped
like a cloud key, OAuth token, password, private URL, or personal record. Keep the scene
offline and do not use a network honeytoken. Trigger it from a deliberate UI gesture, not
from the physical stop control.

This is a stretch feature. The primary end-to-end safety and permission loop comes first.
