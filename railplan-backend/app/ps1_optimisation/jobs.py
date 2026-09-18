"""Small in-process executor for durable optimisation jobs.

PostgreSQL is the source of job status. The local executor is intentionally bounded;
production deployments should run one API replica or replace this adapter with a
durable queue while keeping the HTTP/database contract.
"""
from concurrent.futures import Future, ThreadPoolExecutor
import os
from threading import Event, Lock
from typing import Callable
from uuid import UUID

_workers=max(1,min(4,int(os.getenv('RAILPLAN_OPTIMISER_WORKERS','1'))))
_executor=ThreadPoolExecutor(max_workers=_workers,thread_name_prefix='railplan-optimiser')
_guard=Lock()
_cancellations:dict[UUID,Event]={}
_futures:dict[UUID,Future]={}

def launch(job_id:UUID,work:Callable[[Event],None]):
    with _guard:
        event=_cancellations.setdefault(job_id,Event())
        existing=_futures.get(job_id)
        if existing is not None and not existing.done():return
        future=_executor.submit(_run,job_id,event,work)
        _futures[job_id]=future

def _run(job_id:UUID,event:Event,work:Callable[[Event],None]):
    try:work(event)
    finally:
        with _guard:
            _futures.pop(job_id,None)
            _cancellations.pop(job_id,None)

def request_cancel(job_id:UUID):
    with _guard:
        event=_cancellations.get(job_id)
        if event is not None:event.set()

def active(job_id:UUID)->bool:
    with _guard:
        future=_futures.get(job_id)
        return bool(future is not None and not future.done())
