"""Adversarial proofs for THS-0021 proposals and owner decisions."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import stat
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from io import StringIO
from pathlib import Path
from urllib.request import Request

import pytest
from jsonschema import Draft202012Validator

from threshold.capture import openai_vision
from threshold.capture import vision_proposals as proposals


BATCH_ID = "a" * 16
PROPOSAL_ID = "b" * 32
OWNER_CREDENTIAL = "owner-token-value-" + "o" * 32
PROVIDER_CREDENTIAL = "provider-key-value-" + "p" * 32
PRIVATE_ROOM = "PRIVATE_ROOM_SENTINEL"


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _jpeg(seed: str, width: int = 640, height: int = 360) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return (
        b"\xff\xd8"
        b"\xff\xc0\x00\x0b\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x01\x01\x11\x00"
        + b"\xff\xda\x00\x02"
        + digest
        + b"\xff\xd9"
    )


def _make_batch(
    tmp_path: Path,
    *,
    batch_id: str = BATCH_ID,
    frame_count: int = 3,
) -> tuple[Path, str]:
    project = tmp_path / f"project-{batch_id[:4]}"
    project.mkdir()
    data = project / "data"
    capture = data / "capture"
    batch = capture / f"batch-{batch_id}"
    batch.mkdir(parents=True)
    for directory in (data, capture, batch):
        directory.chmod(0o700)
    frames: list[dict[str, object]] = []
    for index in range(frame_count):
        frame_id = f"frame-{index + 1:06d}"
        frame_bytes = _jpeg(f"synthetic-frame-{index}")
        frame = batch / f"{frame_id}.jpg"
        frame.write_bytes(frame_bytes)
        frame.chmod(0o600)
        frames.append(
            {
                "id": frame_id,
                "file": f"{frame_id}.jpg",
                "sha256": hashlib.sha256(frame_bytes).hexdigest(),
                "bytes": len(frame_bytes),
                "source_kind": "image",
                "source_index": index,
            }
        )
    manifest = {
        "schema": proposals.CAPTURE_MANIFEST_SCHEMA,
        "batch_id": batch_id,
        "room_id": PRIVATE_ROOM,
        "input_count": frame_count,
        "frame_count": frame_count,
        "frames": frames,
        "model_called": False,
        "canonical_housefile_written": False,
    }
    manifest_bytes = _canonical(manifest)
    manifest_path = batch / "manifest.json"
    manifest_path.write_bytes(manifest_bytes)
    manifest_path.chmod(0o600)
    return project, hashlib.sha256(manifest_bytes).hexdigest()


def _observations(frame_ids: tuple[str, ...] = ("frame-000001",)) -> dict[str, object]:
    return {
        "schema": proposals.OBSERVATION_SCHEMA,
        "zone_candidate": {
            "suggested_name": "Synthetic Studio",
            "outdoor_suggestion": False,
            "confidence": "high",
            "evidence_frame_ids": list(frame_ids),
        },
        "inventory_candidates": [
            {
                "suggested_name": "Foam calibration object",
                "flags": ["fragile"],
                "confidence": "medium",
                "evidence_frame_ids": [frame_ids[0]],
            }
        ],
        "uncertainties": [
            {
                "question": "Is the object fixed in place?",
                "evidence_frame_ids": [frame_ids[0]],
            }
        ],
    }


class FakeGenerator:
    def __init__(self, observations: object | None = None, error: Exception | None = None):
        self.observations = _observations() if observations is None else observations
        self.error = error
        self.calls: list[tuple[proposals.FrameEvidence, ...]] = []

    def generate(self, frames):
        self.calls.append(tuple(frames))
        if self.error is not None:
            raise self.error
        return proposals.GeneratedVisionOutput(
            observations=self.observations,
            provider="openai",
            model="gpt-5.6",
            response_id_sha256="c" * 64,
        )


def _create(
    project: Path,
    manifest_digest: str,
    generator: FakeGenerator | None = None,
    *,
    proposal_id: str = PROPOSAL_ID,
) -> proposals.ProposalResult:
    return proposals.create_proposal(
        BATCH_ID,
        manifest_digest,
        generator or FakeGenerator(),
        project_root=project,
        id_factory=lambda _bytes: proposal_id,
    )


def _proposal_path(project: Path, proposal_id: str = PROPOSAL_ID) -> Path:
    return (
        project
        / "data"
        / "capture"
        / f"batch-{BATCH_ID}"
        / f"proposal-{proposal_id}.json"
    )


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def _provider_response(observations: object | None = None) -> bytes:
    output_text = json.dumps(_observations() if observations is None else observations)
    return json.dumps(
        {
            "id": "resp_synthetic_001",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": output_text}],
                }
            ],
        }
    ).encode("utf-8")


def test_valid_proposal_is_private_bound_and_not_canonical(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    canonical = project / "data" / "housefile.json"
    canonical.write_bytes(b'{"canonical":"unchanged"}\n')
    before = (canonical.read_bytes(), canonical.stat().st_ino, canonical.stat().st_mtime_ns)
    generator = FakeGenerator()

    result = _create(project, manifest_digest, generator)

    proposal_path = _proposal_path(project)
    envelope = json.loads(proposal_path.read_text(encoding="utf-8"))
    assert _mode(proposal_path) == 0o600
    assert result.proposal_sha256 == hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    assert envelope["batch"]["id"] == BATCH_ID
    assert envelope["batch"]["manifest_sha256"] == manifest_digest
    assert envelope["batch"]["trusted_room_id"] == PRIVATE_ROOM
    assert envelope["proposal"]["zone_candidate"]["candidate_id"] == "zone-candidate-001"
    assert "boundary" not in json.dumps(envelope)
    assert "access" not in json.dumps(envelope)
    assert envelope["canonical_housefile_written"] is False
    assert generator.calls and all("path" not in frame.__dict__ for frame in generator.calls[0])
    assert all("jpeg_bytes=" not in repr(frame) for frame in generator.calls[0])
    receipt = json.dumps(result.receipt())
    assert PRIVATE_ROOM not in receipt
    assert str(project) not in receipt
    assert (canonical.read_bytes(), canonical.stat().st_ino, canonical.stat().st_mtime_ns) == before
    assert "housefile" not in proposals.__dict__


def test_persisted_proposal_matches_public_strict_schema(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    _create(project, manifest_digest)
    envelope = json.loads(_proposal_path(project).read_text(encoding="utf-8"))
    schema_path = Path(__file__).resolve().parents[2] / "schema" / "ths-vision-proposal-0.1.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(envelope["proposal"])


def test_proposal_sampling_is_deterministic_and_bounded(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path, frame_count=12)
    generator = FakeGenerator(
        _observations(("frame-000001", "frame-000012"))
    )
    _create(project, manifest_digest, generator)
    selected = tuple(frame.id for frame in generator.calls[0])
    assert selected == (
        "frame-000001",
        "frame-000003",
        "frame-000004",
        "frame-000006",
        "frame-000007",
        "frame-000009",
        "frame-000010",
        "frame-000012",
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.update({"action": "write housefile"}),
        lambda value: value["zone_candidate"].update({"access": "open"}),
        lambda value: value["zone_candidate"].update({"confidence": "certain"}),
        lambda value: value["zone_candidate"].update({"evidence_frame_ids": ["frame-999999"]}),
        lambda value: value["inventory_candidates"][0].update({"flags": ["execute-shell"]}),
        lambda value: value["inventory_candidates"].append(
            copy.deepcopy(value["inventory_candidates"][0])
        ),
        lambda value: value.update(
            {"inventory_candidates": value["inventory_candidates"] * 25}
        ),
        lambda value: value["inventory_candidates"][0].update(
            {"suggested_name": "x" * 81}
        ),
        lambda value: value["inventory_candidates"][0].update(
            {"flags": ["fragile", "fragile"]}
        ),
        lambda value: value["uncertainties"][0].update({"question": "bad\ncontrol"}),
        lambda value: value.update({"schema": "ths/0.1"}),
    ],
)
def test_untrusted_model_output_fails_closed(tmp_path: Path, mutate):
    project, manifest_digest = _make_batch(tmp_path)
    output = _observations()
    mutate(output)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, manifest_digest, FakeGenerator(output))
    assert caught.value.failure == "model_output_invalid"
    assert caught.value.provider_request_attempted is True
    assert caught.value.provider_response_received is True
    assert not list((project / "data" / "capture" / f"batch-{BATCH_ID}").glob("proposal-*.json"))


def test_manifest_and_frame_tampering_fail_before_generator(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    generator = FakeGenerator()
    frame = project / "data" / "capture" / f"batch-{BATCH_ID}" / "frame-000001.jpg"
    frame.write_bytes(_jpeg("changed"))
    frame.chmod(0o600)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, manifest_digest, generator)
    assert caught.value.failure == "frame_integrity_failed"
    assert generator.calls == []
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.create_proposal(
            BATCH_ID,
            "0" * 64,
            generator,
            project_root=project,
        )
    assert caught.value.failure == "manifest_digest_mismatch"
    assert generator.calls == []


def test_duplicate_key_nan_and_private_mode_fail_before_generator(tmp_path: Path):
    for injected in (b'{"schema":"duplicate",', b'{"unexpected":NaN,'):
        case_root = tmp_path / hashlib.sha256(injected).hexdigest()[:8]
        case_root.mkdir()
        project, _manifest_digest = _make_batch(case_root)
        manifest = project / "data" / "capture" / f"batch-{BATCH_ID}" / "manifest.json"
        original = manifest.read_bytes()
        manifest.write_bytes(injected + original[1:])
        manifest.chmod(0o600)
        digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
        generator = FakeGenerator()
        with pytest.raises(proposals.ProposalFailure) as caught:
            _create(project, digest, generator)
        assert caught.value.failure == "manifest_invalid"
        assert generator.calls == []

    permissions_root = tmp_path / "permissions"
    permissions_root.mkdir()
    project, digest = _make_batch(permissions_root)
    manifest = project / "data" / "capture" / f"batch-{BATCH_ID}" / "manifest.json"
    manifest.chmod(0o644)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, digest)
    assert caught.value.failure == "unsafe_private_boundary"

def test_extra_or_symlinked_frame_is_refused(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    batch = project / "data" / "capture" / f"batch-{BATCH_ID}"
    extra = batch / "frame-999999.jpg"
    extra.write_bytes(_jpeg("extra"))
    extra.chmod(0o600)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, manifest_digest)
    assert caught.value.failure == "frame_integrity_failed"

    extra.unlink()
    original = batch / "frame-000001.jpg"
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(original.read_bytes())
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, manifest_digest)
    assert caught.value.failure == "unsafe_private_boundary"


@pytest.mark.parametrize("batch_id", ["../private", "http:camera", "A" * 16, "a" * 15])
def test_invalid_batch_ids_are_rejected(batch_id: str, tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.create_proposal(
            batch_id,
            manifest_digest,
            FakeGenerator(),
            project_root=project,
        )
    assert caught.value.failure == "invalid_batch_id"


def test_atomic_proposal_failure_leaves_no_artifact(tmp_path: Path, monkeypatch):
    project, manifest_digest = _make_batch(tmp_path)

    def fail_fsync(_path: Path) -> None:
        raise OSError("PRIVATE_FSYNC_SENTINEL")

    monkeypatch.setattr(proposals, "_fsync_directory", fail_fsync)
    with pytest.raises(proposals.ProposalFailure) as caught:
        _create(project, manifest_digest)
    batch = project / "data" / "capture" / f"batch-{BATCH_ID}"
    assert caught.value.failure == "private_persistence_failed"
    assert not list(batch.glob("proposal-*.json"))
    assert not list(batch.glob(".*.staging"))


def test_owner_confirmation_is_digest_bound_terminal_and_noncanonical(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    canonical = project / "data" / "housefile.json"
    canonical.write_bytes(b'{"canonical":"unchanged"}\n')
    before = canonical.read_bytes()
    proposal = _create(project, manifest_digest)

    decision = proposals.decide_proposal(
        BATCH_ID,
        PROPOSAL_ID,
        proposal.proposal_sha256,
        decision="confirm",
        supplied_owner_token=OWNER_CREDENTIAL,
        configured_owner_token=OWNER_CREDENTIAL,
        project_root=project,
        now=datetime(2026, 7, 13, 1, 2, 3, tzinfo=timezone.utc),
    )

    decision_path = _proposal_path(project).with_name(
        f"proposal-{PROPOSAL_ID}.decision.json"
    )
    artifact = json.loads(decision_path.read_text(encoding="utf-8"))
    assert decision.decision == "confirmed"
    assert _mode(decision_path) == 0o600
    assert artifact["proposal_sha256"] == proposal.proposal_sha256
    assert artifact["decision"] == "confirmed"
    assert artifact["decided_at"] == "2026-07-13T01:02:03Z"
    assert artifact["canonical_housefile_written"] is False
    assert OWNER_CREDENTIAL not in decision_path.read_text(encoding="utf-8")
    assert canonical.read_bytes() == before
    with pytest.raises(proposals.ProposalFailure) as replay:
        proposals.decide_proposal(
            BATCH_ID,
            PROPOSAL_ID,
            proposal.proposal_sha256,
            decision="confirm",
            supplied_owner_token=OWNER_CREDENTIAL,
            configured_owner_token=OWNER_CREDENTIAL,
            project_root=project,
        )
    assert replay.value.failure == "proposal_not_pending"


def test_atomic_decision_failure_leaves_proposal_pending(tmp_path: Path, monkeypatch):
    project, manifest_digest = _make_batch(tmp_path)
    proposal = _create(project, manifest_digest)

    def fail_fsync(_path: Path) -> None:
        raise OSError("PRIVATE_FSYNC_SENTINEL")

    monkeypatch.setattr(proposals, "_fsync_directory", fail_fsync)
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.decide_proposal(
            BATCH_ID,
            PROPOSAL_ID,
            proposal.proposal_sha256,
            decision="confirm",
            supplied_owner_token=OWNER_CREDENTIAL,
            configured_owner_token=OWNER_CREDENTIAL,
            project_root=project,
        )
    batch = project / "data" / "capture" / f"batch-{BATCH_ID}"
    assert caught.value.failure == "private_persistence_failed"
    assert not list(batch.glob("proposal-*.decision.json"))
    assert not list(batch.glob(".*.staging"))


def test_reject_is_terminal_and_owner_auth_is_required(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    proposal = _create(project, manifest_digest)
    for supplied in (None, "wrong-token-" + "x" * 32):
        with pytest.raises(proposals.ProposalFailure) as caught:
            proposals.decide_proposal(
                BATCH_ID,
                PROPOSAL_ID,
                proposal.proposal_sha256,
                decision="reject",
                supplied_owner_token=supplied,
                configured_owner_token=OWNER_CREDENTIAL,
                project_root=project,
            )
        assert caught.value.failure == "owner_authentication_required"
    result = proposals.decide_proposal(
        BATCH_ID,
        PROPOSAL_ID,
        proposal.proposal_sha256,
        decision="reject",
        supplied_owner_token=OWNER_CREDENTIAL,
        configured_owner_token=OWNER_CREDENTIAL,
        project_root=project,
    )
    assert result.decision == "rejected"


def test_wrong_or_tampered_proposal_digest_fails(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    proposal = _create(project, manifest_digest)
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.decide_proposal(
            BATCH_ID,
            PROPOSAL_ID,
            "0" * 64,
            decision="confirm",
            supplied_owner_token=OWNER_CREDENTIAL,
            configured_owner_token=OWNER_CREDENTIAL,
            project_root=project,
        )
    assert caught.value.failure == "stale_proposal_digest"

    path = _proposal_path(project)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["batch"]["trusted_room_id"] = "changed-room"
    path.write_bytes(_canonical(envelope))
    path.chmod(0o600)
    changed_digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.decide_proposal(
            BATCH_ID,
            PROPOSAL_ID,
            changed_digest,
            decision="confirm",
            supplied_owner_token=OWNER_CREDENTIAL,
            configured_owner_token=OWNER_CREDENTIAL,
            project_root=project,
        )
    assert caught.value.failure == "proposal_binding_mismatch"


def test_frame_tamper_after_proposal_blocks_owner_decision(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    proposal = _create(project, manifest_digest)
    frame = project / "data" / "capture" / f"batch-{BATCH_ID}" / "frame-000001.jpg"
    frame.write_bytes(_jpeg("post-proposal-tamper"))
    frame.chmod(0o600)
    with pytest.raises(proposals.ProposalFailure) as caught:
        proposals.decide_proposal(
            BATCH_ID,
            PROPOSAL_ID,
            proposal.proposal_sha256,
            decision="confirm",
            supplied_owner_token=OWNER_CREDENTIAL,
            configured_owner_token=OWNER_CREDENTIAL,
            project_root=project,
        )
    assert caught.value.failure == "frame_integrity_failed"
    assert not _proposal_path(project).with_name(
        f"proposal-{PROPOSAL_ID}.decision.json"
    ).exists()


def test_concurrent_owner_decisions_have_one_winner(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    proposal = _create(project, manifest_digest)

    def decide(decision: str):
        try:
            return proposals.decide_proposal(
                BATCH_ID,
                PROPOSAL_ID,
                proposal.proposal_sha256,
                decision=decision,
                supplied_owner_token=OWNER_CREDENTIAL,
                configured_owner_token=OWNER_CREDENTIAL,
                project_root=project,
            ).decision
        except proposals.ProposalFailure as exc:
            return exc.failure

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = list(executor.map(decide, ("confirm", "reject")))
    assert len([outcome for outcome in outcomes if outcome in {"confirmed", "rejected"}]) == 1
    assert len([outcome for outcome in outcomes if outcome == "proposal_conflict"]) == 1


def test_openai_request_is_fixed_structured_and_path_free(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    captured: list[tuple[Request, int]] = []

    def sender(request: Request, timeout: int) -> bytes:
        captured.append((request, timeout))
        return _provider_response()

    result = openai_vision.create_openai_proposal(
        BATCH_ID,
        manifest_digest,
        allow_external_processing=True,
        environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
        project_root=project,
        sender=sender,
        id_factory=lambda _bytes: PROPOSAL_ID,
    )

    assert result.model == "gpt-5.6"
    request, timeout = captured[0]
    body_text = request.data.decode("utf-8")
    body = json.loads(body_text)
    assert request.full_url == "https://api.openai.com/v1/responses"
    assert request.get_method() == "POST"
    assert request.get_header("Authorization") == f"Bearer {PROVIDER_CREDENTIAL}"
    assert timeout == openai_vision.REQUEST_TIMEOUT_SECONDS
    assert body["model"] == "gpt-5.6"
    assert body["store"] is False
    assert "tools" not in body
    assert body["text"]["format"]["type"] == "json_schema"
    assert body["text"]["format"]["strict"] is True
    images = [
        item
        for item in body["input"][1]["content"]
        if item["type"] == "input_image"
    ]
    assert len(images) == 3
    assert all(image["detail"] == "high" for image in images)
    assert all(image["image_url"].startswith("data:image/jpeg;base64,") for image in images)
    assert PROVIDER_CREDENTIAL not in body_text
    assert PRIVATE_ROOM not in body_text
    assert str(project) not in body_text
    assert manifest_digest not in body_text
    assert all(frame["sha256"] not in body_text for frame in json.loads(
        (project / "data" / "capture" / f"batch-{BATCH_ID}" / "manifest.json").read_text()
    )["frames"])
    assert PROVIDER_CREDENTIAL not in repr(openai_vision.OpenAIResponsesGenerator(PROVIDER_CREDENTIAL, sender=sender))


def test_external_consent_and_key_are_required_before_sender(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    calls = 0

    def sender(_request: Request, _timeout: int) -> bytes:
        nonlocal calls
        calls += 1
        raise AssertionError("sender must not run")

    with pytest.raises(proposals.ProposalFailure) as consent:
        openai_vision.create_openai_proposal(
            BATCH_ID,
            manifest_digest,
            allow_external_processing=False,
            environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
            project_root=project,
            sender=sender,
        )
    assert consent.value.failure == "external_processing_consent_required"
    with pytest.raises(proposals.ProposalFailure) as key:
        openai_vision.create_openai_proposal(
            BATCH_ID,
            manifest_digest,
            allow_external_processing=True,
            environ={},
            project_root=project,
            sender=sender,
        )
    assert key.value.failure == "provider_key_unavailable"
    assert calls == 0


@pytest.mark.parametrize(
    ("response", "failure"),
    [
        (b"not-json", "provider_response_invalid"),
        (json.dumps({"id": "r", "status": "incomplete", "output": []}).encode(), "provider_response_incomplete"),
        (
            json.dumps(
                {
                    "id": "r",
                    "status": "completed",
                    "output": [
                        {"type": "message", "content": [{"type": "refusal", "refusal": "PRIVATE_REFUSAL_SENTINEL"}]}
                    ],
                }
            ).encode(),
            "provider_refused",
        ),
        (_provider_response({"schema": "bad"}), "model_output_invalid"),
    ],
)
def test_provider_response_failures_are_sanitized(tmp_path: Path, response: bytes, failure: str):
    project, manifest_digest = _make_batch(tmp_path)
    output = StringIO()
    code = openai_vision.main(
        [
            "propose",
            BATCH_ID,
            "--manifest-sha256",
            manifest_digest,
            "--allow-external-processing",
        ],
        output=output,
        environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
        project_root=project,
        sender=lambda _request, _timeout: response,
    )
    receipt = json.loads(output.getvalue())
    assert code in {proposals.EXIT_PROVIDER, proposals.EXIT_VALIDATION}
    assert receipt["failure"] == failure
    assert receipt["provider_request_attempted"] is True
    assert receipt["provider_response_received"] is True
    assert "PRIVATE_REFUSAL_SENTINEL" not in output.getvalue()
    assert PRIVATE_ROOM not in output.getvalue()


def test_provider_transport_failure_marks_attempt_without_reflection(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    output = StringIO()

    def sender(_request: Request, _timeout: int) -> bytes:
        raise OSError("PRIVATE_PROVIDER_ERROR_SENTINEL")

    code = openai_vision.main(
        [
            "propose",
            BATCH_ID,
            "--manifest-sha256",
            manifest_digest,
            "--allow-external-processing",
        ],
        output=output,
        environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
        project_root=project,
        sender=sender,
    )
    receipt = json.loads(output.getvalue())
    assert code == proposals.EXIT_PROVIDER
    assert receipt["failure"] == "provider_request_failed"
    assert receipt["provider_request_attempted"] is True
    assert receipt["provider_response_received"] is False
    assert "PRIVATE_PROVIDER_ERROR_SENTINEL" not in output.getvalue()
    assert PROVIDER_CREDENTIAL not in output.getvalue()


def test_duplicate_model_json_and_oversized_provider_response_are_rejected(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    duplicate_output = (
        '{"schema":"ths/vision-observations/0.1",'
        '"schema":"ths/vision-observations/0.1",'
        '"zone_candidate":{},"inventory_candidates":[],"uncertainties":[]}'
    )
    response = json.dumps(
        {
            "id": "r",
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [{"type": "output_text", "text": duplicate_output}],
                }
            ],
        }
    ).encode()
    with pytest.raises(proposals.ProposalFailure) as duplicate:
        openai_vision.create_openai_proposal(
            BATCH_ID,
            manifest_digest,
            allow_external_processing=True,
            environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
            project_root=project,
            sender=lambda _request, _timeout: response,
        )
    assert duplicate.value.failure == "model_output_invalid"
    with pytest.raises(proposals.ProposalFailure) as oversized:
        openai_vision.create_openai_proposal(
            BATCH_ID,
            manifest_digest,
            allow_external_processing=True,
            environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
            project_root=project,
            sender=lambda _request, _timeout: b"x" * (openai_vision.MAX_RESPONSE_BYTES + 1),
        )
    assert oversized.value.failure == "provider_response_invalid"


def test_cli_propose_and_confirm_emit_one_sanitized_line(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    propose_output = StringIO()
    code = openai_vision.main(
        [
            "propose",
            BATCH_ID,
            "--manifest-sha256",
            manifest_digest,
            "--allow-external-processing",
        ],
        output=propose_output,
        environ={"OPENAI_API_KEY": PROVIDER_CREDENTIAL},
        project_root=project,
        sender=lambda _request, _timeout: _provider_response(),
        id_factory=lambda _bytes: PROPOSAL_ID,
    )
    proposal_receipt = json.loads(propose_output.getvalue())
    assert code == 0
    assert len(propose_output.getvalue().splitlines()) == 1
    assert PRIVATE_ROOM not in propose_output.getvalue()
    assert PROVIDER_CREDENTIAL not in propose_output.getvalue()

    confirm_output = StringIO()
    prompts: list[str] = []

    def secret_reader(prompt: str) -> str:
        prompts.append(prompt)
        return OWNER_CREDENTIAL

    code = openai_vision.main(
        [
            "confirm",
            BATCH_ID,
            PROPOSAL_ID,
            "--proposal-sha256",
            proposal_receipt["proposal_sha256"],
        ],
        output=confirm_output,
        environ={"THS_OWNER_TOKEN": OWNER_CREDENTIAL},
        project_root=project,
        secret_reader=secret_reader,
    )
    assert code == 0
    assert len(confirm_output.getvalue().splitlines()) == 1
    assert json.loads(confirm_output.getvalue())["decision"] == "confirmed"
    assert OWNER_CREDENTIAL not in confirm_output.getvalue()
    assert prompts == ["Owner token: "]


def test_cli_invalid_values_are_not_reflected(tmp_path: Path):
    project, _manifest_digest = _make_batch(tmp_path)
    output = StringIO()
    code = openai_vision.main(
        ["propose", "PRIVATE_BATCH_SENTINEL", "--manifest-sha256", "PRIVATE_DIGEST_SENTINEL"],
        output=output,
        environ={},
        project_root=project,
    )
    assert code == proposals.EXIT_CONFIG
    assert "PRIVATE_BATCH_SENTINEL" not in output.getvalue()
    assert "PRIVATE_DIGEST_SENTINEL" not in output.getvalue()


def test_public_scanner_rejects_force_tracked_proposal(tmp_path: Path):
    project, manifest_digest = _make_batch(tmp_path)
    _create(project, manifest_digest)
    proposal_path = _proposal_path(project)
    subprocess.run(["git", "init", "-q"], cwd=project, check=True)
    subprocess.run(["git", "add", "-f", str(proposal_path)], cwd=project, check=True)
    scanner = Path(__file__).resolve().parents[2] / "scripts" / "public_release_check.py"
    result = subprocess.run(
        [os.sys.executable, str(scanner), str(project)],
        capture_output=True,
        check=False,
        text=True,
    )
    report = json.loads(result.stdout)
    assert result.returncode == 1
    assert report["findings"][0]["rule"] == "tracked_private_capture"
    assert PROPOSAL_ID not in result.stdout
    assert PRIVATE_ROOM not in result.stdout
