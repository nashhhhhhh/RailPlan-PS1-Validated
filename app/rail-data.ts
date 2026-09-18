export type Job={id:string;title:string;sector:string;team:string;start:number;duration:number;row:number;track?:number;kind:string;options:number[];equipment:string;priority:string};
export const time=(minute:number)=>{const n=minute+30;return `${String(Math.floor(n/60)).padStart(2,"0")}:${String(n%60).padStart(2,"0")}`};
export const stations=[{name:"Yio Chu Kang",code:"NS15",x:80,y:180},{name:"Ang Mo Kio",code:"NS16",x:200,y:140},{name:"Bishan",code:"NS17",x:315,y:85},{name:"Braddell",code:"NS18",x:425,y:85},{name:"Toa Payoh",code:"NS19",x:565,y:180},{name:"Novena",code:"NS20",x:675,y:180},{name:"Newton",code:"NS21",x:785,y:180},{name:"Orchard",code:"NS22",x:880,y:180}];
export const jobs:Job[]=[
{id:"MR-018",title:"Signal inspection",sector:"Bishan–Braddell",team:"Team Alpha",start:15,duration:60,row:0,kind:"red",options:[15,15,15],equipment:"Inspection kit",priority:"High"},
{id:"MR-024",title:"Rail renewal",sector:"Bishan–Braddell",team:"Team Bravo",start:45,duration:75,row:0,track:1,kind:"red",options:[90,75,90],equipment:"Rail crane",priority:"High"},
{id:"MR-031",title:"Cable inspection",sector:"Braddell–Toa Payoh",team:"Team Charlie",start:30,duration:60,row:1,kind:"amber",options:[30,30,30],equipment:"Test meter",priority:"Normal"},
{id:"MR-037",title:"Point machine test",sector:"Braddell–Toa Payoh",team:"Team Bravo",start:140,duration:45,row:1,kind:"cyan",options:[170,160,170],equipment:"Test meter",priority:"Normal"},
{id:"MR-040",title:"Drainage clearance",sector:"Toa Payoh–Novena",team:"Team Delta",start:10,duration:50,row:2,kind:"cyan",options:[10,10,10],equipment:"Drain pump",priority:"Normal"},
{id:"MR-045",title:"Track walk",sector:"Toa Payoh–Novena",team:"Team Echo",start:110,duration:65,row:2,kind:"violet",options:[110,110,100],equipment:"Inspection kit",priority:"Normal"},
{id:"MR-042",title:"Platform inspection",sector:"Novena–Newton",team:"Team Alpha",start:45,duration:45,row:3,kind:"red",options:[90,90,90],equipment:"Inspection kit",priority:"Normal"},
{id:"MR-048",title:"Safety handback",sector:"Bishan–Braddell",team:"Team Alpha",start:200,duration:30,row:3,kind:"cyan",options:[200,200,200],equipment:"Inspection kit",priority:"High"},
{id:"MR-050",title:"Geometry run",sector:"Bishan–Braddell",team:"Vehicle crew",start:110,duration:45,row:4,kind:"amber",options:[165,165,180],equipment:"Inspection vehicle",priority:"High"},
{id:"MR-052",title:"Vehicle transfer",sector:"Novena–Newton",team:"Vehicle crew",start:135,duration:30,row:4,track:1,kind:"red",options:[210,210,150],equipment:"Inspection vehicle",priority:"Normal"},
{id:"MR-054",title:"P4 isolation window",sector:"Bishan–Braddell",team:"Power team",start:0,duration:145,row:5,kind:"violet",options:[0,0,0],equipment:"Isolation panel",priority:"High"},
{id:"MR-056",title:"Station systems",sector:"Newton–Orchard",team:"Team Foxtrot",start:65,duration:60,row:6,kind:"cyan",options:[65,65,65],equipment:"Test meter",priority:"Normal"},
{id:"MR-061",title:"Equipment staging",sector:"Jurong East",team:"Team Golf",start:30,duration:45,row:6,kind:"amber",options:[75,60,90],equipment:"Rail crane",priority:"Normal"},
{id:"MR-062",title:"Bundled station work",sector:"Paya Lebar",team:"Team Hotel",start:120,duration:45,row:6,kind:"cyan",options:[120,120,120],equipment:"Inspection kit",priority:"Normal"},
{id:"MR-063",title:"Track inspection",sector:"Woodlands",team:"Team India",start:175,duration:30,row:6,kind:"cyan",options:[175,175,175],equipment:"Inspection kit",priority:"Normal"},
{id:"MR-064",title:"Isolation review",sector:"Marina Bay",team:"Power team",start:10,duration:45,row:6,kind:"violet",options:[10,10,10],equipment:"Isolation panel",priority:"Normal"}
];
export const conflicts=[
{title:"Overlapping possession",rule:"POS-001",jobs:["MR-018","MR-024"],lens:"Possession",reason:"Signal inspection and rail renewal request exclusive use of the Bishan–Braddell sector for an overlapping 30-minute period."},
{title:"Isolation dependency",rule:"ISO-004",jobs:["MR-054","MR-050"],lens:"Isolation",reason:"The geometry run is requested before the synthetic P4 isolation window ends. The vehicle run needs the power state restored."},
{title:"Engineer double-booking",rule:"RES-002",jobs:["MR-018","MR-042"],lens:"Manpower",reason:"Team Alpha is assigned to signal inspection and platform inspection between 01:15 and 01:45."},
{title:"Shared inspection vehicle",rule:"EQP-003",jobs:["MR-050","MR-052"],lens:"Equipment",reason:"Geometry inspection and vehicle transfer need the same inspection vehicle between 02:45 and 03:05."},
{title:"Handback sequence review",rule:"DEP-005",jobs:["MR-024","MR-048"],lens:"Dependencies",reason:"The handback package must follow track renewal and its testing buffer. This seeded review warning illustrates dependency tracing, not a calculated conflict."}];
export const plans=[{name:"Minimum disruption",description:"Preserve the critical work. Move only what needs to change.",possessions:4},{name:"Closest requested timing",description:"Stay close to each team’s original engineering window.",possessions:5},{name:"Resource efficiency",description:"Group compatible work and coordinate shared equipment.",possessions:3}];
