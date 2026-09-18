import { z } from "zod";

const windowSchema = z.object({
  id: z.string().uuid(), name: z.string(), starts_at: z.string(), ends_at: z.string(),
});
const windowPageSchema = z.object({ items: z.array(windowSchema) });
const centreSchema = z.object({
  requests: z.array(z.object({ id: z.string().uuid(), request_code: z.string(), title: z.string() })).nullable(),
  scenarios: z.array(z.object({ id: z.string().uuid(), name: z.string() })).nullable(),
});
const summarySchema = z.object({
  id: z.string().uuid(), status: z.enum(["completed", "failed"]), scenario_id: z.string().uuid().nullable().optional(),
  conflict_count: z.number().int().nonnegative(), blocking_conflict_count: z.number().int().nonnegative(),
  counts_by_severity: z.record(z.number()), completed_at: z.string().nullable(), detail: z.string().nullable().optional(),
});
const conflictSchema = z.object({
  id: z.string().uuid(), conflict_code: z.string(), title: z.string(), explanation: z.string(),
  rule_code: z.string(), rule_version: z.number(), category: z.string(), severity: z.string(),
  blocking: z.boolean(), request_ids: z.array(z.string().uuid()),
});
export type EngineeringWindow = z.infer<typeof windowSchema>;
export type Centre = z.infer<typeof centreSchema>;
export type AnalysisSummary = z.infer<typeof summarySchema>;
export type AnalysisConflict = z.infer<typeof conflictSchema>;

export function createAnalysisApi(base: string, userId: string) {
  const url = new URL(base);
  if (!["http:", "https:"].includes(url.protocol) || url.username || url.password || url.search || url.hash) {
    throw new Error("Enter an HTTP(S) backend URL without credentials, a query, or a fragment.");
  }
  if (!z.string().uuid().safeParse(userId).success) throw new Error("Enter a valid demo planner UUID.");
  const root = url.href.replace(/\/$/, "");
  async function request<T>(path: string, schema: z.ZodType<T>, signal: AbortSignal, body?: unknown): Promise<T> {
    const timeout = new AbortController();
    const cancel = () => timeout.abort(signal.reason);
    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
    const timer = setTimeout(() => timeout.abort(new Error("The backend did not respond within 60 seconds.")), 60000);
    try {
      const response = await fetch(root + path, {
        method: body === undefined ? "GET" : "POST", signal: timeout.signal,
        headers: { "X-Demo-User-Id": userId, ...(body === undefined ? {} : { "Content-Type": "application/json" }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        const parsedError=z.object({error:z.object({message:z.string()}).optional(),detail:z.string().optional(),id:z.string().optional()}).safeParse(data);
        const failure=parsedError.success?parsedError.data:{};
        const message = failure.error?.message || failure.detail || `Backend request failed (HTTP ${response.status}).`;
        throw new Error(message + (failure.id ? ` Run: ${failure.id}` : ""));
      }
      const parsed = schema.safeParse(data);
      if (!parsed.success) throw new Error("The backend response is incompatible. Check that the merged backend and migration are installed.");
      return parsed.data;
    } catch (error) {
      if (!signal.aborted && timeout.signal.aborted) throw new Error("The request timed out. The backend may still finish the analysis; no results are shown until retrieved.");
      throw error;
    } finally {
      clearTimeout(timer);
      signal.removeEventListener("abort", cancel);
    }
  }
  return {
    windows: async (signal: AbortSignal) => (await request("/api/engineering-windows", windowPageSchema, signal)).items,
    centre: (id: string, signal: AbortSignal) => request(`/api/command-centre/${encodeURIComponent(id)}`, centreSchema, signal),
    run: (windowId: string, scenarioId: string, signal: AbortSignal) => request("/api/analyses", summarySchema, signal,
      { window_id: windowId, scenario_id: scenarioId || null }),
    conflicts: (id: string, signal: AbortSignal) => request(`/api/analyses/${encodeURIComponent(id)}/conflicts`, z.array(conflictSchema), signal),
  };
}
