"""THS-0010 — the whole thesis, pure. SPEC-THS-0.1 §3, rules 1–7.
No I/O, no clock, no globals. Ledger writes happen at the API boundary."""
from __future__ import annotations
from threshold.core.types import (Access, Grant, GrantStatus, Housefile, SAFETY_FLAGS, Scope)


def scoped_view(file: Housefile, grant: Grant) -> dict:
    if grant.status != GrantStatus.ACTIVE:                                   # rule 1
        return {"schema": file.schema, "error": "grant_inactive",
                "grant": grant.id, "status": grant.status.value}

    # Defense in depth: never trust grants loaded outside GrantManager.issue().
    granted = {
        zone_id
        for zone_id in grant.zones
        if (zone := file.zone(zone_id)) is not None and zone.access != Access.NO_GO
    }
    out: dict = {
        "schema": file.schema,
        "grant": {"id": grant.id, "agent": grant.name,
                  "scopes": [s.value for s in grant.scopes], "window": grant.window},
        "policies": {"quietHours": {"start": file.policies.quiet_start,      # rule 6
                                    "end": file.policies.quiet_end,
                                    "timezone": file.policies.timezone},
                     "teleop": file.policies.teleop},
    }

    if Scope.READ_LAYOUT in grant.scopes:
        zones = []
        for z in file.zones:
            if z.access == Access.NO_GO:                                     # rule 2
                zones.append({"id": z.id, "access": "no-go", "boundary": list(z.boundary)})
            elif z.id not in granted:                                        # rule 3
                zones.append({"id": z.id, "disclosed": False})
            else:
                d = {"id": z.id, "name": z.name, "access": z.access.value,
                     "boundary": list(z.boundary)}
                if z.note: d["note"] = z.note
                if z.outdoor: d["outdoor"] = True
                zones.append(d)
        out["zones"] = zones
        out["quirks"] = [{"zone": q.zone, "text": q.text}
                         for q in file.quirks if q.zone in granted]

    if Scope.READ_SYSTEMS in grant.scopes:                                   # rule 4
        out["systems"] = [{"name": s.name, "zone": s.zone, "detail": s.detail}
                          for s in file.systems if s.zone in granted]

    if Scope.READ_INVENTORY in grant.scopes:                                 # rule 4
        out["inventory"] = [{"name": i.name, "zone": i.zone, "flags": list(i.flags),
                             **({"note": i.note} if i.note else {})}
                            for i in file.inventory if i.zone in granted]

    out["safety"] = [{"zone": i.zone,                                        # rule 5
                      "flags": [f for f in i.flags if f in SAFETY_FLAGS]}
                     for i in file.inventory
                     if i.zone in granted and any(f in SAFETY_FLAGS for f in i.flags)]

    out["capabilities"] = [s.value for s in grant.scopes if s.value.startswith("command:")]
    return out
