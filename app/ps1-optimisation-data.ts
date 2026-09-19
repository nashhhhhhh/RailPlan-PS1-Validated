import { z } from "zod";
import { ApiError, RailPlanClient } from "../railplan-backend/frontend/client";
import type {
  SavedOptimiseInput,
  Placement,
} from "../railplan-backend/frontend/contracts.generated";
export type { SavedOptimiseInput, Placement };
const record = z.record(z.unknown());
const nullableNumber = z.number().nullable();
export const accessSchema = z.object({
  activity_id: z.string(),
  access_seq: z.number().int(),
  week: z.number().int(),
  physical_night: z.number().int(),
  access_night: nullableNumber,
  locked: z.boolean(),
  eclo: z.union([z.boolean(), z.number()]),
  baseline_week: nullableNumber,
  baseline_physical_night: nullableNumber,
});
export const occupancySchema = z.object({
  activity_id: z.string(),
  week: z.number().int(),
  location_id: z.string(),
  co_share_group: z.union([z.string(), z.number()]),
});
export const summarySchema = z
  .object({
    id: z.string(),
    instance_id: z.string(),
    baseline_run_id: z.string().nullable(),
    solver_status: z.string(),
    terminal_outcome: z.string(),
    publishable: z.boolean(),
    physical_validation_complete: z.boolean(),
    primary_optimal: z.boolean(),
    lexicographic_complete: z.boolean(),
    objective_score: z.string().nullable(),
    primary_objective_bound: z.string().nullable(),
    primary_objective_gap: z.string().nullable(),
    solve_duration_seconds: z.number(),
    created_at: z.string(),
    scenario: z.enum(["A", "B", "C"]).default("A"),
  })
  .passthrough();
export const detailSchema = z.object({
  run: summarySchema,
  result: z
    .object({
      solver_status: z.string(),
      scenario: z.enum(["A", "B", "C"]).default("A"),
      publishable: z.boolean(),
      primary_optimal: z.boolean(),
      lexicographic_complete: z.boolean(),
      solve_time_seconds: z.number(),
      physical_validation_complete: z.boolean(),
      settings: record,
      objective_components: record.nullable(),
      completion_changes: z.array(record),
      workload_delivery: z.array(record).default([]),
      capacity_hotspots: z.array(record).default([]),
      baseline_movement: z.number().int().default(0),
      contract_completion_gate: z.boolean().default(false),
      eclo_windows: z.record(record).default({}),
      cross_line_eclo_activities: z.array(z.string()).default([]),
      stages: z.array(record),
      judge_validation: z.literal("not_run"),
      score_verification: z.literal("internal_only"),
    })
    .passthrough(),
  validation: record.nullable(),
  diagnostics: z.array(record),
  contract_results: z.array(
    z.object({
      contract_number: z.string(),
      simulated_completion_date: z.string(),
      overrun_days: z.number(),
      weighted_overrun: z.string().nullable(),
    }),
  ),
});
export const createdSchema = z.object({
  run_id: z.string(),
  created: z.boolean(),
  reused: z.boolean(),
});
export const previewResultSchema = detailSchema.shape.result.extend({
  submission_files: z.record(z.string()).nullable(),
  physical_nights: z.array(
    z.object({
      activity_id: z.string(),
      access_seq: z.number().int(),
      week: z.number().int(),
      physical_night: z.number().int(),
      access_night: nullableNumber,
      eclo: z.number().int().nullable().optional(),
    }).passthrough(),
  ),
  validation_report: record.nullable(),
  diagnostics: z.array(record),
});
export const artifactsSchema = z.object({
  run_id: z.string(),
  files: z.record(z.string()),
  physical_validation_complete: z.boolean(),
  judge_validation: z.literal("not_run"),
  score_verification: z.literal("internal_only"),
});
export type Access = z.infer<typeof accessSchema>;
export type Occupancy = z.infer<typeof occupancySchema>;
export type RunSummary = z.infer<typeof summarySchema>;
export type RunDetail = z.infer<typeof detailSchema>;
export type Artifacts = z.infer<typeof artifactsSchema>;
export const pageSchema = z.object({
  items: z.array(record),
  total: z.number().int().nonnegative(),
  offset: z.number().int().nonnegative(),
  limit: z.number().int().positive(),
});
export const optionsSchema = z.object({
  time_limit_seconds: z.number().min(0.1).max(120),
  deterministic_time_limit: z.number().min(0.001).max(60),
  random_seed: z.number().int().min(0).max(2147483647),
  physical_nights_per_week: z.number().int().min(1).max(7),
});
export const defaults = {
  time_limit_seconds: 20,
  deterministic_time_limit: 10,
  random_seed: 0,
  physical_nights_per_week: 7,
};
export const statusLabels: Record<string, string> = {
  OPTIMAL: "Optimal schedule found",
  FEASIBLE: "Feasible schedule found",
  INFEASIBLE: "No feasible schedule under these constraints",
  UNKNOWN: "No schedule found within the configured limits",
  MODEL_LIMIT: "Instance exceeds the configured model limit",
  MODEL_INVALID: "Optimisation model rejected",
  VALIDATION_FAILED: "Generated candidate failed internal validation",
  ERROR: "Optimisation failed",
};
export function statusLabel(status: string) {
  return statusLabels[status] ?? status;
}
export function connectionClient(baseUrl: string, demoUserId: string) {
  const url = new URL(baseUrl);
  if (
    !["http:", "https:"].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw Error(
      "Enter an HTTP(S) backend address without credentials or query parameters.",
    );
  // Native browser fetch requires a Window receiver. Pass an arrow adapter so
  // the shared client's method call cannot bind fetch to the client instance.
  return new RailPlanClient({
    baseUrl: url.href,
    demoUserId,
    fetcher: (...args) => globalThis.fetch(...args),
  });
}
export function errorText(error: unknown) {
  if (error instanceof z.ZodError)
    return (
      "The backend response or options do not match the expected contract. " +
      error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join("; ")
    );
  if (error instanceof ApiError) {
    const labels: Record<number, string> = {
      401: "Sign in or configure your demo planner identity.",
      403: "Your account cannot perform this action.",
      404: "This instance or run is unavailable to your account.",
      409: "The request conflicts with a saved attempt or artifacts are unavailable.",
      422: "Check the solver options, baseline and locked placements.",
      503: "The backend or its database is unavailable.",
    };
    return `${labels[error.status] ?? "API request failed."} ${error.message} (Reference: ${error.envelope.error.correlation_id})`;
  }
  return error instanceof Error
    ? error.message
    : "Could not complete the request.";
}
export async function allPages<T>(
  load: (offset: number) => Promise<unknown>,
  schema: z.ZodType<T>,
  key: (row: T) => string,
  signal?: AbortSignal,
): Promise<T[]> {
  let offset = 0;
  const rows = new Map<string, T>();
  while (true) {
    signal?.throwIfAborted();
    const page = pageSchema.parse(await load(offset));
    signal?.throwIfAborted();
    const before = rows.size;
    for (const raw of page.items) {
      const row = schema.parse(raw);
      rows.set(key(row), row);
    }
    offset += page.items.length;
    if (offset >= page.total) return [...rows.values()];
    if (!page.items.length || rows.size === before)
      throw Error(
        "The backend returned an incomplete page. Refresh this run to retry; partial schedules are not displayed.",
      );
    if (offset > 100000)
      throw Error("The complete schedule exceeds the API pagination range.");
  }
}
export const accessKey = (row: Pick<Access, "activity_id" | "access_seq">) =>
  JSON.stringify([row.activity_id, row.access_seq]);
export const occupancyKey = (row: Occupancy) =>
  JSON.stringify([row.activity_id, row.week, row.location_id]);
export function movement(row: Access) {
  return row.baseline_week === null
    ? "No baseline"
    : row.week !== row.baseline_week
      ? "Moved week"
      : row.physical_night !== row.baseline_physical_night
        ? "Moved night"
        : "Unchanged";
}
export function placement(row: Access): Placement {
  return {
    activity_id: row.activity_id,
    access_seq: row.access_seq,
    week: row.week,
    physical_night: row.physical_night,
    access_night: row.access_night,
    eclo: Number(Boolean(row.eclo)),
  };
}
export function joinOccupancy(rows: Occupancy[], accesses: Access[]) {
  const nights = new Map<string, Set<number>>();
  for (const a of accesses) {
    const key = JSON.stringify([a.activity_id, a.week]);
    const values = nights.get(key) ?? new Set<number>();
    values.add(a.physical_night);
    nights.set(key, values);
  }
  return rows.map((o) => ({
    ...o,
    physical_nights: [
      ...(nights.get(JSON.stringify([o.activity_id, o.week])) ?? []),
    ].sort((a, b) => a - b),
  }));
}
export type Attempt = { body: SavedOptimiseInput; instanceId: string };
export function newAttempt(
  instanceId: string,
  options: SavedOptimiseInput,
  uuid: () => string = () => crypto.randomUUID(),
): Attempt {
  return {
    instanceId,
    body: structuredClone({ ...options, idempotency_key: uuid() }),
  };
}
export function csvBlob(text: string) {
  return new Blob([text], { type: "text/csv;charset=utf-8" });
}
export function downloadCsv(name: string, text: string) {
  const href = URL.createObjectURL(csvBlob(text));
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(href), 1000);
}
export function display(value: unknown) {
  return value === null || value === undefined
    ? "—"
    : typeof value === "object"
      ? JSON.stringify(value)
      : String(value);
}
