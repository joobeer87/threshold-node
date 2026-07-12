"""THS-0014/0015 — pre-alpha API with fail-closed request authentication."""
from __future__ import annotations
from datetime import datetime, timezone
from hmac import compare_digest
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from threshold.core.auth import token_matches
from threshold.core.config import SETTINGS, Settings
from threshold.core.events import BUS
from threshold.core.types import Access, EventType, Grant, GrantStatus, Housefile, Scope
from threshold.grants.manager import GrantManager
from threshold.housefile.scoped_view import scoped_view
from threshold.capture.seed import SEED_FILE, SEED_GRANTS  # demo boot state

app = FastAPI(
    title="Threshold Node",
    version="0.1.0",
    description="Pre-alpha local permission node; adapters and safety hardware are not implemented.",
)
FILE: Housefile = SEED_FILE
MGR = GrantManager(FILE)
for g in SEED_GRANTS: MGR.grants[g.id] = g
LEDGER: list[dict] = []


class CommandRequest(BaseModel):
    grant: str = Field(min_length=1, max_length=128)
    verb: Literal["navigate", "manipulate"]
    zone: str = Field(min_length=1, max_length=128)
    params: dict[str, object] = Field(default_factory=dict)

    class Config:
        extra = "forbid"


def require_owner(
    x_threshold_owner_token: str | None = Header(
        default=None,
        alias="X-Threshold-Owner-Token",
    ),
) -> None:
    """Reject sensitive requests when auth is missing or unconfigured."""
    settings: Settings = SETTINGS
    if settings.owner_token is None:
        raise HTTPException(503, "owner authentication is not configured")
    if x_threshold_owner_token is None or not compare_digest(
        x_threshold_owner_token,
        settings.owner_token,
    ):
        raise HTTPException(401, "owner authentication required")


def _authorized_grant(grant_id: str, supplied_token: str | None) -> Grant:
    grant = MGR.grants.get(grant_id)
    if grant is None or not token_matches(supplied_token, grant.credential_digest):
        raise HTTPException(401, "grant authentication required")
    return grant

def _log(t: EventType, agent: str, detail: str):
    e = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
         "type": t.value, "agent": agent, "detail": detail}
    LEDGER.insert(0, e); BUS.emit(t.value, e)

@app.get("/health")
def health():
    return {
        "service": "up",
        "release_stage": "pre-alpha",
        "armed": False,
        "interlock": "not_implemented",
        "ledger": "memory_only",
        "adapters": [],
        "demo_mode": SETTINGS.demo_mode,
    }


@app.get("/.well-known/aurora", include_in_schema=False)
def aurora_signature():
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
    x_threshold_grant_token: str | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
):
    g = _authorized_grant(grant, x_threshold_grant_token)
    if g.status != GrantStatus.ACTIVE:
        _log(EventType.DENY, g.name, "scoped read refused: grant inactive")
        raise HTTPException(403, "grant inactive")
    payload = scoped_view(FILE, g)                       # pure
    _log(EventType.DENY if "error" in payload else EventType.READ,
         g.name, "scoped read")                          # rule 7: log before return
    return payload

@app.post("/command")
def command(
    body: CommandRequest,
    x_threshold_grant_token: str | None = Header(
        default=None,
        alias="X-Threshold-Grant-Token",
    ),
):
    g = _authorized_grant(body.grant, x_threshold_grant_token)
    zone = FILE.zone(body.zone)
    required_scope = {
        "navigate": Scope.CMD_NAVIGATE,
        "manipulate": Scope.CMD_MANIPULATE,
    }[body.verb]
    if (
        g.status != GrantStatus.ACTIVE
        or zone is None
        or zone.id not in g.zones
        or zone.access == Access.NO_GO
        or required_scope not in g.scopes
    ):
        _log(EventType.DENY, g.name, f"command→{body.zone} refused")
        raise HTTPException(403, "gate refused")
    _log(EventType.DENY, g.name, f"command→{body.zone} not relayed: adapter unavailable")
    raise HTTPException(
        503,
        detail={
            "relayed": False,
            "reason": "adapter_not_configured",
            "tier": "UNAVAILABLE",
        },
    )

@app.get("/ledger", dependencies=[Depends(require_owner)])
def ledger(): return LEDGER
