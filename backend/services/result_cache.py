"""Revision-keyed, cross-worker cache for read-only analysis results."""
import copy
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import threading
import fcntl

_ROOT = Path(__file__).resolve().parents[2]
_memory = {}
_dataset_versions = {}
_guard = threading.RLock()

def revision(processed=None):
    processed = Path(processed or _ROOT / "data/processed")
    paths = list(processed.glob("*.csv")) + list(processed.glob("*.json"))
    paths += list(processed.glob("analysis.sqlite*"))
    paths += list((processed / "uploads").glob("*"))
    paths += list((_ROOT / "backend/analysis").glob("*.py"))
    paths += [_ROOT / "backend/services/real_data.py", Path(__file__)]
    return tuple((str(p.resolve()), p.stat().st_mtime_ns, p.stat().st_size)
                 for p in sorted(paths) if p.is_file())

def data_cached(fn):
    signature = inspect.signature(fn)
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        processed = Path(fn.__globals__.get('PROCESSED', _ROOT / 'data/processed'))
        version = revision(processed)
        with _guard:
            dataset = str(processed.resolve())
            if _dataset_versions.get(dataset) != version:
                snapshot = fn.__globals__.get("snapshot")
                if snapshot is not None and hasattr(snapshot, "cache_clear"):
                    snapshot.cache_clear()
                _dataset_versions[dataset] = version
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        key = hashlib.sha256(json.dumps([str(processed.resolve()), fn.__module__, fn.__qualname__, bound.arguments, version],
                                       sort_keys=True, default=str).encode()).hexdigest()
        with _guard:
            if key in _memory:
                return copy.deepcopy(_memory[key])
        folder = processed / ".analysis-cache"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (key + ".json")
        with (folder / (key + ".lock")).open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                with path.open(encoding="utf-8") as stream:
                    result = json.load(stream)
            except (FileNotFoundError, ValueError):
                result = fn(*args, **kwargs)
                temporary = path.with_suffix("." + str(os.getpid()) + ".tmp")
                try:
                    with temporary.open("w", encoding="utf-8") as stream:
                        json.dump(result, stream, ensure_ascii=False, allow_nan=False)
                    os.replace(temporary, path)
                finally:
                    if temporary.exists(): temporary.unlink()
            with _guard:
                if len(_memory) >= 48: _memory.pop(next(iter(_memory)))
                _memory[key] = result
            return copy.deepcopy(result)
    def cache_clear():
        # Clearing is intentionally in-memory only; persisted entries are revision keyed.
        with _guard: _memory.clear()
    wrapped.cache_clear = cache_clear
    return wrapped
