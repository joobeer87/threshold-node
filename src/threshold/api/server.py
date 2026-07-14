"""THS-0014/0015/0016 — authenticated API with durable policy receipts."""

from __future__ import annotations

import copy
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from hmac import compare_digest
from threading import RLock
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field, SecretStr

from threshold.capture.seed import SEED_FILE, SEED_GRANTS
from threshold.core.auth import is_valid_bearer_token, token_digest
from threshold.core.config import SETTINGS, Settings
from threshold.core.errors import ValidationError as ThresholdValidationError
from threshold.core.events import BUS
from threshold.core.ledger import JsonlLedger
from threshold.core.quiet_hours import evaluate_command_quiet_hours
from threshold.core.types import Access, EventType, Grant, GrantStatus, Housefile, Scope
from threshold.grants.authority import (
    GrantAuthenticationFailed,
    GrantAuthority,
    GrantAuthorityUnavailable,
    GrantCredentialConflict,
)
from threshold.grants.manager import normalize_time
from threshold.grants.store import GrantMetadataStore
from threshold.hardware.display import DisplayState
from threshold.hardware.estop import (
    SIMULATED_TIMING_SCOPE,
    InterlockState,
    SimulatedLatchedInterlock,
    TripNotice,
    TripReport,
)
from threshold.hardware.receipt import build_receipt, render_receipt_png
from threshold.housefile.scoped_view import scoped_view


app = FastAPI(
    title="Threshold Node",
    version="0.1.0",
    description=(
        "Pre-alpha local permission node with simulated software-path interlocks; "
        "physical safety hardware is not implemented or verified."
    ),
)
FILE: Housefile = SEED_FILE
GRANT_LOCK = RLock()
LEDGER = JsonlLedger(SETTINGS.ledger_path)
ADAPTERS: tuple[object, ...] = ()
DISPLAY_STATE = DisplayState()
OWNER_CONSOLE_ORIGINS = frozenset({"http://127.0.0.1:5173"})
OWNER_CORS_HEADERS = frozenset(
    {
        "content-type",
        "x-threshold-owner-token",
        "x-threshold-new-grant-token",
    }
)


def _demo_seeds(settings: Settings) -> tuple[Grant, ...]:
    if not (
        settings.demo_mode
        and is_valid_bearer_token(settings.demo_grant_token)
        and (
            settings.owner_token is None
            or not compare_digest(settings.owner_token, settings.demo_grant_token)
        )
    ):
        return ()
    seed = copy.deepcopy(next(item for item in SEED_GRANTS if item.id == "g-neo"))
    seed.credential_digest = token_digest(settings.demo_grant_token)
    return (seed,)


AUTHORITY = GrantAuthority(
    FILE,
    GrantMetadataStore(SETTINGS.grant_store_path),
    LEDGER,
    demo_mode=SETTINGS.demo_mode,
    demo_seeds=_demo_seeds(SETTINGS),
    observer=BUS.emit,
)
MGR = AUTHORITY.manager
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


class OwnerDwelling(BaseModel):
    name: str


class OwnerZone(BaseModel):
    id: str
    name: str
    access: Access
    boundary: tuple[float, float, float, float]
    note: str
    outdoor: bool


class OwnerSystem(BaseModel):
    id: str
    name: str
    zone: str
    tag: str
    detail: str


class OwnerInventory(BaseModel):
    id: str
    name: str
    zone: str
    flags: tuple[str, ...]
    note: str


class OwnerQuirk(BaseModel):
    id: str
    zone: str
    text: str


class OwnerQuietHours(BaseModel):
    start: str
    end: str
    timezone: str


class OwnerPolicies(BaseModel):
    quietHours: OwnerQuietHours
    teleop: str
    residency: str


class OwnerHousefile(BaseModel):
    schema_id: str = Field(alias="schema")
    rev: str
    dwelling: OwnerDwelling
    zones: tuple[OwnerZone, ...]
    systems: tuple[OwnerSystem, ...]
    inventory: tuple[OwnerInventory, ...]
    quirks: tuple[OwnerQuirk, ...]
    policies: OwnerPolicies


class OwnerHealth(BaseModel):
    service: Literal["up"]
    release_stage: Literal["pre-alpha"]
    armed: Literal[False]
    interlock: Literal["simulated_latched", "simulated_disabled"]
    interlock_state: Literal["ARMED", "TRIPPED"]
    physical_stop_verified: Literal[False]
    timing_scope: Literal["simulated_software_path_only"]
    ledger: Literal["persistent_jsonl_configured"]
    ledger_availability: Literal["not_probed"]
    grant_store: Literal["authoritative_digest_only_configured"]
    grant_store_availability: Literal["not_probed"]
    adapters: tuple[str, ...]
    demo_mode: bool


class OwnerDisplay(BaseModel):
    state: Literal["ARMED", "READ", "DENY", "TRIPPED", "UNAVAILABLE"]
    agent: str | None = None


class OwnerStatus(BaseModel):
    health: OwnerHealth
    display: OwnerDisplay
    active_grants: int = Field(ge=0)


class OwnerLedgerEvent(BaseModel):
    ts: str
    type: EventType
    agent: str
    detail: str
    tier: str | None = None


class OwnerSnapshot(BaseModel):
    housefile: OwnerHousefile
    grants: tuple[PublicGrant, ...]
    status: OwnerStatus
    ledger: tuple[OwnerLedgerEvent, ...]


class GrantIssueResponse(BaseModel):
    grant: PublicGrant
    credential_registered: bool


class GrantRevokeResponse(BaseModel):
    grant: PublicGrant
    changed: bool


class SimulatedTripResponse(BaseModel):
    state: Literal["TRIPPED"]
    newly_tripped: bool
    persistence_succeeded: bool
    suspended_grants: int
    adapter_call_attempts: int
    adapter_call_completions: int
    adapter_call_failures: int
    simulated_display_updated: bool
    synthetic_receipt_rendered: bool
    simulated_elapsed_ms: float | None
    timing_scope: Literal["simulated_software_path_only"]
    physical_stop_verified: Literal[False]


class SimulatedRearmResponse(BaseModel):
    state: Literal["ARMED"]
    changed: bool
    grants_restored: Literal[False]
    timing_scope: Literal["simulated_software_path_only"]
    physical_stop_verified: Literal[False]


def _owner_methods(path: str) -> frozenset[str]:
    """Return the exact methods that cross-origin console calls may use."""

    if path in {"/owner/snapshot", "/owner/status", "/ledger"}:
        return frozenset({"GET"})
    if path == "/grants" or path in {
        "/sim/interlock/trip",
        "/sim/interlock/rearm",
    }:
        return frozenset({"POST"})
    if path.startswith("/grants/") and path.endswith("/revoke"):
        return frozenset({"POST"})
    return frozenset()


def _owner_origin_allowed(request: Request) -> bool:
    """Allow no Origin, the request's exact origin, or the fixed Vite origin."""

    origin = request.headers.get("origin")
    if origin is None:
        return True
    request_origin = f"{request.url.scheme}://{request.url.netloc}"
    return origin == request_origin or origin in OWNER_CONSOLE_ORIGINS


def _cors_response_headers(origin: str, methods: frozenset[str]) -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Methods": ", ".join(sorted(methods)),
        "Access-Control-Allow-Headers": ", ".join(sorted(OWNER_CORS_HEADERS)),
        "Vary": "Origin",
    }


@app.middleware("http")
async def owner_console_origin_policy(request: Request, call_next):
    """Reject foreign owner-console origins and answer bounded preflights."""

    requested_method = request.method
    if request.method == "OPTIONS":
        requested_method = request.headers.get(
            "access-control-request-method",
            "",
        ).upper()
    methods = _owner_methods(request.url.path)
    is_owner_route = requested_method in methods
    if not is_owner_route:
        return await call_next(request)

    if not _owner_origin_allowed(request):
        return JSONResponse(
            status_code=403,
            content={"detail": "owner origin not allowed"},
        )

    origin = request.headers.get("origin")
    if request.method == "OPTIONS":
        if origin is None:
            return JSONResponse(
                status_code=403,
                content={"detail": "owner origin not allowed"},
            )
        requested_headers = {
            item.strip().lower()
            for item in request.headers.get(
                "access-control-request-headers",
                "",
            ).split(",")
            if item.strip()
        }
        if not requested_headers.issubset(OWNER_CORS_HEADERS):
            return JSONResponse(
                status_code=403,
                content={"detail": "owner headers not allowed"},
            )
        return Response(
            status_code=204,
            headers=_cors_response_headers(origin, methods),
        )

    response = await call_next(request)
    if origin is not None:
        response.headers.update(_cors_response_headers(origin, methods))
    return response


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


def _request_utc() -> datetime:
    """Capture and normalize the request clock exactly once under the grant lock."""

    try:
        return normalize_time(_now(), "current time")
    except ThresholdValidationError as exc:
        raise HTTPException(503, "node clock is invalid") from exc


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


def _owner_housefile(file: Housefile) -> OwnerHousefile:
    """Project the canonical in-memory THS shape without generic serialization."""

    return OwnerHousefile(
        schema=file.schema,
        rev=file.rev,
        dwelling=OwnerDwelling(name=file.dwelling_name),
        zones=tuple(
            OwnerZone(
                id=zone.id,
                name=zone.name,
                access=zone.access,
                boundary=zone.boundary,
                note=zone.note,
                outdoor=zone.outdoor,
            )
            for zone in file.zones
        ),
        systems=tuple(
            OwnerSystem(
                id=item.id,
                name=item.name,
                zone=item.zone,
                tag=item.tag,
                detail=item.detail,
            )
            for item in file.systems
        ),
        inventory=tuple(
            OwnerInventory(
                id=item.id,
                name=item.name,
                zone=item.zone,
                flags=item.flags,
                note=item.note,
            )
            for item in file.inventory
        ),
        quirks=tuple(
            OwnerQuirk(id=item.id, zone=item.zone, text=item.text)
            for item in file.quirks
        ),
        policies=OwnerPolicies(
            quietHours=OwnerQuietHours(
                start=file.policies.quiet_start,
                end=file.policies.quiet_end,
                timezone=file.policies.timezone,
            ),
            teleop=file.policies.teleop,
            residency=file.policies.residency,
        ),
    )


def _owner_health() -> OwnerHealth:
    return OwnerHealth(
        service="up",
        release_stage="pre-alpha",
        armed=False,
        interlock=(
            "simulated_latched"
            if _simulated_appliance_enabled()
            else "simulated_disabled"
        ),
        interlock_state=INTERLOCK.state.value,
        physical_stop_verified=False,
        timing_scope=SIMULATED_TIMING_SCOPE,
        ledger="persistent_jsonl_configured",
        ledger_availability="not_probed",
        grant_store="authoritative_digest_only_configured",
        grant_store_availability="not_probed",
        adapters=(),
        demo_mode=SETTINGS.demo_mode,
    )


def _owner_grants(*, now: datetime) -> tuple[Grant, ...]:
    """Copy one verified authority revision for a stable owner projection."""

    try:
        grants = AUTHORITY.snapshot(now=now)
    except GrantAuthorityUnavailable as exc:
        raise HTTPException(503, "grant authority unavailable") from exc
    return tuple(sorted(grants.values(), key=lambda item: item.id))


def _owner_status(*, now: datetime, grants: tuple[Grant, ...]) -> OwnerStatus:
    active_grants = sum(
        grant.status == GrantStatus.ACTIVE for grant in grants
    )
    try:
        frame = DISPLAY_STATE.frame(active_grants=active_grants, now=now)
        display = OwnerDisplay(state=frame.mode.value, agent=frame.agent)
    except Exception:
        display = OwnerDisplay(state="UNAVAILABLE")
    return OwnerStatus(
        health=_owner_health(),
        display=display,
        active_grants=active_grants,
    )


def _owner_ledger(limit: int) -> tuple[OwnerLedgerEvent, ...]:
    try:
        entries = LEDGER.read(limit, fail_on_unavailable=True)
    except OSError as exc:
        raise HTTPException(503, "audit ledger unavailable") from exc
    return tuple(
        OwnerLedgerEvent(
            ts=str(entry["ts"]),
            type=EventType(str(entry["type"])),
            agent=str(entry["agent"]),
            detail=str(entry["detail"]),
            tier=str(entry["tier"]) if "tier" in entry else None,
        )
        for entry in entries
    )


def _ensure_authority(now: datetime) -> None:
    try:
        AUTHORITY.ensure_ready(now=now)
    except GrantAuthorityUnavailable as exc:
        raise HTTPException(503, "grant authority unavailable") from exc


async def require_owner(
    request: Request,
    x_threshold_owner_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Owner-Token",
    ),
) -> None:
    """Reject sensitive requests when auth is missing or unconfigured."""

    if not _owner_origin_allowed(request):
        raise HTTPException(403, "owner origin not allowed")
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
    except ThresholdValidationError as exc:
        raise HTTPException(503, "node clock is invalid") from exc
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


def _simulated_appliance_enabled() -> bool:
    """Limit the control surface to the explicit synthetic demo appliance."""

    return SETTINGS.demo_mode and SETTINGS.esp32_serial == "SIMULATED"


def _display_read(agent: str, *, now: datetime) -> None:
    """Publish a best-effort transient only after the READ receipt is durable."""

    global DISPLAY_STATE
    try:
        DISPLAY_STATE = DISPLAY_STATE.on_read(agent, now=now)
    except Exception:
        return


def _display_deny(agent: str, *, now: datetime) -> None:
    """Publish a best-effort transient only after a restrictive decision."""

    global DISPLAY_STATE
    try:
        DISPLAY_STATE = DISPLAY_STATE.on_deny(agent, now=now)
    except Exception:
        return


def _interlock_display(state: InterlockState) -> None:
    """Latch the simulated terminal display before slower trip work begins."""

    global DISPLAY_STATE
    if state != InterlockState.TRIPPED:
        raise ValueError("simulated interlock display state is invalid")
    DISPLAY_STATE = DISPLAY_STATE.trip()


def _interlock_receipt(notice: TripNotice) -> None:
    """Exercise the deterministic in-memory ESTOP PNG fallback.

    Runtime persistence remains the JSONL ESTOP receipt owned by
    :class:`GrantAuthority`.  The bitmap is generated and discarded: no public
    artifact, household data, or credential material is written.
    """

    if not notice.persistence_succeeded or notice.tripped_at is None:
        raise ValueError("simulated receipt unavailable")
    receipt = build_receipt(
        EventType.ESTOP,
        occurred_at=notice.tripped_at,
        sequence=AUTHORITY.revision,
        actor="SYSTEM",
    )
    render_receipt_png(receipt)


def _build_simulated_interlock() -> SimulatedLatchedInterlock:
    """Build an injected, side-effect-bounded appliance coordinator."""

    return SimulatedLatchedInterlock(
        lambda *, now: AUTHORITY.suspend_all(now=now),
        ADAPTERS,
        utc_clock=_request_utc,
        display=_interlock_display,
        receipt=_interlock_receipt,
    )


def _trip_response(report: TripReport) -> SimulatedTripResponse:
    """Project only bounded counters and explicit simulation nonclaims."""

    if not report.persistence_succeeded or report.suspended_grants is None:
        raise HTTPException(
            503,
            detail={
                "state": InterlockState.TRIPPED.value,
                "reason": "durable grant suspension unavailable",
                "timing_scope": SIMULATED_TIMING_SCOPE,
                "physical_stop_verified": False,
            },
        )
    return SimulatedTripResponse(
        state="TRIPPED",
        newly_tripped=report.newly_tripped,
        persistence_succeeded=True,
        suspended_grants=report.suspended_grants,
        adapter_call_attempts=report.adapter_attempts,
        adapter_call_completions=report.adapter_completions,
        adapter_call_failures=report.adapter_failures,
        simulated_display_updated=(
            report.display_attempts == 1 and report.display_failures == 0
        ),
        synthetic_receipt_rendered=(
            report.receipt_attempts == 1 and report.receipt_failures == 0
        ),
        simulated_elapsed_ms=report.simulated_elapsed_ms,
        timing_scope="simulated_software_path_only",
        physical_stop_verified=False,
    )


INTERLOCK = _build_simulated_interlock()


@contextmanager
def _usable_grant(
    grant_id: str,
    supplied_token: SecretStr | None,
    *,
    action: Literal["scoped read", "command"],
    now: datetime,
) -> Iterator[Grant]:
    raw_token = (
        supplied_token.get_secret_value() if supplied_token is not None else None
    )
    try:
        with AUTHORITY.authorized(
            grant_id,
            raw_token,
            now=now,
            action=action,
        ) as (grant, decision):
            if not decision.allowed:
                if decision.next_status is None:
                    _log(
                        EventType.DENY,
                        grant.id,
                        f"{action} refused: {decision.reason}",
                        now=now,
                    )
                _display_deny(grant.id, now=now)
                raise HTTPException(
                    403,
                    detail={"policy_decision": "denied", "reason": decision.reason},
                )
            if INTERLOCK.state == InterlockState.TRIPPED:
                _log(
                    EventType.DENY,
                    grant.id,
                    f"{action} refused: simulated interlock tripped",
                    now=now,
                )
                _display_deny(grant.id, now=now)
                raise HTTPException(
                    403,
                    detail={
                        "policy_decision": "denied",
                        "reason": "interlock_tripped",
                    },
                )
            yield grant
    except GrantAuthenticationFailed as exc:
        raise HTTPException(401, "grant authentication required") from exc
    except GrantAuthorityUnavailable as exc:
        raise HTTPException(503, "grant authority unavailable") from exc


@app.get("/health", response_model=OwnerHealth)
async def health() -> OwnerHealth:
    with GRANT_LOCK:
        return _owner_health()


@app.get(
    "/owner/status",
    response_model=OwnerStatus,
    response_model_exclude_none=True,
    dependencies=[Depends(require_owner)],
)
async def owner_status() -> OwnerStatus:
    """Return bounded health, interlock, and display state for the console."""

    with GRANT_LOCK:
        request_now = _request_utc()
        grants = _owner_grants(now=request_now)
        return _owner_status(now=request_now, grants=grants)


@app.get(
    "/owner/snapshot",
    response_model=OwnerSnapshot,
    response_model_exclude_none=True,
    dependencies=[Depends(require_owner)],
)
async def owner_snapshot(
    ledger_limit: int = Query(default=100, ge=1, le=1_000),
) -> OwnerSnapshot:
    """Return one owner-only, credential-free console snapshot."""

    with GRANT_LOCK:
        request_now = _request_utc()
        grants = _owner_grants(now=request_now)
        return OwnerSnapshot(
            housefile=_owner_housefile(FILE),
            grants=tuple(_public_grant(grant) for grant in grants),
            status=_owner_status(now=request_now, grants=grants),
            ledger=_owner_ledger(ledger_limit),
        )


@app.post(
    "/sim/interlock/trip",
    response_model=SimulatedTripResponse,
    dependencies=[Depends(require_owner)],
)
async def trip_simulated_interlock() -> SimulatedTripResponse:
    """Run the synthetic software path without claiming physical actuation."""

    with GRANT_LOCK:
        if not _simulated_appliance_enabled():
            raise HTTPException(503, "simulated appliance is not enabled")
        return _trip_response(INTERLOCK.trip())


@app.post(
    "/sim/interlock/rearm",
    response_model=SimulatedRearmResponse,
    dependencies=[Depends(require_owner)],
)
async def rearm_simulated_interlock() -> SimulatedRearmResponse:
    """Clear only a successfully persisted local latch; never restore grants."""

    global DISPLAY_STATE
    with GRANT_LOCK:
        if not _simulated_appliance_enabled():
            raise HTTPException(503, "simulated appliance is not enabled")
        previous = INTERLOCK.last_report
        if (
            INTERLOCK.state == InterlockState.TRIPPED
            and (previous is None or not previous.persistence_succeeded)
        ):
            raise HTTPException(
                503,
                detail={
                    "state": InterlockState.TRIPPED.value,
                    "reason": "durable grant suspension unavailable",
                    "grants_restored": False,
                },
            )
        changed = INTERLOCK.rearm()
        try:
            DISPLAY_STATE = DISPLAY_STATE.rearm()
        except Exception:
            pass
        return SimulatedRearmResponse(
            state="ARMED",
            changed=changed,
            grants_restored=False,
            timing_scope="simulated_software_path_only",
            physical_stop_verified=False,
        )


@app.get("/.well-known/aurora", include_in_schema=False)
async def aurora_signature() -> dict[str, object]:
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
async def housefile(
    grant: str,
    x_threshold_grant_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
) -> dict[str, object]:
    with GRANT_LOCK:
        request_now = _request_utc()
        with _usable_grant(
            grant,
            x_threshold_grant_token,
            action="scoped read",
            now=request_now,
        ) as active_grant:
            payload = scoped_view(FILE, active_grant)
            event_type = EventType.DENY if "error" in payload else EventType.READ
            _log(event_type, active_grant.id, "scoped read", now=request_now)
            if event_type == EventType.READ:
                _display_read(active_grant.id, now=request_now)
            else:
                _display_deny(active_grant.id, now=request_now)
            return payload


def _evaluate_command(
    body: CommandRequest,
    active_grant: Grant,
    *,
    now: datetime,
) -> None:
    try:
        policy_zone = ZoneInfo(FILE.policies.timezone)
        policy_now = now.astimezone(policy_zone)
    except (AttributeError, TypeError, ValueError, ZoneInfoNotFoundError):
        _log(
            EventType.DENY,
            active_grant.id,
            "command refused: quiet_hours_timezone_invalid",
            now=now,
        )
        _display_deny(active_grant.id, now=now)
        raise HTTPException(
            503,
            detail={
                "policy_decision": "denied",
                "relayed": False,
                "reason": "quiet_hours_timezone_invalid",
            },
        )
    quiet_hours = evaluate_command_quiet_hours(
        FILE.policies.quiet_start,
        FILE.policies.quiet_end,
        now=policy_now,
    )
    if not quiet_hours.allowed:
        _log(
            EventType.DENY,
            active_grant.id,
            f"command refused: {quiet_hours.reason}",
            now=now,
        )
        _display_deny(active_grant.id, now=now)
        raise HTTPException(
            403 if quiet_hours.reason == "quiet_hours_active" else 503,
            detail={
                "policy_decision": "denied",
                "relayed": False,
                "reason": quiet_hours.reason,
            },
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
            now=now,
        )
        _display_deny(active_grant.id, now=now)
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
            now=now,
        )
        _display_deny(active_grant.id, now=now)
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
        now=now,
        tier="UNAVAILABLE",
    )
    _display_deny(active_grant.id, now=now)
    raise HTTPException(
        503,
        detail={
            "policy_decision": "allowed",
            "relayed": False,
            "reason": "adapter_not_configured",
            "tier": "UNAVAILABLE",
        },
    )


@app.post("/command")
async def command(
    body: CommandRequest,
    x_threshold_grant_token: SecretStr | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
) -> None:
    with GRANT_LOCK:
        request_now = _request_utc()
        with _usable_grant(
            body.grant,
            x_threshold_grant_token,
            action="command",
            now=request_now,
        ) as active_grant:
            _evaluate_command(body, active_grant, now=request_now)


@app.post(
    "/grants",
    status_code=201,
    response_model=GrantIssueResponse,
)
async def issue_grant(
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

    if (
        not body.scopes
        or len(body.scopes) > 16
        or not body.zones
        or len(body.zones) > 32
    ):
        raise HTTPException(422, "grant needs bounded non-empty scopes and zones")
    if body.name != body.name.strip() or any(zone != zone.strip() for zone in body.zones):
        raise HTTPException(422, "grant text fields must not have surrounding whitespace")
    if len(set(body.scopes)) != len(body.scopes) or len(set(body.zones)) != len(
        body.zones
    ):
        raise HTTPException(422, "grant scopes and zones must be unique")

    with GRANT_LOCK:
        request_now = _request_utc()
        if INTERLOCK.state == InterlockState.TRIPPED:
            _display_deny("system", now=request_now)
            raise HTTPException(
                423,
                detail={
                    "policy_decision": "denied",
                    "reason": "interlock_tripped",
                },
            )
        _ensure_authority(request_now)
        try:
            issued = _rfc3339(request_now)
        except ThresholdValidationError as exc:
            raise HTTPException(503, "node clock is invalid") from exc
        if any(
            existing.credential_digest
            and compare_digest(credential_digest, existing.credential_digest)
            for existing in AUTHORITY.grants.values()
        ):
            raise HTTPException(409, "grant credential is already registered")

        grant_id = ""
        for _ in range(5):
            candidate = _new_grant_id()
            if candidate not in AUTHORITY.grants:
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
            grant = AUTHORITY.issue(grant, now=request_now)
        except GrantCredentialConflict as exc:
            raise HTTPException(409, "grant credential is already registered") from exc
        except ThresholdValidationError as exc:
            raise HTTPException(422, "grant policy is invalid") from exc
        except GrantAuthorityUnavailable as exc:
            raise HTTPException(503, "grant authority unavailable") from exc
        return GrantIssueResponse(
            grant=_public_grant(grant),
            credential_registered=True,
        )


@app.post(
    "/grants/{grant_id}/revoke",
    response_model=GrantRevokeResponse,
)
async def revoke_grant(
    grant_id: str,
    _owner: None = Depends(require_owner),
) -> GrantRevokeResponse:
    del _owner
    with GRANT_LOCK:
        request_now = _request_utc()
        _ensure_authority(request_now)
        grant = AUTHORITY.grants.get(grant_id)
        if grant is None:
            raise HTTPException(404, "grant not found")
        try:
            grant, changed = AUTHORITY.revoke(grant_id, now=request_now)
        except GrantAuthorityUnavailable as exc:
            raise HTTPException(503, "grant authority unavailable") from exc
        return GrantRevokeResponse(grant=_public_grant(grant), changed=changed)


@app.get("/ledger", dependencies=[Depends(require_owner)])
async def ledger(
    limit: int = Query(default=100, ge=1, le=1_000),
) -> list[dict[str, object]]:
    try:
        return LEDGER.read(limit, fail_on_unavailable=True)
    except OSError as exc:
        raise HTTPException(503, "audit ledger unavailable") from exc
