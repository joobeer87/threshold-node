"""The public-tree scanner must catch leaks without echoing their values."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCANNER = Path(__file__).resolve().parents[2] / "scripts" / "public_release_check.py"


def run_scan(root: Path) -> tuple[subprocess.CompletedProcess[str], dict]:
    result = subprocess.run(
        [sys.executable, str(SCANNER), str(root)],
        capture_output=True,
        check=False,
        text=True,
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
