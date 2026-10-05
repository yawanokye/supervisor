"""Async-task-local durable provider state used by recovery and cancellation."""
from __future__ import annotations
from contextlib import contextmanager
from contextvars import ContextVar
import hashlib
import json

_state = ContextVar('provider_checkpoint_context', default=None)

@contextmanager
def provider_checkpoint_context(manager, key: str):
    token = _state.set((manager,key))
    try: yield
    finally: _state.reset(token)

def request_state(body: dict):
    state = _state.get()
    if not state: return None, '', ''
    manager, stage = state
    digest = hashlib.sha256(json.dumps(body,sort_keys=True,default=str).encode()).hexdigest()
    return manager, 'provider-inflight-'+hashlib.sha256((stage+digest).encode()).hexdigest()[:24], digest
