"""Source-aware report reader for web workers; never restarts a service."""
import importlib,threading
from pathlib import Path
_lock=threading.RLock()
_stamp=None
def presentation():
    global _stamp
    with _lock:
        module=importlib.import_module("backend.research.advanced_presentation")
        p=Path(module.__file__);stamp=(p.stat().st_mtime_ns,p.stat().st_size)
        if _stamp!=stamp:
            module=importlib.reload(module);_stamp=stamp
        return module
