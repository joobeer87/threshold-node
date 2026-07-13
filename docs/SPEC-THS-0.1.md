# SPEC — THS-0.1 · the housefile

Status: DRAFT-A (frozen for build week) · Owner: The Architect.

## 1. Object model
`Housefile { schema:"ths/0.1", dwelling, zones[], systems[], inventory[], quirks[], policies, rev }`

- **Zone** `{id, name, access: open|restricted|no-go, boundary:[x,y,w,h] (dwelling frame), note?, outdoor?:bool}`
  - `outdoor:true` zones map to mower work-areas / stay-out zones (INTEGRATIONS §2).
- **SystemItem** `{id, name, zone, tag: water|power|hvac|net, detail}`
- **InventoryItem** `{id, name, zone, flags[], note?}` — reserved flags: `fragile`, `do-not-touch`, `high-value`.
- **Quirk** `{id, zone, text}` — tribal knowledge, transmitted with layout scope.
- **Policies** `{quietHours{start,end,timezone}, teleop:"per-session"|"never", residency:"local-first"}`
  - `start` and `end` use zero-padded `HH:MM`; `timezone` is an explicit IANA timezone
    identifier resolved by the node through `zoneinfo.ZoneInfo`.

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
The private authoritative store persists complete grant metadata across restart but stores
only a digest of each bearer credential; raw credentials never persist. Owner and per-grant
credentials are distinct bounded visible-ASCII values suitable for masked HTTP header
fields.

Grant revisions are committed through the local ledger rather than by a naive two-file
save-and-rollback sequence. A pending envelope binds the exact target grants, base/target
revision, prepared event bytes, ledger checkpoint, and receipt digest. A pending issue is
not part of the effective grant set before its ledger receipt. Pending revoke, expiry, and
suspend transitions expose their restrictive target state, so recovery cannot temporarily
reactivate a grant. Recovery aborts an uncommitted issue, rolls an uncommitted restrictive
transition forward, or finalizes a transition whose exact ledger receipt is already
present. Pending recovery first reconstructs the base snapshot, compares it with the prior
clean target hash, and verifies that prior revision's ledger receipt. Corrupt, ambiguous,
or witness-mismatched authority state makes grant operations unavailable with HTTP `503`;
it never falls back to seeds. First-boot synthetic seeding is allowed only in explicit demo
mode. This is crash-consistency evidence, not tamper evidence.

Revoke, observed expiry, and simulated-interlock suspension therefore survive restart.
Every new simulated trip commits an ESTOP transition even when no active grant needs a
status change. Expiry is persisted when a request first observes the exact
expiry/window-end boundary; the pure manager computes the transition but does not mutate
state before the authority commits it.

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
6. `policies.quietHours`, including its IANA `timezone`, always transmits. `capabilities` =
   granted `command:*` scopes only.
7. Ledger entry appends **before** the payload returns. No unlogged reads.

## 4. Enforcement tiers — label the guarantee
| Tier | Meaning | Example |
|---|---|---|
| **ENFORCED** | Device-native keep-out set via its API | Matter Service Area selection; Automower stay-out zone ON |
| **GATED** | Threshold refuses to relay out-of-grant commands | HA service calls filtered by grant |
| **ADVISORY** | Logged + displayed only | legacy device, manual override |
Adapters compute tier from capabilities; asserting it by hand fails audit test T-ENF-01.
An ADVISORY zone presented as ENFORCED is a spec violation.

## 5. Quiet-hours command policy

Quiet hours gate `command:*` operations only; they do not gate scoped reads. The API
captures UTC exactly once while holding the grant lock, uses the same instant for the grant
decision and receipt, converts it to `policies.quietHours.timezone`, and then evaluates the
local wall-clock interval. Intervals are start-inclusive and end-exclusive. An overnight
interval wraps across midnight, and equal start/end values mean quiet hours are active all
day.

When quiet hours are active, the node appends and fsyncs DENY before returning `403` with
`relayed:false`. If the timezone cannot be resolved or the quiet-hours policy is malformed,
the node appends and fsyncs DENY, relays nothing, and returns `503`. A schema-shaped timezone
string is not sufficient proof that the host has that IANA definition; runtime resolution
is authoritative.

## 6. Ledger
Append-only JSON Lines `{ts, type: GRANT|READ|DENY|REVOKE|ESTOP|PROVISION, agent, detail,
tier?, transaction?, grant_revision?}` in ignored local storage. `transaction` and
`grant_revision` are an optional pair reserved for revisioned grant-authority commits.
API-boundary events append and fsync before a successful payload or state-change response.
Bounded owner reads tolerate corrupt unrelated lines and reject malformed fields rather
than inventing data. Grant recovery is stricter: the current authority revision must verify
its exact witnessed ledger line. The ledger is durable but is not hash-chained or
tamper-evident. ESTOP entries are never pruned.

The current ESTOP producer is an owner-authenticated simulated route gated by explicit demo
mode and exact `ESP32_SERIAL=SIMULATED`. It latches the serving process before persistence;
successful persistence suspends active grants, while failure leaves the process denying use
and refusing re-arm. Duplicate trips in one latch cycle do not append duplicate ESTOP
events. Re-arm never restores grants. The latch and elapsed measurement are process-local
`simulated_software_path_only` evidence, not proof of physical input, adapter delivery, or
device stop.

## 7. Vision proposal boundary

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
