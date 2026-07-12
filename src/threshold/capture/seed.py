"""Fictional demo seed; never replace with a real dwelling export."""
from threshold.core.types import (Access, Grant, GrantStatus, Housefile, InventoryItem,
                                  Policies, Quirk, Scope, SystemItem, Zone)
from threshold.core.auth import token_digest
from threshold.core.config import SETTINGS


_DEMO_GRANT_DIGEST = (
    token_digest(SETTINGS.demo_grant_token)
    if SETTINGS.demo_mode and SETTINGS.demo_grant_token
    else ""
)

SEED_FILE = Housefile(
    dwelling_name="Threshold Demo House (Synthetic)",
    zones=(
        Zone("kitchen", "Kitchen", Access.OPEN, (0, 0, 150, 100)),
        Zone("living", "Living Room", Access.OPEN, (150, 0, 150, 100)),
        Zone("utility", "Utility", Access.OPEN, (300, 0, 100, 100), note="Panel wall"),
        Zone("studio", "Demo Studio", Access.RESTRICTED, (0, 100, 130, 100), note="Synthetic restricted-window example"),
        Zone("office", "Office", Access.OPEN, (130, 100, 130, 100)),
        Zone("workshop", "Workshop", Access.NO_GO, (260, 100, 140, 100), note="Owner only."),
        Zone("backlawn", "Back Lawn", Access.OPEN, (0, 200, 400, 120), outdoor=True),
        Zone("garden", "Vegetable Garden", Access.NO_GO, (300, 200, 100, 120), outdoor=True, note="Stay-out: seedlings"),
    ),
    systems=(
        SystemItem("sys-water", "Demo water shutoff", "utility", "water", "Synthetic marker W on the utility-room plan."),
        SystemItem("sys-power", "Demo breaker panel", "utility", "power", "Synthetic circuit label K for the demo kitchen."),
        SystemItem("sys-hvac", "Demo HVAC filter", "utility", "hvac", "Synthetic maintenance marker H."),
    ),
    inventory=(
        InventoryItem("inv-edge", "Edge compute demo unit", "workshop", ("do-not-touch", "high-value"), "Synthetic inventory item."),
        InventoryItem("inv-sculpture", "Foam calibration sculpture", "living", ("fragile",), "Synthetic fragile-object example."),
        InventoryItem("inv-cookware", "Demo cookware", "kitchen", ("never-soap",), "Synthetic handling-rule example."),
    ),
    quirks=(
        Quirk("q1", "kitchen", "Synthetic obstacle marker A requires a slower approach."),
        Quirk("q2", "living", "Synthetic quiet-zone marker activates after 21:00."),
    ),
    policies=Policies(),
)

SEED_GRANTS = [
    Grant("g-neo", "NEO Unit 04", "humanoid",
          (Scope.READ_LAYOUT, Scope.READ_INVENTORY, Scope.CMD_NAVIGATE, Scope.CMD_MANIPULATE),
          ("kitchen", "living", "office", "utility"), issued="2026-07-13T09:12:00Z",
          credential_digest=_DEMO_GRANT_DIGEST),
    Grant("g-mower", "Automower 430X", "agent",
          (Scope.READ_LAYOUT, Scope.CMD_NAVIGATE), ("backlawn",),
          window="standing", issued="2026-07-10T06:00:00Z"),
    Grant("g-clean", "Sparkle Cleaning Co.", "human",
          (Scope.READ_LAYOUT, Scope.READ_SYSTEMS),
          ("kitchen", "living", "studio", "office", "utility"),
          window="standing", issued="2026-07-13T09:30:00Z"),
]
