"""Load the current Bike Link API inside WIZ's long-lived Python worker.

WIZ can retain modules imported by an older course component after a source
build. Reload this app's dependency chain once per source revision, under a
lock, rather than serving a mix of old and new analysis functions.
"""
import importlib
from pathlib import Path
import threading

_ROOT = Path(__file__).resolve().parents[2]
_MODULES = (
    "backend.services.result_cache",
    "backend.analysis.clustering", "backend.analysis.network", "backend.analysis.similarity",
    "backend.models.schemas", "backend.models.normalized",
    "backend.services.real_data", "backend.analysis.transit", "backend.services.transit", "backend.services.vulnerability", "backend.services.periods", "backend.services.all_regions", "backend.services.data", "backend.services.imports",
    "backend.agents.solar_checks", "backend.agents.solar_audit", "backend.agents.solar", "backend.main",
)
_lock = threading.Lock()
_revision = None
_app = None


def get_app():
    global _revision, _app
    revision = tuple((_ROOT / (name.replace(".", "/") + ".py")).stat().st_mtime_ns
                     for name in _MODULES)
    with _lock:
        if revision != _revision:
            for name in _MODULES:
                module = importlib.import_module(name)
                importlib.reload(module)
            _app = importlib.import_module("backend.main").app
            _revision = revision
        return _app
