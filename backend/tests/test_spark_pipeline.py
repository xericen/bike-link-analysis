"""Optional only when Spark/JRE are absent; fixture data never enters real results."""
import csv
import importlib.util
import shutil
from pathlib import Path
import pytest

@pytest.mark.skipif(importlib.util.find_spec("pyspark") is None or shutil.which("java") is None,reason="optional PySpark/JRE not installed")
def test_spark_matches_fixture_daily_and_return_date(tmp_path):
    from scripts.preprocess.spark_tashu import run
    source=Path(__file__).parent/"fixtures/spark_trips.csv"
    result=run(tmp_path/"spark",[str(source.resolve())],master="local[2]")
    assert result["valid_rows"]==4
    def rows(name):
        return [r for p in (tmp_path/"spark"/name).glob("part-*.csv") for r in csv.DictReader(p.open())]
    daily=rows("od_daily")
    assert sum(int(x["trip_count"]) for x in daily)==4
    assert next(x for x in daily if x["date"]=="2026-01-01" and x["origin_station_id"]=="A")["trip_count"]=="2"
    assert any(x["date"]=="2026-01-02" and x["hour"]=="0" and x["station_id"]=="A" and x["return_count"]=="1" for x in rows("station_usage"))
    with pytest.raises(ValueError): run(tmp_path/"spark",[str(source.resolve())],master="local[2]")
