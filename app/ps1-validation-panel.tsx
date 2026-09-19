"use client";
import {useState} from 'react';
import {z} from 'zod';

const violationSchema=z.object({rule_code:z.string(),message:z.string(),week:z.number().nullable(),activity_ids:z.array(z.string()),contract_ids:z.array(z.string()),location_ids:z.array(z.string()),possession_group:z.record(z.unknown()).nullable(),evidence:z.record(z.unknown())});
export type PS1Violation=z.infer<typeof violationSchema>;
const reportSchema=z.object({scenario:z.enum(['A','B','C']),feasible:z.boolean(),validation_status:z.string(),validator_version:z.string(),dataset_fingerprint:z.string(),submission_fingerprint:z.string(),rule_policy:z.record(z.unknown()),hard_violations:z.array(violationSchema),warnings:z.array(z.record(z.unknown())),objective_score:z.string().nullable(),objective_components:z.object({overrun_days_total:z.number(),priority_weighted_overrun:z.string(),excess_access_nights_total:z.number(),excess_penalty:z.string(),eclo_nights_total:z.number(),eclo_penalty:z.string(),diagnostic_objective:z.string(),metrics_complete:z.boolean()}).passthrough(),completeness:z.object({activity_count:z.number(),activities_present:z.number(),activities_complete:z.number(),workload_gate_passed:z.boolean()}).passthrough(),capacity_hotspots:z.array(z.object({location_id:z.string(),week:z.number(),supply:z.number(),used:z.number(),excess:z.number()}).passthrough()),active_rule_assumptions:z.array(z.string()),judge_validation:z.literal('not_run'),score_verification:z.literal('internal_only')});
const contextualReportSchema=reportSchema.extend({validation_context:z.enum(['submission','rich_schedule']).default('submission'),physical_validation_complete:z.boolean().default(false)});
type Report=z.infer<typeof contextualReportSchema>;
const names=['SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv'];

export default function PS1ValidationPanel({scenario,files,instanceId,busy,api,action,onSelect}:{
 scenario:'A'|'B'|'C';files:Record<string,string>;instanceId:string;busy:boolean;
 api:(path:string,c:AbortController,body?:unknown)=>Promise<unknown>;
 action:(run:(c:AbortController)=>Promise<void>)=>Promise<void>;
 onSelect:(v:PS1Violation|null)=>void;
}){
 const [submission,setSubmission]=useState<Record<string,string>>({});
 const [report,setReport]=useState<Report|null>(null),[filter,setFilter]=useState(''),[week,setWeek]=useState(''),[term,setTerm]=useState(''),[selectedViolation,setSelectedViolation]=useState<PS1Violation|null>(null);
 const [error,setError]=useState(''),[validationId,setValidationId]=useState('');
 const [history,setHistory]=useState<{id:string;scenario:string;feasible:boolean}[]>([]);
 function accept(raw:unknown){const next=contextualReportSchema.parse(raw);setReport(next);onSelect(null);setSelectedViolation(null);setFilter('');setWeek('');setTerm('');}
 async function upload(list:FileList|null){
  if(!list)return;const selected=Array.from(list);setError('');setReport(null);setSubmission({});setValidationId('');onSelect(null);
  if(selected.length!==3||new Set(selected.map(f=>f.name)).size!==3||selected.some(f=>!names.includes(f.name))){setError('Select exactly SCHEDULE_ACCESS.csv, SCHEDULE_OCCUPANCY.csv and RESULTS.csv.');return;}
  if(selected.reduce((n,f)=>n+f.size,0)>4_000_000){setError('Submission exceeds 4 MB.');return;}
  await action(async()=>{setSubmission(Object.fromEntries(await Promise.all(selected.map(async f=>[f.name,await f.text()]))));});
 }
 function validate(persist:boolean){void action(async c=>{
  const body={scenario,files:submission};
  if(persist){const result=z.object({id:z.string(),report:contextualReportSchema}).parse(await api(`/api/ps1/instances/${instanceId}/validations`,c,body));if(!c.signal.aborted){accept(result.report);setValidationId(result.id);}}
  else {const result=await api('/api/ps1/validate',c,{...body,instance_files:files});if(!c.signal.aborted){accept(result);setValidationId('');}}
 });}
 function download(){if(!report)return;const url=URL.createObjectURL(new Blob([JSON.stringify(report,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`PS1-${report.scenario}-validation.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 const violations=report?.hard_violations.filter(v=>(!filter||v.rule_code===filter)&&(!week||String(v.week)===week)&&(!term||`${v.message} ${v.activity_ids.join(' ')} ${v.location_ids.join(' ')}`.toLowerCase().includes(term.toLowerCase())))||[];
 return <section className="ps1-detail ps1-validator" aria-label="PS1 submission validator">
  <h3>Internal provisional validator</h3><p>Judge validation not run · Score verification: internal only · CSV feasibility is not physical-night clearance · Conflict severity is separate from schedule objective</p>
  <div className="ps1-actions"><label className="control">Upload 3 submission CSVs<input type="file" multiple accept=".csv" disabled={busy} onChange={e=>{void upload(e.target.files);e.target.value='';}}/></label>
   <button className="control primary" disabled={busy||Object.keys(submission).length!==3||!Object.keys(files).length} onClick={()=>validate(false)}>Preview Scenario {scenario}</button>
   <button className="control" disabled={busy||!instanceId||Object.keys(submission).length!==3} onClick={()=>validate(true)}>Validate and save run</button>
   {instanceId&&<button className="control" disabled={busy} onClick={()=>void action(async c=>{const r=z.object({items:z.array(z.object({id:z.string(),scenario:z.string(),feasible:z.boolean()}))}).parse(await api(`/api/ps1/instances/${instanceId}/validations`,c));if(!c.signal.aborted)setHistory(r.items);})}>Load validation history</button>}
  </div>
  <p>{Object.keys(submission).length===3?'Three files ready.':'No submission loaded.'} Saved-instance validation requires a planner or administrator. Preview needs FastAPI but no database or login.</p>
  {history.map(h=><button className="control" disabled={busy} key={h.id} onClick={()=>void action(async c=>{const r=z.object({result_snapshot:contextualReportSchema}).parse(await api(`/api/ps1/validations/${h.id}`,c));if(!c.signal.aborted){accept(r.result_snapshot);setValidationId(h.id);}})}>Scenario {h.scenario} · {h.feasible?'feasible':'infeasible'} · {h.id.slice(0,8)}</button>)}
  {error&&<p role="alert" className="ps1-error">{error}</p>}
  {report&&<>
   <h4 className={report.feasible?'ps1-status':'ps1-error'}>Schedule {report.feasible?'feasible':'infeasible'} · Scenario {report.scenario}</h4>
   <p>{report.validator_version} · {report.validation_status} {validationId&&`· Saved ${validationId}`}</p>
   <p>{report.physical_validation_complete?'Explicit physical-night checks completed; internal assumptions still apply.':'Physical-night alignment not verified. Feasible means the locally verifiable submission constraints passed, not operational safety clearance.'}</p>
   {report.scenario!==scenario&&<p className="ps1-error">This report is for Scenario {report.scenario}; validate again for the selected Scenario {scenario}.</p>}
   <div className="ps1-stats"><div><strong>{report.completeness.workload_gate_passed?'PASS':'FAIL'}</strong><span>Workload gate</span></div><div><strong>{report.completeness.activities_complete}/{report.completeness.activity_count}</strong><span>Activities complete</span></div><div><strong>{report.hard_violations.length}</strong><span>Hard violations</span></div><div><strong>{report.objective_score??'Not eligible'}</strong><span>Internal objective</span></div></div>
   <p>Raw contract overrun: {report.objective_components.overrun_days_total} days · Weighted activity overrun: {report.objective_components.priority_weighted_overrun} · Excess supply: {report.objective_components.excess_access_nights_total} (penalty {report.objective_components.excess_penalty}) · ECLO: {report.objective_components.eclo_nights_total} (penalty {report.objective_components.eclo_penalty})</p>
   <p>Diagnostic objective: {report.objective_components.diagnostic_objective} — {report.objective_components.metrics_complete?'all workloads accounted for':'partial metrics; incomplete workload'}. Only feasible submissions receive an objective score. Scores are internal, not officially verified.</p>
   <button className="control" onClick={download}>Download JSON report</button>
   <details><summary>Active assumptions and warnings ({report.warnings.length})</summary><ul>{report.active_rule_assumptions.map(a=><li key={a}>{a}</li>)}</ul>{report.warnings.map((w,i)=><pre key={i}>{JSON.stringify(w,null,2)}</pre>)}</details>
   <details><summary>Capacity hotspots ({report.capacity_hotspots.length})</summary><div className="ps1-table-wrap"><table><thead><tr><th>Location</th><th>Week</th><th>Used / supply</th><th>Excess</th></tr></thead><tbody>{report.capacity_hotspots.map(h=><tr key={`${h.location_id}/${h.week}`}><td>{h.location_id}</td><td>{h.week}</td><td>{h.used} / {h.supply}</td><td>{h.excess}</td></tr>)}</tbody></table></div></details>
   <div className="ps1-actions"><select aria-label="Violation rule" value={filter} onChange={e=>setFilter(e.target.value)}><option value="">All rules</option>{[...new Set(report.hard_violations.map(v=>v.rule_code))].sort().map(r=><option key={r}>{r}</option>)}</select><input aria-label="Violation week" placeholder="Filter week" value={week} onChange={e=>setWeek(e.target.value)}/><input aria-label="Violation activity or location" placeholder="Activity or location" value={term} onChange={e=>setTerm(e.target.value)}/><button className="control" onClick={()=>{setSelectedViolation(null);onSelect(null);}}>Clear highlight</button></div>
   {selectedViolation&&<section className="ps1-selected-evidence" aria-label="Selected violation"><h4>Selected violation: {selectedViolation.rule_code}</h4><p>Selected week: {selectedViolation.week??'Not applicable'}</p><p>Selected activity IDs: {selectedViolation.activity_ids.join(', ')||'None'}</p><p>Selected location IDs: {selectedViolation.location_ids.join(', ')||'None'}</p><details open><summary>Structured evidence</summary><pre>{JSON.stringify({possession_group:selectedViolation.possession_group,...selectedViolation.evidence},null,2)}</pre></details></section>}
   <div className="ps1-table-wrap"><table><thead><tr><th>Rule</th><th>Week</th><th>Activities</th><th>Message / evidence</th></tr></thead><tbody>{violations.map((v,i)=><tr key={i}><td><button onClick={()=>{setSelectedViolation(v);onSelect(v);}}>{v.rule_code}</button></td><td>{v.week??'—'}</td><td>{v.activity_ids.join(', ')}</td><td>{v.message}<details><summary>Evidence</summary><pre>{JSON.stringify({locations:v.location_ids,group:v.possession_group,...v.evidence},null,2)}</pre></details></td></tr>)}</tbody></table></div>
  </>}
 </section>;
}
