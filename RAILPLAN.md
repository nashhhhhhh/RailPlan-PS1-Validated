# RailPlan AI

A frontend-only engineering planning demonstration. No real AI, solver, operational database or rail-system connection is included. All scenarios and rule explanations are synthetic presets.

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

TypeScript checking and production compilation passed. Browser-based visual/end-to-end testing was not performed. The optional WebMCP navigation tool is feature-detected; runtime validation was unavailable in this environment.

## Boundaries

Displayed outcomes are not safety validation. Drag feedback is illustrative rather than a constraint engine. Added or resized requests and mismatched locks require review and cannot approve a preset. There are no credentials, external assistant calls or production rail actions.
