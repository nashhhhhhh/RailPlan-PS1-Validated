"""One-command local launcher for RailPlan.

Default mode starts the stateless FastAPI service and the frontend. Pass
``--persisted`` to start PostgreSQL/PostGIS through Docker Compose, apply all
migrations, and enable saved instances, validations and optimisation jobs.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import quote_plus
import webbrowser

ROOT=Path(__file__).resolve().parent
BACKEND=ROOT/'railplan-backend'
DEFAULT_HOST='127.0.0.1'
DEFAULT_FRONTEND_PORT=5173
DEFAULT_BACKEND_PORT=8000

def command(name:str)->str|None:
    return shutil.which(name) or (shutil.which(f'{name}.cmd') if os.name=='nt' else None)

def run_checked(args:list[str],*,cwd:Path=ROOT,env:dict[str,str]|None=None)->None:
    print('\n> '+' '.join(args),flush=True)
    try:subprocess.run(args,cwd=cwd,env=env,check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f'Command failed with exit code {exc.returncode}: {" ".join(args)}') from exc

def frontend_dependencies(corepack:str,refresh:bool)->None:
    if refresh or not (ROOT/'node_modules'/'next').is_dir():
        print('Installing pinned frontend dependencies from pnpm-lock.yaml.',flush=True)
        run_checked([corepack,'pnpm','install','--frozen-lockfile'])

def backend_python(refresh:bool)->Path:
    scripts='Scripts' if os.name=='nt' else 'bin'
    executable='python.exe' if os.name=='nt' else 'python'
    target=BACKEND/'.venv'/scripts/executable
    if not target.exists():
        print('Creating the local backend virtual environment.',flush=True)
        run_checked([sys.executable,'-m','venv','.venv'],cwd=BACKEND)
    probe=subprocess.run([str(target),'-c','import fastapi,uvicorn,ortools,alembic'],cwd=BACKEND,
                         stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if refresh or probe.returncode:
        print('Installing the declared FastAPI backend dependencies.',flush=True)
        run_checked([str(target),'-m','pip','install','-e','.'],cwd=BACKEND)
    return target

def port_available(host:str,port:int)->bool:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as probe:
        try:probe.bind((host,port))
        except OSError:return False
    return True

def wait_http(url:str,process:subprocess.Popen,timeout:float=60)->bool:
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline and process.poll() is None:
        try:
            with urllib.request.urlopen(url,timeout=1) as response:
                if response.status<500:return True
        except (OSError,urllib.error.URLError):time.sleep(.25)
    return False

def open_when_ready(url:str,process:subprocess.Popen,should_open:bool)->None:
    if wait_http(url,process) and should_open:webbrowser.open(url)

def stop_process(process:subprocess.Popen)->None:
    if process.poll() is not None:return
    if os.name=='nt':
        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    else:
        process.terminate()
    try:process.wait(timeout=6)
    except subprocess.TimeoutExpired:
        process.kill();process.wait()

def start_postgres(environment:dict[str,str],backend_python_path:Path,seed:bool)->None:
    docker=command('docker')
    if not docker:raise SystemExit('--persisted requires Docker with the Compose plugin. Docker was not found.')
    password=environment.get('POSTGRES_PASSWORD')
    if not password:raise SystemExit('--persisted requires POSTGRES_PASSWORD in your shell environment. It is never written to source.')
    environment.setdefault('DATABASE_URL',f'postgresql+psycopg://railplan_owner:{quote_plus(password)}@127.0.0.1:5432/railplan')
    run_checked([docker,'compose','-f','compose.yaml','up','-d','db'],cwd=BACKEND,env=environment)
    print('Waiting for PostgreSQL/PostGIS readiness.',flush=True)
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        ready=subprocess.run([docker,'compose','-f','compose.yaml','exec','-T','db','pg_isready','-U','railplan_owner','-d','railplan'],
            cwd=BACKEND,env=environment,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if ready.returncode==0:break
        time.sleep(1)
    else:raise SystemExit('PostgreSQL did not become ready within 90 seconds.')
    run_checked([str(backend_python_path),'-m','alembic','upgrade','head'],cwd=BACKEND,env=environment)
    if seed:
        run_checked([str(backend_python_path),'-m','app.seed'],cwd=BACKEND,env=environment)
        run_checked([str(backend_python_path),'-m','app.seed_scoring'],cwd=BACKEND,env=environment)

def parse_args()->argparse.Namespace:
    parser=argparse.ArgumentParser(description='Start the RailPlan frontend and FastAPI service.')
    parser.add_argument('--host',default=DEFAULT_HOST)
    parser.add_argument('--port',type=int,default=DEFAULT_FRONTEND_PORT,help='Frontend port (default: 5173).')
    parser.add_argument('--backend-port',type=int,default=DEFAULT_BACKEND_PORT,help='FastAPI port (default: 8000).')
    parser.add_argument('--persisted',action='store_true',help='Start PostgreSQL/PostGIS and enable persisted mode.')
    parser.add_argument('--seed',action='store_true',help='Seed local demo records after migration (requires --persisted).')
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--install',action='store_true',help='Refresh both Python and pnpm dependencies first.')
    return parser.parse_args()

def main()->int:
    args=parse_args()
    if args.seed and not args.persisted:raise SystemExit('--seed requires --persisted')
    for name,value in (('--port',args.port),('--backend-port',args.backend_port)):
        if not 1<=value<=65535:raise SystemExit(f'{name} must be between 1 and 65535')
    if args.port==args.backend_port:raise SystemExit('Frontend and backend ports must differ')
    node,corepack=command('node'),command('corepack')
    if not node or not corepack:raise SystemExit('Node.js 22.13+ with Corepack is required.')
    version=subprocess.run([node,'--version'],capture_output=True,text=True,check=True).stdout.strip()
    try:node_version=tuple(int(part) for part in version.removeprefix('v').split('.')[:2])
    except ValueError:node_version=(0,0)
    if node_version<(22,13):raise SystemExit(f'Node.js 22.13 or newer is required; found {version}.')
    for port in (args.port,args.backend_port):
        if not port_available(args.host,port):raise SystemExit(f'Port {port} is already in use.')

    frontend_dependencies(corepack,args.install)
    python=backend_python(args.install)
    environment=os.environ.copy()
    environment.pop('NODE_ENV',None)
    environment['NEXT_TELEMETRY_DISABLED']='1'
    environment['RAILPLAN_ENV']='development'
    environment['RAILPLAN_CORS_ORIGINS']=f'http://{args.host}:{args.port}'
    if args.persisted:
        environment['RAILPLAN_DEMO_AUTH']='1';environment['RAILPLAN_REQUIRE_DATABASE']='1'
        start_postgres(environment,python,args.seed)
    else:
        environment.pop('DATABASE_URL',None);environment['RAILPLAN_REQUIRE_DATABASE']='0'
    backend_url=f'http://{args.host}:{args.backend_port}'
    frontend_url=f'http://{args.host}:{args.port}'
    environment['NEXT_PUBLIC_RAILPLAN_API_URL']=backend_url
    shutil.rmtree(ROOT/'.next'/'dev',ignore_errors=True)

    print(f'\nStarting RailPlan ({"persisted" if args.persisted else "stateless"} mode)',flush=True)
    print(f'Dashboard: {frontend_url}',flush=True)
    print(f'FastAPI:   {backend_url}  (docs: {backend_url}/docs)',flush=True)
    print('Press Ctrl+C to stop the application.\n',flush=True)
    backend=subprocess.Popen([str(python),'-m','uvicorn','app.main:app','--host',args.host,'--port',str(args.backend_port)],cwd=BACKEND,env=environment)
    next_cli=ROOT/'node_modules'/'next'/'dist'/'bin'/'next'
    frontend=subprocess.Popen([node,str(next_cli),'dev','--hostname',args.host,'--port',str(args.port)],cwd=ROOT,env=environment)
    opener=threading.Thread(target=open_when_ready,args=(frontend_url,frontend,not args.no_browser),daemon=True);opener.start()
    processes=[frontend,backend]
    try:
        while all(process.poll() is None for process in processes):time.sleep(.25)
        failed=next((process.returncode for process in processes if process.poll() is not None),1)
        return failed or 0
    except KeyboardInterrupt:
        print('\nStopping RailPlan...',flush=True);return 0
    finally:
        for process in processes:stop_process(process)

if __name__=='__main__':sys.exit(main())
