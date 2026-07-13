# SPEC — THS-0.1 · the housefile

Status: DRAFT-A (frozen for build week) · Owner: The Architect.

## 1. Object model
`Housefile { schema:"ths/0.1", dwelling, zones[], systems[], inventory[], quirks[], policies, rev }`

- **Zone** `{id, name, access: open|restricted|no-go, boundary:[x,y,w,h] (dwelling frame), note?, outdoor?:bool}`
  - `outdoor:true` zones map to mower work-areas / stay-out zones (INTEGRATIONS §2).
- **SystemItem** `{id, name, zone, tag: water|power|hvac|net, detail}`
- **InventoryItem** `{id, name, zone, flags[], note?}` — reserved flags: `fragile`, `do-not-touch`, `high-value`.
- **Quirk** `{id, zone, text}` — tribal knowledge, transmitted with layout scope.
- **Policies** `{quietHours{start,end}, teleop:"per-session"|"never", residency:"local-first"}`

## 2. Grants
`Grant {id, name, kind: humanoid|agent|human, scopes[], zones[], window, expires, status: active|revoked|expired|suspended, issued}`

Scopes: `read:layout` · `read:systems` · `read:inventory` · `command:navigate` · `command:manipulate`.
No-go zones are **ungrantable** — issue-time validation error, visible to the owner, never a silent strip.

`window` is either `standing` or `<RFC3339 start>/<RFC3339 end>`. Timestamps must include
a timezone offset. A one-time window is start-inclusive and end-exclusive: `start <= now <
end`; reaching its end marks the grant expired. `expires` is either `revocable` or one
timezone-aware RFC3339 timestamp, and `now >= expires` marks the grant expired. Issue-time
validation rejects already-ended policies and policies with no usable intersection.

The local API generates `id` and `issued`. A new credential arrives separately from the
JSON grant body, is hashed immediately, and is never part of the public Grant projection.
Issued grant metadata is process-local in v0.1 and resets when the node restarts.
Owner and per-grant credentials are distinct bounded visible-ASCII values suitable for
masked HTTP header fields.

## 3. Scoped read — normative semantics (housefile/scoped_view.py)
1. Pure `scoped_view()` returns `{error:"grant_inactive"}` with no resource fields when
   `status != active`. The API normally intercepts that state first, durably appends DENY,
   and returns HTTP `403`; the pure function itself performs no I/O.
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
Append-only JSON Lines `{ts, type: GRANT|READ|DENY|REVOKE|ESTOP|PROVISION, agent, detail,
tier?}` in ignored local storage. API-boundary events append and fsync before a successful
payload or state-change response. Reads are bounded and tolerate corrupt lines. The ledger
rejects malformed historical entries rather than inventing missing fields. The ledger is
durable but is not hash-chained or tamper-evident. ESTOP entries are never pruned.

## 6. Vision proposal boundary

`ths/vision-proposal/0.1` is a private review artifact, not a `ths/0.1` Housefile. It may
contain one locally identified zone candidate, bounded inventory candidates with only the
reserved `fragile|do-not-touch|high-value` flags, evidence frame references, confidence
levels, and owner-facing uncertainties. It MUST NOT contain or imply boundary geometry,
access, policies, grants, commands, enforcement tiers, canonical paths, or applied state.
THS-0022 owns geometry.

Provider output uses a separate strict observation schema and is untrusted even when the
provider reports schema adherence. Local validation rejects unknown fields, type coercion,
duplicate keys/names/references, non-finite values, control characters, excessive counts or
lengths, unrecognized flags, and references to frames not sent to the model. Candidate IDs
are generated locally after validation.

The persisted proposal binds its batch ID, capture-manifest hash, ordered frame hashes,
provider/model, prompt version, and validator version. An owner decision binds the exact
proposal digest and is terminal: one confirm or reject record. “Confirmed” means
owner-approved proposal only. It does not create geometry, change a revision, mutate
grants, or write the canonical housefile. Hash binding detects later changes but is not
tamper evidence against an attacker who controls the local filesystem.
