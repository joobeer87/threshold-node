"""THS-0012 — JSON store, atomic write. SQLite is a later swap."""
from __future__ import annotations
import json, os, tempfile

def save(path: str, data: dict) -> None:
    d = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=d)
    with os.fdopen(fd, "w") as f: json.dump(data, f, indent=2)
    os.replace(tmp, path)

def load(path: str) -> dict:
    with open(path) as f: return json.load(f)
