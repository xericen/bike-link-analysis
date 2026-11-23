"""Refresh research presentation in long-lived web workers without touching KPI inputs."""
import importlib
from pathlib import Path
import threading
_lock=threading.Lock()
def presentation():
    with _lock:
        module=importlib.import_module("backend.research.presentation")
        stamp=Path(module.__file__).stat().st_mtime_ns
        if getattr(module,"_source_stamp",None)!=stamp:
            module=importlib.reload(module)
            module._source_stamp=stamp
        return module
