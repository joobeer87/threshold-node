"""THS-0020 — local-only, privacy-first room capture intake.

This module normalizes one local room batch into bounded JPEG frames under the
ignored ``data/capture`` workspace. It never calls a model, opens a network
resource, or writes the canonical housefile.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import subprocess
import sys
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Literal, TextIO


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CAPTURE_ROOT = PROJECT_ROOT / "data" / "capture"
PROCESS_FD_ROOT = Path("/proc/self/fd")

IMAGE_SUFFIXES = frozenset({".jpg", ".jpeg", ".png"})
VIDEO_SUFFIXES = frozenset({".mp4", ".m4v", ".mov"})
EXPECTED_IMAGE_CODECS = {
    ".jpg": frozenset({"mjpeg"}),
    ".jpeg": frozenset({"mjpeg"}),
    ".png": frozenset({"png"}),
}
EXPECTED_IMAGE_FORMATS = {
    ".jpg": frozenset({"jpeg_pipe"}),
    ".jpeg": frozenset({"jpeg_pipe"}),
    ".png": frozenset({"png_pipe"}),
}
INPUT_DEMUXERS = {
    ".jpg": "jpeg_pipe",
    ".jpeg": "jpeg_pipe",
    ".png": "png_pipe",
    ".mp4": "mov",
    ".m4v": "mov",
    ".mov": "mov",
}

MAX_FRAMES = 12
MAX_INPUT_FILES = 64
MAX_SOURCE_BYTES = 1024 * 1024 * 1024
MAX_TOTAL_INPUT_BYTES = 2 * 1024 * 1024 * 1024
MAX_VIDEO_SECONDS = Decimal("600")
MAX_SOURCE_EDGE = 12_000
MAX_SOURCE_PIXELS = 50_000_000
MAX_NORMALIZED_FRAME_BYTES = 20 * 1024 * 1024
MAX_PROBE_OUTPUT_BYTES = 256 * 1024
PROBE_TIMEOUT_SECONDS = 15
EXTRACT_TIMEOUT_SECONDS = 45
NORMALIZED_MAX_EDGE = 1280
JPEG_START_OF_FRAME_MARKERS = frozenset(
    {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
)

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_DEPENDENCY = 3
EXIT_INPUT = 4
EXIT_PROCESSING = 5
EXIT_PRIVACY = 6

RECEIPT_SCHEMA = "ths/capture-receipt/0.1"
MANIFEST_SCHEMA = "ths/capture-manifest/0.1"
_PROTOCOL_INPUT = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*:")

Runner = Callable[..., subprocess.CompletedProcess[str]]
Which = Callable[[str], str | None]
IdFactory = Callable[[int], str]


class IntakeFailure(Exception):
    """Bounded internal failure that is safe to project as a fixed receipt."""

    def __init__(self, failure: str, step: str, exit_code: int) -> None:
        super().__init__(failure)
        self.failure = failure
        self.step = step
        self.exit_code = exit_code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        raise IntakeFailure("invalid_invocation", "configuration", EXIT_CONFIG)


@dataclass(frozen=True)
class SourceFile:
    path: Path = field(repr=False)
    kind: Literal["image", "video"]
    suffix: str
    index: int
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class ProbeResult:
    width: int
    height: int
    codec: str
    duration: Decimal | None
    frame_interval: Decimal | None


@dataclass(frozen=True)
class FrameCandidate:
    source: SourceFile
    timestamp: Decimal | None = None


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: str
    ffprobe: str


@dataclass(frozen=True)
class CaptureResult:
    batch_id: str
    input_count: int
    frame_count: int
    output_bytes: int
    manifest_sha256: str

    def receipt(self) -> dict[str, object]:
        return {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "batch_id": self.batch_id,
            "input_count": self.input_count,
            "frame_count": self.frame_count,
            "output_bytes": self.output_bytes,
            "manifest_sha256": self.manifest_sha256,
            "model_called": False,
            "canonical_housefile_written": False,
        }


def _emit(output: TextIO, payload: dict[str, object]) -> None:
    output.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")


def _failure_receipt(error: IntakeFailure) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "failed",
        "step": error.step,
        "failure": error.failure,
        "exit_code": error.exit_code,
        "model_called": False,
        "canonical_housefile_written": False,
    }


def _normalize_room(room: str) -> str:
    if (
        not isinstance(room, str)
        or room != room.strip()
        or not 1 <= len(room) <= 80
        or room in {".", ".."}
        or any(character in room for character in ("/", "\\"))
        or any(not character.isprintable() for character in room)
    ):
        raise IntakeFailure("invalid_room_label", "configuration", EXIT_CONFIG)
    return room


def _validate_max_frames(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= MAX_FRAMES:
        raise IntakeFailure("invalid_frame_limit", "configuration", EXIT_CONFIG)
    return value


def _looks_like_protocol(value: str) -> bool:
    stripped = value.strip()
    return (
        not stripped
        or stripped == "-"
        or stripped.startswith(("//", "\\\\"))
        or _PROTOCOL_INPUT.match(stripped) is not None
    )


def _reject_symlink_components(path: Path, *, failure: str) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise IntakeFailure(failure, "privacy_boundary", EXIT_PRIVACY) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise IntakeFailure(failure, "privacy_boundary", EXIT_PRIVACY)


def _source_file(path: Path, *, index: int, kind: Literal["image", "video"]) -> SourceFile:
    _reject_symlink_components(path, failure="symlink_input_refused")
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise IntakeFailure("input_unavailable", "input_validation", EXIT_INPUT) from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise IntakeFailure("special_input_refused", "input_validation", EXIT_INPUT)
    if metadata.st_size <= 0 or metadata.st_size > MAX_SOURCE_BYTES:
        raise IntakeFailure("source_size_refused", "input_validation", EXIT_INPUT)
    return SourceFile(
        path=path,
        kind=kind,
        suffix=path.suffix.lower(),
        index=index,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        size=metadata.st_size,
        modified_ns=metadata.st_mtime_ns,
    )


def discover_sources(source_value: str, *, capture_root: Path) -> list[SourceFile]:
    """Resolve one local image/video or one flat still-image directory."""

    if _looks_like_protocol(source_value):
        raise IntakeFailure("nonlocal_input_refused", "input_validation", EXIT_INPUT)
    source = Path(source_value).absolute()
    _reject_symlink_components(source, failure="symlink_input_refused")

    capture_absolute = capture_root.absolute()
    if source == capture_absolute or capture_absolute in source.parents:
        raise IntakeFailure("capture_output_as_input_refused", "privacy_boundary", EXIT_PRIVACY)
    project_root = capture_absolute.parents[1]
    private_media_root = project_root / "media" / "raw"
    inside_project = source == project_root or project_root in source.parents
    inside_private_media = source == private_media_root or private_media_root in source.parents
    if inside_project and not inside_private_media:
        raise IntakeFailure("repository_input_refused", "privacy_boundary", EXIT_PRIVACY)

    try:
        metadata = source.lstat()
    except OSError as exc:
        raise IntakeFailure("input_unavailable", "input_validation", EXIT_INPUT) from exc

    if stat.S_ISREG(metadata.st_mode):
        suffix = source.suffix.lower()
        if suffix in IMAGE_SUFFIXES:
            return [_source_file(source, index=0, kind="image")]
        if suffix in VIDEO_SUFFIXES:
            return [_source_file(source, index=0, kind="video")]
        raise IntakeFailure("unsupported_media_type", "input_validation", EXIT_INPUT)

    if not stat.S_ISDIR(metadata.st_mode):
        raise IntakeFailure("special_input_refused", "input_validation", EXIT_INPUT)

    try:
        entries = sorted(source.iterdir(), key=lambda item: (item.name.casefold(), item.name))
    except OSError as exc:
        raise IntakeFailure("input_unavailable", "input_validation", EXIT_INPUT) from exc
    if not entries:
        raise IntakeFailure("empty_input_batch", "input_validation", EXIT_INPUT)
    if len(entries) > MAX_INPUT_FILES:
        raise IntakeFailure("input_count_refused", "input_validation", EXIT_INPUT)

    sources: list[SourceFile] = []
    total_bytes = 0
    for index, entry in enumerate(entries):
        _reject_symlink_components(entry, failure="symlink_input_refused")
        try:
            entry_metadata = entry.lstat()
        except OSError as exc:
            raise IntakeFailure("input_unavailable", "input_validation", EXIT_INPUT) from exc
        if stat.S_ISDIR(entry_metadata.st_mode):
            raise IntakeFailure("nested_input_refused", "input_validation", EXIT_INPUT)
        suffix = entry.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            raise IntakeFailure("mixed_or_unsupported_batch", "input_validation", EXIT_INPUT)
        item = _source_file(entry, index=index, kind="image")
        total_bytes += item.size
        if total_bytes > MAX_TOTAL_INPUT_BYTES:
            raise IntakeFailure("total_input_size_refused", "input_validation", EXIT_INPUT)
        sources.append(item)
    return sources


def _tool_environment() -> dict[str, str]:
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "LANG": "C",
    }


def discover_tools(which: Which = shutil.which) -> MediaTools:
    if os.name != "posix" or not PROCESS_FD_ROOT.is_dir():
        raise IntakeFailure(
            "secure_fd_transport_unavailable",
            "dependency_check",
            EXIT_DEPENDENCY,
        )
    paths: dict[str, str] = {}
    for name in ("ffmpeg", "ffprobe"):
        candidate = which(name)
        if candidate is None:
            raise IntakeFailure("media_tool_unavailable", "dependency_check", EXIT_DEPENDENCY)
        resolved = Path(candidate).resolve()
        try:
            metadata = resolved.stat()
        except OSError as exc:
            raise IntakeFailure("media_tool_unavailable", "dependency_check", EXIT_DEPENDENCY) from exc
        if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
            raise IntakeFailure("media_tool_unavailable", "dependency_check", EXIT_DEPENDENCY)
        paths[name] = str(resolved)
    return MediaTools(ffmpeg=paths["ffmpeg"], ffprobe=paths["ffprobe"])


@contextmanager
def _open_verified(source: SourceFile) -> Iterator[int]:
    _reject_symlink_components(source.path, failure="symlink_input_refused")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(source.path, flags)
    except OSError as exc:
        raise IntakeFailure("input_unavailable", "input_validation", EXIT_INPUT) from exc
    try:
        metadata = os.fstat(descriptor)
        identity = (
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_size,
            metadata.st_mtime_ns,
        )
        expected = (source.device, source.inode, source.size, source.modified_ns)
        if not stat.S_ISREG(metadata.st_mode) or identity != expected:
            raise IntakeFailure("input_changed", "input_validation", EXIT_INPUT)
        yield descriptor
    finally:
        os.close(descriptor)


def _run_tool(
    runner: Runner,
    args: list[str],
    *,
    descriptor: int,
    timeout: int,
    capture_stdout: bool = False,
) -> subprocess.CompletedProcess[str]:
    try:
        result = runner(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
            timeout=timeout,
            env=_tool_environment(),
            pass_fds=(descriptor,),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise IntakeFailure("media_processing_failed", "media_processing", EXIT_PROCESSING) from exc
    if result.returncode != 0:
        raise IntakeFailure("media_processing_failed", "media_processing", EXIT_PROCESSING)
    return result


def _finite_decimal(value: object) -> Decimal | None:
    if value is None or value == "N/A":
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _finite_frame_interval(value: object) -> Decimal | None:
    text = str(value)
    if "/" not in text:
        rate = _finite_decimal(text)
    else:
        numerator_text, denominator_text = text.split("/", 1)
        numerator = _finite_decimal(numerator_text)
        denominator = _finite_decimal(denominator_text)
        if numerator is None or denominator is None or denominator == 0:
            return None
        rate = numerator / denominator
    if rate is None or rate <= 0 or rate > 1000:
        return None
    return Decimal(1) / rate


def probe_source(source: SourceFile, tools: MediaTools, runner: Runner) -> ProbeResult:
    with _open_verified(source) as descriptor:
        fd_path = str(PROCESS_FD_ROOT / str(descriptor))
        args = [
            tools.ffprobe,
            "-v",
            "error",
            "-protocol_whitelist",
            "file",
        ]
        if source.kind == "video":
            args.extend(["-enable_drefs", "0", "-use_absolute_path", "0"])
        args.extend(
            [
                "-f",
                INPUT_DEMUXERS[source.suffix],
                "-select_streams",
                "v:0",
                "-show_entries",
                (
                    "format=format_name,duration:"
                    "stream=codec_type,codec_name,width,height,duration,avg_frame_rate"
                ),
                "-of",
                "json",
                fd_path,
            ]
        )
        result = _run_tool(
            runner,
            args,
            descriptor=descriptor,
            timeout=PROBE_TIMEOUT_SECONDS,
            capture_stdout=True,
        )
    if not isinstance(result.stdout, str) or len(result.stdout.encode("utf-8")) > MAX_PROBE_OUTPUT_BYTES:
        raise IntakeFailure("media_probe_invalid", "media_probe", EXIT_PROCESSING)
    try:
        payload = json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError) as exc:
        raise IntakeFailure("media_probe_invalid", "media_probe", EXIT_PROCESSING) from exc
    if not isinstance(payload, dict):
        raise IntakeFailure("media_probe_invalid", "media_probe", EXIT_PROCESSING)
    streams = payload.get("streams")
    if not isinstance(streams, list):
        raise IntakeFailure("media_probe_invalid", "media_probe", EXIT_PROCESSING)
    video_stream = next(
        (stream for stream in streams if isinstance(stream, dict) and stream.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        raise IntakeFailure("video_stream_missing", "input_validation", EXIT_INPUT)
    try:
        width = int(video_stream.get("width", 0))
        height = int(video_stream.get("height", 0))
    except (TypeError, ValueError) as exc:
        raise IntakeFailure("media_probe_invalid", "media_probe", EXIT_PROCESSING) from exc
    if (
        width <= 0
        or height <= 0
        or width > MAX_SOURCE_EDGE
        or height > MAX_SOURCE_EDGE
        or width * height > MAX_SOURCE_PIXELS
    ):
        raise IntakeFailure("source_dimensions_refused", "input_validation", EXIT_INPUT)
    codec = str(video_stream.get("codec_name", ""))
    format_data = payload.get("format") if isinstance(payload.get("format"), dict) else {}
    format_names = set(str(format_data.get("format_name", "")).split(","))

    if source.kind == "image":
        if (
            codec not in EXPECTED_IMAGE_CODECS[source.suffix]
            or not format_names.intersection(EXPECTED_IMAGE_FORMATS[source.suffix])
        ):
            raise IntakeFailure("media_type_mismatch", "input_validation", EXIT_INPUT)
        return ProbeResult(
            width=width,
            height=height,
            codec=codec,
            duration=None,
            frame_interval=None,
        )

    if not format_names.intersection({"mov", "mp4", "m4v", "3gp", "3g2", "mj2"}):
        raise IntakeFailure("media_type_mismatch", "input_validation", EXIT_INPUT)
    duration = _finite_decimal(format_data.get("duration")) or _finite_decimal(
        video_stream.get("duration")
    )
    if duration is None or duration <= 0 or duration > MAX_VIDEO_SECONDS:
        raise IntakeFailure("video_duration_refused", "input_validation", EXIT_INPUT)
    frame_interval = _finite_frame_interval(video_stream.get("avg_frame_rate"))
    if frame_interval is None:
        raise IntakeFailure("video_rate_refused", "input_validation", EXIT_INPUT)
    return ProbeResult(
        width=width,
        height=height,
        codec=codec,
        duration=duration,
        frame_interval=frame_interval,
    )


def _center_select(values: Sequence[SourceFile], limit: int) -> list[SourceFile]:
    if len(values) <= limit:
        return list(values)
    return [values[((2 * index + 1) * len(values)) // (2 * limit)] for index in range(limit)]


def build_candidates(
    sources: Sequence[SourceFile],
    probes: Sequence[ProbeResult],
    *,
    max_frames: int,
) -> list[FrameCandidate]:
    if len(sources) != len(probes) or not sources:
        raise IntakeFailure("capture_plan_invalid", "capture_planning", EXIT_PROCESSING)
    if sources[0].kind == "image":
        return [FrameCandidate(source=source) for source in _center_select(sources, max_frames)]

    duration = probes[0].duration
    frame_interval = probes[0].frame_interval
    if len(sources) != 1 or duration is None or frame_interval is None:
        raise IntakeFailure("capture_plan_invalid", "capture_planning", EXIT_PROCESSING)
    denominator = Decimal(2 * max_frames)
    quantum = Decimal("0.000001")
    latest_timestamp = max(Decimal(0), duration - frame_interval)
    return [
        FrameCandidate(
            source=sources[0],
            timestamp=min(
                latest_timestamp,
                duration * Decimal(2 * index + 1) / denominator,
            ).quantize(quantum, rounding=ROUND_HALF_UP),
        )
        for index in range(max_frames)
    ]


def _ensure_private_directory(path: Path) -> None:
    _reject_symlink_components(path, failure="unsafe_output_boundary")
    try:
        path.mkdir(mode=0o700, parents=False, exist_ok=True)
        metadata = path.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise OSError("not a directory")
        if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
            raise OSError("unexpected owner")
        os.chmod(path, 0o700)
    except OSError as exc:
        raise IntakeFailure("unsafe_output_boundary", "privacy_boundary", EXIT_PRIVACY) from exc


def _prepare_capture_root(project_root: Path, capture_root: Path) -> Path:
    project = project_root.absolute()
    data_root = project / "data"
    capture = capture_root.absolute()
    if capture != data_root / "capture":
        raise IntakeFailure("unsafe_output_boundary", "privacy_boundary", EXIT_PRIVACY)
    _reject_symlink_components(project, failure="unsafe_output_boundary")
    _ensure_private_directory(data_root)
    _ensure_private_directory(capture)
    return capture


def _new_batch_paths(capture_root: Path, id_factory: IdFactory) -> tuple[str, Path, Path]:
    for _ in range(5):
        batch_id = id_factory(8)
        if not re.fullmatch(r"[0-9a-f]{16}", batch_id):
            raise IntakeFailure("batch_id_invalid", "privacy_boundary", EXIT_PRIVACY)
        staging = capture_root / f".staging-{batch_id}"
        final = capture_root / f"batch-{batch_id}"
        if staging.exists() or final.exists() or staging.is_symlink() or final.is_symlink():
            continue
        try:
            staging.mkdir(mode=0o700)
            os.chmod(staging, 0o700)
        except OSError as exc:
            raise IntakeFailure("capture_workspace_unavailable", "privacy_boundary", EXIT_PRIVACY) from exc
        return batch_id, staging, final
    raise IntakeFailure("batch_id_unavailable", "privacy_boundary", EXIT_PRIVACY)


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("write made no progress")
        remaining = remaining[written:]


def _write_private_file(path: Path, data: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        _write_all(descriptor, data)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(128 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _jpeg_dimensions(path: Path, size: int) -> tuple[int, int]:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size != size or size < 8:
            raise OSError("invalid JPEG file")
        if os.pread(descriptor, 2, 0) != b"\xff\xd8":
            raise OSError("missing JPEG start marker")
        if os.pread(descriptor, 2, size - 2) != b"\xff\xd9":
            raise OSError("missing JPEG end marker")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            stream.seek(2)
            while stream.tell() < size - 2:
                prefix = stream.read(1)
                while prefix and prefix != b"\xff":
                    prefix = stream.read(1)
                if not prefix:
                    break
                marker_byte = stream.read(1)
                while marker_byte == b"\xff":
                    marker_byte = stream.read(1)
                if not marker_byte:
                    break
                marker = marker_byte[0]
                if marker in {0x00, 0x01} or 0xD0 <= marker <= 0xD9:
                    continue
                length_bytes = stream.read(2)
                if len(length_bytes) != 2:
                    break
                segment_length = int.from_bytes(length_bytes, "big")
                if segment_length < 2:
                    break
                if marker in JPEG_START_OF_FRAME_MARKERS:
                    dimensions = stream.read(5)
                    if len(dimensions) != 5:
                        break
                    height = int.from_bytes(dimensions[1:3], "big")
                    width = int.from_bytes(dimensions[3:5], "big")
                    return width, height
                stream.seek(segment_length - 2, os.SEEK_CUR)
    finally:
        os.close(descriptor)
    raise OSError("JPEG dimensions unavailable")


def _extract_frame(
    candidate: FrameCandidate,
    destination: Path,
    tools: MediaTools,
    runner: Runner,
) -> None:
    with _open_verified(candidate.source) as descriptor:
        fd_path = str(PROCESS_FD_ROOT / str(descriptor))
        args = [
            tools.ffmpeg,
            "-v",
            "error",
            "-nostdin",
            "-n",
            "-protocol_whitelist",
            "file",
        ]
        if candidate.source.kind == "video":
            args.extend(
                [
                    "-enable_drefs",
                    "0",
                    "-use_absolute_path",
                    "0",
                    "-ss",
                    format(candidate.timestamp, "f"),
                ]
            )
        args.extend(
            [
                "-f",
                INPUT_DEMUXERS[candidate.source.suffix],
                "-i",
                fd_path,
                "-map",
                "0:v:0",
                "-map_metadata",
                "-1",
                "-map_chapters",
                "-1",
                "-an",
                "-sn",
                "-dn",
                "-frames:v",
                "1",
                "-vf",
                (
                    f"scale={NORMALIZED_MAX_EDGE}:{NORMALIZED_MAX_EDGE}:"
                    "force_original_aspect_ratio=decrease"
                ),
                "-q:v",
                "3",
                "-f",
                "image2",
                str(destination),
            ]
        )
        _run_tool(
            runner,
            args,
            descriptor=descriptor,
            timeout=EXTRACT_TIMEOUT_SECONDS,
        )
    try:
        metadata = destination.lstat()
        if (
            not stat.S_ISREG(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or metadata.st_size <= 0
            or metadata.st_size > MAX_NORMALIZED_FRAME_BYTES
        ):
            raise OSError("invalid normalized frame")
        width, height = _jpeg_dimensions(destination, metadata.st_size)
        if (
            width <= 0
            or height <= 0
            or width > NORMALIZED_MAX_EDGE
            or height > NORMALIZED_MAX_EDGE
            or width * height > NORMALIZED_MAX_EDGE * NORMALIZED_MAX_EDGE
        ):
            raise OSError("invalid normalized dimensions")
        os.chmod(destination, 0o600)
        with destination.open("rb") as stream:
            os.fsync(stream.fileno())
    except OSError as exc:
        raise IntakeFailure("normalized_frame_invalid", "media_processing", EXIT_PROCESSING) from exc


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _remove_owned_directory(path: Path, capture_root: Path, *, prefix: str) -> bool:
    try:
        if path.parent != capture_root or not path.name.startswith(prefix):
            return False
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return True
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            return False
        shutil.rmtree(path)
        return True
    except OSError:
        return False


def _cleanup_staging(staging: Path, capture_root: Path) -> None:
    _remove_owned_directory(staging, capture_root, prefix=".staging-")


def run_intake(
    source_value: str,
    *,
    room: str,
    max_frames: int,
    project_root: Path = PROJECT_ROOT,
    capture_root: Path | None = None,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    id_factory: IdFactory = secrets.token_hex,
) -> CaptureResult:
    """Normalize one local room batch without printing private source context."""

    room_id = _normalize_room(room)
    frame_limit = _validate_max_frames(max_frames)
    effective_capture_root = capture_root or project_root / "data" / "capture"
    private_root = _prepare_capture_root(project_root, effective_capture_root)
    sources = discover_sources(source_value, capture_root=private_root)
    tools = discover_tools(which)
    probes = [probe_source(source, tools, runner) for source in sources]
    candidates = build_candidates(sources, probes, max_frames=frame_limit)

    batch_id, staging, final = _new_batch_paths(private_root, id_factory)
    try:
        frames: list[dict[str, object]] = []
        seen_hashes: set[str] = set()
        frame_bytes = 0
        for candidate in candidates:
            frame_number = len(frames) + 1
            frame_name = f"frame-{frame_number:06d}.jpg"
            destination = staging / frame_name
            _extract_frame(candidate, destination, tools, runner)
            frame_hash = _hash_file(destination)
            if frame_hash in seen_hashes:
                destination.unlink()
                continue
            seen_hashes.add(frame_hash)
            size = destination.stat().st_size
            frame_bytes += size
            frames.append(
                {
                    "id": f"frame-{frame_number:06d}",
                    "file": frame_name,
                    "sha256": frame_hash,
                    "bytes": size,
                    "source_kind": candidate.source.kind,
                    "source_index": candidate.source.index,
                }
            )
        if not frames:
            raise IntakeFailure("no_distinct_frames", "media_processing", EXIT_PROCESSING)

        manifest = {
            "schema": MANIFEST_SCHEMA,
            "batch_id": batch_id,
            "room_id": room_id,
            "input_count": len(sources),
            "frame_count": len(frames),
            "frames": frames,
            "model_called": False,
            "canonical_housefile_written": False,
        }
        manifest_bytes = (
            json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n"
        ).encode("utf-8")
        manifest_path = staging / "manifest.json"
        _write_private_file(manifest_path, manifest_bytes)
        manifest_hash = hashlib.sha256(manifest_bytes).hexdigest()
        _fsync_directory(staging)
        os.rename(staging, final)
        try:
            _fsync_directory(private_root)
        except OSError as exc:
            if _remove_owned_directory(final, private_root, prefix="batch-"):
                try:
                    _fsync_directory(private_root)
                except OSError:
                    pass
            raise IntakeFailure(
                "capture_finalize_failed",
                "media_processing",
                EXIT_PROCESSING,
            ) from exc
        return CaptureResult(
            batch_id=batch_id,
            input_count=len(sources),
            frame_count=len(frames),
            output_bytes=frame_bytes + len(manifest_bytes),
            manifest_sha256=manifest_hash,
        )
    except IntakeFailure:
        _cleanup_staging(staging, private_root)
        raise
    except OSError as exc:
        _cleanup_staging(staging, private_root)
        raise IntakeFailure("capture_finalize_failed", "media_processing", EXIT_PROCESSING) from exc


def _parser() -> SafeArgumentParser:
    parser = SafeArgumentParser(description="Normalize one local room capture batch.")
    parser.add_argument("source", metavar="SOURCE")
    parser.add_argument("--room", required=True, metavar="ROOM")
    parser.add_argument("--max-frames", type=int, default=8, metavar="N")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    output: TextIO = sys.stdout,
    project_root: Path = PROJECT_ROOT,
    capture_root: Path | None = None,
    runner: Runner = subprocess.run,
    which: Which = shutil.which,
    id_factory: IdFactory = secrets.token_hex,
) -> int:
    try:
        args = _parser().parse_args(list(sys.argv[1:] if argv is None else argv))
        result = run_intake(
            args.source,
            room=args.room,
            max_frames=args.max_frames,
            project_root=project_root,
            capture_root=capture_root,
            runner=runner,
            which=which,
            id_factory=id_factory,
        )
        _emit(output, result.receipt())
        return EXIT_OK
    except IntakeFailure as exc:
        _emit(output, _failure_receipt(exc))
        return exc.exit_code
    except Exception:  # noqa: BLE001 — CLI must never reflect private exception context
        error = IntakeFailure("internal_capture_failure", "media_processing", EXIT_PROCESSING)
        _emit(output, _failure_receipt(error))
        return error.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
