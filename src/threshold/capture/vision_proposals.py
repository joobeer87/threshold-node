"""THS-0021 private vision proposals and digest-bound owner decisions.

Model output is untrusted observation data. This module validates it into an
incomplete proposal, stores it beside its private capture batch, and records an
owner decision without importing or writing the canonical housefile.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import stat
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from typing import Literal, Protocol

from threshold.capture import vision_intake
from threshold.core.auth import is_valid_bearer_token


PROJECT_ROOT = Path(__file__).resolve().parents[3]
CAPTURE_ROOT = PROJECT_ROOT / "data" / "capture"

CAPTURE_MANIFEST_SCHEMA = "ths/capture-manifest/0.1"
OBSERVATION_SCHEMA = "ths/vision-observations/0.1"
PROPOSAL_SCHEMA = "ths/vision-proposal-envelope/0.1"
DECISION_SCHEMA = "ths/vision-decision/0.1"
RECEIPT_SCHEMA = "ths/vision-receipt/0.1"
PROMPT_VERSION = "ths-vision-prompt/0.1"
VALIDATOR_VERSION = "ths-vision-validator/0.1"

MAX_MANIFEST_BYTES = 128 * 1024
MAX_PROPOSAL_BYTES = 512 * 1024
MAX_PROVIDER_FRAMES = 8
MAX_PROVIDER_FRAME_BYTES = 20 * 1024 * 1024
MAX_PROVIDER_TOTAL_BYTES = 24 * 1024 * 1024
MAX_INVENTORY_CANDIDATES = 24
MAX_UNCERTAINTIES = 12
MAX_NAME_LENGTH = 80
MAX_QUESTION_LENGTH = 160
ALLOWED_FLAGS = frozenset({"fragile", "do-not-touch", "high-value"})
CONFIDENCE_LEVELS = frozenset({"low", "medium", "high"})

EXIT_OK = 0
EXIT_CONFIG = 2
EXIT_AUTH = 3
EXIT_INPUT = 4
EXIT_PROVIDER = 5
EXIT_PRIVACY = 6
EXIT_VALIDATION = 7
EXIT_CONFLICT = 8

_BATCH_ID = re.compile(r"[0-9a-f]{16}")
_PROPOSAL_ID = re.compile(r"[0-9a-f]{32}")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_FRAME_ID = re.compile(r"frame-[0-9]{6}")

IdFactory = Callable[[int], str]


class ProposalFailure(Exception):
    """Fixed failure projection that never carries private input in its message."""

    def __init__(
        self,
        failure: str,
        step: str,
        exit_code: int,
        *,
        provider_request_attempted: bool = False,
        provider_response_received: bool = False,
    ) -> None:
        super().__init__(failure)
        self.failure = failure
        self.step = step
        self.exit_code = exit_code
        self.provider_request_attempted = provider_request_attempted
        self.provider_response_received = provider_response_received


@dataclass(frozen=True)
class FrameBinding:
    id: str
    sha256: str
    bytes: int


@dataclass(frozen=True)
class FrameEvidence:
    id: str
    sha256: str
    jpeg_bytes: bytes = field(repr=False)


@dataclass(frozen=True)
class CaptureBatch:
    id: str
    manifest_sha256: str
    room_id: str = field(repr=False)
    frame_bindings: tuple[FrameBinding, ...]
    evidence_frames: tuple[FrameEvidence, ...]
    path: Path = field(repr=False)


@dataclass(frozen=True)
class GeneratedVisionOutput:
    observations: Mapping[str, object] = field(repr=False)
    provider: str
    model: str
    response_id_sha256: str


class VisionGenerator(Protocol):
    def generate(self, frames: Sequence[FrameEvidence]) -> GeneratedVisionOutput: ...


@dataclass(frozen=True)
class ProposalResult:
    batch_id: str
    proposal_id: str
    proposal_sha256: str
    frame_count: int
    provider: str
    model: str

    def receipt(self) -> dict[str, object]:
        return {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "action": "proposal_created",
            "batch_id": self.batch_id,
            "proposal_id": self.proposal_id,
            "proposal_sha256": self.proposal_sha256,
            "frame_count": self.frame_count,
            "provider": self.provider,
            "model": self.model,
            "provider_request_attempted": True,
            "provider_response_received": True,
            "owner_confirmation_required": True,
            "canonical_housefile_written": False,
        }


@dataclass(frozen=True)
class DecisionResult:
    batch_id: str
    proposal_id: str
    proposal_sha256: str
    decision: Literal["confirmed", "rejected"]

    def receipt(self) -> dict[str, object]:
        return {
            "schema": RECEIPT_SCHEMA,
            "status": "passed",
            "action": "owner_decision_recorded",
            "batch_id": self.batch_id,
            "proposal_id": self.proposal_id,
            "proposal_sha256": self.proposal_sha256,
            "decision": self.decision,
            "provider_request_attempted": False,
            "provider_response_received": False,
            "canonical_housefile_written": False,
        }


def failure_receipt(error: ProposalFailure) -> dict[str, object]:
    return {
        "schema": RECEIPT_SCHEMA,
        "status": "failed",
        "step": error.step,
        "failure": error.failure,
        "exit_code": error.exit_code,
        "provider_request_attempted": error.provider_request_attempted,
        "provider_response_received": error.provider_response_received,
        "canonical_housefile_written": False,
    }


def _canonical_json(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _reject_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise ValueError("non-finite JSON number")


def parse_json_bytes(data: bytes, *, failure: str, step: str) -> object:
    try:
        text = data.decode("utf-8")
        value = json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError, ValueError) as exc:
        raise ProposalFailure(failure, step, EXIT_VALIDATION) from exc
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        current, depth = stack.pop()
        if depth > 12:
            raise ProposalFailure(failure, step, EXIT_VALIDATION)
        if isinstance(current, dict):
            stack.extend((child, depth + 1) for child in current.values())
        elif isinstance(current, list):
            stack.extend((child, depth + 1) for child in current)
    return value


def _exact_keys(value: Mapping[str, object], expected: set[str]) -> bool:
    return set(value) == expected


def _bounded_text(value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not 1 <= len(value) <= maximum
        or any(not character.isprintable() for character in value)
    ):
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    return value


def _evidence_ids(value: object, allowed: frozenset[str]) -> list[str]:
    if (
        not isinstance(value, list)
        or not 1 <= len(value) <= MAX_PROVIDER_FRAMES
        or any(not isinstance(item, str) or _FRAME_ID.fullmatch(item) is None for item in value)
        or len(set(value)) != len(value)
        or not set(value).issubset(allowed)
    ):
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    return list(value)


def _confidence(value: object) -> str:
    if not isinstance(value, str) or value not in CONFIDENCE_LEVELS:
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    return value


def validate_and_normalize_observations(
    value: object,
    *,
    evidence_frame_ids: frozenset[str],
) -> dict[str, object]:
    """Strictly validate provider output and add only locally generated IDs."""

    if not isinstance(value, dict) or not _exact_keys(
        value,
        {"schema", "zone_candidate", "inventory_candidates", "uncertainties"},
    ):
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    if value["schema"] != OBSERVATION_SCHEMA:
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)

    raw_zone = value["zone_candidate"]
    if not isinstance(raw_zone, dict) or not _exact_keys(
        raw_zone,
        {"suggested_name", "outdoor_suggestion", "confidence", "evidence_frame_ids"},
    ):
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    if not isinstance(raw_zone["outdoor_suggestion"], bool):
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    zone = {
        "candidate_id": "zone-candidate-001",
        "suggested_name": _bounded_text(raw_zone["suggested_name"], maximum=MAX_NAME_LENGTH),
        "outdoor_suggestion": raw_zone["outdoor_suggestion"],
        "confidence": _confidence(raw_zone["confidence"]),
        "evidence_frame_ids": _evidence_ids(
            raw_zone["evidence_frame_ids"], evidence_frame_ids
        ),
    }

    raw_inventory = value["inventory_candidates"]
    if not isinstance(raw_inventory, list) or len(raw_inventory) > MAX_INVENTORY_CANDIDATES:
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    inventory: list[dict[str, object]] = []
    inventory_names: set[str] = set()
    for index, item in enumerate(raw_inventory, start=1):
        if not isinstance(item, dict) or not _exact_keys(
            item,
            {"suggested_name", "flags", "confidence", "evidence_frame_ids"},
        ):
            raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
        name = _bounded_text(item["suggested_name"], maximum=MAX_NAME_LENGTH)
        folded_name = name.casefold()
        if folded_name in inventory_names:
            raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
        inventory_names.add(folded_name)
        flags = item["flags"]
        if (
            not isinstance(flags, list)
            or len(flags) > len(ALLOWED_FLAGS)
            or any(not isinstance(flag, str) or flag not in ALLOWED_FLAGS for flag in flags)
            or len(set(flags)) != len(flags)
        ):
            raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
        inventory.append(
            {
                "candidate_id": f"inventory-candidate-{index:03d}",
                "suggested_name": name,
                "flags": list(flags),
                "confidence": _confidence(item["confidence"]),
                "evidence_frame_ids": _evidence_ids(
                    item["evidence_frame_ids"], evidence_frame_ids
                ),
            }
        )

    raw_uncertainties = value["uncertainties"]
    if not isinstance(raw_uncertainties, list) or len(raw_uncertainties) > MAX_UNCERTAINTIES:
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    uncertainties: list[dict[str, object]] = []
    questions: set[str] = set()
    for item in raw_uncertainties:
        if not isinstance(item, dict) or not _exact_keys(
            item,
            {"question", "evidence_frame_ids"},
        ):
            raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
        question = _bounded_text(item["question"], maximum=MAX_QUESTION_LENGTH)
        folded_question = question.casefold()
        if folded_question in questions:
            raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
        questions.add(folded_question)
        uncertainties.append(
            {
                "question": question,
                "evidence_frame_ids": _evidence_ids(
                    item["evidence_frame_ids"], evidence_frame_ids
                ),
            }
        )

    return {
        "schema": "ths/vision-proposal/0.1",
        "zone_candidate": zone,
        "inventory_candidates": inventory,
        "uncertainties": uncertainties,
    }


def _reject_symlink_components(path: Path) -> None:
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            metadata = current.lstat()
        except FileNotFoundError:
            return
        except OSError as exc:
            raise ProposalFailure(
                "unsafe_private_boundary", "batch_validation", EXIT_PRIVACY
            ) from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY)


def _private_metadata(path: Path, *, directory: bool) -> os.stat_result:
    _reject_symlink_components(path)
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise ProposalFailure("batch_unavailable", "batch_validation", EXIT_INPUT) from exc
    expected_type = stat.S_ISDIR if directory else stat.S_ISREG
    if not expected_type(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
        raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY)
    if metadata.st_mode & 0o077:
        raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY)
    if hasattr(os, "geteuid") and metadata.st_uid != os.geteuid():
        raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY)
    return metadata


def _read_private_file(path: Path, *, maximum: int) -> bytes:
    metadata = _private_metadata(path, directory=False)
    if metadata.st_size <= 0 or metadata.st_size > maximum:
        raise ProposalFailure("private_artifact_invalid", "batch_validation", EXIT_INPUT)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
            != (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns)
        ):
            raise ProposalFailure("private_artifact_changed", "batch_validation", EXIT_INPUT)
        chunks: list[bytes] = []
        remaining = opened.st_size
        while remaining:
            chunk = os.read(descriptor, min(128 * 1024, remaining))
            if not chunk:
                raise ProposalFailure("private_artifact_changed", "batch_validation", EXIT_INPUT)
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _validate_identifier(value: str, pattern: re.Pattern[str], failure: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        raise ProposalFailure(failure, "configuration", EXIT_CONFIG)
    return value


def _capture_root(project_root: Path) -> Path:
    project = project_root.absolute()
    capture = project / "data" / "capture"
    _reject_symlink_components(project)
    try:
        project_metadata = project.lstat()
    except OSError as exc:
        raise ProposalFailure("batch_unavailable", "batch_validation", EXIT_INPUT) from exc
    if not stat.S_ISDIR(project_metadata.st_mode) or stat.S_ISLNK(project_metadata.st_mode):
        raise ProposalFailure("unsafe_private_boundary", "batch_validation", EXIT_PRIVACY)
    _private_metadata(project / "data", directory=True)
    _private_metadata(capture, directory=True)
    return capture


def _center_indices(length: int, limit: int) -> list[int]:
    if length <= limit:
        return list(range(length))
    return [((2 * index + 1) * length) // (2 * limit) for index in range(limit)]


def load_capture_batch(
    batch_id: str,
    expected_manifest_sha256: str,
    *,
    project_root: Path = PROJECT_ROOT,
) -> CaptureBatch:
    batch_id = _validate_identifier(batch_id, _BATCH_ID, "invalid_batch_id")
    expected_manifest_sha256 = _validate_identifier(
        expected_manifest_sha256,
        _SHA256,
        "invalid_manifest_digest",
    )
    capture = _capture_root(project_root)
    batch_path = capture / f"batch-{batch_id}"
    _private_metadata(batch_path, directory=True)
    manifest_bytes = _read_private_file(
        batch_path / "manifest.json",
        maximum=MAX_MANIFEST_BYTES,
    )
    manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
    if not compare_digest(manifest_digest, expected_manifest_sha256):
        raise ProposalFailure("manifest_digest_mismatch", "batch_validation", EXIT_INPUT)
    manifest = parse_json_bytes(
        manifest_bytes,
        failure="manifest_invalid",
        step="batch_validation",
    )
    if not isinstance(manifest, dict) or not _exact_keys(
        manifest,
        {
            "schema",
            "batch_id",
            "room_id",
            "input_count",
            "frame_count",
            "frames",
            "model_called",
            "canonical_housefile_written",
        },
    ):
        raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)
    if (
        manifest["schema"] != CAPTURE_MANIFEST_SCHEMA
        or manifest["batch_id"] != batch_id
        or manifest["model_called"] is not False
        or manifest["canonical_housefile_written"] is not False
        or not isinstance(manifest["input_count"], int)
        or isinstance(manifest["input_count"], bool)
        or not 1 <= manifest["input_count"] <= vision_intake.MAX_INPUT_FILES
    ):
        raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)
    room_id = manifest["room_id"]
    if (
        not isinstance(room_id, str)
        or room_id != room_id.strip()
        or not 1 <= len(room_id) <= 80
        or any(not character.isprintable() for character in room_id)
    ):
        raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)
    frames = manifest["frames"]
    frame_count = manifest["frame_count"]
    if (
        not isinstance(frames, list)
        or not isinstance(frame_count, int)
        or isinstance(frame_count, bool)
        or not 1 <= frame_count <= vision_intake.MAX_FRAMES
        or frame_count != len(frames)
    ):
        raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)

    selected_indices = frozenset(_center_indices(frame_count, MAX_PROVIDER_FRAMES))
    bindings: list[FrameBinding] = []
    evidence: list[FrameEvidence] = []
    expected_files: set[str] = set()
    provider_bytes = 0
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict) or not _exact_keys(
            frame,
            {"id", "file", "sha256", "bytes", "source_kind", "source_index"},
        ):
            raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)
        frame_id = f"frame-{index + 1:06d}"
        frame_file = f"{frame_id}.jpg"
        frame_size = frame["bytes"]
        frame_sha = frame["sha256"]
        if (
            frame["id"] != frame_id
            or frame["file"] != frame_file
            or not isinstance(frame_sha, str)
            or _SHA256.fullmatch(frame_sha) is None
            or not isinstance(frame_size, int)
            or isinstance(frame_size, bool)
            or not 1 <= frame_size <= MAX_PROVIDER_FRAME_BYTES
            or frame["source_kind"] not in {"image", "video"}
            or not isinstance(frame["source_index"], int)
            or isinstance(frame["source_index"], bool)
            or frame["source_index"] < 0
        ):
            raise ProposalFailure("manifest_invalid", "batch_validation", EXIT_INPUT)
        frame_path = batch_path / frame_file
        frame_bytes = _read_private_file(frame_path, maximum=MAX_PROVIDER_FRAME_BYTES)
        if len(frame_bytes) != frame_size or not compare_digest(
            hashlib.sha256(frame_bytes).hexdigest(), frame_sha
        ):
            raise ProposalFailure("frame_integrity_failed", "batch_validation", EXIT_INPUT)
        try:
            width, height = vision_intake._jpeg_dimensions(frame_path, frame_size)
        except OSError as exc:
            raise ProposalFailure(
                "frame_integrity_failed", "batch_validation", EXIT_INPUT
            ) from exc
        if (
            width <= 0
            or height <= 0
            or width > vision_intake.NORMALIZED_MAX_EDGE
            or height > vision_intake.NORMALIZED_MAX_EDGE
        ):
            raise ProposalFailure("frame_integrity_failed", "batch_validation", EXIT_INPUT)
        bindings.append(FrameBinding(frame_id, frame_sha, frame_size))
        expected_files.add(frame_file)
        if index in selected_indices:
            provider_bytes += frame_size
            evidence.append(FrameEvidence(frame_id, frame_sha, frame_bytes))
    try:
        present_files = {path.name for path in batch_path.glob("frame-*.jpg")}
    except OSError as exc:
        raise ProposalFailure("batch_unavailable", "batch_validation", EXIT_INPUT) from exc
    if present_files != expected_files or provider_bytes > MAX_PROVIDER_TOTAL_BYTES:
        raise ProposalFailure("frame_integrity_failed", "batch_validation", EXIT_INPUT)

    return CaptureBatch(
        id=batch_id,
        manifest_sha256=manifest_digest,
        room_id=room_id,
        frame_bindings=tuple(bindings),
        evidence_frames=tuple(evidence),
        path=batch_path,
    )


def _write_all(descriptor: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        written = os.write(descriptor, remaining)
        if written <= 0:
            raise OSError("write made no progress")
        remaining = remaining[written:]


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_private_artifact(path: Path, data: bytes) -> None:
    staging = path.parent / f".{path.name}.staging"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor: int | None = None
    staging_created = False
    linked = False
    try:
        descriptor = os.open(staging, flags, 0o600)
        staging_created = True
        _write_all(descriptor, data)
        os.fchmod(descriptor, 0o600)
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
        os.link(staging, path, follow_symlinks=False)
        linked = True
        staging.unlink()
        staging_created = False
        try:
            _fsync_directory(path.parent)
        except OSError:
            path.unlink()
            linked = False
            try:
                _fsync_directory(path.parent)
            except OSError:
                pass
            raise
    except FileExistsError as exc:
        raise ProposalFailure("proposal_conflict", "private_persistence", EXIT_CONFLICT) from exc
    except ProposalFailure:
        raise
    except OSError as exc:
        if linked:
            try:
                path.unlink()
                linked = False
            except OSError:
                pass
        raise ProposalFailure(
            "private_persistence_failed", "private_persistence", EXIT_PRIVACY
        ) from exc
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if staging_created:
            try:
                staging.unlink()
            except OSError:
                pass
        if linked and not path.exists():
            linked = False


def _new_proposal_id(batch: CaptureBatch, id_factory: IdFactory) -> str:
    for _ in range(5):
        proposal_id = id_factory(16)
        if not isinstance(proposal_id, str) or _PROPOSAL_ID.fullmatch(proposal_id) is None:
            raise ProposalFailure("proposal_id_invalid", "private_persistence", EXIT_PRIVACY)
        proposal_path = batch.path / f"proposal-{proposal_id}.json"
        decision_path = batch.path / f"proposal-{proposal_id}.decision.json"
        if (
            not proposal_path.exists()
            and not proposal_path.is_symlink()
            and not decision_path.exists()
            and not decision_path.is_symlink()
        ):
            return proposal_id
    raise ProposalFailure("proposal_id_unavailable", "private_persistence", EXIT_CONFLICT)


def create_proposal(
    batch_id: str,
    expected_manifest_sha256: str,
    generator: VisionGenerator,
    *,
    project_root: Path = PROJECT_ROOT,
    id_factory: IdFactory = secrets.token_hex,
) -> ProposalResult:
    batch = load_capture_batch(
        batch_id,
        expected_manifest_sha256,
        project_root=project_root,
    )
    try:
        generated = generator.generate(batch.evidence_frames)
    except ProposalFailure:
        raise
    except Exception as exc:  # noqa: BLE001 - provider context must never escape
        raise ProposalFailure(
            "generation_failed",
            "provider_request",
            EXIT_PROVIDER,
            provider_request_attempted=True,
        ) from exc
    if (
        not isinstance(generated, GeneratedVisionOutput)
        or generated.provider != "openai"
        or generated.model != "gpt-5.6"
        or not isinstance(generated.response_id_sha256, str)
        or _SHA256.fullmatch(generated.response_id_sha256) is None
    ):
        raise ProposalFailure(
            "provider_response_invalid",
            "provider_response",
            EXIT_PROVIDER,
            provider_request_attempted=True,
            provider_response_received=True,
        )
    allowed_evidence = frozenset(frame.id for frame in batch.evidence_frames)
    try:
        normalized = validate_and_normalize_observations(
            generated.observations,
            evidence_frame_ids=allowed_evidence,
        )
    except ProposalFailure as exc:
        raise ProposalFailure(
            exc.failure,
            exc.step,
            exc.exit_code,
            provider_request_attempted=True,
            provider_response_received=True,
        ) from exc

    proposal_id = _new_proposal_id(batch, id_factory)
    envelope = {
        "schema": PROPOSAL_SCHEMA,
        "proposal_id": proposal_id,
        "batch": {
            "id": batch.id,
            "manifest_sha256": batch.manifest_sha256,
            "trusted_room_id": batch.room_id,
            "frames": [
                {"id": frame.id, "sha256": frame.sha256, "bytes": frame.bytes}
                for frame in batch.frame_bindings
            ],
        },
        "generator": {
            "provider": generated.provider,
            "model": generated.model,
            "prompt_version": PROMPT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "response_id_sha256": generated.response_id_sha256,
        },
        "proposal": normalized,
        "owner_confirmation_required": True,
        "canonical_housefile_written": False,
    }
    proposal_bytes = _canonical_json(envelope)
    if len(proposal_bytes) > MAX_PROPOSAL_BYTES:
        raise ProposalFailure("model_output_invalid", "model_validation", EXIT_VALIDATION)
    proposal_path = batch.path / f"proposal-{proposal_id}.json"
    _atomic_private_artifact(proposal_path, proposal_bytes)
    return ProposalResult(
        batch_id=batch.id,
        proposal_id=proposal_id,
        proposal_sha256=hashlib.sha256(proposal_bytes).hexdigest(),
        frame_count=len(batch.evidence_frames),
        provider=generated.provider,
        model=generated.model,
    )


def _validate_normalized_proposal(value: object, evidence_ids: frozenset[str]) -> None:
    if not isinstance(value, dict) or not _exact_keys(
        value,
        {"schema", "zone_candidate", "inventory_candidates", "uncertainties"},
    ) or value.get("schema") != "ths/vision-proposal/0.1":
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    zone = value["zone_candidate"]
    if not isinstance(zone, dict) or zone.get("candidate_id") != "zone-candidate-001":
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    observations = {
        "schema": OBSERVATION_SCHEMA,
        "zone_candidate": {
            key: zone.get(key)
            for key in (
                "suggested_name",
                "outdoor_suggestion",
                "confidence",
                "evidence_frame_ids",
            )
        },
        "inventory_candidates": [],
        "uncertainties": value["uncertainties"],
    }
    inventory = value["inventory_candidates"]
    if not isinstance(inventory, list):
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    for index, item in enumerate(inventory, start=1):
        if (
            not isinstance(item, dict)
            or item.get("candidate_id") != f"inventory-candidate-{index:03d}"
        ):
            raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
        observations["inventory_candidates"].append(
            {
                key: item.get(key)
                for key in ("suggested_name", "flags", "confidence", "evidence_frame_ids")
            }
        )
    try:
        expected = validate_and_normalize_observations(
            observations,
            evidence_frame_ids=evidence_ids,
        )
    except ProposalFailure as exc:
        raise ProposalFailure(
            "proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION
        ) from exc
    if value != expected:
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)


def _load_proposal_envelope(
    batch_id: str,
    proposal_id: str,
    expected_proposal_sha256: str,
    *,
    project_root: Path,
) -> tuple[dict[str, object], bytes, CaptureBatch, Path]:
    batch_id = _validate_identifier(batch_id, _BATCH_ID, "invalid_batch_id")
    proposal_id = _validate_identifier(proposal_id, _PROPOSAL_ID, "invalid_proposal_id")
    expected_proposal_sha256 = _validate_identifier(
        expected_proposal_sha256,
        _SHA256,
        "invalid_proposal_digest",
    )
    capture = _capture_root(project_root)
    batch_path = capture / f"batch-{batch_id}"
    _private_metadata(batch_path, directory=True)
    proposal_path = batch_path / f"proposal-{proposal_id}.json"
    proposal_bytes = _read_private_file(proposal_path, maximum=MAX_PROPOSAL_BYTES)
    proposal_digest = hashlib.sha256(proposal_bytes).hexdigest()
    if not compare_digest(proposal_digest, expected_proposal_sha256):
        raise ProposalFailure("stale_proposal_digest", "owner_decision", EXIT_CONFLICT)
    envelope = parse_json_bytes(
        proposal_bytes,
        failure="proposal_artifact_invalid",
        step="owner_decision",
    )
    if (
        not isinstance(envelope, dict)
        or _canonical_json(envelope) != proposal_bytes
        or not _exact_keys(
            envelope,
            {
                "schema",
                "proposal_id",
                "batch",
                "generator",
                "proposal",
                "owner_confirmation_required",
                "canonical_housefile_written",
            },
        )
        or envelope["schema"] != PROPOSAL_SCHEMA
        or envelope["proposal_id"] != proposal_id
        or envelope["owner_confirmation_required"] is not True
        or envelope["canonical_housefile_written"] is not False
    ):
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    batch_binding = envelope["batch"]
    generator = envelope["generator"]
    if (
        not isinstance(batch_binding, dict)
        or not _exact_keys(
            batch_binding,
            {"id", "manifest_sha256", "trusted_room_id", "frames"},
        )
        or batch_binding["id"] != batch_id
        or not isinstance(generator, dict)
        or not _exact_keys(
            generator,
            {
                "provider",
                "model",
                "prompt_version",
                "validator_version",
                "response_id_sha256",
            },
        )
        or generator != {
            "provider": "openai",
            "model": "gpt-5.6",
            "prompt_version": PROMPT_VERSION,
            "validator_version": VALIDATOR_VERSION,
            "response_id_sha256": generator.get("response_id_sha256"),
        }
        or not isinstance(generator.get("response_id_sha256"), str)
        or _SHA256.fullmatch(generator["response_id_sha256"]) is None
    ):
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    manifest_digest = batch_binding["manifest_sha256"]
    if not isinstance(manifest_digest, str) or _SHA256.fullmatch(manifest_digest) is None:
        raise ProposalFailure("proposal_artifact_invalid", "owner_decision", EXIT_VALIDATION)
    batch = load_capture_batch(batch_id, manifest_digest, project_root=project_root)
    expected_frames = [
        {"id": frame.id, "sha256": frame.sha256, "bytes": frame.bytes}
        for frame in batch.frame_bindings
    ]
    if batch_binding["trusted_room_id"] != batch.room_id or batch_binding["frames"] != expected_frames:
        raise ProposalFailure("proposal_binding_mismatch", "owner_decision", EXIT_CONFLICT)
    _validate_normalized_proposal(
        envelope["proposal"],
        frozenset(frame.id for frame in batch.evidence_frames),
    )
    return envelope, proposal_bytes, batch, proposal_path


def _decision_timestamp(now: datetime) -> str:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ProposalFailure("decision_clock_invalid", "owner_decision", EXIT_CONFIG)
    return now.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def decide_proposal(
    batch_id: str,
    proposal_id: str,
    expected_proposal_sha256: str,
    *,
    decision: Literal["confirm", "reject"],
    supplied_owner_token: str | None,
    configured_owner_token: str | None,
    project_root: Path = PROJECT_ROOT,
    now: datetime | None = None,
) -> DecisionResult:
    """Record one terminal owner decision; never materialize or save a housefile."""

    if (
        not is_valid_bearer_token(configured_owner_token)
        or not is_valid_bearer_token(supplied_owner_token)
        or not compare_digest(supplied_owner_token or "", configured_owner_token or "")
    ):
        raise ProposalFailure("owner_authentication_required", "owner_auth", EXIT_AUTH)
    if decision not in {"confirm", "reject"}:
        raise ProposalFailure("invalid_owner_decision", "configuration", EXIT_CONFIG)
    _envelope, proposal_bytes, batch, proposal_path = _load_proposal_envelope(
        batch_id,
        proposal_id,
        expected_proposal_sha256,
        project_root=project_root,
    )
    proposal_digest = hashlib.sha256(proposal_bytes).hexdigest()
    decision_path = proposal_path.with_name(f"proposal-{proposal_id}.decision.json")
    if decision_path.exists() or decision_path.is_symlink():
        raise ProposalFailure("proposal_not_pending", "owner_decision", EXIT_CONFLICT)
    recorded_decision: Literal["confirmed", "rejected"] = (
        "confirmed" if decision == "confirm" else "rejected"
    )
    artifact = {
        "schema": DECISION_SCHEMA,
        "proposal_id": proposal_id,
        "proposal_sha256": proposal_digest,
        "batch_id": batch.id,
        "manifest_sha256": batch.manifest_sha256,
        "decision": recorded_decision,
        "decided_at": _decision_timestamp(now or datetime.now(timezone.utc)),
        "owner_confirmation_recorded": True,
        "canonical_housefile_written": False,
    }
    _atomic_private_artifact(decision_path, _canonical_json(artifact))
    return DecisionResult(
        batch_id=batch.id,
        proposal_id=proposal_id,
        proposal_sha256=proposal_digest,
        decision=recorded_decision,
    )
