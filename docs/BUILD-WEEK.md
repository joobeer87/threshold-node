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

1. A phone walk produces a constrained housefile proposal using GPT-5.6 structured output.
2. The owner reviews and confirms the proposal before it becomes policy.
3. A simulated physical agent receives a scoped view and is denied access to a no-go zone.
4. The Jetson-connected I/O rig shows the decision, records a receipt, and responds to the
   prototype stop control.

The memorable object should be the physical threshold: the model may propose, but it
cannot bypass deterministic validation, owner confirmation, or the permission gate.

## Implementation

The edge node uses FastAPI and Pydantic. The planned owner console uses Vite, React, and
TypeScript. The hardware path uses an ESP32 bridge with Arduino or PlatformIO. A virtual
Matter RVC is optional; the simulated agent and real I/O rig are enough for the primary
demo.

## Where Threshold Node stands

The scoped-view policy core and authenticated API boundary run today. The GPT-5.6 capture
flow, persistent ledger, live owner console, hardware bridge, and complete demo sequence
still need to be built and tested. The repository should only claim a capability after its
code and demo evidence exist.

Real-room footage can make the video stronger, but it must pass
`REAL-FOOTAGE-CHECKLIST.md`, and every visible housefile, actor, receipt, and terminal value
must remain synthetic.
