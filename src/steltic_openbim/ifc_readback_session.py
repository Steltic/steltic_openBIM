"""Reuse a read-only parsed STEP inside one delivery check, never across deliveries."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

import ifcopenshell


_current = ContextVar('steltic_readback_step', default=None)


@contextmanager
def readback_session(path):
    state = {'path': Path(path).resolve(), 'model': None}
    token = _current.set(state)
    try:
        yield
    finally:
        _current.reset(token)
        state['model'] = None


def read_step(path):
    path = Path(path).resolve()
    state = _current.get()
    if state is None or state['path'] != path:
        return ifcopenshell.open(str(path))
    if state['model'] is None:
        state['model'] = ifcopenshell.open(str(path))
    return state['model']
