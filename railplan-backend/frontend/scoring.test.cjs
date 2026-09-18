const {test}=require('node:test');
const assert=require('node:assert/strict');
const {scorePanel,ScoringClient}=require('./build/scoring.js');
test('unscored is not a zero risk score',()=>{
 const result=scorePanel(null);
 assert.equal(result.label,'Not scored');assert.equal(result.canRecalculate,false);
});
test('unknown bars and stale state remain visible',()=>{
 const result=scorePanel({id:'s',freshness:'stale',result:{risk_score:0,score_status:'partial',confidence:.25,coverage:.5,
 effective_severity:'critical',blocking:true,components:[{name:'passenger',score:null,weight:.1,weighted_contribution:null,status:'unknown',evidence:[],missing_inputs:['Passenger dataset']}]}});
 assert.equal(result.label,'0.00 / 100 (partial)');assert.equal(result.state,'stale');
 assert.equal(result.bars[0].value,null);assert.equal(result.bars[0].label,'Unknown');assert.equal(result.blocking,true);
});
test('scoring client carries concurrency tokens without automatically retrying',async()=>{
 const calls=[];const api=new ScoringClient({call:async(...args)=>{calls.push(args);return {};}});
 const body={policy_id:'p',expected_conflict_version:1,expected_input_fingerprint:'hash',idempotency_key:'retry-key'};
 await api.calculate('c',body);
 assert.deepEqual(calls,[['/api/conflicts/c/scores',{method:'POST',body}]]);
});
