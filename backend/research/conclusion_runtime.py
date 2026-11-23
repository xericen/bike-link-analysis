"""Reload only the conclusion reader under a stable worker-local lock."""
import importlib,threading
from pathlib import Path
_lock=threading.RLock()
_stamp=None
def presentation():
    global _stamp
    with _lock:
        module=importlib.import_module("backend.research.conclusion")
        path=Path(module.__file__);stamp=(path.stat().st_mtime_ns,path.stat().st_size)
        if _stamp!=stamp:
            module=importlib.reload(module);_stamp=stamp
        return module
