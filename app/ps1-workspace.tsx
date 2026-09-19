"use client";
import {useEffect,useRef,useState} from "react";
import {Dialog,DialogContent,DialogDescription,DialogTitle} from "@/components/ui/dialog";
import "./ps1.css";
import {z} from "zod";
import PS1OptimisationPanel from './ps1-optimisation-panel';
import PS1ValidationPanel,{type PS1Violation} from './ps1-validation-panel';
import {demoSteps,scenarioDescriptions,type DemoStep} from './components/ps1/demo-state';

type Activity={activity_id:string;contract_number:string;activity_type:string;total_accesses:number;planned_start_week:number;planned_start_date:string;predecessor_activity_id:string;activity_priority:number;line_code:string;bound:string;span_location_ids:string[]};
type Project={contract_number:string;contract_description:string;nature_of_activity:string;contract_priority:number;planned_completion_date:string;number_of_workfronts:number;number_of_maximum_access_per_week:number;access_type:string};
type Location={location_id:string;supply_capacity:number;line_code:string;bound:string};
export type Dataset={fingerprint:string;summary:{lines:number;station_records:number;unique_station_ids:number;tunnel_sectors:number;locations:number;contracts:number;activities:number;total_access_workload:number;dependencies:number;horizon_start:string;horizon_end:string;horizon_weeks:number};tables:{activity_details:Activity[];project_details:Project[];location_supply:Location[];stations:{station_id:string;line_code:string;seq:number;is_interchange:number}[]};warnings:string[];schedule_status:string;judge_validation:string};
type Bundle={name:string;files:Record<string,string>;dataset:Dataset};
const n=z.number().int().nonnegative();
const datasetSchema:z.ZodType<Dataset>=z.object({fingerprint:z.string(),summary:z.object({lines:n,station_records:n,unique_station_ids:n,tunnel_sectors:n,locations:n,contracts:n,activities:n,total_access_workload:n,dependencies:n,horizon_start:z.string(),horizon_end:z.string(),horizon_weeks:n}),tables:z.object({
 activity_details:z.array(z.object({activity_id:z.string(),contract_number:z.string(),activity_type:z.string(),total_accesses:n,planned_start_week:n,planned_start_date:z.string(),predecessor_activity_id:z.string(),activity_priority:n,line_code:z.string(),bound:z.string(),span_location_ids:z.array(z.string())})),
 project_details:z.array(z.object({contract_number:z.string(),contract_description:z.string(),nature_of_activity:z.string(),contract_priority:n,planned_completion_date:z.string(),number_of_workfronts:n,number_of_maximum_access_per_week:n,access_type:z.string()})),
 location_supply:z.array(z.object({location_id:z.string(),supply_capacity:n,line_code:z.string(),bound:z.string()})),
 stations:z.array(z.object({station_id:z.string(),line_code:z.string(),seq:n,is_interchange:n}))}),warnings:z.array(z.string()),schedule_status:z.string(),judge_validation:z.string()});
const bundleSchema=z.object({name:z.string(),files:z.record(z.string()),dataset:datasetSchema});
const savedSchema=z.object({id:z.string().uuid(),name:z.string(),dataset:datasetSchema});
const listSchema=z.object({items:z.array(z.object({id:z.string().uuid(),name:z.string()}))});
const descriptions={A:"Fixed supply; ECLO forbidden. Minimise priority-weighted completion overrun.",B:"Fixed planned deadlines. Minimise 7 × excess access-nights + 5 × ECLO nights.",C:"Balance overrun, extra supply and ECLO. At most one excess access-night per location/week; ECLO within a two-week span per line."};

export default function PS1Workspace({onClose,initialDemo=false}:{onClose:()=>void;initialDemo?:boolean}){
 const [bundle,setBundle]=useState<Bundle|null>(null),[error,setError]=useState(""),[busy,setBusy]=useState(false);
 const [tab,setTab]=useState<"activities"|"contracts"|"supply">("activities"),[line,setLine]=useState("All"),[scenario,setScenario]=useState<"A"|"B"|"C">("A");
 const [query,setQuery]=useState(""),[selected,setSelected]=useState(""),[saved,setSaved]=useState("");
 const [url,setUrl]=useState(process.env.NEXT_PUBLIC_RAILPLAN_API_URL||"http://127.0.0.1:8000"),[user,setUser]=useState(process.env.NEXT_PUBLIC_RAILPLAN_DEMO_USER_ID||"1a677983-6052-53d0-a3fa-880c7a5e186a");
 const [history,setHistory]=useState<{id:string;name:string}[]>([]);
 const [highlight,setHighlight]=useState<PS1Violation|null>(null);
 const [demo,setDemo]=useState(initialDemo),[demoStep,setDemoStep]=useState<DemoStep>('Dataset');
 const [demoReset,setDemoReset]=useState(0);
 const [connection,setConnection]=useState<'Connecting'|'Stateless mode'|'Persisted mode'|'Unavailable'>('Connecting');
 const [optimiserLocations,setOptimiserLocations]=useState<string[]>([]);
 const connectionRef=useRef<HTMLDetailsElement|null>(null);
 const controller=useRef<AbortController|null>(null);
 useEffect(()=>()=>controller.current?.abort(),[]);
 useEffect(()=>{
  const c=new AbortController();setConnection('Connecting');
  (async()=>{try{
   const base=new URL(url);if(!['http:','https:'].includes(base.protocol)||base.username||base.password||base.search||base.hash)throw Error('Invalid backend address');
   const host=base.href.replace(/\/$/,'');
   const live=await fetch(host+'/health',{signal:c.signal});if(!live.ok)throw Error('Backend unavailable');
   const ready=await fetch(host+'/health/ready',{signal:c.signal});if(!ready.ok)throw Error('Backend unavailable');
   const body=z.object({status:z.literal('ready'),mode:z.enum(['stateless','persisted'])}).parse(await ready.json());
   if(!c.signal.aborted)setConnection(body.mode==='persisted'?'Persisted mode':'Stateless mode');
  }catch{if(!c.signal.aborted)setConnection('Unavailable');}})();
  return()=>c.abort();
 },[url]);
 function begin(){controller.current?.abort();const c=new AbortController();controller.current=c;setBusy(true);setError("");return c;}
 async function api(path:string,c:AbortController,body?:unknown){
  const base=new URL(url);if(!["http:","https:"].includes(base.protocol)||base.username||base.password||base.search||base.hash)throw Error("Enter an HTTP(S) backend address without credentials or query parameters.");
  const response=await fetch(base.href.replace(/\/$/,"")+path,{signal:c.signal,method:body===undefined?"GET":"POST",headers:{"Content-Type":"application/json",...(user?{"X-Demo-User-Id":user}:{})},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await response.json();if(!response.ok){const e=z.object({error:z.object({message:z.string()}).optional(),detail:z.string().optional()}).safeParse(result);throw Error(e.success?(e.data.error?.message||e.data.detail||"Request failed"):"Request failed");}return result;
 }
 async function action(run:(c:AbortController)=>Promise<void>){const c=begin();try{await run(c);}catch(e){if(!c.signal.aborted)setError(e instanceof Error?e.message:"Could not load instance");}finally{if(!c.signal.aborted)setBusy(false);}}
 function useBundle(next:Bundle){setBundle(next);setSelected("");setSaved("");setLine("All");setQuery("");setHighlight(null);setOptimiserLocations([]);}
 function example(){void action(async c=>{const r=await fetch('/ps1/example.json',{signal:c.signal});if(!r.ok)throw Error("Bundled example is unavailable");const next=bundleSchema.parse(await r.json());if(!c.signal.aborted)useBundle(next);});}
 async function upload(files:FileList|null){
  if(!files)return;
  const items=Array.from(files);if(items.length!==8){setError("Select all eight input CSV files from 01_data together.");return;}
  if(items.reduce((n,f)=>n+f.size,0)>4_000_000){setError("Instance exceeds 4 MB.");return;}
  if(new Set(items.map(f=>f.name)).size!==8){setError("Duplicate filenames selected.");return;}
  void action(async c=>{const entries=await Promise.all(items.map(async f=>[f.name,await f.text()]));const files=Object.fromEntries(entries);const dataset=datasetSchema.parse(await api('/api/ps1/preview',c,{name:"Uploaded PS1 instance",files}));if(!c.signal.aborted)useBundle({name:"Uploaded PS1 instance",files,dataset});});
 }
 const data=bundle?.dataset,s=data?.summary;
 const activities=(data?.tables.activity_details||[]).filter(a=>(line==='All'||a.line_code===line)&&`${a.activity_id} ${a.contract_number} ${a.activity_type}`.toLowerCase().includes(query.toLowerCase()));
 const detail=data?.tables.activity_details.find(a=>a.activity_id===selected);
 const project=detail&&data?.tables.project_details.find(p=>p.contract_number===detail.contract_number);
 return <Dialog open onOpenChange={open=>{if(!open)onClose();}}><DialogContent className="ps1-workspace">
  <div className="ps1-demo-head"><button className="control" aria-pressed={demo} onClick={()=>{setDemo(v=>!v);setDemoStep('Dataset');}}>{demo?'Exit Competition Demo':'Start Competition Demo'}</button><span role="status">Backend: {connection==='Connecting'?'Connecting':connection==='Unavailable'?'Unavailable':`Connected · ${connection}`}</span></div>
  {demo&&<section className="ps1-demo" aria-label="Competition Demo"><h3>Competition Demo</h3><nav aria-label="Demo steps">{demoSteps.map((step,index)=><button key={step} className={`control ${step===demoStep?'primary':''}`} aria-current={step===demoStep?'step':undefined} onClick={()=>setDemoStep(step)}>{index+1}. {step}</button>)}</nav><p>Step {demoSteps.indexOf(demoStep)+1} of 6: {demoStep}</p>
   {demoStep==='Dataset'&&<p>Load the organiser input dataset below, or import all eight input CSV files. Organiser reference output is an example, not a generated result.</p>}
   {demoStep==='Scenario'&&<div className="ps1-demo-cards">{(['A','B','C'] as const).map(k=><button key={k} className={`ps1-demo-card ${scenario===k?'selected':''}`} onClick={()=>setScenario(k)} aria-pressed={scenario===k}><strong>Scenario {k}</strong>{scenarioDescriptions[k].map(sentence=><span key={sentence}>{sentence}</span>)}</button>)}</div>}
   {demoStep==='Optimisation'&&<p>Choose Quick, Balanced or Thorough below, then run the solver. Longer limits improve search but do not guarantee optimality. Scenario A requires persisted mode; B and C support stateless preview.</p>}
   {demoStep==='Validation'&&<p>Inspect the generated run's internal validation and publication checklist below. You can also upload three submission CSV files for separate internal validation.</p>}
   {demoStep==='Objective'&&<p>Review each objective component below. Conflict severity is separate from schedule objective. Score verification: internal only.</p>}
   {demoStep==='Export'&&<p>Download generated CSV files only when every publication check passes. Download the JSON validation report for the same run.</p>}
   <div className="ps1-actions"><button className="control" disabled={demoStep==='Dataset'} onClick={()=>setDemoStep(demoSteps[Math.max(0,demoSteps.indexOf(demoStep)-1)])}>Previous</button><button className="control primary" disabled={demoStep==='Export'} onClick={()=>setDemoStep(demoSteps[Math.min(5,demoSteps.indexOf(demoStep)+1)])}>Next step</button><button className="control" onClick={()=>{setDemoStep('Dataset');setScenario('A');setTab('activities');setSelected('');setHighlight(null);setOptimiserLocations([]);setQuery('');setLine('All');setDemoReset(n=>n+1);}}>Restart demo</button></div>
  </section>}
  <DialogTitle>PS1 · Track access planning</DialogTitle><DialogDescription>Line Alpha and Line Beta · official hackathon instance · weekly possession planning</DialogDescription>
  <div className="ps1-actions"><button className="control primary" disabled={busy} onClick={example}>Load organiser dataset</button><label className="control">Import 8 CSV files<input type="file" accept=".csv" multiple disabled={busy} onChange={e=>{void upload(e.target.files);e.target.value="";}}/></label><span>{busy?'Loading…':saved?`Saved instance ${saved}`:bundle?'Preview loaded':'Choose a dataset to begin'}</span></div>
  <details className="ps1-connection" ref={connectionRef}><summary>Connection and saved instances</summary><p>Import validation uses FastAPI. Saving and reopening use PostgreSQL and your planner identity.</p><label>Backend address<input value={url} onChange={e=>setUrl(e.target.value)} disabled={busy}/></label>{connection==='Persisted mode'&&<label>Demo planner ID<input value={user} onChange={e=>setUser(e.target.value)} disabled={busy}/></label>}
   {connection==='Persisted mode'&&<><button className="control" disabled={busy||!bundle||!Object.keys(bundle.files).length} onClick={()=>void action(async c=>{const r=z.object({id:z.string().uuid()}).parse(await api('/api/ps1/instances',c,{name:bundle!.name,files:bundle!.files}));if(!c.signal.aborted)setSaved(r.id);})}>Save dataset</button>
   <button className="control" disabled={busy} onClick={()=>void action(async c=>{const r=listSchema.parse(await api('/api/ps1/instances',c));if(!c.signal.aborted)setHistory(r.items);})}>Load saved list</button></>}
   {connection==='Persisted mode'&&history.map(h=><button key={h.id} className="control" disabled={busy} onClick={()=>void action(async c=>{const r=savedSchema.parse(await api('/api/ps1/instances/'+h.id,c));if(!c.signal.aborted){useBundle({name:r.name,files:{},dataset:r.dataset});setSaved(r.id);}})}>{h.name}</button>)}
  </details>
  {error&&<p role="alert" className="ps1-error">{error}</p>}
  {s&&data&&<>
   <div className="ps1-stats">{[[s.activities,'activities'],[s.contracts,'contracts'],[s.total_access_workload,'access-nights required'],[s.horizon_weeks,'planning weeks'],[s.locations,'capacity locations']].map(([v,l])=><div key={l}><strong>{v}</strong><span>{l}</span></div>)}</div>
   <p>{bundle?.name} · {s.horizon_start} to {s.horizon_end} · {s.dependencies} predecessor links. Full workload must be scheduled before quality scoring.</p>
   <div className="ps1-network">{['ALP','BET'].map(l=><div key={l}><strong>{l==='ALP'?'Line Alpha':'Line Beta'}</strong><div>{data.tables.stations.filter(r=>r.line_code===l).sort((a,b)=>a.seq-b.seq).map(st=><span className={`${st.is_interchange?'hub':''} ${[...(highlight?.location_ids??[]),...optimiserLocations].some(id=>id.split(':')[1]===l&&id.split(':')[2]?.split('_').includes(st.station_id))?'ps1-highlight':''}`} key={st.station_id}>{st.station_id}</span>)}</div></div>)}</div>
   <p className="ps1-note">H01 and H02 share interchange names; each line and bound has its own tunnel/platform capacity. Live possessions require cross-line closure checks. These locations have no Singapore coordinates.</p>
   <div className="ps1-scenarios">{(['A','B','C'] as const).map(k=><button className={`control ${scenario===k?'primary':''}`} key={k} onClick={()=>setScenario(k)}>Scenario {k}</button>)}<p>{descriptions[scenario]}</p></div>
   <p className="ps1-status">Dataset loaded · Judge validation not run. Generate and inspect saved schedules below, or validate an uploaded submission separately.</p>
   <PS1OptimisationPanel key={data.fingerprint+'/'+saved+'/'+url+'/'+user+'/'+scenario+'/'+demoReset} instanceId={saved} instanceFiles={bundle!.files} dataset={data} scenario={scenario} baseUrl={url} demoUserId={connection==='Persisted mode'?user:''} onSaveDataset={()=>{if(connectionRef.current){connectionRef.current.open=true;connectionRef.current.scrollIntoView({block:'center'});connectionRef.current.querySelector<HTMLButtonElement>('button')?.focus();}}} onSelectActivity={id=>{setSelected(id);setTab('activities');setLine('All');setQuery('');setHighlight(null);}} onHighlightLocations={setOptimiserLocations}/>
   <PS1ValidationPanel key={data.fingerprint+'/'+saved+'/'+demoReset} scenario={scenario} files={bundle!.files} instanceId={saved} busy={busy} api={api} action={action} onSelect={v=>{setOptimiserLocations([]);setHighlight(v);setLine('All');setQuery('');if(v?.activity_ids.length){setSelected(v.activity_ids[0]);setTab('activities');}}}/>
   {highlight&&<section className="ps1-status"><strong>Selected violation · {highlight.rule_code} · Week {highlight.week??'not applicable'}</strong><p>Activities: {highlight.activity_ids.join(', ')||'—'} · Contracts: {highlight.contract_ids.join(', ')||'—'}</p><div>{highlight.location_ids.map(id=><mark key={id}>{id} </mark>)}</div></section>}
   {data.warnings.map((w,i)=><p className="ps1-error" key={i}>{w}</p>)}
   <div className="ps1-actions">{(['activities','contracts','supply'] as const).map(t=><button key={t} className={`control ${tab===t?'primary':''}`} onClick={()=>setTab(t)}>{t}</button>)}<input aria-label="Search dataset" placeholder="Activity, contract or location…" value={query} onChange={e=>setQuery(e.target.value)}/><select aria-label="Filter line" value={line} onChange={e=>setLine(e.target.value)} disabled={tab==='contracts'}><option>All</option><option>ALP</option><option>BET</option></select></div>
   <div className="ps1-table-wrap"><table><thead><tr>{(tab==='activities'?['Activity','Contract','Line / bound','Workload','Start week','Predecessor','Priority']:tab==='contracts'?['Contract','Nature','Possession','Priority','Workfronts','Nights / week','Target']:['Location','Line','Bound','Weekly supply']).map(h=><th key={h}>{h}</th>)}</tr></thead><tbody>
   {tab==='activities'&&activities.map(a=><tr key={a.activity_id} className={selected===a.activity_id||highlight?.activity_ids.includes(a.activity_id)?'selected':''}><td><button onClick={()=>setSelected(a.activity_id)}>{a.activity_id}</button></td><td>{a.contract_number}</td><td>{a.line_code} / {a.bound}</td><td>{a.total_accesses}</td><td>{a.planned_start_week}</td><td>{a.predecessor_activity_id||'—'}</td><td>{a.activity_priority}</td></tr>)}
   {tab==='contracts'&&data.tables.project_details.filter(p=>`${p.contract_number} ${p.contract_description}`.toLowerCase().includes(query.toLowerCase())).map(p=><tr key={p.contract_number}><td>{p.contract_number}</td><td>{p.nature_of_activity}</td><td>{p.access_type}</td><td>{p.contract_priority}</td><td>{p.number_of_workfronts}</td><td>{p.number_of_maximum_access_per_week}</td><td>{p.planned_completion_date}</td></tr>)}
   {tab==='supply'&&data.tables.location_supply.filter(l=>(line==='All'||l.line_code===line)&&l.location_id.toLowerCase().includes(query.toLowerCase())).map(l=><tr key={l.location_id} className={highlight?.location_ids.includes(l.location_id)||optimiserLocations.includes(l.location_id)?'selected':''}><td>{l.location_id}</td><td>{l.line_code}</td><td>{l.bound}</td><td>{l.supply_capacity} access-nights</td></tr>)}
   </tbody></table></div>
   {detail&&tab==='activities'&&<section className="ps1-detail"><h3>{detail.activity_id} · Occupied span</h3><p>{project?.nature_of_activity} · {project?.access_type} · {detail.total_accesses} access-nights required</p><div>{detail.span_location_ids.map(id=><span key={id}>{id}</span>)}</div><p>Includes book-in and book-out platforms. Exclusion buffers, opposite-bound mirroring and Live cross-line closures must be added by the PS1 scheduling engine.</p></section>}
   <details><summary>Organiser reference output (Scenario A)</summary><p>Provided examples only; these files are not a schedule generated for your uploaded instance.</p>{['SCHEDULE_ACCESS.csv','SCHEDULE_OCCUPANCY.csv','RESULTS.csv'].map(name=><a className="control" href={'/ps1/'+name} download key={name}>{name}</a>)}</details>
  </>}
 </DialogContent></Dialog>;
}
