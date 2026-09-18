const test=require("node:test");
const assert=require("node:assert/strict");
const {RailPlanClient,ApiError}=require("./build/client.js");
const {timelineView,composerTime,moveDraft}=require("./build/adapters.js");

test("timeline offsets respect midnight and absolute instants",()=>{
 const item={request_id:"u",request_code:"MR-018",title:"Work",starts_at:"2026-09-15T00:30:00+08:00",
 ends_at:"2026-09-15T01:30:00+08:00",original_start:"2026-09-14T23:45:00+08:00",priority:"high"};
 const result=timelineView(item,"2026-09-14T23:30:00+08:00");
 assert.equal(result.start,60);assert.equal(result.duration,60);assert.equal(result.originalStart,15);
});

test("composer rejects calendar rollovers",()=>{
 for(const [date,time] of [["2026-02-30","12:00"],["2025-02-29","12:00"],["2026-09-14","24:00"]])
   assert.throws(()=>composerTime(date,time));
 assert.equal(composerTime("2028-02-29","00:00"),"2028-02-28T16:00:00.000Z");
});
test("timeline rejects invalid original positions and reversed intervals",()=>{
 const item={request_id:"u",request_code:"MR-018",title:"Work",starts_at:"2026-09-15T00:30:00+08:00",
 ends_at:"2026-09-15T01:30:00+08:00",original_start:"bad",priority:"high"};
 assert.throws(()=>timelineView(item,"2026-09-14T23:30:00+08:00"));
 item.original_start=item.starts_at;item.ends_at=item.starts_at;
 assert.throws(()=>timelineView(item,"2026-09-14T23:30:00+08:00"));
});
test("null error responses are normalized",async()=>{
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async()=>Response.json(null,{status:503})});
 await assert.rejects(()=>api.capabilities(),error=>error instanceof ApiError&&error.status===503);
});
test("resource and map wrappers preserve query parameters",async()=>{
 const urls=[];
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async url=>{urls.push(url);return Response.json({items:[]});}});
 await api.stations({line_id:"line",bbox:"103,1,104,2",offset:50});
 await api.availability({resource_type:"engineer",starts_at:"a",ends_at:"b",skill_ids:["s1","s2"]});
 assert.equal(urls[0].pathname,"/api/network/stations");
 assert.equal(urls[0].searchParams.get("offset"),"50");
 assert.deepEqual(urls[1].searchParams.getAll("skill_ids"),["s1","s2"]);
});
test("PS1 optimiser preserves separate night identities and bounded status",async()=>{
 let request;
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url,init)=>{
  request={url,init};return Response.json({solver_status:"UNKNOWN",publishable:false,submission_files:null});
 }});
 const options={time_limit_seconds:2,physical_nights_per_week:7,locked_placements:[{activity_id:"A1",access_seq:1,week:2,physical_night:6,access_night:1}]};
 const result=await api.optimisePs1ScenarioA("instance",options);
 assert.equal(request.url.pathname,"/api/ps1/instances/instance/optimise/scenario-a");
 assert.equal(request.init.method,"POST");
 assert.deepEqual(JSON.parse(request.init.body),options);
 assert.equal(result.solver_status,"UNKNOWN");assert.equal(result.submission_files,null);
});
test("composer explicitly converts Singapore time",()=>assert.equal(composerTime("2026-09-14","01:00"),"2026-09-13T17:00:00.000Z"));
test("saved PS1 client preserves additive response and baseline/key options",async()=>{
 let sent;
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url,init)=>{
  sent=JSON.parse(init.body);return Response.json({run_id:"run",created:false,reused:true,solver_status:"FEASIBLE",primary_optimal:true,lexicographic_complete:false,publishable:true});
 }});
 const result=await api.optimisePs1ScenarioA("instance",{baseline_run_id:"baseline",idempotency_key:"retry",random_seed:4});
 assert.deepEqual(sent,{baseline_run_id:"baseline",idempotency_key:"retry",random_seed:4});
 assert.equal(result.run_id,"run");assert.equal(result.reused,true);
 assert.equal(result.primary_optimal,true);assert.equal(result.lexicographic_complete,false);
});
test("Scenario B exposes saved and database-free preview paths",async()=>{
 const calls=[];
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url,init)=>{
  calls.push({url,body:JSON.parse(init.body)});return Response.json({scenario:"B",solver_status:"FEASIBLE",publishable:true});
 }});
 await api.optimisePs1ScenarioB("instance",{random_seed:7});
 await api.previewPs1ScenarioB({random_seed:7,instance_files:{a:"1",b:"2",c:"3",d:"4",e:"5",f:"6",g:"7",h:"8"}});
 assert.equal(calls[0].url.pathname,"/api/ps1/instances/instance/optimise/scenario-b");
 assert.equal(calls[1].url.pathname,"/api/ps1/optimise/scenario-b/preview");
 assert.equal(calls[0].body.random_seed,7);
 assert.equal(calls[1].body.instance_files.h,"8");
});
test("Scenario C exposes saved and database-free preview paths",async()=>{
 const calls=[];
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url,init)=>{
  calls.push({url,body:JSON.parse(init.body)});return Response.json({scenario:"C",solver_status:"FEASIBLE",publishable:true});
 }});
 await api.optimisePs1ScenarioC("instance",{random_seed:11});
 await api.previewPs1ScenarioC({random_seed:11,instance_files:{a:"1",b:"2",c:"3",d:"4",e:"5",f:"6",g:"7",h:"8"}});
 assert.equal(calls[0].url.pathname,"/api/ps1/instances/instance/optimise/scenario-c");
 assert.equal(calls[1].url.pathname,"/api/ps1/optimise/scenario-c/preview");
});
test("saved PS1 retrieval filters and artifact errors remain explicit",async()=>{
 const calls=[];
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url)=>{
  calls.push(url);
  if(url.pathname.endsWith("/artifacts"))return Response.json({error:{code:"STATE_CONFLICT",message:"No accepted artifacts",fields:[],correlation_id:"test"}},{status:409});
  return Response.json({items:[],total:0});
 }});
 await api.ps1Optimisations("instance",{limit:1,offset:2,scenario:"B"});
 await api.ps1Optimisation("run");
 await api.ps1OptimisationAccesses("run",{week:2,activity_id:"A1"});
 await api.ps1OptimisationOccupancies("run",{week:2,location_id:"PLAT:ALP:S01:EB"});
 await assert.rejects(()=>api.ps1OptimisationArtifacts("run"),e=>e instanceof ApiError&&e.status===409);
 assert.equal(calls[0].searchParams.get("offset"),"2");
 assert.equal(calls[0].searchParams.get("scenario"),"B");
 assert.equal(calls[2].searchParams.get("activity_id"),"A1");
 assert.equal(calls[3].searchParams.get("location_id"),"PLAT:ALP:S01:EB");
 assert.equal(calls.length,5);
});
test("API serializes repeated comparison IDs",async()=>{
 let called;
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async(url)=>{called=url;return Response.json({scenarios:[]});}});
 await api.compareScenarios(["a","b"]);
 assert.deepEqual(called.searchParams.getAll("ids"),["a","b"]);
});
test("client propagates AbortSignal and demo identity",async()=>{
 const controller=new AbortController();let options;
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",demoUserId:"user",fetcher:async(url,init)=>{options=init;return Response.json({});}});
 await api.capabilities(controller.signal);
 assert.equal(options.signal,controller.signal);assert.equal(options.headers["X-Demo-User-Id"],"user");
});
test("failed requests do not retry or substitute mock data",async()=>{
 let count=0;
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async()=>{
 count++;return Response.json({error:{code:"STATE_CONFLICT",message:"Reload",fields:[],correlation_id:"c"}},{status:409});}});
 await assert.rejects(()=>api.createScenario({window_id:"w",objective_id:"o",name:"Demo"}),error=>error instanceof ApiError&&error.status===409);
 assert.equal(count,1);
});
test("invalid response is reported",async()=>{
 const api=new RailPlanClient({baseUrl:"http://localhost:8000",fetcher:async()=>new Response("Bad gateway",{status:502})});
 await assert.rejects(()=>api.capabilities(),error=>error.envelope.error.code==="INVALID_RESPONSE");
});
test("rejected preview never writes",async()=>{
 let written=false;
 const api={preview:async()=>({basic_valid:false,issues:["Timing is locked"]}),editAssignment:async()=>{written=true;}};
 await assert.rejects(()=>moveDraft(api,"s",{id:"a"},{}),/locked/);assert.equal(written,false);
});
test("successful draft write reloads new server version",async()=>{
 const calls=[];
 const api={preview:async()=>({basic_valid:true}),editAssignment:async()=>calls.push("write"),scenario:async()=>{calls.push("read");return{summary:{version:9}};}};
 const result=await moveDraft(api,"s",{id:"a"},{expected_version:2});
 assert.deepEqual(calls,["write","read"]);assert.equal(result.summary.version,9);
});
