# OpenAI Build Week plan

Status checked: **2026-07-11**.

The official OpenAI page says the challenge opens July 13 and submissions close July 21.
The linked Devpost schedule currently gives the deadline as July 21 at 5:00 p.m. PDT. The
official rules, tracks, and complete submission requirements are not published yet.

- Challenge: <https://openai.com/build-week/>
- Devpost overview and judging criteria: <https://openai.devpost.com/>
- Schedule: <https://openai.devpost.com/details/dates>
- Rules gate: <https://openai.devpost.com/rules>
- Resources gate: <https://openai.devpost.com/resources>

## Candidate-two gate

The current pages do not say whether one entrant may submit multiple projects. Do not
submit Threshold Node as a second candidate until the July 13 rules explicitly permit it.
Re-check eligibility, existing-project rules, categories, repository visibility, required
materials, token availability, and video limits at the same time.

## Fit to the published judging criteria

1. **Technological implementation:** make GPT-5.6 central to the phone-walk capture and
   constrained plan proposal, with structured outputs, schema validation, and evals.
2. **Design:** deliver one complete loop—capture proposal, owner confirmation, grant,
   scoped robot read, denied no-go action, prototype stop, and receipt.
3. **Potential impact:** demonstrate a specific household-robot privacy and authority
   problem, not a general chat interface.
4. **Quality of idea:** make the memorable object the physical threshold: a local policy
   boundary that models can propose through but cannot bypass.

## Recommended stack

Keep FastAPI/Pydantic for the edge node and build the console with Vite, React, and
TypeScript. Use Matterbridge/matter.js only for the virtual RVC fixture and PlatformIO or
Arduino for the ESP32. An agent orchestration framework would add more surface than value
for the first demo; the important boundary is model proposal → deterministic validation →
owner confirmation → policy gate.

## Honest current state

Codex is being used to build and review the project. GPT-5.6 is not yet wired into the
runtime. Do not describe model integration, robot relay, persistent audit, or hardware
latency as complete until the code and demo evidence exist.

Real-room footage is encouraged for impact, provided it passes
`REAL-FOOTAGE-CHECKLIST.md` and every visible data surface remains synthetic.
