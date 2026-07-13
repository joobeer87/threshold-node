"""The public-tree scanner must catch leaks without echoing their values."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


SCANNER = Path(__file__).resolve().parents[2] / "scripts" / "public_release_check.py"


def run_scan(
    root: Path,
    *,
    env: dict[str, str] | None = None,
) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        [sys.executable, str(SCANNER), str(root)],
        capture_output=True,
        check=False,
        text=True,
        env=env,
    )
    return result, json.loads(result.stdout)


def test_clean_example_passes(tmp_path: Path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "env.example").write_text("THS_OWNER_TOKEN=\n", encoding="utf-8")
    result, report = run_scan(tmp_path)
    assert result.returncode == 0
    assert report["status"] == "pass"


def test_secret_shape_fails_without_echoing_value(tmp_path: Path):
    suspicious = "AK" + "IA" + "A" * 16
    (tmp_path / "oops.txt").write_text(suspicious, encoding="utf-8")
    result, report = run_scan(tmp_path)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "cloud_access_key"
    assert suspicious not in result.stdout


def test_forbidden_environment_file_fails(tmp_path: Path):
    (tmp_path / ".env").write_text("THS_OWNER_TOKEN=\n", encoding="utf-8")
    result, report = run_scan(tmp_path)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "forbidden_path"


def test_real_world_video_file_fails(tmp_path: Path):
    (tmp_path / "room-demo.mp4").write_bytes(b"synthetic test bytes")
    result, report = run_scan(tmp_path)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "forbidden_path"


def test_runtime_jsonl_ledger_fails_public_scan(tmp_path: Path):
    (tmp_path / "ledger.jsonl").write_text(
        '{"type":"READ","detail":"private runtime event"}\n',
        encoding="utf-8",
    )
    result, report = run_scan(tmp_path)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "forbidden_path"


def test_ignored_raw_media_workspace_is_not_a_public_candidate(tmp_path: Path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    (raw / "room-demo.mp4").write_bytes(b"local-only test bytes")
    result, report = run_scan(tmp_path)
    assert result.returncode == 0
    assert report["status"] == "pass"


def test_force_tracked_raw_media_fails(tmp_path: Path):
    raw = tmp_path / "media" / "raw"
    raw.mkdir(parents=True)
    video = raw / "room-demo.mp4"
    video.write_bytes(b"local-only test bytes")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", str(video)], cwd=tmp_path, check=True)
    result, report = run_scan(tmp_path)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "tracked_private_media"


def test_untracked_capture_workspace_is_skipped(tmp_path: Path):
    capture = tmp_path / "data" / "capture" / "capture-local"
    capture.mkdir(parents=True)
    private_fixture = "capture-content-must-not-be-read"
    (capture / "frame-000001.jpg").write_bytes(private_fixture.encode("utf-8"))
    (tmp_path / ".gitignore").write_text("/data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    result, report = run_scan(tmp_path)

    assert result.returncode == 0
    assert report["status"] == "pass"
    assert private_fixture not in result.stdout


def test_force_tracked_capture_fails_without_echoing_contents(tmp_path: Path):
    capture = tmp_path / "data" / "capture" / "capture-local"
    capture.mkdir(parents=True)
    private_fixture = "capture-content-must-not-leak"
    frame = capture / "frame-000001.jpg"
    frame.write_bytes(private_fixture.encode("utf-8"))
    (tmp_path / ".gitignore").write_text("/data/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-f", str(frame)], cwd=tmp_path, check=True)

    result, report = run_scan(tmp_path)

    assert result.returncode == 1
    assert report["finding_count"] == 1
    assert report["findings"][0] == {
        "line": None,
        "path": "data/capture/<private>",
        "rule": "tracked_private_capture",
    }
    assert "capture-local" not in result.stdout
    assert "frame-000001.jpg" not in result.stdout
    assert private_fixture not in result.stdout


def test_git_index_failure_fails_closed_without_echoing_tool_output(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/bin/sh\necho PRIVATE_GIT_ERROR_SENTINEL >&2\nexit 1\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o700)
    env = dict(os.environ)
    env["PATH"] = str(fake_bin)

    result, report = run_scan(root, env=env)

    assert result.returncode == 1
    assert report["finding_count"] == 1
    assert report["findings"][0] == {
        "line": None,
        "path": "<git-index>",
        "rule": "git_index_unavailable",
    }
    assert "PRIVATE_GIT_ERROR_SENTINEL" not in result.stdout
    assert "PRIVATE_GIT_ERROR_SENTINEL" not in result.stderr
