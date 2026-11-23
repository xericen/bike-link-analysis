"""Reload pure completion checks when their source changes, under a stable lock."""
import importlib,threading
from pathlib import Path
_lock=threading.RLock();_stamp=None
def checks():
    global _stamp
    with _lock:
        module=importlib.import_module("backend.agents.completion_checks")
        p=Path(module.__file__);stamp=(p.stat().st_mtime_ns,p.stat().st_size)
        if stamp!=_stamp:module=importlib.reload(module);_stamp=stamp
        return module
