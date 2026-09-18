# Connect the client to the existing RailPlan UI

These adapters are provided separately. The hosted site's handlers still use the original
local demonstration data until you explicitly integrate this client.

Copy `client.ts`, `adapters.ts`, and `contracts.generated.ts` to your frontend
data layer. They do not change the UI's visual design.

## Configuration

```typescript
import { RailPlanClient } from "./client";
const api = new RailPlanClient({
  baseUrl: process.env.NEXT_PUBLIC_RAILPLAN_API_URL ?? "http://127.0.0.1:8000",
  // Local demo only. Omit when using a future verified identity adapter.
  demoUserId: process.env.NEXT_PUBLIC_RAILPLAN_DEMO_USER_ID
});
```

No production bearer-auth backend is configured yet. Do not treat the header above as secure identity.

## Handler mapping

| UI operation | Adapter / client method | Expected UI update |
|---|---|---|
| Open/change engineering window | loadWorkspace | Replace timeline and queue; preserve camera/zoom |
| Submit composer | submitComposer | Add returned request; reload workspace |
| Compare alternatives | comparePlans | Render returned scenarios and unknown metrics accurately |
| Drag/resize timeline | moveDraft | Preview, PATCH, then reload the server version |
| Inspect coordination issue | inspectConflict | Show stored rule evidence and affected UUIDs |
| Keep timing fixed | keepTiming | Store returned lock ID and show lock state |
| Unlock | unlockTiming | Release lock by UUID; reload request/scenario |
| Read activity | api.activity | Append pages in server order |
| Acknowledge activity | acknowledgeActivity | Refresh per-user read indicators |

### Load and cancel stale requests

```typescript
const controller = new AbortController();
loadWorkspace(api, windowId, scenarioId, controller.signal)
  .then(result => {
    setJobs(result.jobs); // Adapt view-only row/colour grouping here.
    setAnalysisUnknown(result.analysisUnknown);
  })
  .catch(error => {
    if (error.name !== "AbortError") setLoadError(displayError(error));
  });
// In the React effect cleanup:
controller.abort();
```

Keep your explicit demo-mode switch. Do not load seeds in an API-error catch handler.

### Composer fields

Use the reference-data and network endpoints to populate IDs. Do not send team or station
names as UUIDs. Convert the Singapore date/time inputs with `composerTime`.
Calculate requested_end from the duration, and populate earliest_start/latest_finish from
the engineering window. Supply work_type_id, sector_ids and resource IDs.

The API defaults create to `submit:true` for compatibility. Use `submit:false` to save a draft
and then call submitRequest after review.

### Draft timeline workflow

1. Call createScenario with the engineering-window ID and objective ID, or cloneScenario
   with the source's current version.
2. Load api.scenario to obtain assignment UUIDs and the scenario's version.
3. Pass that version as expected_version to moveDraft.
4. On 409, reload and show the server's explanation. Do not replay a stale drag automatically.
5. Continue rendering original_start/original_end as ghosts.

The preview reports basic validity only. Display “Requires analysis” after a valid placement,
not “Safe” or “Conflict-free”.

### UI-only state

Keep timeline row grouping, overlapping bar lanes, colours, selected panels, camera position,
zoom, intro animations and replay playback locally. Do not use the API UUID as the displayed
MR code. Preserve both request_id and request_code in your view model.

The current island/map has illustrative geometry. API records with geometry_available=false
must be shown as missing operational geometry; they must not silently inherit demo coordinates.

### Unavailable controls

Bind Analyse, Optimise, Copilot and Approve availability to the capability response. Show a
short explanation or explicit demo mode where appropriate. Do not call disabled operations
and pretend they succeeded.

### Read more pages

```typescript
const first = await api.listRequests({window_id: windowId, limit: 100, offset: 0});
const next = first.offset + first.items.length < first.total
  ? await api.listRequests({window_id: windowId, limit: 100, offset: first.offset + first.items.length})
  : null;
```

Mutation requests are not automatically retried. An aborted fetch may still have committed
on the server; reload before retrying a create.

## Client checks

```bash
cd frontend
npm install
npm test
```

The only development dependency is TypeScript. Runtime uses browser fetch.
Generated OpenAPI schema types are in contracts.generated.ts; ergonomic client methods and
UI adapters are in client.ts/adapters.ts.
