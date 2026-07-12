"""THS-0011 — scoped_view suite. Every rule in SPEC-THS §3 gets a test."""
import pytest
from threshold.capture.seed import SEED_FILE
from threshold.core.errors import ValidationError
from threshold.core.types import Grant, GrantStatus, Scope
from threshold.grants.manager import GrantManager
from threshold.housefile.scoped_view import scoped_view


def g(scopes, zones, status=GrantStatus.ACTIVE):
    return Grant("g-t", "Test Agent", "agent", tuple(scopes), tuple(zones), status=status)

def zmap(view): return {z["id"]: z for z in view["zones"]}


def test_happy_path_layout():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT], ["kitchen", "living"]))
    zs = zmap(v)
    assert zs["kitchen"]["name"] == "Kitchen" and zs["kitchen"]["boundary"]
    assert v["policies"]["quietHours"]["start"] == "21:30"          # rule 6

def test_rule1_inactive_grant_transmits_nothing():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT], ["kitchen"], GrantStatus.REVOKED))
    assert v["error"] == "grant_inactive" and "zones" not in v

def test_rule2_no_go_boundary_always_transmits_interior_never():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT, Scope.READ_INVENTORY], ["kitchen"]))
    ws = zmap(v)["workshop"]
    assert ws["access"] == "no-go" and ws["boundary"]               # boundary yes
    assert "name" not in ws and "note" not in ws                    # interior no
    assert all(i["zone"] != "workshop" for i in v["inventory"])     # Jetson invisible

def test_rule3_ungrant_zones_acknowledged_not_described():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT], ["kitchen"]))
    off = zmap(v)["office"]
    assert off == {"id": "office", "disclosed": False}

def test_rule4_scope_filters():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT], ["kitchen", "utility"]))
    assert "systems" not in v and "inventory" not in v
    v2 = scoped_view(SEED_FILE, g([Scope.READ_SYSTEMS], ["utility"]))
    assert {s["name"] for s in v2["systems"]} == {
        "Demo water shutoff",
        "Demo breaker panel",
        "Demo HVAC filter",
    }

def test_rule5_safety_transmits_without_inventory_scope():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT], ["living"]))   # no read:inventory
    assert "inventory" not in v
    assert {"zone": "living", "flags": ["fragile"]} in v["safety"]   # volcano flag, name-free
    assert all("name" not in s for s in v["safety"])

def test_capabilities_only_command_scopes():
    v = scoped_view(SEED_FILE, g([Scope.READ_LAYOUT, Scope.CMD_NAVIGATE], ["kitchen"]))
    assert v["capabilities"] == ["command:navigate"]

def test_manager_refuses_no_go_grant_visibly():
    with pytest.raises(ValidationError, match="ungrantable"):
        GrantManager(SEED_FILE).issue(g([Scope.READ_LAYOUT], ["workshop"]))


def test_malformed_grant_cannot_disclose_no_go_interior():
    malformed = g([Scope.READ_LAYOUT, Scope.READ_INVENTORY], ["workshop"])
    view = scoped_view(SEED_FILE, malformed)
    workshop = zmap(view)["workshop"]
    assert workshop == {
        "id": "workshop",
        "access": "no-go",
        "boundary": [260, 100, 140, 100],
    }
    assert view["inventory"] == []
    assert view["safety"] == []
