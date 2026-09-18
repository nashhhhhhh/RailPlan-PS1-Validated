"use client";

import { useEffect, useMemo, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, X } from "lucide-react";

type TourView = "overview" | "activities" | "contracts" | "schedule" | "data";
type Props = { open: boolean; onClose: () => void; onNavigate: (view: TourView) => void };

const steps: { target: string; view: TourView; kicker: string; title: string; copy: string }[] = [
  { target: "[data-tour='welcome']", view: "overview", kicker: "01 / ORIENT", title: "Your PS1 planning command", copy: "This workspace turns official challenge inputs and organiser reference output into an explorable operating picture. Dashboard data is reference data, not a newly generated RailPlan schedule." },
  { target: "[data-tour='filters']", view: "overview", kicker: "02 / FILTER", title: "Slice line, bound or location", copy: "Focus Line Alpha or Beta, switch Eastbound and Westbound, or search by activity, contract and location ID. Every metric below reacts to the same filter." },
  { target: "[data-tour='kpis']", view: "overview", kicker: "03 / READ", title: "Read the filtered workload", copy: "The KPI strip shows source activities, required access-nights, affected contracts, capacity locations and sample completion performance." },
  { target: "[data-tour='network']", view: "overview", kicker: "04 / EXPLORE", title: "Use the animated digital twin", copy: "Select a line directly on the map. The twin preserves each line’s own H01↔H02 capacity; the central bridge represents Live-only cross-line closure." },
  { target: "[data-tour='pressure']", view: "overview", kicker: "05 / DIAGNOSE", title: "Find capacity pressure", copy: "Each row compares distinct co-share groups with weekly location supply. Select one to apply its line and bound and jump to its peak week." },
  { target: "[data-tour='horizon']", view: "overview", kicker: "06 / SCHEDULE", title: "Move across the 30-week horizon", copy: "Choose any bar to inspect that week’s scheduled access load and open an activity from the queue." },
  { target: "[data-tour='navigation']", view: "overview", kicker: "07 / DETAIL", title: "Change analytical views", copy: "Open full activity and contract tables, inspect the 30-week activity grid, or trace every visual back to its CSV source." },
  { target: "[data-tour='data-catalog']", view: "data", kicker: "08 / PROVENANCE", title: "Trace and download the data", copy: "The lineage catalogue explains where each CSV appears in the dashboard and provides a direct link to the exact file served by the app." },
  { target: "[data-tour='optimizer']", view: "data", kicker: "09 / OPTIMISE", title: "Move from insight to a plan", copy: "Open the optimiser to generate a new schedule. Scenario B permits ECLO and scored capacity excess while enforcing planned dates. Internal rich validation remains separate from official judge validation." },
];

export default function PS1Tour({ open, onClose, onNavigate }: Props) {
  const [index, setIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const step = steps[index];

  useEffect(() => {
    if (!open) return;
    onNavigate(step.view);
    const update = () => {
      const element = document.querySelector(step.target);
      if (!element) return;
      element.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" });
      window.setTimeout(() => setRect(element.getBoundingClientRect()), 280);
    };
    const timer = window.setTimeout(update, 80);
    window.addEventListener("resize", update);
    window.addEventListener("scroll", update, true);
    return () => { window.clearTimeout(timer); window.removeEventListener("resize", update); window.removeEventListener("scroll", update, true); };
  }, [open, step, onNavigate]);

  useEffect(() => {
    if (!open || !playing) return;
    const timer = window.setTimeout(() => {
      if (index === steps.length - 1) { setPlaying(false); onClose(); }
      else setIndex(current => current + 1);
    }, 5200);
    return () => window.clearTimeout(timer);
  }, [open, playing, index, onClose]);

  useEffect(() => { if (!open) { setIndex(0); setPlaying(false); setRect(null); } }, [open]);

  const cardStyle = useMemo(() => {
    if (!rect || typeof window === "undefined") return undefined;
    const width = Math.min(390, window.innerWidth - 28);
    const left = Math.max(14, Math.min(window.innerWidth - width - 14, rect.left + rect.width / 2 - width / 2));
    const roomBelow = window.innerHeight - rect.bottom;
    const top = roomBelow > 260 ? Math.min(window.innerHeight - 235, rect.bottom + 18) : Math.max(14, rect.top - 230);
    return { left, top, width };
  }, [rect]);

  if (!open) return null;
  return <div className="psd-tour-layer" role="dialog" aria-modal="true" aria-label="Dashboard walkthrough">
    {rect && <div className="psd-tour-focus" style={{ left: rect.left - 8, top: rect.top - 8, width: rect.width + 16, height: rect.height + 16 }}/>} 
    <section className="psd-tour-card" style={cardStyle}>
      <header><span>{step.kicker}</span><button onClick={onClose} aria-label="Close walkthrough"><X size={16}/></button></header>
      <div className="psd-tour-visual"><span>{String(index + 1).padStart(2, "0")}</span><div><i/><i/><i/></div></div>
      <h2>{step.title}</h2>
      <p>{step.copy}</p>
      <div className="psd-tour-progress" aria-label={`Step ${index + 1} of ${steps.length}`}>{steps.map((_, dot) => <i key={dot} className={dot === index ? "active" : dot < index ? "done" : ""}/>)}</div>
      <footer>
        <button className="psd-tour-play" onClick={() => setPlaying(value => !value)}>{playing ? <Pause size={14}/> : <Play size={14}/>} {playing ? "Pause" : "Auto play"}</button>
        <div><button onClick={() => setIndex(value => Math.max(0, value - 1))} disabled={index === 0} aria-label="Previous step"><ChevronLeft size={16}/></button><button className="psd-tour-next" onClick={() => index === steps.length - 1 ? onClose() : setIndex(value => value + 1)}>{index === steps.length - 1 ? "Finish" : "Next"}<ChevronRight size={15}/></button></div>
      </footer>
    </section>
  </div>;
}
