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
3. The owner reviews and confirms the digest-bound proposal; THS-0022 geometry and a later
   reviewed materialization step are still required before it can become policy.
4. A simulated physical agent receives a scoped view and is denied access to a no-go zone.
5. The Jetson-connected I/O rig shows the decision, records a receipt, and responds to the
   prototype stop control.

The memorable object should be the physical threshold: the model may propose, but it
cannot bypass deterministic validation, owner confirmation, or the permission gate.

## Implementation

The edge node uses FastAPI and Pydantic. The planned owner console uses Vite, React, and
TypeScript. The hardware path uses an ESP32 bridge with Arduino or PlatformIO. A virtual
Matter RVC is optional; the simulated agent and real I/O rig are enough for the primary
demo.

The proposal adapter uses the OpenAI Responses API with GPT-5.6 image input and strict
structured output. Upload requires an explicit flag; requests use `store:false` and no
tools. Provider output remains untrusted and is deterministically revalidated before a
private proposal can reach a separate owner-decision step.

## Where Threshold Node stands

The scoped-view core, owner/per-grant API boundaries, grant issue and revocation, RFC3339
window/expiry enforcement, local JSONL decision ledger, and three-step synthetic mock
agent run today. The mock proves a scoped read, an allowed policy decision that is not
relayed because no adapter exists, and a no-go denial. It does not move hardware.

The privacy-first local capture intake is implemented for JPEG/PNG photos and MOV/MP4/M4V
video: it creates a bounded normalized batch under ignored `data/capture/`, without a model
call or canonical housefile write. Its local boundary, cleanup, receipt, scanner, and
synthetic FFmpeg proofs pass. The persistent grant store, live owner console, real robot
adapters, hardware bridge, and complete submission demo still need to be built and tested.
The GPT-5.6 request adapter, strict
proposal validator, and digest-bound owner decision are now implemented and provider-free
tested, but a live synthetic model quality/cost evaluation has not been run. Geometry and
canonical housefile materialization remain explicitly out of scope. The repository should
only claim a capability after its code and demo evidence exist.

Real-room footage can make the video stronger, but the source and normalized capture batch
must stay local. Any externally published edit must pass `REAL-FOOTAGE-CHECKLIST.md`, and
every visible housefile, actor, receipt, and terminal value must remain synthetic.
