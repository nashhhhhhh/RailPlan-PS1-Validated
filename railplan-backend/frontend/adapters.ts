import {RailPlanClient,Assignment,RequestItem,TimelineItem,UUID,RequestCreate,AssignmentEdit,ApiError} from "./client";

/** Display codes stay separate from database IDs. Rows/colours remain UI choices. */
export function timelineView(item:TimelineItem,windowStart:string) {
 const origin=Date.parse(windowStart),start=Date.parse(item.starts_at),end=Date.parse(item.ends_at),original=Date.parse(item.original_start);
 if([origin,start,end,original].some(x=>!Number.isFinite(x))||end<=start)throw new Error("Invalid API timestamp or interval");
 return {id:item.request_id,code:item.request_code,title:item.title,
   start:(start-origin)/60000,duration:(end-start)/60000,
   originalStart:(original-origin)/60000,priority:item.priority};
}
export function sgt(instant:string) {
 return new Intl.DateTimeFormat("en-SG",{timeZone:"Asia/Singapore",hour:"2-digit",minute:"2-digit",hourCycle:"h23"}).format(new Date(instant));
}
/** Singapore composer inputs only; explicit UTC+08 handles crossing midnight by date. */
export function composerTime(date:string,time:string) {
 if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!/^\d{2}:\d{2}$/.test(time))throw new Error("Use date and time fields");
 const value=new Date(date+"T"+time+":00+08:00");
 if(!Number.isFinite(value.getTime()))throw new Error("Invalid local time");
 // Date normalizes some invalid dates (e.g. February 30); reject that rollover.
 const roundtrip=new Date(value.getTime()+8*60*60*1000).toISOString().slice(0,16);
 if(roundtrip!==date+"T"+time)throw new Error("Invalid calendar date or time");
 return value.toISOString();
}
export type LoadState<T>={status:"loading"}|{status:"ready";data:T}|{status:"error";message:string;correlationId?:string};
/** Abort the prior load when the selected window changes; never substitute seeds on failure. */
export async function loadWorkspace(api:RailPlanClient,windowId:UUID,scenarioId?:UUID,signal?:AbortSignal) {
 const data=await api.commandCentre(windowId,scenarioId,signal);
 return {data,jobs:data.timeline.map(row=>timelineView(row,data.window.starts_at)),
   analysisUnknown:data.analysis===null||data.analysis.freshness!=="fresh",
   canOptimise:data.capabilities.optimisation_available,
   canApprove:data.capabilities.operational_approval_available};
}
export async function submitComposer(api:RailPlanClient,input:RequestCreate) {
 const created=await api.createRequest(input);
 return api.request(created.id);
}
export async function moveDraft(api:RailPlanClient,scenarioId:UUID,assignment:Assignment,edit:AssignmentEdit) {
 const check=await api.preview(scenarioId,assignment.id,edit);
 if(!check.basic_valid)throw new Error(check.issues.join("; "));
 // Preview is advisory; PATCH repeats all checks transactionally with the same version.
 await api.editAssignment(scenarioId,assignment.id,edit);
 return api.scenario(scenarioId);
}
export async function inspectConflict(api:RailPlanClient,id:UUID) {return api.conflict(id);}
export async function comparePlans(api:RailPlanClient,ids:UUID[]) {return api.compareScenarios(ids);}
export async function keepTiming(api:RailPlanClient,request:RequestItem,scenarioId?:UUID) {
 return api.lock(request.id,{expected_version:request.version,scenario_id:scenarioId,fields:["timing"],reason:"Planner fixed requested timing"});
}
export async function unlockTiming(api:RailPlanClient,lockId:UUID) {return api.releaseLock(lockId,"Planner released timing lock");}
export async function acknowledgeActivity(api:RailPlanClient,ids:UUID[]) {await api.readActivity(ids);return api.activity();}
export function displayError(error:unknown) {
 if(error instanceof ApiError)return {message:error.message,correlationId:error.envelope.error.correlation_id,reload:error.status===409};
 return {message:error instanceof Error?error.message:"Unable to load data",reload:false};
}
