# RailPlan

RailPlan combines an engineering-planning demonstration with a FastAPI/PostgreSQL backend and deterministic PS1 Scenario A/B/C CP-SAT optimisation. AI/Ollama/Qwen remains optional and never decides feasibility. The application is a prototype, not an operational rail-system connection or authority.

## Explore

- Generate best plan: play a staged scan and animate to a preset schedule.
- Scenario Lab: compare three alternatives; keyboard shortcuts 1, 2 and 3.
- Select a queue item: focus its requests and dependencies.
- Lock a request: retain its original start time. Preset mismatches block demo approval.
- Request Composer: add a local request through six review steps.
- Approval Replay: scrub through changes and confirm a local-only approval.
- Ctrl/Cmd+K: command palette. A: analysis. F: focus. P: presentation.
- Reset demo restores the seed dataset. Changes are held only in memory.

## Run

Install with the package manager pinned in package.json. Run `pnpm dev`; `pnpm build` creates the bundled site. React, TypeScript, Framer Motion and the starter's accessible Radix primitives power the UI. Local mock data lives in app/rail-data.ts.

## Validation

Current TypeScript, Next.js and Vinext production builds pass, together with the mocked browser workflow. See `RELEASE_VERIFICATION.md` for exact totals and limitations.

## Boundaries

Displayed outcomes are not safety validation. Drag feedback is illustrative rather than a constraint engine. Added or resized requests and mismatched locks require review and cannot approve a preset. There are no credentials, external assistant calls or production rail actions.
