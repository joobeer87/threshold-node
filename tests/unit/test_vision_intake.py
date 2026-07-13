"""Privacy and behavior proofs for the local capture intake boundary."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
from io import StringIO
from pathlib import Path

import pytest

from threshold.capture import vision_intake as intake


class FakeMediaRunner:
    """Small deterministic stand-in for ffprobe and ffmpeg."""

    def __init__(
        self,
        *,
        duration: str = "4.0",
        probe_payload: dict[str, object] | None = None,
        probe_stdout: str | None = None,
        fail_probe: bool = False,
        fail_extract_at: int | None = None,
        invalid_output: bool = False,
        tool_sentinel: str = "PRIVATE_TOOL_OUTPUT_SENTINEL",
    ) -> None:
        self.duration = duration
        self.probe_payload = probe_payload
        self.probe_stdout = probe_stdout
        self.fail_probe = fail_probe
        self.fail_extract_at = fail_extract_at
        self.invalid_output = invalid_output
        self.tool_sentinel = tool_sentinel
        self.calls: list[tuple[list[str], dict[str, object]]] = []
        self.extract_count = 0

    @staticmethod
    def _descriptor(args: list[str]) -> int:
        fd_path = args[args.index("-i") + 1] if "-i" in args else args[-1]
        return int(fd_path.rsplit("/", 1)[-1])

    def __call__(self, args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        self.calls.append((list(args), dict(kwargs)))
        executable = Path(args[0]).name
        descriptor = self._descriptor(args)
        source_path = Path(os.readlink(f"/proc/self/fd/{descriptor}"))

        if executable == "ffprobe":
            if self.fail_probe:
                return subprocess.CompletedProcess(
                    args,
                    1,
                    stdout="",
                    stderr=self.tool_sentinel,
                )
            if self.probe_stdout is not None:
                return subprocess.CompletedProcess(
                    args,
                    0,
                    stdout=self.probe_stdout,
                    stderr=self.tool_sentinel,
                )
            suffix = source_path.suffix.lower()
            codec = "png" if suffix == ".png" else "mjpeg"
            format_name = "png_pipe" if suffix == ".png" else "jpeg_pipe"
            duration: str | None = None
            if suffix in intake.VIDEO_SUFFIXES:
                codec = "mpeg4"
                format_name = "mov,mp4,m4a,3gp,3g2,mj2"
                duration = self.duration
            payload = self.probe_payload or {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": codec,
                        "width": 640,
                        "height": 360,
                        "duration": duration,
                        "avg_frame_rate": "2/1",
                    }
                ],
                "format": {"format_name": format_name, "duration": duration},
            }
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=json.dumps(payload),
                stderr=self.tool_sentinel,
            )

        if executable != "ffmpeg":
            raise AssertionError("unexpected executable")
        self.extract_count += 1
        if self.fail_extract_at == self.extract_count:
            return subprocess.CompletedProcess(
                args,
                1,
                stdout="",
                stderr=self.tool_sentinel,
            )
        source_bytes = os.pread(descriptor, 1024 * 1024, 0)
        timestamp = args[args.index("-ss") + 1] if "-ss" in args else "still"
        digest = hashlib.sha256(source_bytes + timestamp.encode("ascii")).digest()
        normalized = (
            b"not-a-jpeg"
            if self.invalid_output
            else (
                b"\xff\xd8"
                b"\xff\xc0\x00\x0b\x08\x01\x68\x02\x80\x01\x01\x11\x00"
                b"\xff\xda\x00\x02"
                + digest
                + b"\xff\xd9"
            )
        )
        Path(args[-1]).write_bytes(normalized)
        return subprocess.CompletedProcess(args, 0, stdout="", stderr=self.tool_sentinel)


@pytest.fixture
def tool_lookup(tmp_path: Path):
    tool_dir = tmp_path / "fake-tools"
    tool_dir.mkdir()
    paths: dict[str, str] = {}
    for name in ("ffmpeg", "ffprobe"):
        path = tool_dir / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o700)
        paths[name] = str(path)
    return paths.get


def _project(tmp_path: Path, name: str = "project") -> Path:
    project = tmp_path / name
    project.mkdir()
    return project


def _batch(project: Path, batch_id: str) -> Path:
    return project / "data" / "capture" / f"batch-{batch_id}"


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _frame_hashes(batch: Path) -> list[str]:
    manifest = json.loads((batch / "manifest.json").read_text(encoding="utf-8"))
    return [frame["sha256"] for frame in manifest["frames"]]


def test_image_directory_is_bounded_private_and_path_free(
    tmp_path: Path,
    tool_lookup,
):
    project = _project(tmp_path)
    source = tmp_path / "PRIVATE_SOURCE_SENTINEL"
    source.mkdir()
    names = ["z-last.PNG", "a-first.jpg", "m-middle.jpeg", "b-two.png", "n-four.jpg"]
    originals: dict[Path, bytes] = {}
    for index, name in enumerate(names):
        path = source / name
        content = f"synthetic-image-{index}".encode()
        path.write_bytes(content)
        originals[path] = content

    result = intake.run_intake(
        str(source),
        room="PRIVATE_ROOM_SENTINEL",
        max_frames=3,
        project_root=project,
        runner=FakeMediaRunner(),
        which=tool_lookup,
        id_factory=lambda _bytes: "a" * 16,
    )

    batch = _batch(project, "a" * 16)
    manifest_path = batch / "manifest.json"
    manifest_text = manifest_path.read_text(encoding="utf-8")
    manifest = json.loads(manifest_text)
    assert result.frame_count == 3
    assert result.input_count == 5
    assert [frame["source_index"] for frame in manifest["frames"]] == [0, 2, 4]
    assert set(manifest) == {
        "schema",
        "batch_id",
        "room_id",
        "input_count",
        "frame_count",
        "frames",
        "model_called",
        "canonical_housefile_written",
    }
    assert manifest["room_id"] == "PRIVATE_ROOM_SENTINEL"
    assert "PRIVATE_SOURCE_SENTINEL" not in manifest_text
    assert not any(name in manifest_text for name in names)
    assert [path.name for path in sorted(batch.glob("*.jpg"))] == [
        "frame-000001.jpg",
        "frame-000002.jpg",
        "frame-000003.jpg",
    ]
    assert _mode(project / "data") == 0o700
    assert _mode(project / "data" / "capture") == 0o700
    assert _mode(batch) == 0o700
    assert _mode(manifest_path) == 0o600
    assert all(_mode(path) == 0o600 for path in batch.glob("*.jpg"))
    assert all(path.read_bytes() == content for path, content in originals.items())
    assert result.receipt()["model_called"] is False
    assert result.receipt()["canonical_housefile_written"] is False
    assert "room" not in result.receipt()


def test_video_sampling_is_deterministic_and_tool_invocation_is_constrained(
    tmp_path: Path,
    tool_lookup,
):
    project = _project(tmp_path)
    video = tmp_path / "synthetic-room.MP4"
    video.write_bytes(b"synthetic-video")
    runner = FakeMediaRunner(duration="4.0")

    intake.run_intake(
        str(video),
        room="room-01",
        max_frames=3,
        project_root=project,
        runner=runner,
        which=tool_lookup,
        id_factory=lambda _bytes: "b" * 16,
    )

    ffmpeg_calls = [call for call in runner.calls if Path(call[0][0]).name == "ffmpeg"]
    assert [args[args.index("-ss") + 1] for args, _kwargs in ffmpeg_calls] == [
        "0.666667",
        "2.000000",
        "3.333333",
    ]
    for args, kwargs in runner.calls:
        assert isinstance(args, list)
        assert "shell" not in kwargs
        assert kwargs["stdin"] is subprocess.DEVNULL
        assert kwargs["stderr"] is subprocess.DEVNULL
        assert kwargs["stdout"] in {subprocess.DEVNULL, subprocess.PIPE}
        assert kwargs["check"] is False
        assert kwargs["pass_fds"]
        assert kwargs["env"] == {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "LC_ALL": "C",
            "LANG": "C",
        }
        assert "-protocol_whitelist" in args
        assert args[args.index("-protocol_whitelist") + 1] == "file"
        assert "-enable_drefs" in args
        assert "-use_absolute_path" in args
        input_position = args.index("-i") if "-i" in args else len(args)
        input_args = args[:input_position]
        assert input_args[input_args.index("-f") + 1] == "mov"
    probe_calls = [call for call in runner.calls if Path(call[0][0]).name == "ffprobe"]
    assert len(probe_calls) == 1
    assert probe_calls[0][1]["stdout"] is subprocess.PIPE
    assert "-select_streams" in probe_calls[0][0]
    assert probe_calls[0][0][probe_calls[0][0].index("-select_streams") + 1] == "v:0"
    for args, _kwargs in ffmpeg_calls:
        assert _kwargs["stdout"] is subprocess.DEVNULL
        assert args[args.index("-map") + 1] == "0:v:0"
        assert all(flag in args for flag in ("-nostdin", "-map_metadata", "-map_chapters"))
        assert all(flag in args for flag in ("-an", "-sn", "-dn"))
        assert args[args.index("-map_metadata") + 1] == "-1"
        assert args[args.index("-map_chapters") + 1] == "-1"


def test_same_input_yields_same_ordered_frame_hashes(tmp_path: Path, tool_lookup):
    source = tmp_path / "images"
    source.mkdir()
    for index in range(6):
        (source / f"image-{index}.png").write_bytes(f"image-{index}".encode())

    projects = [_project(tmp_path, "first"), _project(tmp_path, "second")]
    batch_ids = ["c" * 16, "d" * 16]
    for project, batch_id in zip(projects, batch_ids, strict=True):
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=4,
            project_root=project,
            runner=FakeMediaRunner(),
            which=tool_lookup,
            id_factory=lambda _bytes, value=batch_id: value,
        )

    assert _frame_hashes(_batch(projects[0], batch_ids[0])) == _frame_hashes(
        _batch(projects[1], batch_ids[1])
    )


def test_cli_emits_exactly_one_sanitized_json_line(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    source = tmp_path / "PRIVATE_FILENAME_SENTINEL.png"
    source.write_bytes(b"synthetic")
    output = StringIO()

    exit_code = intake.main(
        ["--room", "PRIVATE_ROOM_SENTINEL", "--max-frames", "1", str(source)],
        output=output,
        project_root=project,
        runner=FakeMediaRunner(),
        which=tool_lookup,
        id_factory=lambda _bytes: "e" * 16,
    )

    lines = output.getvalue().splitlines()
    assert exit_code == intake.EXIT_OK
    assert len(lines) == 1
    assert "PRIVATE_FILENAME_SENTINEL" not in lines[0]
    assert "PRIVATE_ROOM_SENTINEL" not in lines[0]
    assert "PRIVATE_TOOL_OUTPUT_SENTINEL" not in lines[0]
    assert set(json.loads(lines[0])) == {
        "schema",
        "status",
        "batch_id",
        "input_count",
        "frame_count",
        "output_bytes",
        "manifest_sha256",
        "model_called",
        "canonical_housefile_written",
    }


def test_tool_failure_is_sanitized_and_leaves_no_batch(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    source = tmp_path / "PRIVATE_FILENAME_SENTINEL.png"
    source.write_bytes(b"synthetic")
    output = StringIO()

    exit_code = intake.main(
        ["--room", "PRIVATE_ROOM_SENTINEL", str(source)],
        output=output,
        project_root=project,
        runner=FakeMediaRunner(fail_probe=True),
        which=tool_lookup,
    )

    receipt = output.getvalue()
    assert exit_code == intake.EXIT_PROCESSING
    assert len(receipt.splitlines()) == 1
    assert json.loads(receipt)["failure"] == "media_processing_failed"
    assert "PRIVATE_FILENAME_SENTINEL" not in receipt
    assert "PRIVATE_ROOM_SENTINEL" not in receipt
    assert "PRIVATE_TOOL_OUTPUT_SENTINEL" not in receipt
    assert not list((project / "data" / "capture").glob("batch-*"))


def test_invalid_normalized_output_is_refused_and_cleaned(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=1,
            project_root=project,
            runner=FakeMediaRunner(invalid_output=True),
            which=tool_lookup,
            id_factory=lambda _bytes: "3" * 16,
        )
    assert caught.value.failure == "normalized_frame_invalid"
    capture_root = project / "data" / "capture"
    assert not list(capture_root.glob(".staging-*"))
    assert not list(capture_root.glob("batch-*"))


def test_malformed_probe_and_timeout_are_sanitized(tmp_path: Path, tool_lookup):
    source = tmp_path / "PRIVATE_SOURCE_SENTINEL.png"
    source.write_bytes(b"synthetic")
    malformed_output = StringIO()
    malformed_code = intake.main(
        ["--room", "PRIVATE_ROOM_SENTINEL", str(source)],
        output=malformed_output,
        project_root=_project(tmp_path, "malformed-project"),
        runner=FakeMediaRunner(probe_stdout="{PRIVATE_PROBE_SENTINEL"),
        which=tool_lookup,
    )
    assert malformed_code == intake.EXIT_PROCESSING
    assert json.loads(malformed_output.getvalue())["failure"] == "media_probe_invalid"

    def timeout_runner(args: list[str], **_kwargs: object):
        raise subprocess.TimeoutExpired(
            args,
            timeout=1,
            stderr="PRIVATE_TIMEOUT_SENTINEL",
        )

    timeout_output = StringIO()
    timeout_code = intake.main(
        ["--room", "PRIVATE_ROOM_SENTINEL", str(source)],
        output=timeout_output,
        project_root=_project(tmp_path, "timeout-project"),
        runner=timeout_runner,
        which=tool_lookup,
    )
    assert timeout_code == intake.EXIT_PROCESSING
    assert json.loads(timeout_output.getvalue())["failure"] == "media_processing_failed"
    combined = malformed_output.getvalue() + timeout_output.getvalue()
    for private_value in (
        "PRIVATE_SOURCE_SENTINEL",
        "PRIVATE_ROOM_SENTINEL",
        "PRIVATE_PROBE_SENTINEL",
        "PRIVATE_TIMEOUT_SENTINEL",
    ):
        assert private_value not in combined


def test_missing_tools_fails_before_any_subprocess(tmp_path: Path):
    project = _project(tmp_path)
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")

    def unexpected_runner(*_args: object, **_kwargs: object):
        raise AssertionError("runner must not be called")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=1,
            project_root=project,
            runner=unexpected_runner,
            which=lambda _name: None,
        )
    assert caught.value.failure == "media_tool_unavailable"
    assert caught.value.exit_code == intake.EXIT_DEPENDENCY


def test_source_count_and_byte_limits_fail_before_tool_use(tmp_path: Path, monkeypatch):
    project = _project(tmp_path)
    direct = tmp_path / "direct.png"
    direct.write_bytes(b"1234")
    monkeypatch.setattr(intake, "MAX_SOURCE_BYTES", 3)
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(direct), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "source_size_refused"

    source = tmp_path / "many"
    source.mkdir()
    for index in range(3):
        (source / f"image-{index}.png").write_bytes(b"12")
    monkeypatch.setattr(intake, "MAX_SOURCE_BYTES", 10)
    monkeypatch.setattr(intake, "MAX_INPUT_FILES", 2)
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(source), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "input_count_refused"

    monkeypatch.setattr(intake, "MAX_INPUT_FILES", 10)
    monkeypatch.setattr(intake, "MAX_TOTAL_INPUT_BYTES", 5)
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(source), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "total_input_size_refused"


def test_invalid_cli_value_is_not_reflected(tmp_path: Path):
    output = StringIO()
    exit_code = intake.main(
        [
            "--room",
            "PRIVATE_ROOM_SENTINEL",
            "--max-frames",
            "PRIVATE_LIMIT_SENTINEL",
            "PRIVATE_SOURCE_SENTINEL",
        ],
        output=output,
        project_root=_project(tmp_path),
    )
    receipt = output.getvalue()
    assert exit_code == intake.EXIT_CONFIG
    assert json.loads(receipt)["failure"] == "invalid_invocation"
    assert "PRIVATE_ROOM_SENTINEL" not in receipt
    assert "PRIVATE_LIMIT_SENTINEL" not in receipt
    assert "PRIVATE_SOURCE_SENTINEL" not in receipt


@pytest.mark.parametrize(
    "source",
    [
        "-",
        "//host/share/image.png",
        "http://invalid.test/image.png",
        "https://invalid.test/image.png",
        "rtsp://invalid.test/camera",
        "file:/tmp/image.png",
        "data:image/png;base64,AAAA",
        "concat:image-a.png|image-b.png",
        "pipe:0",
        "tcp://invalid.test:1234",
        "udp://invalid.test:1234",
    ],
)
def test_protocol_and_stream_inputs_are_rejected(source: str, tmp_path: Path):
    project = _project(tmp_path)
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(source, room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "nonlocal_input_refused"
    assert caught.value.exit_code == intake.EXIT_INPUT


def test_symlinked_and_special_inputs_are_rejected(tmp_path: Path):
    project = _project(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    image = real / "image.png"
    image.write_bytes(b"synthetic")
    leaf_link = tmp_path / "leaf.png"
    leaf_link.symlink_to(image)
    ancestor_link = tmp_path / "ancestor"
    ancestor_link.symlink_to(real, target_is_directory=True)
    fifo = tmp_path / "capture.png"
    os.mkfifo(fifo)

    for source in (leaf_link, ancestor_link / "image.png"):
        with pytest.raises(intake.IntakeFailure) as caught:
            intake.run_intake(str(source), room="room-01", max_frames=1, project_root=project)
        assert caught.value.failure == "symlink_input_refused"
        assert caught.value.exit_code == intake.EXIT_PRIVACY

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(fifo), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "special_input_refused"


@pytest.mark.parametrize("kind", ["empty", "nested", "mixed"])
def test_invalid_directories_are_refused(kind: str, tmp_path: Path):
    project = _project(tmp_path)
    source = tmp_path / kind
    source.mkdir()
    if kind == "nested":
        (source / "child").mkdir()
    if kind == "mixed":
        (source / "image.png").write_bytes(b"synthetic")
        (source / "notes.txt").write_text("not media", encoding="utf-8")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(source), room="room-01", max_frames=1, project_root=project)
    assert caught.value.exit_code == intake.EXIT_INPUT
    assert caught.value.failure in {
        "empty_input_batch",
        "nested_input_refused",
        "mixed_or_unsupported_batch",
    }


def test_probe_rejects_extension_spoofing_and_unbounded_media(tmp_path: Path, tool_lookup):
    image = tmp_path / "spoofed.jpg"
    image.write_bytes(b"synthetic")
    cases = [
        (
            {
                "streams": [
                    {"codec_type": "video", "codec_name": "png", "width": 640, "height": 360}
                ],
                "format": {"format_name": "image2"},
            },
            "media_type_mismatch",
        ),
        (
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "mjpeg",
                        "width": 640,
                        "height": 360,
                    }
                ],
                "format": {"format_name": "mov", "duration": "4.0"},
            },
            "media_type_mismatch",
        ),
        (
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "mjpeg",
                        "width": intake.MAX_SOURCE_EDGE + 1,
                        "height": 1,
                    }
                ],
                "format": {"format_name": "image2"},
            },
            "source_dimensions_refused",
        ),
        ({"streams": [], "format": {}}, "video_stream_missing"),
    ]
    for index, (payload, failure) in enumerate(cases):
        project = _project(tmp_path, f"project-{index}")
        with pytest.raises(intake.IntakeFailure) as caught:
            intake.run_intake(
                str(image),
                room="room-01",
                max_frames=1,
                project_root=project,
                runner=FakeMediaRunner(probe_payload=payload),
                which=tool_lookup,
            )
        assert caught.value.failure == failure


@pytest.mark.parametrize("duration", ["0", "NaN", "601"])
def test_invalid_video_duration_is_refused(duration: str, tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    video = tmp_path / "video.mov"
    video.write_bytes(b"synthetic")
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(video),
            room="room-01",
            max_frames=1,
            project_root=project,
            runner=FakeMediaRunner(duration=duration),
            which=tool_lookup,
        )
    assert caught.value.failure == "video_duration_refused"


def test_mid_batch_failure_removes_only_staging_output(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    source = tmp_path / "images"
    source.mkdir()
    for index in range(3):
        (source / f"image-{index}.png").write_bytes(f"synthetic-{index}".encode())
    unrelated = project / "data" / "keep.txt"
    unrelated.parent.mkdir()
    unrelated.write_text("keep", encoding="utf-8")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=3,
            project_root=project,
            runner=FakeMediaRunner(fail_extract_at=2),
            which=tool_lookup,
            id_factory=lambda _bytes: "f" * 16,
        )
    capture_root = project / "data" / "capture"
    assert caught.value.failure == "media_processing_failed"
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not list(capture_root.glob(".staging-*"))
    assert not list(capture_root.glob("batch-*"))


def test_room_frame_limit_and_output_boundary_fail_closed(tmp_path: Path):
    project = _project(tmp_path)
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")

    for room in ("../room", "room/name", " room", "room\nname"):
        with pytest.raises(intake.IntakeFailure) as caught:
            intake.run_intake(str(source), room=room, max_frames=1, project_root=project)
        assert caught.value.failure == "invalid_room_label"
        assert caught.value.exit_code == intake.EXIT_CONFIG
    for limit in (0, intake.MAX_FRAMES + 1):
        with pytest.raises(intake.IntakeFailure) as caught:
            intake.run_intake(str(source), room="room-01", max_frames=limit, project_root=project)
        assert caught.value.failure == "invalid_frame_limit"

    outside = tmp_path / "outside"
    outside.mkdir()
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=1,
            project_root=project,
            capture_root=outside,
        )
    assert caught.value.failure == "unsafe_output_boundary"
    assert caught.value.exit_code == intake.EXIT_PRIVACY


def test_symlinked_capture_root_is_refused(tmp_path: Path):
    project = _project(tmp_path)
    data = project / "data"
    data.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (data / "capture").symlink_to(outside, target_is_directory=True)
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(source), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "unsafe_output_boundary"
    assert caught.value.exit_code == intake.EXIT_PRIVACY


def test_capture_output_cannot_be_reused_as_input(tmp_path: Path):
    project = _project(tmp_path)
    capture = project / "data" / "capture"
    capture.mkdir(parents=True)
    frame = capture / "frame-000001.jpg"
    frame.write_bytes(b"private-derived-frame")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(str(frame), room="room-01", max_frames=1, project_root=project)
    assert caught.value.failure == "capture_output_as_input_refused"
    assert caught.value.exit_code == intake.EXIT_PRIVACY


def test_repo_source_is_refused_except_for_private_raw_workspace(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    public_candidate = project / "real-room.png"
    public_candidate.write_bytes(b"private-room-image")

    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(public_candidate),
            room="room-01",
            max_frames=1,
            project_root=project,
        )
    assert caught.value.failure == "repository_input_refused"
    assert caught.value.exit_code == intake.EXIT_PRIVACY

    private_raw = project / "media" / "raw"
    private_raw.mkdir(parents=True)
    private_source = private_raw / "room.png"
    private_source.write_bytes(b"private-room-image")
    result = intake.run_intake(
        str(private_source),
        room="room-01",
        max_frames=1,
        project_root=project,
        runner=FakeMediaRunner(),
        which=tool_lookup,
        id_factory=lambda _bytes: "4" * 16,
    )
    assert result.frame_count == 1
    assert _batch(project, "4" * 16).is_dir()


def test_parent_fsync_failure_rolls_back_finalized_batch(
    tmp_path: Path,
    tool_lookup,
    monkeypatch,
):
    project = _project(tmp_path)
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")
    capture_root = project / "data" / "capture"
    real_fsync_directory = intake._fsync_directory

    def fail_capture_root(path: Path) -> None:
        if path == capture_root:
            raise OSError("PRIVATE_FSYNC_SENTINEL")
        real_fsync_directory(path)

    monkeypatch.setattr(intake, "_fsync_directory", fail_capture_root)
    with pytest.raises(intake.IntakeFailure) as caught:
        intake.run_intake(
            str(source),
            room="room-01",
            max_frames=1,
            project_root=project,
            runner=FakeMediaRunner(),
            which=tool_lookup,
            id_factory=lambda _bytes: "5" * 16,
        )
    assert caught.value.failure == "capture_finalize_failed"
    assert not list(capture_root.glob(".staging-*"))
    assert not list(capture_root.glob("batch-*"))


def test_capture_never_changes_canonical_housefile(tmp_path: Path, tool_lookup):
    project = _project(tmp_path)
    data = project / "data"
    data.mkdir()
    canonical = data / "housefile.json"
    canonical.write_bytes(b'{"synthetic":"unchanged"}\n')
    before = canonical.read_bytes()
    source = tmp_path / "image.png"
    source.write_bytes(b"synthetic")

    intake.run_intake(
        str(source),
        room="room-01",
        max_frames=1,
        project_root=project,
        runner=FakeMediaRunner(),
        which=tool_lookup,
        id_factory=lambda _bytes: "1" * 16,
    )

    assert canonical.read_bytes() == before
    assert "housefile" not in intake.__dict__


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="optional local FFmpeg smoke proof",
)
@pytest.mark.parametrize(
    ("suffix", "batch_id"),
    [(".jpg", "6" * 16), (".png", "7" * 16)],
)
def test_real_ffmpeg_normalizes_synthetic_stills(
    suffix: str,
    batch_id: str,
    tmp_path: Path,
):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None and ffprobe is not None
    source = tmp_path / f"synthetic{suffix}"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=blue:size=320x180",
            "-frames:v",
            "1",
            "-metadata",
            "comment=PRIVATE_STILL_METADATA_SENTINEL",
            str(source),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=30,
    )
    project = _project(tmp_path)

    result = intake.run_intake(
        str(source),
        room="synthetic-room",
        max_frames=1,
        project_root=project,
        id_factory=lambda _bytes: batch_id,
    )

    frame = _batch(project, batch_id) / "frame-000001.jpg"
    assert result.frame_count == 1
    assert frame.is_file()
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_format", "-show_streams", str(frame)],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        text=True,
        timeout=15,
    )
    assert "PRIVATE_STILL_METADATA_SENTINEL" not in probe.stdout
    assert _mode(frame) == 0o600


@pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="optional local FFmpeg smoke proof",
)
def test_real_ffmpeg_normalizes_synthetic_video_without_metadata(tmp_path: Path):
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    assert ffmpeg is not None and ffprobe is not None
    source = tmp_path / "synthetic.mp4"
    subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=320x180:rate=2",
            "-t",
            "2",
            "-c:v",
            "mpeg4",
            "-metadata",
            "comment=PRIVATE_METADATA_SENTINEL",
            str(source),
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=30,
    )
    project = _project(tmp_path)

    result = intake.run_intake(
        str(source),
        room="synthetic-room",
        max_frames=3,
        project_root=project,
        id_factory=lambda _bytes: "2" * 16,
    )

    batch = _batch(project, "2" * 16)
    frames = sorted(batch.glob("*.jpg"))
    assert result.frame_count == 3
    assert len(frames) == 3
    for frame in frames:
        probe = subprocess.run(
            [ffprobe, "-v", "error", "-show_format", "-show_streams", str(frame)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=True,
            text=True,
            timeout=15,
        )
        assert "PRIVATE_METADATA_SENTINEL" not in probe.stdout
        assert _mode(frame) == 0o600
