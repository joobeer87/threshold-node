"""THS-0014/0015/0016 — authenticated API with durable policy receipts."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
from hmac import compare_digest
from threading import RLock
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr

from threshold.capture.seed import SEED_FILE, SEED_GRANTS
from threshold.core.auth import is_valid_bearer_token, token_digest, token_matches
from threshold.core.config import SETTINGS, Settings
from threshold.core.errors import ValidationError as ThresholdValidationError
from threshold.core.events import BUS
from threshold.core.ledger import JsonlLedger
from threshold.core.types import Access, EventType, Grant, GrantStatus, Housefile, Scope
from threshold.grants.manager import GrantManager, normalize_time
from threshold.housefile.scoped_view import scoped_view


app = FastAPI(
    title="Threshold Node",
    version="0.1.0",
    description="Pre-alpha local permission node; adapters and safety hardware are not implemented.",
)
FILE: Housefile = SEED_FILE
MGR = GrantManager(FILE)
for seed_grant in SEED_GRANTS:
    MGR.grants[seed_grant.id] = seed_grant
GRANT_LOCK = RLock()
LEDGER = JsonlLedger(SETTINGS.ledger_path)
PYDANTIC_V2 = hasattr(BaseModel, "model_fields")


class StrictRequestModel(BaseModel):
    """Forbid unknown request fields on both supported Pydantic generations."""

    if PYDANTIC_V2:
        model_config = {"extra": "forbid"}
    else:  # pragma: no cover - exercised by compatibility environments
        class Config:
            extra = "forbid"


class CommandRequest(StrictRequestModel):
    grant: str = Field(min_length=1, max_length=128)
    verb: Literal["navigate", "manipulate"]
    zone: str = Field(min_length=1, max_length=128)
    params: dict[str, object] = Field(default_factory=dict)


class GrantIssueRequest(StrictRequestModel):
    name: str = Field(min_length=1, max_length=128)
    kind: Literal["humanoid", "agent", "human"]
    scopes: list[Scope]
    zones: list[str]
    window: str = Field(default="standing", min_length=1, max_length=128)
    expires: str = Field(default="revocable", min_length=1, max_length=64)

class PublicGrant(BaseModel):
    id: str
    name: str
    kind: str
    scopes: tuple[Scope, ...]
    zones: tuple[str, ...]
    window: str
    expires: str
    status: GrantStatus
    issued: str


class GrantIssueResponse(BaseModel):
    grant: PublicGrant
    credential_registered: bool


class GrantRevokeResponse(BaseModel):
    grant: PublicGrant
    changed: bool


@app.exception_handler(RequestValidationError)
async def sanitized_request_validation(
    _request: Request,
    _error: RequestValidationError,
) -> JSONResponse:
    """Reject malformed input without reflecting headers or body values."""

    return JSONResponse(status_code=422, content={"detail": "request validation failed"})


def _now() -> datetime:
    """Single request clock seam used by the expiry/window tests."""

    return datetime.now(timezone.utc)


def _rfc3339(value: datetime) -> str:
    normalized = normalize_time(value, "current time")
    return normalized.isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_grant_id() -> str:
    return f"g-{secrets.token_hex(8)}"


def _public_grant(grant: Grant) -> PublicGrant:
    """Project a grant explicitly; credentials can never enter this schema."""

    return PublicGrant(
        id=grant.id,
        name=grant.name,
        kind=grant.kind,
        scopes=grant.scopes,
        zones=grant.zones,
        window=grant.window,
        expires=grant.expires,
        status=grant.status,
        issued=grant.issued,
    )


def require_owner(
    x_threshold_owner_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Owner-Token",
    ),
) -> None:
    """Reject sensitive requests when auth is missing or unconfigured."""

    settings: Settings = SETTINGS
    if not is_valid_bearer_token(settings.owner_token):
        raise HTTPException(503, "owner authentication is not configured")
    if (
        settings.demo_mode
        and settings.demo_grant_token is not None
        and compare_digest(settings.owner_token, settings.demo_grant_token)
    ):
        raise HTTPException(503, "owner authentication is not configured")
    if x_threshold_owner_token is None or not compare_digest(
        x_threshold_owner_token.get_secret_value(),
        settings.owner_token,
    ):
        raise HTTPException(401, "owner authentication required")


def _authorized_grant(grant_id: str, supplied_token: SecretStr | None) -> Grant:
    grant = MGR.grants.get(grant_id)
    raw_token = supplied_token.get_secret_value() if supplied_token is not None else None
    if (
        grant is None
        or not is_valid_bearer_token(raw_token)
        or not token_matches(raw_token, grant.credential_digest)
    ):
        raise HTTPException(401, "grant authentication required")
    return grant


def _log(
    event_type: EventType,
    agent: str,
    detail: str,
    *,
    now: datetime | None = None,
    tier: str | None = None,
) -> dict[str, object]:
    """Durably append first, then notify best-effort in-process observers."""

    timestamp_source = now or datetime.now(timezone.utc)
    try:
        timestamp = _rfc3339(timestamp_source)
    except ThresholdValidationError:
        timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    event: dict[str, object] = {
        "ts": timestamp,
        "type": event_type.value,
        "agent": agent,
        "detail": detail,
    }
    if tier is not None:
        event["tier"] = tier
    try:
        persisted = LEDGER.record_event(event_type, event)
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(503, "audit ledger unavailable") from exc
    BUS.emit(event_type.value, persisted)
    return persisted


def _usable_grant(
    grant_id: str,
    supplied_token: SecretStr | None,
    *,
    action: Literal["scoped read", "command"],
    now: datetime,
) -> Grant:
    grant = _authorized_grant(grant_id, supplied_token)
    previous_status = grant.status
    decision = MGR.decision(grant, now=now)
    if not decision.allowed:
        try:
            _log(
                EventType.DENY,
                grant.id,
                f"{action} refused: {decision.reason}",
                now=now,
            )
        except HTTPException:
            grant.status = previous_status
            raise
        raise HTTPException(
            403,
            detail={"policy_decision": "denied", "reason": decision.reason},
        )
    return grant


@app.get("/health")
def health() -> dict[str, object]:
    return {
        "service": "up",
        "release_stage": "pre-alpha",
        "armed": False,
        "interlock": "not_implemented",
        "ledger": "persistent_jsonl_configured",
        "ledger_availability": "not_probed",
        "adapters": [],
        "demo_mode": SETTINGS.demo_mode,
    }


@app.get("/.well-known/aurora", include_in_schema=False)
def aurora_signature() -> dict[str, object]:
    """Public design signature, not an embedded private AuroraOS runtime."""

    return {
        "signature": "AURORA",
        "kind": "public_demo_easter_egg",
        "principle": "authority_before_autonomy",
        "boundary": {
            "owner_authority_required": True,
            "model_output_is_proposal": True,
            "fail_closed": True,
            "receipts_required": True,
        },
        "safety_receipt": {
            "secret_material_returned": False,
            "unauthorized_action_executed": False,
            "private_control_plane_exposed": False,
        },
        "disclosure": "Public signature only; AuroraOS is not embedded in this build.",
    }


@app.get("/housefile")
def housefile(
    grant: str,
    x_threshold_grant_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
) -> dict[str, object]:
    with GRANT_LOCK:
        request_now = _now()
        active_grant = _usable_grant(
            grant,
            x_threshold_grant_token,
            action="scoped read",
            now=request_now,
        )
        payload = scoped_view(FILE, active_grant)
        event_type = EventType.DENY if "error" in payload else EventType.READ
        _log(event_type, active_grant.id, "scoped read", now=request_now)
        return payload


@app.post("/command")
def command(
    body: CommandRequest,
    x_threshold_grant_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
) -> None:
    with GRANT_LOCK:
        request_now = _now()
        active_grant = _usable_grant(
            body.grant,
            x_threshold_grant_token,
            action="command",
            now=request_now,
        )
        zone = FILE.zone(body.zone)
        required_scope = {
            "navigate": Scope.CMD_NAVIGATE,
            "manipulate": Scope.CMD_MANIPULATE,
        }[body.verb]
        if body.params:
            _log(
                EventType.DENY,
                active_grant.id,
                "command refused: parameters unsupported",
                now=request_now,
            )
            raise HTTPException(
                403,
                detail={
                    "policy_decision": "denied",
                    "relayed": False,
                    "reason": "unsupported_params",
                },
            )
        if (
            zone is None
            or zone.id not in active_grant.zones
            or zone.access == Access.NO_GO
            or required_scope not in active_grant.scopes
        ):
            _log(
                EventType.DENY,
                active_grant.id,
                "command refused: policy boundary",
                now=request_now,
            )
            raise HTTPException(
                403,
                detail={
                    "policy_decision": "denied",
                    "relayed": False,
                    "reason": "gate_refused",
                },
            )
        _log(
            EventType.DENY,
            active_grant.id,
            "command not relayed: adapter unavailable",
            now=request_now,
            tier="UNAVAILABLE",
        )
        raise HTTPException(
            503,
            detail={
                "policy_decision": "allowed",
                "relayed": False,
                "reason": "adapter_not_configured",
                "tier": "UNAVAILABLE",
            },
        )


@app.post(
    "/grants",
    status_code=201,
    response_model=GrantIssueResponse,
)
def issue_grant(
    body: GrantIssueRequest,
    x_threshold_new_grant_token: SecretStr = Header(
        ...,
        alias="X-Threshold-New-Grant-Token",
    ),
    _owner: None = Depends(require_owner),
) -> GrantIssueResponse:
    del _owner
    raw_credential = x_threshold_new_grant_token.get_secret_value()
    if not is_valid_bearer_token(raw_credential):
        raise HTTPException(422, "grant credential format is invalid")
    settings: Settings = SETTINGS
    if settings.owner_token is not None and compare_digest(
        raw_credential,
        settings.owner_token,
    ):
        raise HTTPException(422, "grant credential must differ from owner credential")
    credential_digest = token_digest(raw_credential)

    if not body.scopes or len(body.scopes) > 16 or not body.zones or len(body.zones) > 32:
        raise HTTPException(422, "grant needs bounded non-empty scopes and zones")
    if body.name != body.name.strip() or any(zone != zone.strip() for zone in body.zones):
        raise HTTPException(422, "grant text fields must not have surrounding whitespace")
    if len(set(body.scopes)) != len(body.scopes) or len(set(body.zones)) != len(body.zones):
        raise HTTPException(422, "grant scopes and zones must be unique")

    with GRANT_LOCK:
        request_now = _now()
        try:
            issued = _rfc3339(request_now)
        except ThresholdValidationError as exc:
            raise HTTPException(503, "node clock is invalid") from exc
        if any(
            existing.credential_digest
            and compare_digest(credential_digest, existing.credential_digest)
            for existing in MGR.grants.values()
        ):
            raise HTTPException(409, "grant credential is already registered")

        grant_id = ""
        for _ in range(5):
            candidate = _new_grant_id()
            if candidate not in MGR.grants:
                grant_id = candidate
                break
        if not grant_id:
            raise HTTPException(503, "grant id allocation unavailable")

        grant = Grant(
            id=grant_id,
            name=body.name,
            kind=body.kind,
            scopes=tuple(body.scopes),
            zones=tuple(body.zones),
            window=body.window,
            expires=body.expires,
            issued=issued,
            credential_digest=credential_digest,
        )
        try:
            MGR.issue(grant, now=request_now)
        except ThresholdValidationError as exc:
            raise HTTPException(422, "grant policy is invalid") from exc
        try:
            _log(EventType.GRANT, grant.id, "grant issued", now=request_now)
        except HTTPException:
            MGR.grants.pop(grant.id, None)
            raise
        return GrantIssueResponse(
            grant=_public_grant(grant),
            credential_registered=True,
        )


@app.post(
    "/grants/{grant_id}/revoke",
    response_model=GrantRevokeResponse,
)
def revoke_grant(
    grant_id: str,
    _owner: None = Depends(require_owner),
) -> GrantRevokeResponse:
    del _owner
    with GRANT_LOCK:
        request_now = _now()
        grant = MGR.grants.get(grant_id)
        if grant is None:
            raise HTTPException(404, "grant not found")
        if grant.status in {GrantStatus.REVOKED, GrantStatus.EXPIRED}:
            return GrantRevokeResponse(grant=_public_grant(grant), changed=False)

        previous_status = grant.status
        MGR.revoke(grant_id)
        try:
            _log(EventType.REVOKE, grant.id, "grant revoked", now=request_now)
        except HTTPException:
            grant.status = previous_status
            raise
        return GrantRevokeResponse(grant=_public_grant(grant), changed=True)


@app.get("/ledger", dependencies=[Depends(require_owner)])
def ledger(limit: int = Query(default=100, ge=1, le=1_000)) -> list[dict[str, object]]:
    try:
        return LEDGER.read(limit, fail_on_unavailable=True)
    except OSError as exc:
        raise HTTPException(503, "audit ledger unavailable") from exc
