"use client";

import { useCallback, useEffect, useMemo, useState, type ComponentType } from "react";
import {
  Activity,
  AlertTriangle,
  CalendarRange,
  ChevronRight,
  CircleGauge,
  CircleHelp,
  Database,
  Download,
  ExternalLink,
  FileCheck2,
  FileSpreadsheet,
  GitBranch,
  Layers3,
  MapPinned,
  Network,
  Route,
  Search,
  SlidersHorizontal,
  TableProperties,
  Wrench,
} from "lucide-react";
import sourceBundle from "../public/ps1/example.json";
import PS1NetworkMap from "./ps1-network-map";
import PS1Tour from "./ps1-tour";
import PS1Workspace from "./ps1-workspace";
import "./ps1-dashboard.css";

type LineCode = "ALP" | "BET";
type Bound = "EB" | "WB";
type View = "overview" | "activities" | "contracts" | "schedule" | "data";
type ActivityRow = {
  activity_id: string;
  contract_number: string;
  activity_type: string;
  start_location_id: string;
  end_location_id: string;
  total_accesses: number;
  planned_start_date: string;
  planned_start_week: number;
  predecessor_activity_id: string;
  activity_priority: number;
  line_code: LineCode;
  bound: Bound;
  span_location_ids: string[];
};
type ContractRow = {
  contract_number: string;
  contract_description: string;
  activity_type: string;
  nature_of_activity: string;
  contract_priority: number;
  contract_completion_date: string;
  planned_completion_date: string;
  number_of_workfronts: number;
  access_type: "PM" | "PC" | "C";
  number_of_maximum_access_per_week: number;
};
type LocationRow = {
  location_id: string;
  location_kind: string;
  line_code: LineCode;
  bound: Bound;
  supply_capacity: number;
};
type Dataset = {
  summary: {
    lines: number;
    station_records: number;
    unique_station_ids: number;
    locations: number;
    contracts: number;
    activities: number;
    total_access_workload: number;
    dependencies: number;
    horizon_start: string;
    horizon_end: string;
    horizon_weeks: number;
  };
  tables: {
    activity_details: ActivityRow[];
    project_details: ContractRow[];
    location_supply: LocationRow[];
    stations: { station_id: string; line_code: LineCode; seq: number; is_interchange: number }[];
  };
};
type AccessRow = { activity_id: string; access_seq: number; week: number; eclo: number; access_night: number };
type OccupancyRow = { activity_id: string; week: number; location_id: string; co_share_group: string };
type ResultRow = { scenario: string; contract_number: string; simulated_completion_date: string; overrun_days: number };
type Sample = { accesses: AccessRow[]; occupancies: OccupancyRow[]; results: ResultRow[] };

const dataset = (sourceBundle as unknown as { dataset: Dataset }).dataset;
const lineNames: Record<LineCode, string> = { ALP: "Line Alpha", BET: "Line Beta" };
const priorityNames: Record<number, string> = { 1: "High", 2: "Default", 3: "Low" };
const dataSources = [
  { group: "01_data", file: "01_LINES.csv", href: "/ps1/datasets/01_data/01_LINES.csv", rows: "2 lines", role: "Defines ALP and BET names used by map labels and the line filter.", feeds: ["Network", "Filters"] },
  { group: "01_data", file: "02_STATIONS.csv", href: "/ps1/datasets/01_data/02_STATIONS.csv", rows: "20 records", role: "Sets station order, interchange flags and the H01/H02 topology.", feeds: ["Digital twin", "Station KPI"] },
  { group: "01_data", file: "03_SECTORS.csv", href: "/ps1/datasets/01_data/03_SECTORS.csv", rows: "18 sectors", role: "Connects adjacent stations and identifies each line-specific tunnel span.", feeds: ["Digital twin", "Activity spans"] },
  { group: "01_data", file: "04_LOCATION_SUPPLY.csv", href: "/ps1/datasets/01_data/04_LOCATION_SUPPLY.csv", rows: "76 locations", role: "Provides weekly capacity for tunnel and platform locations by line and bound.", feeds: ["Capacity KPI", "Peak pressure"] },
  { group: "01_data", file: "05_BUFFER_LOCATION.csv", href: "/ps1/datasets/01_data/05_BUFFER_LOCATION.csv", rows: "Safety rules", role: "Maps locations that must remain protected when nearby access is scheduled.", feeds: ["Optimiser", "Validation"] },
  { group: "01_data", file: "06_PARAMETERS.csv", href: "/ps1/datasets/01_data/06_PARAMETERS.csv", rows: "30 weeks", role: "Defines the planning horizon and scenario-wide parameters.", feeds: ["Week chart", "Schedule grid"] },
  { group: "01_data", file: "07_PROJECT_DETAILS.csv", href: "/ps1/datasets/01_data/07_PROJECT_DETAILS.csv", rows: "14 contracts", role: "Supplies contract roles, workfront limits, priorities and completion targets.", feeds: ["Contract KPI", "Contracts"] },
  { group: "01_data", file: "08_ACTIVITY_DETAILS.csv", href: "/ps1/datasets/01_data/08_ACTIVITY_DETAILS.csv", rows: "54 activities", role: "Drives activity workload, spans, priorities, dependencies and planned starts.", feeds: ["Activity KPI", "Activities", "Filters"] },
  { group: "03_submission_sample", file: "SCHEDULE_ACCESS.csv", href: "/ps1/datasets/03_submission_sample/SCHEDULE_ACCESS.csv", rows: "192 rows", role: "Places each organiser-sample access in a week and access night.", feeds: ["Week chart", "Schedule grid"] },
  { group: "03_submission_sample", file: "SCHEDULE_OCCUPANCY.csv", href: "/ps1/datasets/03_submission_sample/SCHEDULE_OCCUPANCY.csv", rows: "928 rows", role: "Links scheduled activities to occupied locations and co-share groups.", feeds: ["Peak pressure", "Optimiser"] },
  { group: "03_submission_sample", file: "RESULTS.csv", href: "/ps1/datasets/03_submission_sample/RESULTS.csv", rows: "14 results", role: "Compares simulated completion with the planned date for each contract.", feeds: ["On-plan KPI", "Contracts"] },
] as const;

function parseCsv(text: string): Record<string, string>[] {
  const rows: string[][] = [];
  let row: string[] = [], value = "", quoted = false;
  for (let i = 0; i < text.length; i += 1) {
    const char = text[i];
    if (char === '"') {
      if (quoted && text[i + 1] === '"') { value += '"'; i += 1; }
      else quoted = !quoted;
    } else if (char === "," && !quoted) { row.push(value); value = ""; }
    else if ((char === "\n" || char === "\r") && !quoted) {
      if (char === "\r" && text[i + 1] === "\n") i += 1;
      row.push(value); value = "";
      if (row.some(cell => cell.length)) rows.push(row);
      row = [];
    } else value += char;
  }
  if (value.length || row.length) { row.push(value); rows.push(row); }
  const [headers = [], ...body] = rows;
  return body.map(values => Object.fromEntries(headers.map((header, index) => [header.replace(/^\uFEFF/, ""), values[index] ?? ""])));
}

function shortLocation(value: string) {
  const parts = value.split(":");
  return parts.length >= 4 ? `${parts[1]} · ${parts[2]} · ${parts[3]}` : value;
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-SG", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" }).format(new Date(`${value}T00:00:00Z`));
}

function Kpi({ icon: Icon, label, value, detail, tone = "blue" }: { icon: ComponentType<{ size?: number }>; label: string; value: string | number; detail: string; tone?: string }) {
  return <article className={`psd-kpi ${tone}`}><span className="psd-kpi-icon"><Icon size={18}/></span><div><span>{label}</span><strong>{value}</strong><small>{detail}</small></div></article>;
}

export default function PS1CommandDashboard() {
  const [view, setView] = useState<View>("overview");
  const [line, setLine] = useState<"ALL" | LineCode>("ALL");
  const [bound, setBound] = useState<"ALL" | Bound>("ALL");
  const [query, setQuery] = useState("");
  const [selectedWeek, setSelectedWeek] = useState(17);
  const [workspaceOpen, setWorkspaceOpen] = useState(false);
  const [startInDemo, setStartInDemo] = useState(false);
  const [tourOpen, setTourOpen] = useState(false);
  const [sample, setSample] = useState<Sample | null>(null);
  const [sampleError, setSampleError] = useState("");
  const closeTour = useCallback(() => setTourOpen(false), []);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetch("/ps1/SCHEDULE_ACCESS.csv", { signal: controller.signal }).then(response => response.ok ? response.text() : Promise.reject(Error("Access schedule unavailable"))),
      fetch("/ps1/SCHEDULE_OCCUPANCY.csv", { signal: controller.signal }).then(response => response.ok ? response.text() : Promise.reject(Error("Occupancy schedule unavailable"))),
      fetch("/ps1/RESULTS.csv", { signal: controller.signal }).then(response => response.ok ? response.text() : Promise.reject(Error("Contract results unavailable"))),
    ]).then(([accessText, occupancyText, resultText]) => {
      if (controller.signal.aborted) return;
      setSample({
        accesses: parseCsv(accessText).map(row => ({ activity_id: row.activity_id, access_seq: Number(row.access_seq), week: Number(row.week), eclo: Number(row.eclo), access_night: Number(row.access_night) })),
        occupancies: parseCsv(occupancyText).map(row => ({ activity_id: row.activity_id, week: Number(row.week), location_id: row.location_id, co_share_group: row.co_share_group })),
        results: parseCsv(resultText).map(row => ({ scenario: row.scenario, contract_number: row.contract_number, simulated_completion_date: row.simulated_completion_date, overrun_days: Number(row.overrun_days) })),
      });
    }).catch(error => { if (!controller.signal.aborted) setSampleError(error instanceof Error ? error.message : "Reference schedule unavailable"); });
    return () => controller.abort();
  }, []);

  const resultMap = useMemo(() => new Map((sample?.results ?? []).map(result => [result.contract_number, result])), [sample]);
  const filteredActivities = useMemo(() => dataset.tables.activity_details.filter(activity => {
    const text = `${activity.activity_id} ${activity.contract_number} ${activity.activity_type} ${activity.start_location_id} ${activity.end_location_id}`.toLowerCase();
    return (line === "ALL" || activity.line_code === line) && (bound === "ALL" || activity.bound === bound) && text.includes(query.toLowerCase());
  }), [line, bound, query]);
  const filteredIds = useMemo(() => new Set(filteredActivities.map(activity => activity.activity_id)), [filteredActivities]);
  const filteredContracts = useMemo(() => {
    const ids = new Set(filteredActivities.map(activity => activity.contract_number));
    return dataset.tables.project_details.filter(contract => ids.has(contract.contract_number));
  }, [filteredActivities]);
  const filteredLocations = useMemo(() => dataset.tables.location_supply.filter(location => (line === "ALL" || location.line_code === line) && (bound === "ALL" || location.bound === bound)), [line, bound]);
  const filteredAccesses = useMemo(() => (sample?.accesses ?? []).filter(access => filteredIds.has(access.activity_id)), [sample, filteredIds]);
  const scheduledWeeks = useMemo(() => {
    const map = new Map<string, Set<number>>();
    for (const access of filteredAccesses) {
      const weeks = map.get(access.activity_id) ?? new Set<number>();
      weeks.add(access.week); map.set(access.activity_id, weeks);
    }
    return map;
  }, [filteredAccesses]);
  const weekCounts = useMemo(() => Array.from({ length: dataset.summary.horizon_weeks }, (_, index) => filteredAccesses.filter(access => access.week === index + 1).length), [filteredAccesses]);
  const maxWeekCount = Math.max(1, ...weekCounts);
  const weekActivities = useMemo(() => filteredActivities.filter(activity => scheduledWeeks.get(activity.activity_id)?.has(selectedWeek)), [filteredActivities, scheduledWeeks, selectedWeek]);
  const lateResults = (sample?.results ?? []).filter(result => result.overrun_days > 0);

  const pressure = useMemo(() => {
    if (!sample) return { rows: [], saturated: 0, monitored: 0 };
    const supply = new Map(filteredLocations.map(location => [location.location_id, location]));
    const groups = new Map<string, Set<string>>();
    const jobs = new Map<string, Set<string>>();
    for (const occupancy of sample.occupancies) {
      if (!supply.has(occupancy.location_id) || !filteredIds.has(occupancy.activity_id)) continue;
      const key = `${occupancy.location_id}|${occupancy.week}`;
      const slotSet = groups.get(key) ?? new Set<string>(); slotSet.add(occupancy.co_share_group); groups.set(key, slotSet);
      const jobSet = jobs.get(key) ?? new Set<string>(); jobSet.add(occupancy.activity_id); jobs.set(key, jobSet);
    }
    const peak = new Map<string, { location: LocationRow; week: number; used: number; activities: number; ratio: number }>();
    for (const [key, slots] of groups) {
      const [locationId, weekText] = key.split("|");
      const location = supply.get(locationId)!;
      const candidate = { location, week: Number(weekText), used: slots.size, activities: jobs.get(key)?.size ?? 0, ratio: slots.size / location.supply_capacity };
      if (!peak.has(locationId) || peak.get(locationId)!.ratio < candidate.ratio) peak.set(locationId, candidate);
    }
    const ranked = [...peak.values()].sort((a, b) => b.ratio - a.ratio || b.activities - a.activities || a.location.location_id.localeCompare(b.location.location_id));
    const saturated = ranked.filter(item => item.ratio >= 1);
    const withHeadroom = ranked.filter(item => item.ratio < 1);
    return { rows: [...saturated.slice(0, 3), ...withHeadroom.slice(0, 3)], saturated: saturated.length, monitored: ranked.length };
  }, [sample, filteredLocations, filteredIds]);

  const nav: { id: View; label: string; icon: ComponentType<{ size?: number }> }[] = [
    { id: "overview", label: "Network overview", icon: Layers3 },
    { id: "activities", label: "Activities", icon: Wrench },
    { id: "contracts", label: "Contracts", icon: TableProperties },
    { id: "schedule", label: "30-week schedule", icon: CalendarRange },
    { id: "data", label: "Data lineage", icon: Database },
  ];
  const workload = filteredActivities.reduce((total, activity) => total + activity.total_accesses, 0);
  const scheduledCount = filteredAccesses.length;
  const completionText = sample ? `${sample.results.length - lateResults.length}/${sample.results.length}` : "—";

  return <div className={`psd-app ${tourOpen ? "tour-active" : ""}`}>
    <aside className="psd-sidebar">
      <button className="psd-brand" aria-label="RailPlan home" onClick={() => setView("overview")}><Route size={24}/></button>
      <nav data-tour="navigation">{nav.map(item => <button key={item.id} className={view === item.id ? "active" : ""} onClick={() => setView(item.id)} aria-label={item.label}><item.icon size={20}/><span>{item.label}</span></button>)}</nav>
      <div className="psd-sidebar-source"><Database size={17}/><span>PS1<br/>2027</span></div>
    </aside>

    <div className="psd-content">
      <header className="psd-topbar">
        <div className="psd-wordmark">railplan<span>ai</span><i/><small>PS1 planning workspace</small></div>
        <div className="psd-top-actions"><span className="psd-status"><i/>Official challenge data</span><button className="psd-top-button" onClick={() => setTourOpen(true)}><CircleHelp size={16}/>Walkthrough</button><button className="psd-top-button" onClick={() => {setStartInDemo(true);setWorkspaceOpen(true);}}>Competition Demo</button><button className="psd-primary" data-tour="optimizer" onClick={() => {setStartInDemo(false);setWorkspaceOpen(true);}}><SlidersHorizontal size={16}/>Open optimiser</button></div>
      </header>

      <main className="psd-main">
        <section className="psd-heading" data-tour="welcome">
          <div><span className="psd-eyebrow">TRACK ACCESS / LINE ALPHA + LINE BETA</span><h1>Dual-line access command</h1><p>Plan the full workload against directional capacity, safety buffers, dependencies and contract deadlines.</p></div>
          <div className="psd-source-pill"><FileCheck2 size={18}/><span><b>Scenario A reference</b><small>Judge validation not run</small></span></div>
        </section>

        <section className="psd-toolbar" data-tour="filters" aria-label="Dashboard filters">
          <div className="psd-filter-group"><span>Line</span>{(["ALL", "ALP", "BET"] as const).map(value => <button key={value} className={line === value ? "active" : ""} onClick={() => setLine(value)}>{value === "ALL" ? "All" : lineNames[value]}</button>)}</div>
          <div className="psd-filter-group"><span>Bound</span>{(["ALL", "EB", "WB"] as const).map(value => <button key={value} className={bound === value ? "active" : ""} onClick={() => setBound(value)}>{value === "ALL" ? "Both" : value}</button>)}</div>
          <label className="psd-search"><Search size={16}/><input value={query} onChange={event => setQuery(event.target.value)} placeholder="Activity, contract or location"/><button aria-label="Clear search" onClick={() => setQuery("")} disabled={!query}>×</button></label>
        </section>

        <section className="psd-kpis" data-tour="kpis">
          <Kpi icon={Activity} label="Activities" value={filteredActivities.length} detail={`${dataset.summary.activities} in source`} tone="orange"/>
          <Kpi icon={CalendarRange} label="Required access-nights" value={workload} detail={`${scheduledCount || "—"} in sample schedule`} tone="blue"/>
          <Kpi icon={GitBranch} label="Contracts" value={filteredContracts.length} detail={`${dataset.summary.dependencies} predecessor links`} tone="violet"/>
          <Kpi icon={Network} label="Capacity locations" value={filteredLocations.length} detail="Tunnel and platform sectors" tone="green"/>
          <Kpi icon={CircleGauge} label="Contracts on plan" value={completionText} detail={sample ? `${lateResults.reduce((sum, result) => sum + result.overrun_days, 0)} total overrun days` : "Loading sample results"} tone="amber"/>
        </section>

        {view === "overview" && <>
          <section className="psd-overview-grid">
            <article className="psd-card psd-network-card" data-tour="network">
              <header><div><span className="psd-card-kicker">01_DATA / NETWORK TOPOLOGY</span><h2>Dual-line track access topology</h2></div><span className="psd-chip psd-live-chip"><i/>Interactive schematic</span></header>
              <div className="psd-network-scroll"><PS1NetworkMap focusLine={line} focusBound={bound} onSelectLine={selected => setLine(current => current === selected ? "ALL" : selected)}/></div>
              <footer><div><i className="alp"/><b>Line Alpha</b><span>{dataset.tables.activity_details.filter(activity => activity.line_code === "ALP").length} activities · {dataset.tables.activity_details.filter(activity => activity.line_code === "ALP").reduce((sum, activity) => sum + activity.total_accesses, 0)} access-nights</span></div><div><i className="bet"/><b>Line Beta</b><span>{dataset.tables.activity_details.filter(activity => activity.line_code === "BET").length} activities · {dataset.tables.activity_details.filter(activity => activity.line_code === "BET").reduce((sum, activity) => sum + activity.total_accesses, 0)} access-nights</span></div><p>H01↔H02 has separate capacity per line. Only Live work propagates closure across both lines.</p></footer>
            </article>

            <aside className="psd-card psd-pressure-card" data-tour="pressure">
              <header><div><span className="psd-card-kicker">03_SUBMISSION_SAMPLE</span><h2>Weekly capacity hotspots</h2></div><AlertTriangle size={19}/></header>
              {sampleError && <div className="psd-empty">{sampleError}</div>}
              {!sample && !sampleError && <div className="psd-empty">Loading reference occupancy…</div>}
              {sample && <div className="psd-pressure-summary"><span><b>{pressure.saturated}</b> of {pressure.monitored} used locations reached full capacity</span><span>{pressure.monitored - pressure.saturated} retained headroom at their busiest week</span></div>}
              {pressure.rows.map(item => { const free = Math.max(0, item.location.supply_capacity - item.used); return <button key={item.location.location_id} onClick={() => { setLine(item.location.line_code); setBound(item.location.bound); setSelectedWeek(item.week); }}><div><span>{shortLocation(item.location.location_id)}</span><b>{Math.round(item.ratio * 100)}% <em>{free === 0 ? "FULL" : `${free} free`}</em></b></div><small>Week {item.week} · {item.used}/{item.location.supply_capacity} possession slots used · {item.activities} activities</small><span className="psd-pressure-track"><i style={{ width: `${Math.min(100, item.ratio * 100)}%` }}/></span></button>})}
              <footer>100% means that location used every weekly possession slot in its busiest week. It does not mean the whole network is overloaded. Counts use distinct co-share groups from the organiser sample.</footer>
            </aside>
          </section>

          <section className="psd-card psd-week-card" data-tour="horizon">
            <header><div><span className="psd-card-kicker">SCHEDULE_ACCESS.CSV</span><h2>Access load across the 30-week horizon</h2></div><span className="psd-chip">Week {selectedWeek} · {weekCounts[selectedWeek - 1] ?? 0} accesses</span></header>
            <div className="psd-week-chart" role="group" aria-label="Weekly access totals">{weekCounts.map((count, index) => <button key={index} className={selectedWeek === index + 1 ? "active" : ""} onClick={() => setSelectedWeek(index + 1)} title={`Week ${index + 1}: ${count} scheduled accesses`}><span style={{ height: `${Math.max(4, count / maxWeekCount * 100)}%` }}/><small>{index + 1}</small></button>)}</div>
            <div className="psd-week-detail">
              <div><b>Week {selectedWeek}</b><span>{weekActivities.length} active activities across {new Set(weekActivities.map(activity => activity.contract_number)).size} contracts</span></div>
              <div className="psd-week-jobs">{weekActivities.slice(0, 8).map(activity => <button key={activity.activity_id} onClick={() => { setQuery(activity.activity_id); setView("activities"); }}><span className={`psd-line-dot ${activity.line_code.toLowerCase()}`}/><b>{activity.activity_id}</b><span>{activity.activity_type}</span><small>{activity.line_code} · {activity.bound} · {activity.contract_number}</small><ChevronRight size={14}/></button>)}{!weekActivities.length && <p>No scheduled access in the current filter for this week.</p>}</div>
            </div>
          </section>
        </>}

        {view === "activities" && <section className="psd-card psd-table-card" data-tour="activities-view">
          <header><div><span className="psd-card-kicker">08_ACTIVITY_DETAILS.CSV</span><h2>Complete activity workload</h2></div><span className="psd-chip">{filteredActivities.length} activities · {workload} access-nights</span></header>
          <div className="psd-table-wrap"><table><thead><tr><th>Activity</th><th>Contract</th><th>Work</th><th>Line / bound</th><th>Occupied span</th><th>Start</th><th>Workload</th><th>Priority</th><th>Dependency</th></tr></thead><tbody>{filteredActivities.map(activity => <tr key={activity.activity_id}><td><b>{activity.activity_id}</b></td><td>{activity.contract_number}</td><td>{activity.activity_type}</td><td><span className={`psd-line-badge ${activity.line_code.toLowerCase()}`}>{activity.line_code}</span> {activity.bound}</td><td><small>{shortLocation(activity.start_location_id)}</small><span className="psd-arrow">→</span><small>{shortLocation(activity.end_location_id)}</small></td><td>Week {activity.planned_start_week}<small>{formatDate(activity.planned_start_date)}</small></td><td><b>{activity.total_accesses}</b> nights</td><td><span className={`psd-priority p${activity.activity_priority}`}>P{activity.activity_priority} · {priorityNames[activity.activity_priority]}</span></td><td>{activity.predecessor_activity_id || "—"}</td></tr>)}</tbody></table></div>
        </section>}

        {view === "contracts" && <section className="psd-card psd-table-card" data-tour="contracts-view">
          <header><div><span className="psd-card-kicker">07_PROJECT_DETAILS.CSV + RESULTS.CSV</span><h2>Contract delivery and access rules</h2></div><span className="psd-chip">{filteredContracts.length} contracts</span></header>
          <div className="psd-table-wrap"><table><thead><tr><th>Contract</th><th>Programme</th><th>Nature</th><th>Role</th><th>Workfronts</th><th>Weekly cap</th><th>Planned completion</th><th>Sample completion</th></tr></thead><tbody>{filteredContracts.map(contract => { const result = resultMap.get(contract.contract_number); return <tr key={contract.contract_number}><td><b>{contract.contract_number}</b><small>P{contract.contract_priority} contract</small></td><td>{contract.contract_description}</td><td>{contract.nature_of_activity}</td><td><span className="psd-role">{contract.access_type}</span></td><td>{contract.number_of_workfronts}</td><td>{contract.number_of_maximum_access_per_week} nights</td><td>{formatDate(contract.planned_completion_date)}</td><td>{result ? <><b>{formatDate(result.simulated_completion_date)}</b><small className={result.overrun_days ? "late" : "ontime"}>{result.overrun_days ? `+${result.overrun_days} days` : "On plan"}</small></> : "—"}</td></tr>; })}</tbody></table></div>
        </section>}

        {view === "schedule" && <section className="psd-card psd-schedule-card" data-tour="schedule-view">
          <header><div><span className="psd-card-kicker">03_SUBMISSION_SAMPLE / SCENARIO A</span><h2>Activity-by-week access schedule</h2></div><span className="psd-chip">{filteredAccesses.length} scheduled accesses</span></header>
          <div className="psd-schedule-legend"><span><i className="planned"/>Planned start</span><span><i className="access"/>Scheduled access</span><span>Horizontal axis: week 1–30</span></div>
          <div className="psd-schedule-scroll"><div className="psd-schedule-head"><span>Activity</span><div>{Array.from({ length: 30 }, (_, index) => <small key={index}>{index + 1}</small>)}</div></div>{filteredActivities.map(activity => { const weeks = scheduledWeeks.get(activity.activity_id) ?? new Set<number>(); return <button className="psd-schedule-row" key={activity.activity_id} onClick={() => { setQuery(activity.activity_id); setView("activities"); }}><span><b>{activity.activity_id}</b><small>{activity.contract_number} · {activity.line_code}/{activity.bound}</small></span><div>{Array.from({ length: 30 }, (_, index) => { const week = index + 1; return <i key={week} className={`${week === activity.planned_start_week ? "planned" : ""} ${weeks.has(week) ? "access" : ""}`} title={`${activity.activity_id} · week ${week}${weeks.has(week) ? " · scheduled" : ""}`}/>; })}</div></button>; })}</div>
        </section>}

        {view === "data" && <section className="psd-data-view" data-tour="data-catalog">
          <article className="psd-card psd-lineage-hero">
            <div><span className="psd-card-kicker">SOURCE-TO-SCREEN TRACEABILITY</span><h2>Every dashboard signal links back to a challenge file</h2><p>Open the exact CSV served by this app, download it, and see which dashboard components depend on it.</p></div>
            <div className="psd-lineage-flow" aria-label="Data flow from source files to the dashboard">
              <span><Database size={17}/><b>01_data</b><small>8 source CSVs</small></span><i>→</i><span><SlidersHorizontal size={17}/><b>Planning model</b><small>joins + derived metrics</small></span><i>→</i><span><CircleGauge size={17}/><b>Dashboard</b><small>KPIs + decisions</small></span>
            </div>
          </article>
          <div className="psd-data-section-heading"><div><span>01_DATA</span><h2>Challenge inputs</h2></div><b>8 CSV files</b></div>
          <div className="psd-data-grid">{dataSources.filter(source => source.group === "01_data").map(source => <article className="psd-data-card" key={source.file}>
            <header><span><FileSpreadsheet size={17}/></span><div><b>{source.file}</b><small>{source.rows}</small></div></header>
            <p>{source.role}</p>
            <div className="psd-data-feeds"><span>Feeds</span>{source.feeds.map(feed => <i key={feed}>{feed}</i>)}</div>
            <footer><a href={source.href} target="_blank" rel="noreferrer"><ExternalLink size={13}/>Open CSV</a><a href={source.href} download><Download size={13}/>Download</a></footer>
          </article>)}</div>
          <div className="psd-data-section-heading"><div><span>03_SUBMISSION_SAMPLE</span><h2>Organiser Scenario A outputs</h2></div><b>3 CSV files · illustrative</b></div>
          <div className="psd-data-grid">{dataSources.filter(source => source.group === "03_submission_sample").map(source => <article className="psd-data-card sample" key={source.file}>
            <header><span><FileSpreadsheet size={17}/></span><div><b>{source.file}</b><small>{source.rows}</small></div></header>
            <p>{source.role}</p>
            <div className="psd-data-feeds"><span>Feeds</span>{source.feeds.map(feed => <i key={feed}>{feed}</i>)}</div>
            <footer><a href={source.href} target="_blank" rel="noreferrer"><ExternalLink size={13}/>Open CSV</a><a href={source.href} download><Download size={13}/>Download</a></footer>
          </article>)}</div>
          <article className="psd-reference-link"><MapPinned size={18}/><div><b>02_references / network_diagram.svg</b><p>The official topology remains available as the structural reference behind the interactive topology schematic.</p></div><a href="/ps1/network_diagram.svg" target="_blank" rel="noreferrer">Open reference <ExternalLink size={13}/></a></article>
        </section>}

        <footer className="psd-provenance"><div><Database size={16}/><span><b>01_data</b> · network, capacity, contracts and activities</span></div><div><MapPinned size={16}/><span><b>02_references</b> · authoritative dual-line topology</span></div><div><Download size={16}/><span><b>03_submission_sample</b> · organiser Scenario A schedule and results</span></div><p>Reference schedule shown for exploration. Internal validator and judge verification remain separate.</p></footer>
      </main>
    </div>
    {workspaceOpen && <PS1Workspace initialDemo={startInDemo} onClose={() => setWorkspaceOpen(false)}/>}
    <button className="psd-tour-launcher" onClick={() => setTourOpen(true)} aria-label="Start dashboard walkthrough"><CircleHelp size={18}/><span>Tour</span></button>
    <PS1Tour open={tourOpen} onClose={closeTour} onNavigate={setView}/>
  </div>;
}
