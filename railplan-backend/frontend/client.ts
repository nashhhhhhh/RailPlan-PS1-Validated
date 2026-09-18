/** RailPlan v0.2 client. No automatic retries or mock fallback. */
import type {ReferenceData,GeoFeature,Availability,ApprovalHistory,SavedOptimiseInput,SavedOptimiseResult,OptimisationPage,OptimisationDetail,OptimisationArtifacts} from "./contracts.generated";
export type UUID = string;
export type Instant = string;
export interface Page<T> {items:T[]; limit:number; offset:number; total:number}
export interface Entity {id:UUID; [key:string]:unknown}
export interface Named extends Entity {name:string}
export interface Capabilities {conflict_analysis_available:boolean; optimisation_available:boolean; copilot_available:boolean; operational_approval_available:boolean}
export interface RequestItem extends Entity {
 request_code:string; title:string; description:string; window_id:UUID;
 requested_start:Instant; requested_end:Instant; version:number; status_code:string; priority:string;
 sectors?:{id:UUID;name:string;code:string}[]|null; teams?:{id:UUID;name:string}[]|null;
}
export interface Mutation {id:UUID;status:string;version?:number|null;validation_status?:string|null}
export interface Assignment extends Entity {
 scenario_id:UUID;request_id:UUID;starts_at:Instant;ends_at:Instant;original_start:Instant;original_end:Instant;
 feasible:boolean;reason:string;team_ids?:UUID[];engineer_ids?:UUID[];asset_ids?:UUID[];sector_ids?:UUID[];
}
export interface Scenario extends Entity {name:string;status:string;version:number;validation_status:string;provenance:string}
export interface Change {scenario_id:UUID;request_id:UUID;request_code:string;original_start:Instant;original_end:Instant;starts_at:Instant;ends_at:Instant;reason:string;replay_order:number}
export interface TimelineItem {request_id:UUID;request_code:string;title:string;window_id:UUID;scenario_id:UUID|null;starts_at:Instant;ends_at:Instant;original_start:Instant;original_end:Instant;movement_minutes:number;moved:boolean;priority:string}
export interface Window extends Named {starts_at:Instant;ends_at:Instant;timezone:string;version:number}
export interface Analysis {id:UUID;status:string;freshness:"fresh"|"stale"|"unknown";can_certify_current_schedule:boolean}
export interface Conflict extends Entity {conflict_code:string;title:string;explanation:string;analysis_run_id:UUID;rule_code:string;severity:string;lens:string;blocking:boolean;detection_method:string;freshness:string}
export interface CommandCentre {window:Window;requests:RequestItem[];timeline:TimelineItem[];scenarios:Scenario[];conflicts:Conflict[]|null;analysis:Analysis|null;selected_scenario_id:UUID|null;selected_scenario_version:number|null;capabilities:Capabilities;truncated:boolean}
export interface ScenarioDetail {summary:Scenario;assignments:Assignment[];changes:Change[];analysis:Analysis|null;capabilities:Capabilities}
export interface EquipmentRequirement {type_id:UUID;quantity:number}
export interface SkillRequirement {skill_id:UUID;required_count:number}
export interface IsolationRequirement {isolation_zone_id:UUID;required_state:"isolated"|"restored"}
export interface RequestCreate {
 submit?:boolean;window_id:UUID;work_type_id:UUID;title:string;description?:string;
 requested_start:Instant;requested_end:Instant;earliest_start:Instant;latest_finish:Instant;
 min_duration_minutes:number;max_duration_minutes:number;priority?:"normal"|"high"|"urgent";
 sector_ids:UUID[];team_ids?:UUID[];engineer_ids?:UUID[];workzone_ids?:UUID[];
 equipment?:EquipmentRequirement[];skills?:SkillRequirement[];isolations?:IsolationRequirement[];
}
export type RequestPatch=Partial<Omit<RequestCreate,"window_id"|"submit">>&{expected_version:number};
export interface AssignmentEdit {expected_version:number;starts_at:Instant;ends_at:Instant;reason:string;team_ids?:UUID[];engineer_ids?:UUID[];asset_ids?:UUID[];sector_ids?:UUID[]}
export interface Preview {basic_valid:boolean;issues:string[];starts_at:Instant;ends_at:Instant;complete_conflict_validation_performed:false;analysis_required:true;scenario_version:number}
export interface LockCreate {expected_version:number;scenario_id?:UUID|null;reason:string;fields:("timing"|"team"|"engineers"|"equipment"|"sectors")[];expires_at?:Instant}
export interface ErrorEnvelope {error:{code:string;message:string;fields:{location?:unknown[];message?:string}[];correlation_id:string;guidance?:string|null}}
export class ApiError extends Error {
 constructor(public status:number, public envelope:ErrorEnvelope) {super(envelope.error.message);this.name="ApiError";}
}
type QueryValue=string|number|boolean|null|undefined|(string|number)[];
export interface ClientConfig {baseUrl:string;demoUserId?:UUID;bearerToken?:()=>Promise<string|undefined>;fetcher?:typeof fetch}
export class RailPlanClient {
 private readonly fetcher:typeof fetch;
 constructor(private config:ClientConfig) {this.fetcher=config.fetcher??fetch;}
 async call<T>(path:string, options:{method?:string;body?:unknown;query?:Record<string,QueryValue>;signal?:AbortSignal}={}):Promise<T> {
  const url=new URL(path,this.config.baseUrl);
  for(const [key,value] of Object.entries(options.query??{})){
   if(value==null)continue;
   for(const item of Array.isArray(value)?value:[value])url.searchParams.append(key,String(item));
  }
  const headers:Record<string,string>={};
  if(options.body!==undefined)headers["Content-Type"]="application/json";
  if(this.config.demoUserId)headers["X-Demo-User-Id"]=this.config.demoUserId;
  const token=await this.config.bearerToken?.();if(token)headers.Authorization="Bearer "+token;
  const response=await this.fetcher(url,{method:options.method??"GET",headers,body:options.body===undefined?undefined:JSON.stringify(options.body),signal:options.signal});
  let data:unknown;
  try{data=await response.json();}catch{throw new ApiError(response.status,{error:{code:"INVALID_RESPONSE",message:"Server did not return JSON",fields:[],correlation_id:response.headers.get("X-Correlation-Id")??"unknown"}});}
  if(!response.ok){
   const error=(data!==null&&typeof data==="object")?data as Partial<ErrorEnvelope>:{};
   throw new ApiError(response.status,error.error&&typeof error.error.message==="string"?error as ErrorEnvelope:{error:{code:"REQUEST_FAILED",message:"API request failed",fields:[],correlation_id:response.headers.get("X-Correlation-Id")??"unknown"}});
  }
  return data as T;
 }
 capabilities(signal?:AbortSignal){return this.call<Capabilities>("/api/capabilities",{signal});}
 optimisePs1ScenarioA(instanceId:UUID,options:SavedOptimiseInput={},signal?:AbortSignal){return this.call<SavedOptimiseResult>("/api/ps1/instances/"+encodeURIComponent(instanceId)+"/optimise/scenario-a",{method:"POST",body:options,signal});}
 ps1Optimisations(instanceId:UUID,query:{limit?:number;offset?:number}={},signal?:AbortSignal){return this.call<OptimisationPage>("/api/ps1/instances/"+encodeURIComponent(instanceId)+"/optimisations",{query,signal});}
 ps1Optimisation(runId:UUID,signal?:AbortSignal){return this.call<OptimisationDetail>("/api/ps1/optimisations/"+encodeURIComponent(runId),{signal});}
 ps1OptimisationAccesses(runId:UUID,query:{limit?:number;offset?:number;week?:number;activity_id?:string}={},signal?:AbortSignal){return this.call<OptimisationPage>("/api/ps1/optimisations/"+encodeURIComponent(runId)+"/accesses",{query,signal});}
 ps1OptimisationOccupancies(runId:UUID,query:{limit?:number;offset?:number;week?:number;activity_id?:string;location_id?:string}={},signal?:AbortSignal){return this.call<OptimisationPage>("/api/ps1/optimisations/"+encodeURIComponent(runId)+"/occupancies",{query,signal});}
 ps1OptimisationArtifacts(runId:UUID,signal?:AbortSignal){return this.call<OptimisationArtifacts>("/api/ps1/optimisations/"+encodeURIComponent(runId)+"/artifacts",{signal});}
 referenceData(signal?:AbortSignal){return this.call<ReferenceData>("/api/reference-data",{signal});}
 window(id:UUID,signal?:AbortSignal){return this.call<Window>("/api/engineering-windows/"+id,{signal});}
 timeline(windowId:UUID,query:{scenario_id?:UUID;limit?:number;offset?:number}={},signal?:AbortSignal){return this.call<TimelineItem[]>("/api/timeline/"+windowId,{query,signal});}
 lines(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<Named>>("/api/network/lines",{query,signal});}
 stations(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<GeoFeature>>("/api/network/stations",{query,signal});}
 sectors(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<GeoFeature>>("/api/network/sectors",{query,signal});}
 workzones(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<GeoFeature>>("/api/workzones",{query,signal});}
 workzone(id:UUID,signal?:AbortSignal){return this.call<GeoFeature>("/api/workzones/"+id,{signal});}
 teams(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<Named>>("/api/teams",{query,signal});}
 engineers(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<Named>>("/api/engineers",{query,signal});}
 equipment(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<Named>>("/api/equipment",{query,signal});}
 availability(query:{resource_type:"engineer"|"team"|"equipment";starts_at:Instant;ends_at:Instant;skill_ids?:UUID[];limit?:number;offset?:number},signal?:AbortSignal){return this.call<Page<Availability>>("/api/resources/availability",{query,signal});}
 listScenarios(windowId:UUID,offset=0,signal?:AbortSignal){return this.call<Page<Scenario>>("/api/scenarios",{query:{window_id:windowId,offset},signal});}
 changes(id:UUID,offset=0,signal?:AbortSignal){return this.call<Page<Change>>("/api/scenarios/"+id+"/changes",{query:{offset},signal});}
 approvalHistory(id:UUID,signal?:AbortSignal){return this.call<ApprovalHistory>("/api/scenarios/"+id+"/approval",{signal});}
 approval(id:UUID,signal?:AbortSignal){return this.call<Entity>("/api/approvals/"+id,{signal});}
 analysis(id:UUID,signal?:AbortSignal){return this.call<Entity>("/api/analyses/"+id,{signal});}
 optimisationRun(id:UUID,signal?:AbortSignal){return this.call<Entity>("/api/optimisation-runs/"+id,{signal});}
 commandCentre(windowId:UUID,scenarioId?:UUID,signal?:AbortSignal){return this.call<CommandCentre>("/api/command-centre/"+windowId,{query:{scenario_id:scenarioId},signal});}
 windows(signal?:AbortSignal){return this.call<Page<Window>>("/api/engineering-windows",{signal});}
 listRequests(query:Record<string,QueryValue>={},signal?:AbortSignal){return this.call<Page<RequestItem>>("/api/maintenance-requests",{query,signal});}
 request(id:UUID,signal?:AbortSignal){return this.call<RequestItem>("/api/maintenance-requests/"+id,{signal});}
 createRequest(body:RequestCreate,signal?:AbortSignal){return this.call<Mutation>("/api/maintenance-requests",{method:"POST",body,signal});}
 patchRequest(id:UUID,body:RequestPatch,signal?:AbortSignal){return this.call<Mutation>("/api/maintenance-requests/"+id,{method:"PATCH",body,signal});}
 submitRequest(id:UUID,version:number){return this.call<Mutation>("/api/maintenance-requests/"+id+"/submit",{method:"POST",body:{expected_version:version}});}
 cancelRequest(id:UUID,version:number,reason:string){return this.call<Mutation>("/api/maintenance-requests/"+id+"/cancel",{method:"POST",body:{expected_version:version,reason}});}
 scenario(id:UUID,signal?:AbortSignal){return this.call<ScenarioDetail>("/api/scenarios/"+id,{signal});}
 createScenario(body:{window_id:UUID;objective_id:UUID;name:string}){return this.call<Mutation>("/api/scenarios",{method:"POST",body});}
 cloneScenario(id:UUID,version:number,name:string){return this.call<Mutation>("/api/scenarios/"+id+"/clone",{method:"POST",body:{expected_version:version,name}});}
 compareScenarios(ids:UUID[],signal?:AbortSignal){return this.call<{scenarios:Scenario[];conflict_resolution_comparable:boolean;reason:string}>("/api/scenarios/compare",{query:{ids},signal});}
 preview(sid:UUID,aid:UUID,body:AssignmentEdit,signal?:AbortSignal){return this.call<Preview>("/api/scenarios/"+sid+"/assignments/"+aid+"/preview",{method:"POST",body,signal});}
 editAssignment(sid:UUID,aid:UUID,body:AssignmentEdit,signal?:AbortSignal){return this.call<Mutation>("/api/scenarios/"+sid+"/assignments/"+aid,{method:"PATCH",body,signal});}
 conflicts(analysisId:UUID,signal?:AbortSignal){return this.call<Page<Conflict>>("/api/conflicts",{query:{analysis_id:analysisId},signal});}
 conflict(id:UUID,signal?:AbortSignal){return this.call<Conflict>("/api/conflicts/"+id,{signal});}
 lock(id:UUID,body:LockCreate){return this.call<Mutation>("/api/maintenance-requests/"+id+"/locks",{method:"POST",body});}
 locks(id:UUID){return this.call<Page<Entity>>("/api/maintenance-requests/"+id+"/locks");}
 releaseLock(id:UUID,reason:string){return this.call<Mutation>("/api/locks/"+id+"/release",{method:"POST",body:{reason}});}
 activity(offset=0,signal?:AbortSignal){return this.call<Page<Entity>>("/api/activity",{query:{offset},signal});}
 readActivity(ids:UUID[]){return this.call<{marked_read:number}>("/api/activity/read",{method:"POST",body:{event_ids:ids}});}
}
