"use client";

import { useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, MousePointer2, Pause, Play, X } from "lucide-react";

type TourView = "overview" | "activities" | "contracts" | "schedule" | "data";
type Props = { open: boolean; onClose: () => void; onNavigate: (view: TourView) => void };
type Step = { target: string; view: TourView; kicker: string; page: string; title: string; copy: string; action: string };

const steps: Step[] = [
  { target: "[data-tour='welcome']", view: "overview", kicker: "01 / START", page: "Overview", title: "Start with the operating picture", copy: "The overview combines official challenge inputs with the organiser’s Scenario A reference output. It is an exploration view, not a newly generated RailPlan schedule.", action: "Read the title and source badge first so you know which evidence is on screen." },
  { target: "[data-tour='navigation']", view: "overview", kicker: "02 / MOVE", page: "All pages", title: "Use the five connected pages", copy: "Overview explains pressure and workload. Activities and Contracts show the source records. Schedule shows when work happens. Data lineage traces every dashboard signal back to its file.", action: "Select any navigation icon. Your line, bound and search filters stay active between pages." },
  { target: "[data-tour='filters']", view: "overview", kicker: "03 / FILTER", page: "Overview", title: "Narrow the whole dashboard", copy: "Line, bound and search work together. The KPI cards, map, pressure list, charts and tables all recalculate from the same filtered population.", action: "Try Line Alpha, then EB. Select All and Both to reset." },
  { target: "[data-tour='kpis']", view: "overview", kicker: "04 / READ", page: "Overview", title: "Check scope before details", copy: "These cards summarise the filtered activities, workload, contracts, capacity locations and organiser-sample completion performance.", action: "Change a filter and watch every card update." },
  { target: "[data-tour='network']", view: "overview", kicker: "05 / MAP", page: "Overview", title: "Read and filter the network", copy: "The two tracks preserve separate Alpha and Beta capacity through H01 and H02. The highlighted interchange zone shows where Live work may cause a closure across both lines. The line labels are also dashboard controls.", action: "Select ALP or BET to filter by line. Select EB or WB inside that label to filter by line and direction together; the KPI cards and every panel will update." },
  { target: "[data-tour='pressure']", view: "overview", kicker: "06 / PRESSURE", page: "Overview", title: "Find full locations and available headroom", copy: "This panel mixes full hotspots with the next busiest locations that still have spare possession slots. A 100% row means one location used all of its weekly supply in that shown week; it does not mean the whole network is overloaded.", action: "Select a row to apply its line and bound, then inspect that week below." },
  { target: "[data-tour='horizon']", view: "overview", kicker: "07 / TIME", page: "Overview", title: "Move through the 30-week plan", copy: "The bars show scheduled access volume by week. The detail strip lists active work for the selected week and links each activity to its source record.", action: "Select a week bar, then open an activity to move to the Activities page." },
  { target: "[data-tour='activities-view']", view: "activities", kicker: "08 / WORK", page: "Activities", title: "Inspect the work behind the plan", copy: "This table connects activity workload, occupied span, planned start, priority and predecessor. It uses the same filters you set on Overview.", action: "Search an activity or contract, then return to Overview without losing the filter." },
  { target: "[data-tour='contracts-view']", view: "contracts", kicker: "09 / DELIVERY", page: "Contracts", title: "Compare rules and completion", copy: "Contract rows bring delivery targets, access rules and organiser-sample completion together. Overrun labels show which reference results miss plan.", action: "Use line and bound filters to see only contracts touched by that work." },
  { target: "[data-tour='schedule-view']", view: "schedule", kicker: "10 / SEQUENCE", page: "Schedule", title: "Connect activities to weeks", copy: "Each row shows planned start and scheduled access across all 30 weeks. Selecting a row opens the matching activity record.", action: "Select a populated row to continue the investigation on Activities." },
  { target: "[data-tour='data-catalog']", view: "data", kicker: "11 / SOURCES", page: "Data lineage", title: "Trace every value to a file", copy: "The catalogue separates the eight challenge inputs from the three organiser sample outputs and states which dashboard components each file feeds.", action: "Open a CSV for inspection or download the exact served file." },
  { target: "[data-tour='optimizer']", view: "data", kicker: "12 / PLAN", page: "Optimiser", title: "Generate and validate a candidate", copy: "Load organiser dataset already supplies all eight bundled challenge CSVs, so no upload is needed. For your own case, import all eight 01_data CSVs together. Every scenario supports a stateless preview; save the dataset only when you want PostgreSQL run history.", action: "Open the optimiser, then expand its How to use this optimiser guide for the complete five-step workflow." },
];

export default function PS1Tour({ open, onClose, onNavigate }: Props) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = steps[index];
  const finishTour = () => {
    setIndex(0);
    setPlaying(false);
    setRect(null);
    onClose();
  };

  useEffect(() => {
    if (!open) return;
    onNavigate(step.view);
    let settleTimer: number | undefined;
    const locate = () => {
      const element = document.querySelector(step.target);
      if (element) setRect(element.getBoundingClientRect());
    };
    const reveal = () => {
      const element = document.querySelector(step.target);
      if (!element) { settleTimer = window.setTimeout(reveal, 160); return; }
      element.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
      settleTimer = window.setTimeout(locate, 340);
    };
    const timer = window.setTimeout(reveal, 100);
    window.addEventListener("resize", locate);
    window.addEventListener("scroll", locate, true);
    return () => {
      window.clearTimeout(timer);
      if (settleTimer) window.clearTimeout(settleTimer);
      window.removeEventListener("resize", locate);
      window.removeEventListener("scroll", locate, true);
    };
  }, [open, step, onNavigate]);

  useEffect(() => {
    if (!open || !playing) return;
    const timer = window.setTimeout(() => {
      if (index === steps.length - 1) {
        setIndex(0);
        setPlaying(false);
        setRect(null);
        onClose();
      }
      else setIndex(current => current + 1);
    }, 7000);
    return () => window.clearTimeout(timer);
  }, [open, playing, index, onClose]);

  if (!open) return null;
  return <div className="psd-tour-layer" role="dialog" aria-label="Dashboard walkthrough">
    {rect && <div className="psd-tour-focus" style={{ left: rect.left - 6, top: rect.top - 6, width: rect.width + 12, height: rect.height + 12 }}/>}
    <section className="psd-tour-card">
      <header><span>{step.kicker}</span><button onClick={finishTour} aria-label="Close walkthrough"><X size={17}/></button></header>
      <div className="psd-tour-page"><span>{step.page}</span><b>{index + 1} of {steps.length}</b></div>
      <h2>{step.title}</h2>
      <p>{step.copy}</p>
      <div className="psd-tour-action"><MousePointer2 size={16}/><span><b>Try it</b>{step.action}</span></div>
      <p className="psd-tour-hint">Highlighted controls stay interactive while this guide is open.</p>
      <div className="psd-tour-progress" aria-label={`Step ${index + 1} of ${steps.length}`}>{steps.map((_, dot) => <i key={dot} className={dot === index ? "active" : dot < index ? "done" : ""}/>)}</div>
      <footer>
        <button className="psd-tour-play" onClick={() => setPlaying(value => !value)}>{playing ? <Pause size={14}/> : <Play size={14}/>} {playing ? "Pause" : "Auto play"}</button>
        <div><button onClick={() => setIndex(value => Math.max(0, value - 1))} disabled={index === 0} aria-label="Previous step"><ChevronLeft size={16}/></button><button className="psd-tour-next" onClick={() => index === steps.length - 1 ? finishTour() : setIndex(value => value + 1)}>{index === steps.length - 1 ? "Finish" : "Next"}<ChevronRight size={15}/></button></div>
      </footer>
    </section>
  </div>;
}
