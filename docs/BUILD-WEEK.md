# Build Week notes

Last checked: **2026-07-11**.

The challenge opens July 13 and submissions close July 21. The Devpost schedule currently
lists the deadline as July 21 at 5:00 p.m. PDT. The official rules, tracks, and complete
submission requirements were not published at the last check.

- Challenge: <https://openai.com/build-week/>
- Devpost: <https://openai.devpost.com/>
- Dates: <https://openai.devpost.com/details/dates>
- Rules: <https://openai.devpost.com/rules>
- Resources: <https://openai.devpost.com/resources>

## Two-project plan

I am building two candidate projects during the Build Week window. I want to take both far
enough to judge them by working software, then put the final polish, video, and submission
work behind the stronger project. Threshold Node can remain public as a prototype even if
the other project becomes my final Build Week entry.

I will choose based on:

- the strongest end-to-end demo;
- meaningful use of OpenAI models rather than a decorative chat feature;
- a problem and result that are clear in a short video;
- the fewest fragile or unproven dependencies;
- the best chance of reaching a polished, tested submission by the deadline.

When the rules are published, I will recheck eligibility, existing-project requirements,
submission limits, categories, repository visibility, required materials, available model
access, and the video limit before making the final choice.

## What the Threshold Node demo needs to show

1. A phone walk becomes a bounded, private local frame batch.
2. A guarded GPT-5.6 structured-output step turns selected frames into a constrained,
   incomplete observation proposal.
3. The owner reviews and confirms the digest-bound proposal. Deterministic THS-0022
   geometry and separate owner-reviewed THS-0023 materialization now have synthetic local
   proof; the model never chooses access, no-go, or outdoor status. Real-dwelling use and
   live API loading remain prohibited/unimplemented.
4. A synthetic software agent receives a scoped view and is denied access to a no-go zone.
5. The currently runnable software path shows terminal/receipt fallbacks and a latched trip
   that durably suspends grants. A Jetson-connected I/O rig and physical stop control remain
   future evidence and must not be inferred from the simulation.
6. The loopback owner console renders the synthetic blueprint, public grant projections,
   bounded ledger, and prominent simulated `TRIPPED` state, with grant issue/revoke. The
   owner accepted the corrected visual review on 2026-07-14; footage still requires the
   separate privacy and evidence checks.

The memorable object should be the physical threshold: the model may propose, but it
cannot bypass deterministic validation, owner confirmation, or the permission gate.

## Implementation

The edge node uses FastAPI and Pydantic. The implemented owner console uses exact-pinned
Vite, React, TypeScript, and Lucide packages with a committed npm lockfile. The hardware
path uses an ESP32 bridge with Arduino or PlatformIO. A virtual
Matter RVC is optional; the simulated agent and real I/O rig are enough for the primary
demo.

The proposal adapter uses the OpenAI Responses API with GPT-5.6 image input and strict
structured output. Upload requires an explicit flag; requests use `store:false` and no
tools. Provider output remains untrusted and is deterministically revalidated before a
private proposal can reach a separate owner-decision step.

Grant metadata is authoritative across restart in a private digest-only snapshot paired
with the decision ledger. A revisioned pending transaction makes the durable ledger receipt
the issue commit point and keeps restrictive transitions denied during recovery. Synthetic
seeding is limited to a genuinely empty first boot with explicit demo mode; existing corrupt
or ambiguous state returns unavailable instead of falling back to seeds. Quiet hours use an
explicit IANA timezone, capture UTC once inside the grant lock, and gate commands only.

## Where Threshold Node stands

The scoped-view core, owner/per-grant API boundaries, grant issue and revocation, RFC3339
window/expiry enforcement, local JSONL decision ledger, and three-step synthetic mock
agent run today. The mock proves a scoped read, an allowed policy decision that is not
relayed because no adapter exists, and a no-go denial. It does not move hardware.

THS-0041/0042/0043/0051 now provide a bounded simulated-appliance proof. Owner-authenticated
trip/re-arm routes are gated by explicit demo mode and exact `ESP32_SERIAL=SIMULATED`. A
new trip latches its server process first, durably suspends active grants and records ESTOP
even when none are active, attempts injected adapters independently, and makes duplicate
trip calls idempotent. Failed persistence leaves that process TRIPPED and makes server
re-arm unavailable; successful re-arm clears only the latch and never restores grants.
The end-to-end test covers grant → scoped read → no-go denial → simulated trip → suspended
denial, plus re-arm and authority restart.

The terminal fallback deterministically shows two-second READ, four-second DENY, and
latched TRIPPED states. The allowlisted GRANT/DENY/ESTOP receipt primitive renders fixed
text and 384×256 grayscale PNG; the API discards its in-memory ESTOP PNG, while an optional
private sink is write-once. The latch is process-local and single-worker, and every timing
claim is `simulated_software_path_only`. There is still no proof of an NC loop, ESP32,
serial bridge, OLED, printer, configured adapter, physical device stop, or certified safety.

The privacy-first local capture intake is implemented for JPEG/PNG photos and MOV/MP4/M4V
video: it creates a bounded normalized batch under ignored `data/capture/`, without a model
call or canonical housefile write. Its local boundary, cleanup, receipt, scanner, and
synthetic FFmpeg proofs pass. The grant authority now persists digest-only state across
restart with fail-closed ledger-bound recovery, and IANA quiet hours deny commands without
blocking scoped reads. The private store and ledger are a pair; neither is a public artifact
or tamper-evident record.

The owner-authenticated API now exposes `GET /owner/status` and one credential-free
`GET /owner/snapshot` containing the server's current synthetic housefile, public grant
projections, bounded newest-first ledger events, and truthful health/interlock/display
state. The React console covers locked/loading/error/retry/ready states, blueprint, grant
issue/revoke, ledger, and simulated `TRIPPED` handling. The owner and new-grant tokens stay
in page memory and headers only. Owner routes permit same-origin, origin-less clients, or
exactly `http://127.0.0.1:5173`; there is no wildcard CORS. Automated backend/frontend
contract, interaction, build/type, and accessibility checks are present. The owner accepted
the corrected loading duration, semantic colors, and label containment on 2026-07-14, so
the implemented loopback-console delivery gate is `pass`.

The GPT-5.6 request adapter, strict proposal validator, and digest-bound owner decision are
implemented and provider-free tested. A live synthetic model quality, cost, latency, and
token-use evaluation has not been run, so THS-0021 is complete as a guarded adapter but is
not demo-proven model evidence. A read-only AuroraOS review identified a reusable
process-start Vault-injection pattern, but no Threshold-specific injector was created or
approved. THS-0024 defers its hardened sibling runner, dedicated SecretRef, one direct
Responses call, and sanitized usage evidence to a separate L2-build/L3-execution wave;
headless Codex is not a substitute for that transport. THS-0022 now emits a canonical
digest-bound fixed geometry from explicit order. THS-0023 validates an exact explicit review
and atomically advances an unmistakably synthetic temporary housefile under local revision
compare-and-swap. That proof is not observed geometry, a real-house workflow, or live server
state. Real-dwelling materialization review, robot adapters, hardware bridge, and the
complete submission demo still need to be completed. The
repository should only claim a capability after its code and demo evidence exist.

Real-room footage can make the video stronger, but the source and normalized capture batch
must stay local. Any externally published edit must pass `REAL-FOOTAGE-CHECKLIST.md`, and
every visible housefile, actor, receipt, and terminal value must remain synthetic.
