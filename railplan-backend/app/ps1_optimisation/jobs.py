"""Bounded process-local execution for database-backed optimisation jobs.

PostgreSQL, rather than this registry, is the durable source of lifecycle evidence.
The registry only supports cooperative cancellation and lets the API distinguish work
owned by this process from work abandoned by a previous process. It is deliberately
not presented as a durable queue and is safe only for a single API replica.
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
_futures:dict[UUID,Future|None]={}

def reserve(job_id:UUID)->None:
    """Protect the commit-to-launch window from abandoned-job recovery."""
    with _guard:
        _cancellations.setdefault(job_id,Event())
        _futures.setdefault(job_id,None)

def release(job_id:UUID)->None:
    with _guard:
        _futures.pop(job_id,None)
        _cancellations.pop(job_id,None)

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
        future=_futures.get(job_id)
        if future is not None and future.cancel():
            _futures.pop(job_id,None)
            _cancellations.pop(job_id,None)

def active(job_id:UUID)->bool:
    with _guard:
        if job_id not in _futures:return False
        future=_futures[job_id]
        return future is None or not future.done()
