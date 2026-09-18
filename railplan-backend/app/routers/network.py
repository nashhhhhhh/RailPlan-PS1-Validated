from uuid import UUID
from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Query,HTTPException
from pydantic import AwareDatetime
from sqlalchemy import text
from app.dependencies import DB,Actor,Limit,Offset
from app.contracts import Page,Entity,Named,Availability,GeoFeature
from app import repository as repo,services

router=APIRouter(prefix="/api",tags=["Network and resources"])

def bbox_values(bbox):
    if bbox is None:return None
    try:values=[float(x) for x in bbox.split(",")]
    except ValueError:raise HTTPException(422,"bbox must be west,south,east,north")
    if len(values)!=4 or not(-180<=values[0]<values[2]<=180 and -90<=values[1]<values[3]<=90):
        raise HTTPException(422,"Invalid bounding box; crossing the antimeridian is not supported")
    return values

@router.get("/network/lines",response_model=Page[Named])
def lines(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0):
    return repo.page(db,"""SELECT l.* FROM railplan.lines l JOIN railplan.networks n ON n.id=l.network_id
      WHERE n.operator_id=:operator ORDER BY l.code,l.id""",{"operator":actor["operator_id"]},limit,offset)

def spatial(db,actor,kind,limit,offset,line_id=None,bbox=None,window_id=None):
    # All identifiers below are internal whitelisted constants.
    table={"stations":"stations","sectors":"track_sectors","workzones":"workzones"}[kind]
    join="JOIN railplan.networks n ON n.id=x.network_id" if kind!="sectors" else "JOIN railplan.lines l ON l.id=x.line_id JOIN railplan.networks n ON n.id=l.network_id"
    clauses=["n.operator_id=:operator"];params={"operator":actor["operator_id"]}
    if window_id:
        w=repo.window(db,window_id,actor)
        if line_id and line_id!=w["line_id"]:raise HTTPException(422,"Window and line disagree")
        line_id=w["line_id"]
    if line_id:
        params["line"]=line_id
        clauses.append({"stations":"EXISTS(SELECT 1 FROM railplan.line_stations ls WHERE ls.station_id=x.id AND ls.line_id=:line)",
        "sectors":"x.line_id=:line",
        "workzones":"EXISTS(SELECT 1 FROM railplan.workzone_sectors ws JOIN railplan.track_sectors s ON s.id=ws.sector_id WHERE ws.workzone_id=x.id AND s.line_id=:line)"}[kind])
    values=bbox_values(bbox)
    if values:
        clauses.append("x.geom && ST_MakeEnvelope(:west,:south,:east,:north,4326)")
        params.update(zip(("west","south","east","north"),values))
    selected=f"""SELECT x.id,x.name,x.geometry_source,ST_AsGeoJSON(x.geom)::jsonb AS geometry,
       x.geom IS NOT NULL AS geometry_available,'Feature'::text AS type,
       jsonb_build_object('id',x.id,'name',x.name,'source',x.geometry_source) AS properties"""
    return repo.page(db,selected+f" FROM railplan.{table} x "+join+" WHERE "+" AND ".join(clauses)+" ORDER BY x.name,x.id",params,limit,offset)

@router.get("/network/stations",response_model=Page[GeoFeature])
def stations(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,line_id:UUID|None=None,
             bbox:str|None=Query(None,max_length=160),window_id:UUID|None=None):
    return spatial(db,actor,"stations",limit,offset,line_id,bbox,window_id)

@router.get("/network/sectors",response_model=Page[GeoFeature])
def sectors(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,line_id:UUID|None=None,
            bbox:str|None=Query(None,max_length=160),window_id:UUID|None=None):
    return spatial(db,actor,"sectors",limit,offset,line_id,bbox,window_id)

@router.get("/workzones",response_model=Page[GeoFeature])
def zones(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,line_id:UUID|None=None,
          bbox:str|None=Query(None,max_length=160),window_id:UUID|None=None):
    return spatial(db,actor,"workzones",limit,offset,line_id,bbox,window_id)

@router.get("/workzones/{workzone_id}",response_model=GeoFeature)
def zone(workzone_id:UUID,db:DB,actor:Actor):
    value=services.one(db,"""SELECT x.id,x.name,x.code,x.geometry_source,ST_AsGeoJSON(x.geom)::jsonb AS geometry,
      x.geom IS NOT NULL AS geometry_available,'Feature' AS type,
      jsonb_build_object('id',x.id,'name',x.name,'source',x.geometry_source) AS properties
      FROM railplan.workzones x JOIN railplan.networks n ON n.id=x.network_id WHERE x.id=:id AND n.operator_id=:op""",
      id=workzone_id,op=actor["operator_id"])
    if not value:raise HTTPException(404,"Workzone not found")
    return dict(value)

def resource_page(db,actor,kind,limit,offset,search=None):
    table={"teams":"teams","engineers":"engineers","equipment":"equipment_assets"}[kind]
    return repo.page(db,f"""SELECT x.* FROM railplan.{table} x JOIN railplan.departments d ON d.id=x.department_id
      WHERE d.operator_id=:op AND (CAST(:search AS text) IS NULL OR x.name ILIKE :search)
      ORDER BY x.name,x.id""",{"op":actor["operator_id"],"search":"%"+search+"%" if search else None},limit,offset)

@router.get("/teams",response_model=Page[Named])
def teams(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,search:str|None=Query(None,max_length=200)):
    return resource_page(db,actor,"teams",limit,offset,search)

@router.get("/engineers",response_model=Page[Named])
def engineers(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,search:str|None=Query(None,max_length=200)):
    return resource_page(db,actor,"engineers",limit,offset,search)

@router.get("/equipment",response_model=Page[Named])
def equipment(db:DB,actor:Actor,limit:Limit=50,offset:Offset=0,search:str|None=Query(None,max_length=200)):
    return resource_page(db,actor,"equipment",limit,offset,search)

@router.get("/resources/availability",response_model=Page[Availability])
def availability(db:DB,actor:Actor,resource_type:Literal["engineer","team","equipment"],
                 starts_at:AwareDatetime,ends_at:AwareDatetime,limit:Limit=50,offset:Offset=0,
                 skill_ids:list[UUID]=Query(default=[],max_length=50)):
    if not starts_at<ends_at or ends_at-starts_at>timedelta(days=31):raise HTTPException(422,"Use a positive interval no longer than 31 days")
    if skill_ids and resource_type!="engineer":raise HTTPException(422,"Skill filtering applies to individual engineers")
    services.require_ids(db,"skills",skill_ids)
    target,calendar,key={"engineer":("engineers","engineer_availability","engineer_id"),
      "team":("teams","team_availability","team_id"),"equipment":("equipment_assets","equipment_availability","asset_id")}[resource_type]
    active="x.active" if resource_type!="team" else "true"
    qualified="""NOT EXISTS(SELECT 1 FROM unnest(CAST(:skills AS uuid[])) skill WHERE NOT EXISTS(
      SELECT 1 FROM railplan.engineer_skills es WHERE es.engineer_id=x.id AND es.skill_id=skill
      AND es.period @> tstzrange(:start,:end,'[)')))""" if resource_type=="engineer" else "NULL::boolean"
    query=f"""SELECT x.id AS resource_id,:kind AS resource_type,
      CASE WHEN NOT({active}) OR EXISTS(SELECT 1 FROM railplan.{calendar} a WHERE a.{key}=x.id
         AND NOT a.available AND a.period && tstzrange(:start,:end,'[)')) THEN 'unavailable'
        WHEN (SELECT range_agg(a.period) FROM railplan.{calendar} a WHERE a.{key}=x.id AND a.available)
         @> tstzrange(:start,:end,'[)') THEN 'available' ELSE 'unknown' END AS availability,
      {qualified} AS qualified,true AS candidate_only,false AS complete_allocation_validation_performed
      FROM railplan.{target} x JOIN railplan.departments d ON d.id=x.department_id
      WHERE d.operator_id=:op ORDER BY x.name,x.id"""
    return repo.page(db,query,{"op":actor["operator_id"],"start":starts_at,"end":ends_at,"kind":resource_type,"skills":skill_ids},limit,offset)
