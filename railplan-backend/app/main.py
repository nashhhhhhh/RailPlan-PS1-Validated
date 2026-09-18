"""RailPlan API composition. Routers preserve the existing /api namespace."""
import os
from uuid import uuid4
from fastapi import FastAPI,HTTPException,Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from app.database import engine
from app.contracts import ErrorResponse
from app.routers import requests,scenarios,network,operations,scoring,ps1,ps1_validations,ps1_optimisation

app=FastAPI(title="RailPlan data API",version="0.4.0",
    description="Persistent APIs with prototype conflict analysis and internal PS1 validation/optimisation. No operational approval, copilot or publication.",
    responses={status:{"model":ErrorResponse} for status in (401,403,404,409,413,422,500,501,503)})
origins=[x.strip() for x in os.getenv("RAILPLAN_CORS_ORIGINS","http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173").split(",") if x.strip()]
if "*" in origins:raise RuntimeError("Configure explicit CORS origins")
app.add_middleware(CORSMiddleware,allow_origins=origins,allow_credentials=False,
    allow_methods=["GET","POST","PATCH","OPTIONS"],allow_headers=["Content-Type","Authorization","X-Demo-User-Id"],
    expose_headers=["X-Correlation-Id"])

@app.middleware("http")
async def correlation(request,call_next):
    request.state.correlation_id=str(uuid4())
    if request.method=='POST' and request.url.path.startswith('/api/ps1/'):
        # Bound the wire body before JSON/Pydantic allocation, including chunked requests.
        chunks=[]
        size=0
        async for chunk in request.stream():
            size+=len(chunk)
            if size>10_000_000:
                return error(request,413,'PS1 request exceeds 10 MB wire limit',code='PAYLOAD_TOO_LARGE')
            chunks.append(chunk)
        request._body=b''.join(chunks)
    response=await call_next(request)
    response.headers["X-Correlation-Id"]=request.state.correlation_id
    return response

def error(request,status,message,code=None,fields=None):
    guidance="Reload the resource before retrying" if status==409 else (
      "Configure the missing service; no work was accepted" if status in (501,503) else None)
    return JSONResponse(status_code=status,content={"error":{
      "code":code or {401:"UNAUTHENTICATED",403:"FORBIDDEN",404:"NOT_FOUND",405:"METHOD_NOT_ALLOWED",409:"STATE_CONFLICT",
        422:"INVALID_INPUT",501:"NOT_IMPLEMENTED",503:"SERVICE_UNAVAILABLE"}.get(status,"INTERNAL_ERROR"),
      "message":message,"fields":fields or [],"correlation_id":getattr(request.state,"correlation_id","unknown"),
      "guidance":guidance}})

@app.exception_handler(StarletteHTTPException)
async def http_error(request,exc):
    response=error(request,exc.status_code,str(exc.detail))
    if exc.headers:
        response.headers.update(exc.headers)
    return response

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    return error(request,422,"Invalid request fields",fields=[
       {"location":list(e["loc"]),"message":e["msg"],"type":e["type"]} for e in exc.errors()])

@app.exception_handler(DBAPIError)
async def database_error(request,exc):
    code=getattr(exc.orig,"sqlstate","") or ""
    if code.startswith("23") or code in ("P0001","40001","40P01"):
        return error(request,409,"Database consistency checks rejected the change")
    if code.startswith("08") or exc.connection_invalidated:
        return error(request,503,"Database connection unavailable")
    return error(request,500,"Database operation failed")

@app.exception_handler(Exception)
async def unhandled(request,exc):
    return error(request,500,"Unexpected server error; use the correlation ID when reporting it")

@app.get("/health")
@app.get("/health/live")
def health():
    return {"status":"ok","scope":"data-api","conflict_engine_available":True,"validator_available":True,
        "solver_available":True,"scenario_a_solver_available":True,"scenario_b_solver_available":True,"scenario_c_solver_available":True,
        "database_readiness":"see /health/ready","operational_approval_available":False}

@app.get("/health/ready")
def readiness():
    try:
        with engine().connect() as db:
            db.execute(text("SELECT 1"))
            revision=db.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            if revision!="0009":raise HTTPException(503,"Database migration required")
    except HTTPException:raise
    except Exception:raise HTTPException(503,"Database is not ready")
    return {"status":"ready","database_ready":True,"migration":revision,"validator_available":True,
        "scenario_a_solver_available":True,"scenario_b_solver_available":True,"scenario_c_solver_available":True}

app.include_router(requests.router)
app.include_router(scenarios.router)
app.include_router(network.router)
app.include_router(operations.router)
app.include_router(scoring.router)
app.include_router(ps1.router)
app.include_router(ps1_validations.router)
app.include_router(ps1_optimisation.router)

# Keep the original public solver-options type available to generated-client consumers
# even though the HTTP endpoint now accepts its additive persistence subclass.
_base_openapi=app.openapi
def openapi_with_pure_solver_contract():
    from app.ps1_optimisation.contracts import OptimiseInput
    schema=_base_openapi()
    pure=OptimiseInput.model_json_schema(ref_template='#/components/schemas/{model}')
    for name,definition in pure.pop('$defs',{}).items():
        schema['components']['schemas'].setdefault(name,definition)
    schema['components']['schemas'].setdefault('OptimiseInput',pure)
    return schema
app.openapi=openapi_with_pure_solver_contract
