"""Cache correctness: data revisions, isolated readers and concurrent requests."""
import time
from concurrent.futures import ThreadPoolExecutor
from backend.services.result_cache import data_cached

def test_revision_disk_reuse_and_copy(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "PROCESSED", tmp_path)
    source = tmp_path / "input.csv"
    source.write_text("first")
    calls = []
    @data_cached
    def compute():
        calls.append(1)
        return {"value": source.read_text(), "items": [1]}
    first = compute()
    first["items"].append(2)
    assert compute()["items"] == [1]
    compute.cache_clear()
    assert compute()["value"] == "first"
    assert len(calls) == 1
    source.write_text("changed source")
    assert compute()["value"] == "changed source"
    assert len(calls) == 2

def test_concurrent_computation_once(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "PROCESSED", tmp_path)
    calls = []
    @data_cached
    def compute():
        calls.append(1)
        time.sleep(.03)
        return {"answer": 7}
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: compute(), range(4)))
    assert values == [{"answer": 7}] * 4
    assert len(calls) == 1

def test_failure_not_cached(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "PROCESSED", tmp_path)
    calls = []
    @data_cached
    def compute():
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("temporary failure")
        return {"available": False}
    try:
        compute()
    except ValueError:
        pass
    assert compute() == {"available": False}
    assert len(calls) == 2

def test_default_and_explicit_arguments_share_entry(tmp_path, monkeypatch):
    monkeypatch.setitem(globals(), "PROCESSED", tmp_path)
    calls = []
    @data_cached
    def compute(region, start=None):
        calls.append(1)
        return {"region": region}
    assert compute("seoul") == compute(region="seoul", start=None)
    assert len(calls) == 1
