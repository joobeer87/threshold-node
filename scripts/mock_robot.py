"""THS-0035 (WIP) — mock agent: pull scoped file, attempt a no-go zone, obey."""
import json
import os
import sys
import urllib.request

BASE = "http://127.0.0.1:8471"
grant = sys.argv[sys.argv.index("--grant") + 1] if "--grant" in sys.argv else "g-neo"
grant_token = os.getenv("THS_DEMO_GRANT_TOKEN", "")
if not grant_token:
    raise SystemExit("THS_DEMO_GRANT_TOKEN must be set in the local environment")
headers = {"X-Threshold-Grant-Token": grant_token}

read_request = urllib.request.Request(f"{BASE}/housefile?grant={grant}", headers=headers)
with urllib.request.urlopen(read_request) as r:
    view = json.load(r)
print(json.dumps(view, indent=2))
print("\n→ attempting workshop (should be refused)…")
req = urllib.request.Request(f"{BASE}/command", method="POST",
    data=json.dumps({"grant": grant, "verb": "navigate", "zone": "workshop"}).encode(),
    headers={"Content-Type": "application/json", **headers})
try:
    urllib.request.urlopen(req)
    print("!! relayed — that is a bug, file it")
except Exception as e:
    print(f"✓ gate refused ({e}). Obeying. Boundary respected.")
