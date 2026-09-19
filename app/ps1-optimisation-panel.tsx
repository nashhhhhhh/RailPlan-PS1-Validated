"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  Play,
  History,
  Lock,
  Unlock,
  Download,
  RefreshCw,
  ArrowRight,
  Activity,
  CheckCircle2,
  Clock3,
  Layers,
  SlidersHorizontal,
  X,
  AlertTriangle,
} from "lucide-react";
import {
  accessKey,
  accessSchema,
  allPages,
  artifactsSchema,
  connectionClient,
  createdSchema,
  csvBlob,
  defaults,
  detailSchema,
  display,
  downloadCsv,
  errorText,
  joinOccupancy,
  movement,
  newAttempt,
  occupancyKey,
  occupancySchema,
  optionsSchema,
  pageSchema,
  placement,
  previewResultSchema,
  statusLabel,
  summarySchema,
} from "./ps1-optimisation-data";
import type {
  Access,
  Artifacts,
  Attempt,
  Occupancy,
  Placement,
  RunDetail,
  RunSummary,
} from "./ps1-optimisation-data";
import type { Dataset } from "./ps1-workspace";
import {publicationGate,solverExplanation,solverPresets} from "./components/ps1/demo-state";
import "./ps1-optimisation.css";

type Props = {
  instanceId: string;
  instanceFiles: Record<string, string>;
  dataset: Dataset;
  scenario: "A" | "B" | "C";
  baseUrl: string;
  demoUserId: string;
  onSaveDataset: () => void;
  onSelectActivity: (id: string) => void;
  onHighlightLocations: (ids: string[]) => void;
};
type Cache = {
  detail: RunDetail;
  accesses: Access[];
  occupancies: Occupancy[];
};
const tabs = [
  "Schedule",
  "Occupancy",
  "Contracts",
  "Validation",
  "Diagnostics",
  "Downloads",
] as const;
type Tab = (typeof tabs)[number];
const colorList = [
  "#745cf4",
  "#168b92",
  "#c26922",
  "#9a55b9",
  "#307dba",
  "#ae5074",
];
function Evidence({
  value,
  label = "Evidence",
}: {
  value: unknown;
  label?: string;
}) {
  return (
    <details className="opt-evidence">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="opt-metric">
      <span>{label}</span>
      <strong>{display(value)}</strong>
    </div>
  );
}

export default function PS1OptimisationPanel({
  instanceId,
  instanceFiles,
  dataset,
  scenario,
  baseUrl,
  demoUserId,
  onSaveDataset,
  onSelectActivity,
  onHighlightLocations,
}: Props) {
  const previewSupported = (["A", "B", "C"] as const).includes(scenario);
  const elasticScenario = scenario === "B" || scenario === "C";
  const [mode, setMode] = useState<"preview" | "saved">(
    instanceId ? "saved" : "preview",
  );
  const [options, setOptions] = useState(defaults),
    [baseline, setBaseline] = useState(""),
    [locks, setLocks] = useState<Placement[]>([]);
  const [history, setHistory] = useState<RunSummary[]>([]),
    [comparison, setComparison] = useState<RunDetail[]>([]),
    [historyTotal, setHistoryTotal] = useState(0),
    [historyOffset, setHistoryOffset] = useState(0),
    [historyBusy, setHistoryBusy] = useState(false),
    [historyError, setHistoryError] = useState("");
  const [selectedId, setSelectedId] = useState(""),
    [view, setView] = useState<Cache | null>(null),
    [loading, setLoading] = useState(false),
    [loadError, setLoadError] = useState("");
  const [solving, setSolving] = useState(false),
    [attempt, setAttempt] = useState<Attempt | null>(null),
    [notice, setNotice] = useState(""),
    [runError, setRunError] = useState(""),
    [elapsed, setElapsed] = useState(0);
  const [tab, setTab] = useState<Tab>("Schedule"),
    [week, setWeek] = useState(""),
    [query, setQuery] = useState(""),
    [contract, setContract] = useState(""),
    [location, setLocation] = useState(""),
    [compact, setCompact] = useState(false),
    [lateOnly, setLateOnly] = useState(false);
  const [selectedAccess, setSelectedAccess] = useState<Access | null>(null),
    [artifacts, setArtifacts] = useState<Artifacts | null>(null),
    [artifactBusy, setArtifactBusy] = useState(false),
    [artifactError, setArtifactError] = useState("");
  const cache = useRef(new Map<string, Cache>()),
    artifactCache = useRef(new Map<string, Artifacts>());
  const historyController = useRef<AbortController | null>(null),
    detailController = useRef<AbortController | null>(null),
    solveController = useRef<AbortController | null>(null),
    artifactController = useRef<AbortController | null>(null);
  const epoch = useRef(0);
  const activityMap = useMemo(
    () =>
      new Map(dataset.tables.activity_details.map((a) => [a.activity_id, a])),
    [dataset],
  );
  const contracts = useMemo(
    () =>
      [
        ...new Set(
          dataset.tables.project_details.map((p) => p.contract_number),
        ),
      ].sort(),
    [dataset],
  );
  const color = (id: string) =>
    colorList[
      Math.max(
        0,
        contracts.indexOf(activityMap.get(id)?.contract_number ?? ""),
      ) % colorList.length
    ];
  const client = () => connectionClient(baseUrl, demoUserId);
  async function backend(path: string, body: unknown, signal: AbortSignal) {
    const base = new URL(baseUrl);
    if (!["http:", "https:"].includes(base.protocol) || base.username || base.password || base.search || base.hash)
      throw Error("Enter an HTTP(S) backend address without credentials or query parameters.");
    const response = await fetch(base.href.replace(/\/$/, "") + path, {
      method: "POST", signal, headers: { "Content-Type": "application/json", ...(demoUserId ? { "X-Demo-User-Id": demoUserId } : {}) },
      body: JSON.stringify(body),
    });
    const value: unknown = await response.json();
    if (!response.ok) {
      const message = typeof value === "object" && value && "error" in value
        ? String((value as { error?: { message?: string } }).error?.message ?? "Request failed")
        : "Request failed";
      throw Error(message);
    }
    return value;
  }
  async function backendGet(path: string, signal: AbortSignal) {
    const base = new URL(baseUrl);
    const response = await fetch(base.href.replace(/\/$/, "") + path, { signal,
      headers: demoUserId ? { "X-Demo-User-Id": demoUserId } : {} });
    const value: unknown = await response.json();
    if (!response.ok) throw Error("Could not load saved optimisation history.");
    return value;
  }
  function csvRows(text: string | undefined) {
    if (!text) return [] as Record<string, string>[];
    const [header, ...lines] = text.trim().split(/\r?\n/);
    const fields = header.split(",");
    return lines.filter(Boolean).map((line) => Object.fromEntries(fields.map((field, i) => [field, line.split(",")[i] ?? ""])));
  }
  function showPreview(raw: unknown) {
    const result = previewResultSchema.parse(raw);
    const validation = result.validation_report as Record<string, unknown> | null;
    const objective = result.objective_components as Record<string, unknown> | null;
    const firstStage = (result.stages.find((stage) =>
      String((stage as Record<string, unknown>).name).startsWith("official_scenario_"),
    ) ?? result.stages[0]) as Record<string, unknown> | undefined;
    const run = summarySchema.parse({
      id: "local-preview", instance_id: instanceId || "stateless", baseline_run_id: null, scenario,
      solver_status: result.solver_status,
      terminal_outcome: result.solver_status === "UNKNOWN" ? "bounded" : result.solver_status.toLowerCase(),
      publishable: result.publishable, physical_validation_complete: result.physical_validation_complete,
      primary_optimal: result.primary_optimal, lexicographic_complete: result.lexicographic_complete,
      objective_score: typeof validation?.objective_score === "string" ? validation.objective_score : null,
      primary_objective_bound: firstStage?.best_bound === undefined ? null : String(firstStage.best_bound),
      primary_objective_gap: firstStage?.gap === undefined ? null : String(firstStage.gap),
      solve_duration_seconds: result.solve_time_seconds, created_at: new Date().toISOString(),
    });
    const contractResults = Array.isArray(objective?.contract_results)
      ? objective.contract_results.filter((row) => typeof (row as Record<string, unknown>).simulated_completion_date === "string" && typeof (row as Record<string, unknown>).overrun_days === "number")
        .map((row) => ({ ...(row as Record<string, unknown>), weighted_overrun: null }))
      : [];
    const detail = detailSchema.parse({ run, result, validation, diagnostics: result.diagnostics, contract_results: contractResults });
    const accesses = result.physical_nights.map((row) => accessSchema.parse({ ...row, locked: false,
      eclo: row.eclo ?? 0, baseline_week: null, baseline_physical_night: null }));
    const occupancies = csvRows(result.submission_files?.["SCHEDULE_OCCUPANCY.csv"]).map((row) => occupancySchema.parse({
      activity_id: row.activity_id, week: Number(row.week), location_id: row.location_id, co_share_group: row.co_share_group,
    }));
    setView({ detail, accesses, occupancies }); setSelectedId("local-preview");
    if (result.publishable && result.submission_files) setArtifacts({ run_id: "local-preview", files: result.submission_files,
      physical_validation_complete: result.physical_validation_complete, judge_validation: "not_run", score_verification: "internal_only" });
  }
  async function loadHistory(more = false) {
    if (!instanceId) return;
    historyController.current?.abort();
    const c = new AbortController();
    historyController.current = c;
    setHistoryBusy(true);
    setHistoryError("");
    const offset = more ? historyOffset : 0;
    try {
      const page = pageSchema.parse(await client().ps1Optimisations(instanceId, { limit: 50, offset, scenario }, c.signal));
      const rows = page.items.map((x) => summarySchema.parse(x));
      if (c.signal.aborted) return;
      setHistory((previous) => [
        ...new Map(
          [...(more ? previous : []), ...rows].map((r) => [r.id, r]),
        ).values(),
      ]);
      setHistoryTotal(page.total);
      setHistoryOffset(offset + page.items.length);
      if (!more) {
        const all = pageSchema.parse(await client().ps1Optimisations(instanceId, { limit: 50, offset: 0 }, c.signal));
        const latest = new Map<string, RunSummary>();
        for (const item of all.items.map((row) => summarySchema.parse(row))) if (!latest.has(item.scenario)) latest.set(item.scenario, item);
        const details = await Promise.all([...latest.values()].map(async (item) => detailSchema.parse(await client().ps1Optimisation(item.id, c.signal))));
        if (!c.signal.aborted) setComparison(details);
      }
    } catch (e) {
      if (!c.signal.aborted) setHistoryError(errorText(e));
    } finally {
      if (!c.signal.aborted) setHistoryBusy(false);
    }
  }
  async function openRun(id: string, refresh = false) {
    detailController.current?.abort();
    artifactController.current?.abort();
    setArtifactBusy(false);
    const c = new AbortController();
    detailController.current = c;
    setSelectedId(id);
    setSelectedAccess(null);
    onHighlightLocations([]);
    setLoadError("");
    setArtifactError("");
    setArtifacts(artifactCache.current.get(id) ?? null);
    setWeek("");
    setQuery("");
    setContract("");
    setLocation("");
    const existing = cache.current.get(id);
    if (existing && !refresh) {
      setView(existing);
      setLoading(false);
      return;
    }
    setView(null);
    setLoading(true);
    try {
      const api = client();
      const detail = detailSchema.parse(
        await api.ps1Optimisation(id, c.signal),
      );
      if (detail.run.instance_id !== instanceId)
        throw Error("This run belongs to a different dataset instance.");
      const [accesses, occupancies] = detail.run.publishable
        ? await Promise.all([
            allPages(
              (offset) =>
                api.ps1OptimisationAccesses(
                  id,
                  { limit: 200, offset },
                  c.signal,
                ),
              accessSchema,
              accessKey,
              c.signal,
            ),
            allPages(
              (offset) =>
                api.ps1OptimisationOccupancies(
                  id,
                  { limit: 200, offset },
                  c.signal,
                ),
              occupancySchema,
              occupancyKey,
              c.signal,
            ),
          ])
        : [[], []];
      if (c.signal.aborted) return;
      const next = { detail, accesses, occupancies };
      cache.current.set(id, next);
      setView(next);
    } catch (e) {
      if (!c.signal.aborted) setLoadError(errorText(e));
    } finally {
      if (!c.signal.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    epoch.current++;
    for (const ref of [
      historyController,
      detailController,
      solveController,
      artifactController,
    ])
      ref.current?.abort();
    cache.current.clear();
    artifactCache.current.clear();
    onHighlightLocations([]);
    setHistory([]);
    setComparison([]);
    setHistoryTotal(0);
    setHistoryOffset(0);
    setSelectedId("");
    setView(null);
    setBaseline("");
    setLocks([]);
    setAttempt(null);
    setNotice("");
    setRunError("");
    setLoadError("");
    setHistoryError("");
    setSolving(false);
    setLoading(false);
    setHistoryBusy(false);
    setArtifactBusy(false);
    setArtifacts(null);
    setArtifactError("");
    setSelectedAccess(null);
    setWeek("");
    setQuery("");
    setContract("");
    setLocation("");
    if (instanceId) void loadHistory();
    return () => {
      epoch.current++;
      for (const ref of [
        historyController,
        detailController,
        solveController,
        artifactController,
      ])
        ref.current?.abort();
    };
    // Connection changes define a fresh security and data scope.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [instanceId, baseUrl, demoUserId, dataset.fingerprint]);
  useEffect(() => {
    if (!solving) return;
    const start = Date.now();
    setElapsed(0);
    const timer = setInterval(
      () => setElapsed(Math.floor((Date.now() - start) / 1000)),
      1000,
    );
    return () => clearInterval(timer);
  }, [solving]);
  async function run(retry = false) {
    if (solving || (mode === "saved" && !instanceId) || (mode === "preview" && (!previewSupported || !Object.keys(instanceFiles).length))) return;
    setRunError("");
    setNotice("");
    let next: Attempt;
    try {
      if (retry && attempt) next = attempt;
      else {
        const values = optionsSchema.parse(options);
        if (locks.length > 2000)
          throw Error("At most 2000 placements can be locked.");
        if (
          locks.length >= 20 &&
          !window.confirm(
            `Run with ${locks.length} hard placement locks? These constrain the solver.`,
          )
        )
          return;
        next = newAttempt(instanceId, {
          ...values,
          baseline_run_id: baseline || null,
          locked_placements: locks,
        });
      }
    } catch (e) {
      setRunError(errorText(e));
      return;
    }
    setAttempt(next);
    setSolving(true);
    const c = new AbortController();
    solveController.current = c;
    const currentEpoch = epoch.current;
    try {
      if (previewSupported && mode === "preview") {
        const { baseline_run_id: _baseline, idempotency_key: _key, ...solver } = next.body;
        const raw = await backend(`/api/ps1/optimise/scenario-${scenario.toLowerCase()}/preview`, { ...solver, instance_files: instanceFiles }, c.signal);
        if (c.signal.aborted || currentEpoch !== epoch.current) return;
        showPreview(raw); setNotice("Local preview completed. No server-side history was created."); setAttempt(null); return;
      }
      const raw = scenario === "A"
        ? await client().optimisePs1ScenarioA(next.instanceId, next.body, c.signal)
        : await backend(`/api/ps1/instances/${next.instanceId}/optimise/scenario-${scenario.toLowerCase()}`, next.body, c.signal);
      const result = createdSchema.parse(raw);
      if (c.signal.aborted || currentEpoch !== epoch.current) return;
      setNotice(
        result.reused
          ? "Saved result safely reused."
          : "Optimiser run saved to PostgreSQL.",
      );
      setAttempt(null);
      void loadHistory();
      await openRun(result.run_id);
    } catch (e) {
      if (!c.signal.aborted && currentEpoch === epoch.current)
        setRunError(errorText(e));
    } finally {
      if (!c.signal.aborted && currentEpoch === epoch.current)
        setSolving(false);
    }
  }
  function stopWaiting() {
    solveController.current?.abort();
    setSolving(false);
    setNotice(
      "Stopped waiting. The server may still finish and save this run. Refresh history or retry the exact attempt to recover it.",
    );
  }
  async function loadArtifacts() {
    if (!view?.detail.run.publishable) return;
    if (view.detail.run.id === "local-preview") return;
    const id = view.detail.run.id;
    artifactController.current?.abort();
    const c = new AbortController();
    artifactController.current = c;
    setArtifactBusy(true);
    setArtifactError("");
    setArtifacts(null);
    artifactCache.current.delete(id);
    try {
      const next = artifactsSchema.parse(
        await client().ps1OptimisationArtifacts(id, c.signal),
      );
      if (next.run_id !== id)
        throw Error("Artifact run does not match the selected run.");
      if (!c.signal.aborted) {
        artifactCache.current.set(id, next);
        setArtifacts(next);
      }
    } catch (e) {
      if (!c.signal.aborted) setArtifactError(errorText(e));
    } finally {
      if (!c.signal.aborted) setArtifactBusy(false);
    }
  }
  function selectAccess(a: Access) {
    setSelectedAccess(a);
    onSelectActivity(a.activity_id);
    onHighlightLocations(
      view?.occupancies
        .filter((o) => o.activity_id === a.activity_id && o.week === a.week)
        .map((o) => o.location_id) ?? [],
    );
  }
  function toggleLock(a: Access) {
    if (!view?.detail.run.publishable) return;
    const p = placement(a);
    setLocks((previous) =>
      previous.some((x) => accessKey(x) === accessKey(a))
        ? previous.filter((x) => accessKey(x) !== accessKey(a))
        : [...previous, p],
    );
  }
  const result = view?.detail.result,
    summary = view?.detail.run,
    validation = view?.detail.validation;
  const objective = result?.objective_components;
  const completeness = validation?.completeness as Record<string, unknown> | undefined;
  const hardViolationCount = validation && Array.isArray(validation.hard_violations) ? validation.hard_violations.length : null;
  const gate = publicationGate({candidate:!!summary && (summary.solver_status==="OPTIMAL"||summary.solver_status==="FEASIBLE"),feasible:validation?.feasible===true,physicalComplete:summary?.physical_validation_complete===true && validation?.physical_validation_complete===true,hardViolations:hardViolationCount,backendAccepted:summary?.publishable===true});
  const canDownload = gate.eligible && !!artifacts && artifacts.run_id===summary?.id && ["SCHEDULE_ACCESS.csv","SCHEDULE_OCCUPANCY.csv","RESULTS.csv"].every(name=>typeof artifacts.files[name]==="string");
  const downloadReason = !gate.eligible ? gate.reason : artifacts?.run_id!==summary?.id ? "Load the accepted artifacts for this run first." : "One or more required CSV files are missing.";
  function downloadValidationReport(){if(!validation||!summary)return;const url=URL.createObjectURL(new Blob([JSON.stringify(validation,null,2)],{type:"application/json"}));const link=document.createElement("a");link.href=url;link.download=`PS1-${summary.scenario}-${summary.id.slice(0,8)}-validation.json`;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  const accessMatches = (a: Access) =>
    (!week || a.week === Number(week)) &&
    (!contract ||
      activityMap.get(a.activity_id)?.contract_number === contract) &&
    (!query ||
      `${a.activity_id} ${activityMap.get(a.activity_id)?.activity_type ?? ""}`
        .toLowerCase()
        .includes(query.toLowerCase()));
  const shownAccesses = (view?.accesses ?? []).filter(accessMatches);
  const shownWeeks = [...new Set(shownAccesses.map((a) => a.week))].sort(
    (a, b) => a - b,
  );
  const occupied = useMemo(
    () => joinOccupancy(view?.occupancies ?? [], view?.accesses ?? []),
    [view],
  );
  const shownOccupancies = occupied.filter(
    (o) =>
      (!week || o.week === Number(week)) &&
      (!location ||
        o.location_id.toLowerCase().includes(location.toLowerCase())) &&
      (!query || o.activity_id.toLowerCase().includes(query.toLowerCase())) &&
      (!contract ||
        activityMap.get(o.activity_id)?.contract_number === contract),
  );
  const contractRows = (view?.detail.contract_results ?? [])
    .filter((c) => !lateOnly || c.overrun_days > 0)
    .sort(
      (a, b) =>
        b.overrun_days - a.overrun_days ||
        a.contract_number.localeCompare(b.contract_number),
    );
  const violations = Array.isArray(validation?.hard_violations)
    ? validation.hard_violations
    : [];
  const warnings = Array.isArray(validation?.warnings)
    ? validation.warnings
    : [];
  const nights = Number(result?.settings.physical_nights_per_week ?? 7);
  const selectedFootprint = selectedAccess
    ? occupied.filter(
        (o) =>
          o.activity_id === selectedAccess.activity_id &&
          o.week === selectedAccess.week,
      )
    : [];
  const acceptedRuns = [
    ...new Map(
      [
        ...history.filter((r) => r.publishable),
        ...comparison.map((item) => item.run).filter((r) => r.publishable),
      ].map((r) => [r.id, r]),
    ).values(),
  ].filter(
    (r) =>
      scenario === "C" ||
      r.scenario === "A" ||
      (scenario === "B" && r.scenario === "B"),
  );
  const baselineRun =
    history.find((r) => r.id === baseline) ??
    (summary?.id === baseline ? summary : undefined);
  return (
    <section
      className="ps1-optimiser"
      aria-label={`Scenario ${scenario} optimisation workspace`}
    >
      <header className="opt-header">
        <div>
          <span className="opt-eyebrow">
            <Activity size={13} /> SCENARIO {scenario} / PLANNING ENGINE
          </span>
          <h2>Make every night count.</h2>
          <p>{scenario === "B" ? "Meet every planned completion date with explicit ECLO and capacity trade-offs." : scenario === "C" ? "Balance weighted delay, bounded capacity elasticity and line-scoped ECLO windows." : "Generate, inspect and refine a track-access plan."}</p>
        </div>
        <span className="opt-engine">
          <i /> OR-Tools CP-SAT
        </span>
      </header>
      <div className="opt-night-terms"><p><strong>physical_night:</strong> Network-wide engineering night used for physical conflicts.</p><p><strong>access_night:</strong> Local contract/type/week allocation index.</p><p><strong>co_share_group:</strong> Local possession-sharing group at one location/week.</p></div>
      {!instanceId && mode === "saved" && (
        <div className="opt-callout">
          <Layers size={20} />
          <div>
            <strong>Save this dataset before generating a schedule.</strong>
            <p>Your run history will belong to this saved instance.</p>
          </div>
          <button className="control" onClick={onSaveDataset}>
            Go to Save Dataset <ArrowRight size={14} />
          </button>
        </div>
      )}
      {scenario === "A" && (
        <div className="opt-callout">
          <div><strong>Scenario A · fixed supply, no ECLO</strong>
            <p>Stateless preview uses the same optimiser and rich validation gate as a saved run, but creates no PostgreSQL history.</p></div>
        </div>
      )}
      {scenario === "B" && (
        <div className="opt-callout">
          <div><strong>Scenario B · strict schedule, flexible supply</strong>
            <p>ECLO is permitted. Completion after the planned date is forbidden. Official objective: 7 × excess access nights + 5 × ECLO nights.</p>
            <p>Both modes call FastAPI. Local preview needs no PostgreSQL and creates no saved history; the frontend-only app.py launcher does not start FastAPI.</p></div>
        </div>
      )}
      {scenario === "C" && (
        <div className="opt-callout">
          <div><strong>Scenario C · balanced and elastic</strong>
            <p>Objective: priority-weighted overrun + 7 × excess access nights + 5 × ECLO nights. Each location/week may exceed supply by at most one.</p>
            <p>Alpha and Beta have independent ECLO windows of at most two consecutive weeks; cross-line Live ECLO must fit both. Both modes call FastAPI.</p></div>
        </div>
      )}
      <div className="opt-config">
        <div className="opt-section-title">
          <h3>
            <SlidersHorizontal size={17} /> Run configuration
          </h3>
          <button
            className="opt-link"
            disabled={solving}
            onClick={() => {
              setOptions(defaults);
              setBaseline("");
              setLocks([]);
            }}
          >
            Reset defaults
          </button>
        </div>
        <div className="opt-fields">
          <div className="opt-presets" role="group" aria-label="Solver presets">{(Object.keys(solverPresets) as Array<keyof typeof solverPresets>).map(name=><button type="button" className="control" key={name} disabled={solving} onClick={()=>setOptions({...options,...solverPresets[name]})}>{name}</button>)}<p>Longer limits improve search but do not guarantee optimality.</p></div>
          {previewSupported && <label>Run mode<select aria-label="Optimisation mode" value={mode} disabled={solving} onChange={(e) => setMode(e.target.value as "preview" | "saved")}>
            <option value="preview">Local preview · no saved history</option><option value="saved">Saved optimisation · PostgreSQL history</option>
          </select></label>}
          <label>
            Time budget · seconds
            <input
              aria-label="Time limit in seconds"
              type="number"
              min="0.1"
              max="120"
              step="0.1"
              value={options.time_limit_seconds}
              disabled={solving}
              onChange={(e) =>
                setOptions({
                  ...options,
                  time_limit_seconds: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Physical nights per week
            <input
              aria-label="Physical nights per week"
              type="number"
              min="1"
              max="7"
              value={options.physical_nights_per_week}
              disabled={solving}
              onChange={(e) =>
                setOptions({
                  ...options,
                  physical_nights_per_week: Number(e.target.value),
                })
              }
            />
          </label>
          <label>
            Baseline preference
            <select
              aria-label="Baseline run"
              value={baseline}
              disabled={solving || mode === "preview"}
              onChange={(e) => setBaseline(e.target.value)}
            >
              <option value="">No baseline</option>
              {baselineRun &&
                !acceptedRuns.some((r) => r.id === baselineRun.id) && (
                  <option value={baselineRun.id}>
                    {baselineRun.id.slice(0, 8)} · {baselineRun.objective_score}
                  </option>
                )}
              {acceptedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id.slice(0, 8)} · Score {r.objective_score}
                </option>
              ))}
            </select>
          </label>
        </div>
        <details>
          <summary>Advanced settings</summary>
          <div className="opt-fields">
            <label>
              Random seed
              <input
                aria-label="Random seed"
                type="number"
                min="0"
                max="2147483647"
                value={options.random_seed}
                disabled={solving}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    random_seed: Number(e.target.value),
                  })
                }
              />
            </label>
            <label>
              Deterministic time limit
              <input
                aria-label="Deterministic time limit"
                type="number"
                step="0.001"
                min="0.001"
                max="60"
                value={options.deterministic_time_limit}
                disabled={solving}
                onChange={(e) =>
                  setOptions({
                    ...options,
                    deterministic_time_limit: Number(e.target.value),
                  })
                }
              />
            </label>
          </div>
          <p className="opt-muted">
            Physical nights are abstract network-wide slots within each week; no dated
            engineering-night calendar is supplied. Access nights remain contract-local and co-share groups remain location-local.
          </p>
        </details>
        <div className="opt-actions">
          <button
            className="opt-primary"
            disabled={solving || (mode === "saved" && !instanceId) || (mode === "preview" && (!previewSupported || !Object.keys(instanceFiles).length))}
            onClick={() => void run()}
          >
            <Play size={15} />
            {solving ? "Searching…" : "Generate schedule"}
          </button>
          <span className="opt-muted">
            {locks.length} hard locks ·{" "}
            {baseline ? "Baseline selected" : "No baseline"}
          </span>
          {baseline && (
            <button
              className="opt-link"
              disabled={solving}
              onClick={() => setBaseline("")}
            >
              Clear baseline
            </button>
          )}
        </div>
        {locks.length > 0 && (
          <details>
            <summary>
              <Lock size={13} /> Review {locks.length} hard placement locks
            </summary>
            <p>
              A baseline is a soft preference. These locks must be satisfied.
            </p>
            <ul className="opt-locks">
              {locks.map((p) => (
                <li key={accessKey(p)}>
                  {p.activity_id} #{p.access_seq} · W{p.week} / N
                  {p.physical_night}
                  <button
                    disabled={solving}
                    aria-label={`Remove lock ${p.activity_id} ${p.access_seq}`}
                    onClick={() =>
                      setLocks(
                        locks.filter((x) => accessKey(x) !== accessKey(p)),
                      )
                    }
                  >
                    <X size={14} />
                  </button>
                </li>
              ))}
            </ul>
            <button
              className="opt-link"
              disabled={solving}
              onClick={() => setLocks([])}
            >
              Clear all locks
            </button>
          </details>
        )}
      </div>
      {solving && (
        <div className="opt-solving" role="status">
          <div className="opt-orbit">
            <Activity size={25} />
          </div>
          <div>
            <h3>Searching the night network</h3>
            <p>
              Allocating activities within capacity, compatibility and placement
              constraints.
            </p>
            <span>
              {elapsed}s elapsed · {attempt?.body.time_limit_seconds}s solver
              budget · {attempt?.body.physical_nights_per_week} nights/week
            </span>
          </div>
          <button className="control" onClick={stopWaiting}>
            Stop waiting
          </button>
        </div>
      )}
      <div aria-live="polite">
        {notice && <p className="opt-notice">{notice}</p>}
      </div>
      {runError && (
        <p role="alert" className="ps1-error">
          {runError}
        </p>
      )}
      {attempt && !solving && (
        <div className="opt-actions">
          <button
            className="control"
            disabled={(mode === "saved" && !instanceId) || (mode === "preview" && (!previewSupported || !Object.keys(instanceFiles).length))}
            onClick={() => void run(true)}
          >
            Retry exact attempt
          </button>
          <span className="opt-muted">
            Uses the original settings and idempotency key, even if the form has
            changed.
          </span>
          <Evidence value={attempt.body} label="Original attempt settings" />
        </div>
      )}
      <div className="opt-layout">
        <aside className="opt-history" aria-label="Saved run history">
          <div className="opt-section-title">
            <h3>
              <History size={17} /> Saved runs <small>{historyTotal}</small>
            </h3>
            <button
              aria-label="Refresh run history"
              title="Refresh run history"
              disabled={!instanceId || historyBusy}
              onClick={() => void loadHistory()}
            >
              <RefreshCw size={16} className={historyBusy ? "opt-spin" : ""} />
            </button>
          </div>
          {historyError && (
            <p role="alert" className="ps1-error">
              {historyError}
            </p>
          )}
          {!history.length && !historyBusy && (
            <div className="opt-empty">
              <History size={28} />
              <p>No saved runs yet.</p>
              <span>Generate your first Scenario {scenario} schedule.</span>
            </div>
          )}
          {historyBusy && !history.length && (
            <div className="opt-skeleton" role="status">
              Loading run history…
            </div>
          )}
          <div className="opt-history-items">
            {history.map((r) => (
              <button
                key={r.id}
                className={`opt-history-item ${selectedId === r.id ? "is-selected" : ""}`}
                aria-pressed={selectedId === r.id}
                onClick={() => void openRun(r.id)}
              >
                <span className="opt-row">
                  <span
                    className={`opt-badge ${r.publishable ? "good" : "neutral"}`}
                  >
                    {r.solver_status}
                  </span>
                  <strong>{r.objective_score ?? "—"}</strong>
                </span>
                <time>{new Date(r.created_at).toLocaleString()}</time>
                <span className="opt-row">
                  <code>{r.id.slice(0, 8)}</code>
                  <span>{r.solve_duration_seconds.toFixed(1)}s</span>
                </span>
                <span>
                  {r.terminal_outcome} ·{" "}
                  {r.publishable
                    ? "Internally publishable"
                    : "No accepted schedule"}
                </span>
                <span>
                  {r.physical_validation_complete
                    ? "✓ Physical checks complete"
                    : "Physical checks incomplete"}
                  {r.baseline_run_id ? " · Baseline" : ""}
                </span>
              </button>
            ))}
          </div>
          {historyOffset < historyTotal && (
            <button
              className="control"
              disabled={historyBusy}
              onClick={() => void loadHistory(true)}
            >
              Load older runs
            </button>
          )}
          {comparison.length > 0 && <details className="opt-evidence">
            <summary>Latest A/B/C comparison</summary>
            <p className="opt-muted">Scenario objectives use different formulas and must not be ranked directly without context.</p>
            {comparison.map((item) => {
              const objective = item.result.objective_components as Record<string, unknown> | null;
              return <div key={item.run.id} className="opt-history-item">
                <strong>Scenario {item.run.scenario} · {item.run.solver_status}</strong>
                <span>Objective: {item.run.objective_score ?? "—"} · {display(objective?.formula)}</span>
                <span>Weighted/raw overrun: {display(objective?.priority_weighted_overrun)} / {display(objective?.overrun_days_total)} days</span>
                <span>Excess / ECLO: {display(objective?.excess_access_nights_total)} / {display(objective?.eclo_nights_total)}</span>
                <span>Over-delivery: {item.result.workload_delivery.reduce((sum,row)=>sum+Number(row.over_delivery ?? 0),0)} · Hotspots: {item.result.capacity_hotspots.length}</span>
                <span>Late contracts: {display(objective?.contracts_overrunning)} · Solve: {item.run.solve_duration_seconds.toFixed(2)}s</span>
                <span>Publishable: {item.run.publishable ? "Yes" : "No"} · Physical: {item.run.physical_validation_complete ? "Complete" : "Incomplete"}</span>
              </div>;
            })}
          </details>}
        </aside>
        <main className="opt-main">
          {loading && (
            <div className="opt-skeleton" role="status">
              Loading saved result and complete schedule pages…
            </div>
          )}
          {loadError && (
            <div className="ps1-error" role="alert">
              {loadError}
              <button
                className="control"
                onClick={() => void openRun(selectedId, true)}
              >
                Retry loading run
              </button>
            </div>
          )}
          {!view && !loading && !loadError && (
            <div className="opt-empty opt-welcome">
              <Layers size={40} />
              <h3>Your planning canvas</h3>
              <p>
                Generate a schedule or open a saved run to explore every access,
                possession and completion date.
              </p>
              <div className="opt-preview-grid" aria-hidden="true">
                {Array.from({ length: 21 }, (_, i) => (
                  <i key={i} />
                ))}
              </div>
            </div>
          )}
          {view && summary && result && (
            <>
              <div
                className={`opt-result ${summary.publishable ? "accepted" : "rejected"}`}
              >
                <div className="opt-section-title">
                  <span className="opt-eyebrow">
                    {summary.id === "local-preview" ? "LOCAL PREVIEW" : "SAVED RESULT"} · {summary.id.slice(0, 8)}
                  </span>
                  <span
                    className={`opt-badge ${summary.publishable ? "good" : "neutral"}`}
                  >
                    {summary.solver_status}
                  </span>
                </div>
                <h3>{statusLabel(summary.solver_status)}</h3>
                <p role="status">{solverExplanation(summary.solver_status)}</p>
                <p>
                  {summary.publishable ? (
                    <>
                      <CheckCircle2 size={15} /> Internally publishable
                    </>
                  ) : (
                    <>
                      <AlertTriangle size={15} /> No internally accepted
                      schedule
                    </>
                  )}{" "}
                  · {summary.terminal_outcome}
                </p>
                <div className="opt-metrics">
                  <Metric
                    label="Internal objective"
                    value={summary.objective_score}
                  />
                  <Metric
                    label="Solve duration"
                    value={`${summary.solve_duration_seconds.toFixed(2)}s`}
                  />
                  <Metric
                    label="Access nights"
                    value={objective?.nights_scheduled}
                  />
                  <Metric
                    label="Late contracts"
                    value={objective?.contracts_overrunning}
                  />
                  <Metric
                    label="Total overrun · days"
                    value={objective?.overrun_days_total}
                  />
                  <Metric
                    label="Weighted overrun"
                    value={objective?.priority_weighted_overrun}
                  />
                  <Metric label="Raw overrun" value={objective?.overrun_days_total} />
                  <Metric label="Excess access nights" value={objective?.excess_access_nights_total} />
                  <Metric label="ECLO nights" value={objective?.eclo_nights_total} />
                  <Metric label="Final objective" value={summary.objective_score} />
                  {(summary.scenario === "B" || summary.scenario === "C") && <>
                    <Metric label="Excess penalty · 7×" value={objective?.excess_penalty} />
                    <Metric label="ECLO penalty · 5×" value={objective?.eclo_penalty} />
                    <Metric label="Workload over-delivery" value={result.workload_delivery.reduce((total, row) => total + Number(row.over_delivery ?? 0), 0)} />
                    {summary.scenario === "B" && <Metric label="Contract completion gate" value={result.contract_completion_gate ? "Passed" : "Failed"} />}
                    <Metric label="Baseline movement" value={result.baseline_movement} />
                  </>}
                </div>
                <p className="opt-trust">
                  Internal provisional validator · {validation ? (validation.feasible===true ? "Schedule feasible" : "Schedule infeasible") : "Schedule feasibility unverified"} · Judge validation not run · Score verification: internal only · Conflict severity is separate from schedule objective
                </p>
              </div>
              <section className="opt-publication" aria-label="Publication gate"><h3>Publication checklist</h3><ul>{gate.checks.map(check=><li key={check.label}>{check.passed?"✓":"○"} {check.label}: {check.passed?"Passed":check.reason}</li>)}</ul><p>{gate.eligible?"CSV export permitted by internal validation.":`CSV downloads disabled: ${gate.reason}`}</p></section>
              <section className="opt-demo-summary" aria-label="Demo summary"><h3>Demo summary</h3><dl><div><dt>Scenario</dt><dd>{summary.scenario}</dd></div><div><dt>Solver status</dt><dd>{summary.solver_status}</dd></div><div><dt>Feasibility</dt><dd>{validation ? validation.feasible===true?"Schedule feasible":"Schedule infeasible":"Unverified"}</dd></div><div><dt>Objective</dt><dd>{summary.objective_score??"Not eligible"}</dd></div><div><dt>Physical validation</dt><dd>{summary.physical_validation_complete?"Complete":"Incomplete"}</dd></div><div><dt>Hard violations</dt><dd>{hardViolationCount??"Not checked"}</dd></div><div><dt>Publication eligibility</dt><dd>{gate.eligible?"Eligible":"Not eligible"}</dd></div><div><dt>Score status</dt><dd>Internal only · Judge validation not run</dd></div></dl></section>
              <div className="opt-quality">
                <span>
                  <CheckCircle2 size={14} /> Primary optimal:{" "}
                  <b>{summary.primary_optimal ? "Yes" : "Not proven"}</b>
                </span>
                <span>
                  All stages optimal:{" "}
                  <b>{summary.lexicographic_complete ? "Yes" : "No"}</b>
                </span>
                <span>
                  Physical checks:{" "}
                  <b>
                    {summary.physical_validation_complete
                      ? "Complete"
                      : "Incomplete"}
                  </b>
                </span>
                <span>
                  Primary bound: <b>{summary.primary_objective_bound ?? "—"}</b>
                </span>
                <span>
                  Gap:{" "}
                  <b>
                    {summary.primary_objective_gap === null
                      ? "—"
                      : `${(Number(summary.primary_objective_gap) * 100).toFixed(2)}%`}
                  </b>
                </span>
              </div>
              {summary.publishable && !summary.primary_optimal && (
                <p className="opt-muted">
                  A valid schedule was found; a better objective may still be
                  possible.
                </p>
              )}
              <div className="opt-actions">
                {summary.publishable && summary.id !== "local-preview" && (
                  <button
                    className="control"
                    disabled={solving}
                    onClick={() => {
                      setBaseline(summary.id);
                      setNotice(
                        `Run ${summary.id.slice(0, 8)} selected as a soft baseline for the next attempt.`,
                      );
                    }}
                  >
                    Use as baseline
                  </button>
                )}
                {summary.id !== "local-preview" && <button
                  className="opt-link"
                  onClick={() => void openRun(summary.id, true)}
                >
                  Reload saved result
                </button>}
                <code>{summary.id}</code>
              </div>
              <div
                className="opt-tabs"
                role="tablist"
                aria-label="Run result views"
              >
                {tabs.map((t) => (
                  <button
                    key={t}
                    id={`opt-tab-${t}`}
                    role="tab"
                    aria-selected={tab === t}
                    aria-controls="opt-result-panel"
                    tabIndex={tab === t ? 0 : -1}
                    onKeyDown={(e) => {
                      if (
                        ["ArrowRight", "ArrowLeft", "Home", "End"].includes(
                          e.key,
                        )
                      ) {
                        e.preventDefault();
                        const next =
                          e.key === "Home"
                            ? 0
                            : e.key === "End"
                              ? tabs.length - 1
                              : (tabs.indexOf(t) +
                                  (e.key === "ArrowRight" ? 1 : -1) +
                                  tabs.length) %
                                tabs.length;
                        setTab(tabs[next]);
                        document
                          .getElementById(`opt-tab-${tabs[next]}`)
                          ?.focus();
                      }
                    }}
                    onClick={() => setTab(t)}
                  >
                    {t}
                  </button>
                ))}
              </div>
              <div
                id="opt-result-panel"
                role="tabpanel"
                aria-labelledby={`opt-tab-${tab}`}
                className="opt-panel"
                key={tab}
              >
                {(tab === "Schedule" || tab === "Occupancy") && (
                  <div className="opt-filters">
                    <label>
                      Week
                      <input
                        aria-label="Filter week"
                        placeholder="All weeks"
                        type="number"
                        min="1"
                        max="520"
                        value={week}
                        onChange={(e) => setWeek(e.target.value)}
                      />
                    </label>
                    <label>
                      Activity
                      <input
                        aria-label="Filter activity"
                        placeholder="Search activity…"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                      />
                    </label>
                    <label>
                      Contract
                      <select
                        aria-label="Filter contract"
                        value={contract}
                        onChange={(e) => setContract(e.target.value)}
                      >
                        <option value="">All contracts</option>
                        {contracts.map((c) => (
                          <option key={c}>{c}</option>
                        ))}
                      </select>
                    </label>
                    {tab === "Occupancy" ? (
                      <label>
                        Location
                        <input
                          aria-label="Filter location"
                          placeholder="Tunnel or platform…"
                          value={location}
                          onChange={(e) => setLocation(e.target.value)}
                        />
                      </label>
                    ) : (
                      <button
                        className="control"
                        aria-pressed={compact}
                        onClick={() => setCompact(!compact)}
                      >
                        {compact ? "Expanded density" : "Compact density"}
                      </button>
                    )}
                    <button
                      className="opt-link"
                      onClick={() => {
                        setWeek("");
                        setQuery("");
                        setContract("");
                        setLocation("");
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                )}
                {tab === "Schedule" && (
                  <>
                    <div className="opt-section-title">
                      <span className="opt-muted">
                        {shownAccesses.length} accesses · Network-wide physical
                        nights
                      </span>
                      <label className="opt-jump">
                        Jump to week{" "}
                        <select
                          aria-label="Jump to week"
                          defaultValue=""
                          onChange={(e) =>
                            document
                              .getElementById(`opt-week-${e.target.value}`)
                              ?.scrollIntoView({
                                behavior: window.matchMedia(
                                  "(prefers-reduced-motion: reduce)",
                                ).matches
                                  ? "instant"
                                  : "smooth",
                                block: "nearest",
                              })
                          }
                        >
                          <option value="">Select</option>
                          {shownWeeks.map((w) => (
                            <option key={w} value={w}>
                              {w}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    {!shownAccesses.length ? (
                      <div className="opt-empty">
                        <Clock3 size={28} />
                        <p>
                          {summary.publishable
                            ? "No accesses match these filters."
                            : "This run has no accepted access placements."}
                        </p>
                      </div>
                    ) : (
                      <div
                        className={`opt-timeline ${compact ? "compact" : ""}`}
                      >
                        <div
                          className="opt-grid-heading"
                          style={{
                            gridTemplateColumns: `65px repeat(${nights},minmax(130px,1fr))`,
                          }}
                        >
                          <span>WEEK</span>
                          {Array.from({ length: nights }, (_, i) => (
                            <span key={i}>NIGHT {i + 1}</span>
                          ))}
                        </div>
                        {shownWeeks.map((w) => (
                          <div
                            id={`opt-week-${w}`}
                            className="opt-week"
                            key={w}
                            style={{
                              gridTemplateColumns: `65px repeat(${nights},minmax(130px,1fr))`,
                            }}
                          >
                            <strong>W{w}</strong>
                            {Array.from({ length: nights }, (_, i) => (
                              <div className="opt-night" key={i}>
                                {shownAccesses
                                  .filter(
                                    (a) =>
                                      a.week === w &&
                                      a.physical_night === i + 1,
                                  )
                                  .map((a) => (
                                    <button
                                      key={accessKey(a)}
                                      className={`opt-access ${selectedAccess && accessKey(selectedAccess) === accessKey(a) ? "is-selected" : ""}`}
                                      style={{
                                        borderLeftColor: color(a.activity_id),
                                      }}
                                      onClick={() => selectAccess(a)}
                                      aria-label={`${a.activity_id} access ${a.access_seq}, week ${a.week}, physical night ${a.physical_night}`}
                                    >
                                      <strong>{a.activity_id}</strong>
                                      <span>
                                        #{a.access_seq} · local{" "}
                                        {a.access_night ?? "—"}
                                      </span>
                                      <span>{movement(a)}</span>
                                      {(a.locked ||
                                        locks.some(
                                          (l) => accessKey(l) === accessKey(a),
                                        )) && (
                                        <span>
                                          <Lock size={10} />{" "}
                                          {a.locked
                                            ? "Saved lock"
                                            : "Next-run lock"}
                                        </span>
                                      )}
                                      {Boolean(a.eclo) && <span>ECLO</span>}
                                    </button>
                                  ))}
                              </div>
                            ))}
                          </div>
                        ))}
                      </div>
                    )}
                    <p className="opt-muted">
                      Local access-night indices do not establish concurrency
                      across allocation pools.
                    </p>
                  </>
                )}
                {tab === "Occupancy" && (
                  <>
                    <p className="opt-muted">
                      {shownOccupancies.length} occupancy rows · Co-sharing
                      labels apply within one location and week.
                    </p>
                    <div className="ps1-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Week</th>
                            <th>Physical night</th>
                            <th>Location</th>
                            <th>Activity</th>
                            <th>Local co-share group</th>
                          </tr>
                        </thead>
                        <tbody>
                          {shownOccupancies.map((o) => (
                            <tr key={occupancyKey(o)}>
                              <td>{o.week}</td>
                              <td>
                                {o.physical_nights.join(", ") || "Unavailable"}
                              </td>
                              <td>
                                <button
                                  onClick={() =>
                                    onHighlightLocations([o.location_id])
                                  }
                                >
                                  {o.location_id}
                                </button>
                              </td>
                              <td>
                                <button
                                  onClick={() => {
                                    const a = view.accesses.find(
                                      (a) =>
                                        a.activity_id === o.activity_id &&
                                        a.week === o.week,
                                    );
                                    if (a) selectAccess(a);
                                  }}
                                >
                                  {o.activity_id}
                                </button>
                              </td>
                              <td>{o.co_share_group}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    {!shownOccupancies.length && (
                      <p className="opt-empty">
                        No accepted occupancy records match these filters.
                      </p>
                    )}
                  </>
                )}
                {tab === "Contracts" && (
                  <>
                    <div className="opt-actions">
                      <label>
                        <input
                          type="checkbox"
                          checked={lateOnly}
                          onChange={(e) => setLateOnly(e.target.checked)}
                        />{" "}
                        Late contracts only
                      </label>
                      <span className="opt-muted">
                        Sorted by greatest overrun
                      </span>
                    </div>
                    <div
                      className="opt-bars"
                      aria-label="Contract overrun distribution"
                    >
                      {contractRows.map((c) => (
                        <div key={c.contract_number}>
                          <span>{c.contract_number}</span>
                          <meter
                            min="0"
                            max={Math.max(
                              1,
                              ...contractRows.map((x) => x.overrun_days),
                            )}
                            value={c.overrun_days}
                            aria-label={`${c.contract_number} overrun days`}
                          />
                          <b>{c.overrun_days}d</b>
                        </div>
                      ))}
                    </div>
                    <div className="ps1-table-wrap">
                      <table>
                        <thead>
                          <tr>
                            <th>Contract</th>
                            <th>Planned completion</th>
                            <th>Simulated completion</th>
                            <th>Overrun days</th>
                            <th>Weighted overrun</th>
                            <th>Priority</th>
                            <th>Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {contractRows.map((c) => {
                            const projects =
                              dataset.tables.project_details.filter(
                                (p) => p.contract_number === c.contract_number,
                              );
                            return (
                              <tr key={c.contract_number}>
                                <td>
                                  <button
                                    onClick={() => {
                                      setContract(c.contract_number);
                                      setWeek("");
                                      setQuery("");
                                      setTab("Schedule");
                                    }}
                                  >
                                    {c.contract_number}
                                  </button>
                                </td>
                                <td>
                                  {[
                                    ...new Set(
                                      projects.map(
                                        (p) => p.planned_completion_date,
                                      ),
                                    ),
                                  ].join(", ")}
                                </td>
                                <td>{c.simulated_completion_date}</td>
                                <td>{c.overrun_days}</td>
                                <td>{c.weighted_overrun}</td>
                                <td>
                                  {[
                                    ...new Set(
                                      projects.map((p) => p.contract_priority),
                                    ),
                                  ].join(", ")}
                                </td>
                                <td>
                                  {c.overrun_days > 0 ? "Late" : "On time"}
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                    {!contractRows.length && (
                      <p className="opt-empty">
                        No contract results match this view.
                      </p>
                    )}
                    <h4>Changes from baseline</h4>
                    {!summary.baseline_run_id ? (
                      <p className="opt-muted">
                        No saved baseline was used for this run.
                      </p>
                    ) : (
                      <div className="ps1-table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Type / ID</th>
                              <th>Baseline completion</th>
                              <th>New completion</th>
                              <th>Change</th>
                              <th>Explanation</th>
                            </tr>
                          </thead>
                          <tbody>
                            {result.completion_changes.map((c, i) => (
                              <tr key={i}>
                                <td>
                                  {display(c.kind)} ·{" "}
                                  {display(c.activity_id ?? c.contract_number)}
                                </td>
                                <td>{display(c.baseline_completion_date)}</td>
                                <td>
                                  {display(
                                    c.completion_date ??
                                      c.simulated_completion_date,
                                  )}
                                </td>
                                <td>
                                  {typeof c.change_days === "number"
                                    ? `${Math.abs(c.change_days)}d ${c.change_days < 0 ? "earlier" : c.change_days > 0 ? "later" : "unchanged"}`
                                    : "Unavailable"}
                                </td>
                                <td className="opt-wrap">
                                  {display(c.reason)}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
                {tab === "Validation" && (
                  <>
                    <div className="opt-metrics">
                      <Metric label="Workload completeness" value={completeness?.workload_gate_passed===true?"Complete":completeness?"Incomplete":"Not checked"} />
                      <Metric label="Activities complete" value={completeness?`${display(completeness.activities_complete)} / ${display(completeness.activity_count)}`:"Not checked"} />
                      <Metric
                        label="Physical-night checks"
                        value={
                          summary.physical_validation_complete
                            ? "Complete"
                            : "Incomplete"
                        }
                      />
                      <Metric
                        label="Hard violations"
                        value={validation ? violations.length : null}
                      />
                      <Metric
                        label="Validator"
                        value={validation?.validator_version}
                      />
                      <Metric
                        label="Validation status"
                        value={validation?.validation_status}
                      />
                    </div>
                    <p className="opt-muted">
                      Internal validation is not official judge acceptance or
                      operational approval.
                    </p>
                    {!validation && (
                      <p>No validation report is available for this outcome.</p>
                    )}
                    {violations.map((v, i) => (
                      <Evidence
                        key={i}
                        value={v}
                        label={`Hard violation ${i + 1}`}
                      />
                    ))}
                    {warnings.map((w, i) => (
                      <Evidence key={i} value={w} label={`Warning ${i + 1}`} />
                    ))}
                    {validation && (
                      <Evidence
                        value={validation}
                        label="Complete saved validation report"
                      />
                    )}
                  </>
                )}
                {tab === "Diagnostics" && (
                  <>
                    {(summary.scenario === "B" || summary.scenario === "C") && <>
                      <h4>Workload delivery</h4>
                      <Evidence value={result.workload_delivery} label="Required, delivered and over-delivered workload" />
                      <h4>Capacity hotspots</h4>
                      {result.capacity_hotspots.length ? result.capacity_hotspots.map((hotspot, i) =>
                        <Evidence key={`hotspot-${i}`} value={hotspot} label={`${display(hotspot.location_id)} · week ${display(hotspot.week)}`} />)
                        : <p>No capacity hotspots were reported.</p>}
                    </>}
                    {summary.scenario === "C" && <>
                      <h4>Scenario C ECLO windows</h4>
                      <Evidence value={result.eclo_windows} label="Alpha and Beta ECLO windows" />
                      <Evidence value={result.cross_line_eclo_activities} label="Cross-line ECLO activities" />
                    </>}
                    <h4>Solver stages</h4>
                    {result.stages.length ? (
                      result.stages.map((s, i) => (
                        <Evidence
                          key={i}
                          value={s}
                          label={`Stage ${i + 1} · ${display(s.name ?? s.stage)}`}
                        />
                      ))
                    ) : (
                      <p>No solver-stage records.</p>
                    )}
                    <h4>Diagnostics</h4>
                    {view.detail.diagnostics.length ? (
                      view.detail.diagnostics.map((d, i) => (
                        <Evidence
                          key={i}
                          value={d}
                          label={display(d.code ?? `Diagnostic ${i + 1}`)}
                        />
                      ))
                    ) : (
                      <p>No diagnostics were reported.</p>
                    )}
                    <Evidence
                      value={result.settings}
                      label="Effective settings and policy"
                    />
                    <Evidence
                      value={summary}
                      label="Saved run metadata and original request"
                    />
                    {result.failed_candidate != null && (
                      <Evidence
                        value={result.failed_candidate}
                        label="Rejected candidate · diagnostic only"
                      />
                    )}
                  </>
                )}
                {tab === "Downloads" && (
                  <>
                    {!gate.eligible ? (
                      <div className="opt-empty">
                        <Lock size={28} />
                        <h4>CSV downloads disabled</h4>
                        <p>{gate.reason}</p>
                      </div>
                    ) : (
                      <>
                        <p>
                          Download the exact CSV strings saved with this
                          accepted run.
                        </p>
                        <button
                          className="control"
                          disabled={artifactBusy}
                          onClick={() => void loadArtifacts()}
                        >
                          {artifactBusy
                            ? "Loading saved files…"
                            : artifacts
                              ? "Refresh artifacts"
                              : "Load saved artifacts"}
                        </button>
                        {artifactError && (
                          <p role="alert" className="ps1-error">
                            {artifactError}
                          </p>
                        )}
                        {artifacts && (
                          <>
                            <div className="opt-downloads">
                              {Object.entries(artifacts.files).filter(([name])=>["SCHEDULE_ACCESS.csv","SCHEDULE_OCCUPANCY.csv","RESULTS.csv"].includes(name)).map(
                                ([name, text]) => (
                                  <button
                                    className="opt-download"
                                    key={name}
                                    disabled={!canDownload}
                                    title={!canDownload?downloadReason:undefined}
                                    onClick={() => downloadCsv(name, text)}
                                  >
                                    <Download size={22} />
                                    <strong>{name}</strong>
                                    <span>
                                      {csvBlob(text).size.toLocaleString()}{" "}
                                      bytes · exact saved CSV
                                    </span>
                                  </button>
                                ),
                              )}
                            </div>
                            <button
                              className="opt-primary"
                              disabled={!canDownload}
                              onClick={() =>
                                ["SCHEDULE_ACCESS.csv","SCHEDULE_OCCUPANCY.csv","RESULTS.csv"].forEach(name=>downloadCsv(name,artifacts.files[name]))
                              }
                            >
                              Download all files
                            </button>
                            <p className="opt-muted">
                              Your browser may ask to allow multiple downloads.
                            </p>
                            {!canDownload&&<p role="status">CSV downloads disabled: {downloadReason}</p>}
                          </>
                        )}
                      </>
                    )}
                    <p className="opt-trust">
                      Judge validation: Not run · Score verification: Internal
                      only
                    </p>
                    <button className="control" disabled={!validation} onClick={downloadValidationReport}>Download JSON validation report</button>
                  </>
                )}
              </div>
              {selectedAccess && (
                <section
                  className="opt-inspector"
                  aria-label="Selected access details"
                >
                  <div className="opt-section-title">
                    <h4>
                      <Activity size={15} /> {selectedAccess.activity_id} ·
                      Access #{selectedAccess.access_seq}
                    </h4>
                    <button
                      aria-label="Close access details"
                      onClick={() => {
                        setSelectedAccess(null);
                        onHighlightLocations([]);
                      }}
                    >
                      <X size={17} />
                    </button>
                  </div>
                  <p>
                    Week {selectedAccess.week} · Physical night{" "}
                    {selectedAccess.physical_night} · Local index{" "}
                    {selectedAccess.access_night ?? "—"} ·{" "}
                    {movement(selectedAccess)}
                  </p>
                  <p className="opt-muted">
                    Baseline:{" "}
                    {selectedAccess.baseline_week === null
                      ? "Not available"
                      : `W${selectedAccess.baseline_week} / N${selectedAccess.baseline_physical_night}`}{" "}
                    · Saved lock: {selectedAccess.locked ? "Yes" : "No"}
                  </p>
                  <div className="opt-footprint">
                    {selectedFootprint.map((o) => (
                      <button
                        key={o.location_id}
                        onClick={() => onHighlightLocations([o.location_id])}
                      >
                        {o.location_id}
                        <small>Group {o.co_share_group}</small>
                      </button>
                    ))}
                  </div>
                  <button
                    className="control"
                    disabled={solving}
                    onClick={() => toggleLock(selectedAccess)}
                  >
                    {locks.some(
                      (l) => accessKey(l) === accessKey(selectedAccess),
                    ) ? (
                      <>
                        <Unlock size={14} /> Remove next-run lock
                      </>
                    ) : (
                      <>
                        <Lock size={14} /> Lock for next run
                      </>
                    )}
                  </button>
                </section>
              )}
            </>
          )}
        </main>
      </div>
    </section>
  );
}
