#!/usr/bin/env python3
"""Fail-closed public-tree scan with sanitized findings only."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "htmlcov",
    "node_modules",
    "venv",
}
EXCLUDED_PATH_PREFIXES = {
    ("media", "exports"),
    ("media", "raw"),
    ("media", "review"),
}
ALLOWED_EXAMPLE_PATHS = {"config/env.example"}
FORBIDDEN_NAMES = {
    ".env",
    "credentials.json",
    "id_dsa",
    "id_ed25519",
    "id_rsa",
    "secrets.json",
}
FORBIDDEN_SUFFIXES = {
    ".heic",
    ".jsonl",
    ".key",
    ".m4v",
    ".mov",
    ".mp4",
    ".p12",
    ".pem",
    ".pfx",
}
MAX_FILE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES = (
    Rule("private_key_marker", re.compile(r"BEGIN(?: [A-Z]+)? " + r"PRIVATE KEY")),
    Rule("cloud_access_key", re.compile("AK" + r"IA[0-9A-Z]{16}")),
    Rule("provider_token", re.compile(r"\b" + "s" + r"k-[A-Za-z0-9_-]{20,}\b")),
    Rule("github_token", re.compile(r"\bg" + r"h[pousr]_[A-Za-z0-9]{30,}\b")),
    Rule("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
    Rule("credentialed_url", re.compile(r"https?://[^/\s:@]+:[^@\s]+@")),
    Rule(
        "home_path",
        re.compile(
            r"(?:/h[o]me/|/U[s]ers/|[A-Za-z]:\\U[s]ers\\)[^/\\\s]+"
        ),
    ),
    Rule(
        "sensitive_assignment",
        re.compile(
            r"(?i)['\"]?(?:api[_-]?key|client[_-]?secret|password|passwd|secret|token)['\"]?"
            r"\s*[:=]\s*['\"]([^'\"\r\n]+)['\"]"
        ),
    ),
    Rule(
        "sensitive_env_value",
        re.compile(
            r"(?m)^[A-Z][A-Z0-9_]*(?:API_KEY|PASSWORD|SECRET|TOKEN)\s*=\s*([^\s#]+)"
        ),
    ),
    Rule(
        "email_address",
        re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    ),
)


def _is_placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {
        "<redacted>",
        "<required>",
        "changeme",
        "example",
        "placeholder",
        "redacted",
        "required",
    } or normalized.startswith(("${", "<your-"))


def _allowed_match(rule: Rule, match: re.Match[str]) -> bool:
    if rule.name == "sensitive_assignment":
        return _is_placeholder(match.group(1))
    if rule.name == "sensitive_env_value":
        return _is_placeholder(match.group(1))
    if rule.name == "email_address":
        address = match.group(0).lower()
        return address.endswith(("@example.com", "@users.noreply.github.com"))
    return False


def _tracked_paths(root: Path) -> set[str]:
    if not (root / ".git").exists():
        return set()
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return set()
    return {
        value.decode("utf-8")
        for value in result.stdout.split(b"\0")
        if value
    }


def scan(root: Path) -> dict[str, object]:
    findings: list[dict[str, object]] = []
    scanned_files = 0
    skipped_binary = 0

    for relative in sorted(_tracked_paths(root)):
        parts = Path(relative).parts
        if parts[:2] in EXCLUDED_PATH_PREFIXES:
            findings.append(
                {"path": relative, "line": None, "rule": "tracked_private_media"}
            )

    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        parts = path.relative_to(root).parts
        if (
            any(part in EXCLUDED_DIRS or part.endswith(".egg-info") for part in parts)
            or parts[:2] in EXCLUDED_PATH_PREFIXES
        ):
            continue
        if not path.is_file():
            continue

        lower_name = path.name.lower()
        if relative not in ALLOWED_EXAMPLE_PATHS and (
            lower_name in FORBIDDEN_NAMES
            or lower_name.startswith(".env.")
            or path.suffix.lower() in FORBIDDEN_SUFFIXES
        ):
            findings.append({"path": relative, "line": None, "rule": "forbidden_path"})
            continue

        if path.stat().st_size > MAX_FILE_BYTES:
            findings.append({"path": relative, "line": None, "rule": "oversized_file"})
            continue

        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            skipped_binary += 1
            continue

        scanned_files += 1
        for line_number, line in enumerate(text.splitlines(), start=1):
            for rule in RULES:
                for match in rule.pattern.finditer(line):
                    if not _allowed_match(rule, match):
                        findings.append(
                            {"path": relative, "line": line_number, "rule": rule.name}
                        )

    return {
        "status": "pass" if not findings else "fail",
        "scanned_files": scanned_files,
        "skipped_binary": skipped_binary,
        "finding_count": len(findings),
        "findings": findings,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    report = scan(Path(args.root).resolve())
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
