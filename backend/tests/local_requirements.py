"""Explicit gates for integration checks requiring Git-excluded local data.

Pure unit tests and saved public result checks remain enabled in fresh clones.
These decorators do not weaken the application's stale-input validation.
"""
import json
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

def requires_local_files(*paths):
    missing = [path for path in paths if not (ROOT / path).is_file()]
    return pytest.mark.skipif(bool(missing), reason="Local dataset not published: " + ", ".join(missing))

def requires_local_inputs(report):
    path = ROOT / report
    unavailable = []
    if not path.is_file():
        unavailable.append(report)
    else:
        for relative, meta in json.loads(path.read_text()).get("inputs", {}).items():
            source = ROOT / relative
            if not source.is_file() or (source.stat().st_size, source.stat().st_mtime_ns) != (meta["size"], meta["mtime_ns"]):
                unavailable.append(relative)
    return pytest.mark.skipif(bool(unavailable), reason="Prepared local inputs must be rebuilt: " + ", ".join(unavailable))
