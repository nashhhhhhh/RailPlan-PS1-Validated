/** Display adapters deliberately keep missing scores distinct from zero. */
import type {RailPlanClient, UUID, Entity, Page} from "./client";
export type Severity = "information"|"low"|"medium"|"high"|"critical";
export interface ScoreComponent {
 name:string; score:number|null; weight:number; weighted_contribution:number|null;
 status:"complete"|"partial"|"unknown"|"not_applicable"; evidence:string[]; missing_inputs:string[];
}
export interface ScoreResult {
 engine_version:string; rule_severity:Severity; risk_score:number|null; risk_upper_bound:number|null;
 risk_band:Severity|null; effective_severity:Severity; blocking:boolean;
 score_status:"complete"|"partial"|"unknown"; confidence:number; coverage:number;
 synthetic:boolean; policy_validated:boolean; eligible_for_auto_prioritisation:boolean;
 explanation:string; components:ScoreComponent[];
}
export interface Score extends Entity {
 conflict_id:UUID; policy_id:UUID; input_fingerprint:string; policy_fingerprint:string;
 engine_version:string; source_revision:number; result:ScoreResult; created_at:string;
 freshness:"fresh"|"stale"; active_policy_matches:boolean; can_certify_current_schedule:false;
}
export interface ScoringContext extends Entity {version:number; input_fingerprint:string; source_revision:number; analysis_freshness:"unknown";can_recalculate:boolean}
export interface ScoreRequest {policy_id:UUID;expected_conflict_version:number;expected_input_fingerprint:string;idempotency_key:string}
export interface PolicyInput {code?:string;version?:number;weights?:Record<"safety"|"operational"|"resource"|"urgency"|"passenger",number|string>;description?:string}
export class ScoringClient {
 constructor(private api:RailPlanClient){}
 policies(){return this.api.call<Page<Entity>>("/api/scoring-policies");}
 policy(id:UUID){return this.api.call<Entity>("/api/scoring-policies/"+id);}
 createPolicy(body:PolicyInput={}){return this.api.call<Entity>("/api/scoring-policies",{method:"POST",body});}
 activatePolicy(id:UUID){return this.api.call<Entity>("/api/scoring-policies/"+id+"/activate",{method:"POST"});}
 context(id:UUID){return this.api.call<ScoringContext>("/api/conflicts/"+id+"/scoring-context");}
 calculate(id:UUID,body:ScoreRequest){return this.api.call<Score>("/api/conflicts/"+id+"/scores",{method:"POST",body});}
 history(id:UUID,offset=0){return this.api.call<Page<Score>>("/api/conflicts/"+id+"/scores",{query:{offset}});}
 latest(id:UUID){return this.api.call<Score|null>("/api/conflicts/"+id+"/scores/latest");}
 score(id:UUID){return this.api.call<Score>("/api/conflict-scores/"+id);}
}
export function scorePanel(score:Score|null,context?:ScoringContext){
 if(!score)return {state:"unscored" as const,label:"Not scored",bars:[],canRecalculate:context?.can_recalculate??false};
 const r=score.result;
 return {state:score.freshness,label:r.risk_score===null?"Unknown":`${r.risk_score.toFixed(2)} / 100 (${r.score_status})`,
  upperBound:r.risk_upper_bound,severity:r.effective_severity,blocking:r.blocking,
  confidencePercent:Math.round(r.confidence*100),coveragePercent:Math.round(r.coverage*100),
  explanation:r.explanation,policyId:score.policy_id,engineVersion:score.engine_version,calculatedAt:score.created_at,
  activePolicyMatches:score.active_policy_matches,synthetic:r.synthetic,
  canRecalculate:context?.can_recalculate??false,
  bars:r.components.map(c=>({name:c.name,value:c.score,label:c.score===null?"Unknown":String(c.score),
   contribution:c.weighted_contribution,weightPercent:c.weight*100,status:c.status,evidence:c.evidence,missingInputs:c.missing_inputs}))};
}
