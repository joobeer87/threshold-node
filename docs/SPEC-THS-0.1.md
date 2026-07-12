# SPEC — THS-0.1 · the housefile

Status: DRAFT-A (frozen for build week) · Owner: The Architect.

## 1. Object model
`Housefile { schema:"ths/0.1", dwelling, zones[], systems[], inventory[], quirks[], policies, rev }`

- **Zone** `{id, name, access: open|restricted|no-go, boundary:[x,y,w,h] (dwelling frame), note?, outdoor?:bool}`
  - `outdoor:true` zones map to mower work-areas / stay-out zones (INTEGRATIONS §2).
- **SystemItem** `{id, name, zone, tag: water|power|hvac|net, detail}`
- **InventoryItem** `{id, name, zone, flags[], note?}` — reserved flags: `fragile`, `do-not-touch`, `high-value`.
- **Quirk** `{id, zone, text}` — tribal knowledge, transmitted with layout scope.
- **Policies** `{quietHours{start,end}, teleop:"per-session"|"never", residency:"local-first", safetyMeta:"always"}`

## 2. Grants
`Grant {id, name, kind: humanoid|agent|human, scopes[], zones[], window, expires, status: active|revoked|expired|suspended, issued}`

Scopes: `read:layout` · `read:systems` · `read:inventory` · `command:navigate` · `command:manipulate`.
No-go zones are **ungrantable** — issue-time validation error, visible to the owner, never a silent strip.

## 3. Scoped read — normative semantics (housefile/scoped_view.py)
1. `status != active` → `{error:"grant_inactive"}` and a DENY ledger entry. Nothing else transmits.
2. **No-go zones ALWAYS transmit** as `{id, access:"no-go", boundary}` — a robot must know
   where not to go; it never learns what's inside. Boundary yes, interior no.
3. Zones outside the grant → `{id, disclosed:false}`. Existence acknowledged; geometry withheld.
4. `read:systems` / `read:inventory` filter to granted zones only.
5. **Safety invariant:** `fragile|do-not-touch` flags in granted zones transmit even WITHOUT
   `read:inventory` (as `safety[]`, name-free). Safety metadata is not a privilege tier.
6. `policies.quietHours` always transmits. `capabilities` = granted `command:*` scopes only.
7. Ledger entry appends **before** the payload returns. No unlogged reads.

## 4. Enforcement tiers — label the guarantee
| Tier | Meaning | Example |
|---|---|---|
| **ENFORCED** | Device-native keep-out set via its API | Matter Service Area selection; Automower stay-out zone ON |
| **GATED** | Threshold refuses to relay out-of-grant commands | HA service calls filtered by grant |
| **ADVISORY** | Logged + displayed only | legacy device, manual override |
Adapters compute tier from capabilities; asserting it by hand fails audit test T-ENF-01.
An ADVISORY zone presented as ENFORCED is a spec violation.

## 5. Ledger
Append-only `{ts, type: GRANT|READ|DENY|REVOKE|ESTOP|PROVISION, agent, detail, tier?}`. ESTOP entries are never pruned.
