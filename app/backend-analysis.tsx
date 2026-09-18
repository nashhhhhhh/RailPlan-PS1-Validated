"use client";
import { useEffect, useRef, useState } from "react";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog";
import { createAnalysisApi, type EngineeringWindow, type Centre, type AnalysisSummary, type AnalysisConflict } from "./analysis-api";

const defaultUrl = process.env.NEXT_PUBLIC_RAILPLAN_API_URL || "http://127.0.0.1:8000";
const defaultUser = process.env.NEXT_PUBLIC_RAILPLAN_DEMO_USER_ID || "1a677983-6052-53d0-a3fa-880c7a5e186a";
const stamp = (value: string) => new Date(value).toLocaleString("en-SG", { timeZone: "Asia/Singapore" });

export default function BackendAnalysis({ onClose }: { onClose: () => void }) {
  const [url, setUrl] = useState(defaultUrl), [userId, setUserId] = useState(defaultUser);
  const [windows, setWindows] = useState<EngineeringWindow[]>([]), [windowId, setWindowId] = useState("");
  const [centre, setCentre] = useState<Centre | null>(null), [scenarioId, setScenarioId] = useState("");
  const [summary, setSummary] = useState<AnalysisSummary | null>(null), [conflicts, setConflicts] = useState<AnalysisConflict[]>([]);
  const [busy, setBusy] = useState(false), [error, setError] = useState(""), [connected, setConnected] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);

  function clearResult() { setSummary(null); setConflicts([]); setError(""); }
  function begin() {
    controller.current?.abort();
    const next = new AbortController(); controller.current = next;
    setBusy(true); clearResult(); return next;
  }
  function fail(err: unknown, task: AbortController) {
    if (!task.signal.aborted) setError(err instanceof TypeError
      ? "Cannot reach the backend. Start FastAPI, check the backend address and allowed frontend origin, then retry."
      : err instanceof Error ? err.message : "Analysis failed.");
  }
  async function connect() {
    const task = begin(); setConnected(false); setWindows([]); setCentre(null); setWindowId(""); setScenarioId("");
    try {
      const api = createAnalysisApi(url.trim(), userId.trim());
      const list = await api.windows(task.signal);
      const first = list[0];
      const details = first ? await api.centre(first.id, task.signal) : null;
      if (task.signal.aborted) return;
      setWindows(list); setWindowId(first?.id || ""); setCentre(details); setConnected(true);
    } catch (err) { fail(err, task); }
    finally { if (!task.signal.aborted) setBusy(false); }
  }
  async function selectWindow(id: string) {
    const task = begin(); setWindowId(id); setScenarioId(""); setCentre(null);
    try {
      const data = await createAnalysisApi(url.trim(), userId.trim()).centre(id, task.signal);
      if (!task.signal.aborted) setCentre(data);
    } catch (err) { fail(err, task); }
    finally { if (!task.signal.aborted) setBusy(false); }
  }
  async function analyse() {
    if (busy || !centre || !windowId) return;
    const task = begin();
    try {
      const api = createAnalysisApi(url.trim(), userId.trim());
      const result = await api.run(windowId, scenarioId, task.signal);
      if (result.status === "failed") throw new Error(result.detail || `Conflict analysis ${result.id} failed.`);
      const rows = await api.conflicts(result.id, task.signal);
      if (rows.length !== result.conflict_count) throw new Error("The saved result count does not match the analysis summary. Please retry.");
      if (!task.signal.aborted) { setSummary(result); setConflicts(rows); }
    } catch (err) { fail(err, task); }
    finally { if (!task.signal.aborted) setBusy(false); }
  }
  const requests = new Map((centre?.requests || []).map(r => [r.id, `${r.request_code} · ${r.title}`]));
  const selectedWindow = windows.find(w => w.id === windowId);
  function changeConnection(change: () => void) {
    change(); setConnected(false); setCentre(null); setWindows([]); setWindowId(""); clearResult();
  }

  return <Dialog open onOpenChange={open => { if (!open) onClose(); }}>
    <DialogContent className="backend-analysis-dialog">
      <DialogTitle>Analyse saved maintenance requests</DialogTitle>
      <DialogDescription>Run deterministic checks on a saved engineering window or scenario. Local timeline edits and newly composed demo requests are not included.</DialogDescription>
      <fieldset disabled={busy} className="backend-connection">
        <legend>Local backend connection</legend>
        <label>Backend address<input aria-label="Backend address" value={url} onChange={e => changeConnection(() => setUrl(e.target.value))}/></label>
        <label>Demo planner ID<input aria-label="Demo planner ID" value={userId} onChange={e => changeConnection(() => setUserId(e.target.value))}/></label>
        <button className="control" type="button" onClick={connect}>{connected ? "Refresh saved windows" : "Connect"}</button>
      </fieldset>
      {connected && <div className="backend-selectors">
        {windows.length === 0 ? <p>No saved engineering windows. Load the backend demo data, then refresh.</p> : <>
          <label>Engineering window<select aria-label="Engineering window" disabled={busy} value={windowId} onChange={e => void selectWindow(e.target.value)}>
            {windows.map(w => <option key={w.id} value={w.id}>{w.name} · {stamp(w.starts_at)}</option>)}
          </select></label>
          <label>Schedule<select aria-label="Schedule" value={scenarioId} disabled={busy || !centre} onChange={e => { setScenarioId(e.target.value); clearResult(); }}>
            <option value="">Original requested schedule</option>
            {(centre?.scenarios || []).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select></label>
          {selectedWindow && <p>{stamp(selectedWindow.starts_at)} – {stamp(selectedWindow.ends_at)} SGT. {centre?.requests?.length ?? 0} saved requests in this window.</p>}
          <button className="control primary" disabled={busy || !centre} onClick={analyse}>Run conflict analysis</button>
        </>}
      </div>}
      {busy && <p role="status">Waiting for the backend…</p>}
      {error && <p role="alert" className="backend-error">{error}</p>}
      {summary && <section aria-label="Analysis results" className="backend-results">
        <h3>{summary.conflict_count} findings · {summary.blocking_conflict_count} blocking</h3>
        <p>{summary.completed_at ? `Completed ${stamp(summary.completed_at)} SGT` : "Analysis completed"}. Run {summary.id}.</p>
        <p>These are saved results as of this run. Re-run after changes. Completion does not authorize railway operations.</p>
        {conflicts.length === 0 && <p>No conflicts detected by the configured rules for this snapshot.</p>}
        {conflicts.map(c => <article key={c.id} className="backend-finding">
          <div><strong>{c.title}</strong><span className="tag">{c.severity} · {c.blocking ? "blocking" : "review"}</span></div>
          <small>{c.conflict_code} · {c.rule_code} v{c.rule_version} · {c.category}</small>
          <p>{c.explanation}</p>
          <ul>{c.request_ids.map(id => <li key={id}>{requests.get(id) || id}</li>)}</ul>
        </article>)}
      </section>}
    </DialogContent>
  </Dialog>;
}
