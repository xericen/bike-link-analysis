import csv
import math
import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.analysis.transit import match_stations, hourly_linkage, EARTH_M
from backend.services import real_data
from scripts.preprocess.normalize_transit import normalize, write_new_csv
from scripts.collect.collect_transit_stops import store
from backend.tests.test_api import fixture_data

def test_haversine_and_missing_type():
    stations=[{"station_id":"A","latitude":37.5,"longitude":127},
              {"station_id":"B","latitude":None,"longitude":None}]
    # Same meridian; exactly 250m north, no longitude approximation.
    stops=[{"stop_id":"S","type":"지하철","lat":37.5 + math.degrees(250/EARTH_M),"lon":127}]
    result=match_stations(stations,stops)
    assert result[0]["nearest_stop_distance_m"] == pytest.approx(250,abs=.001)
    assert result[0]["subway_within_300m"] == 1
    assert result[0]["bus_within_500m"] is None
    assert result[1]["nearest_stop_distance_m"] is None

def test_hourly_or_rule_and_unknown_endpoints():
    rows=[{"date":"2026-10-01","hour":8,"origin_station_id":"A","destination_station_id":"B","trip_count":3},
          {"date":"2026-10-01","hour":8,"origin_station_id":"X","destination_station_id":"C","trip_count":2}]
    result=hourly_linkage(rows,{"A","B"},{"A","B","C"})
    assert result == [{"date":"2026-10-01","hour":8,"total_count":5,"linked_count":3,"unknown_endpoint_count":2}]

def test_normalization_excludes_ferries_and_conflicts():
    base={"NODE_ID":"001","정류소명":"버스","X좌표":127,"Y좌표":37.5}
    result, stats=normalize([base,base,{**base,"NODE_ID":"002","X좌표":0},
        {**base,"정류소타입":"한강선착장"}],"seoul","버스")
    assert result[0]["stop_id"]=="001"
    assert stats == {"raw":4,"invalid":1,"excluded_non_bus":1,"duplicates":1,"valid":1}
    with pytest.raises(ValueError):
        normalize([base,{**base,"Y좌표":37.6}],"seoul","버스")

def test_original_artifacts_cannot_be_overwritten(tmp_path):
    path=tmp_path/"stops.csv"
    write_new_csv(path,[{"id":"01"}],["id"])
    write_new_csv(path,[{"id":"01"}],["id"])
    with pytest.raises(ValueError):
        write_new_csv(path,[{"id":"02"}],["id"])
    raw=tmp_path/"raw.csv"
    store(b"real",raw,{"method":"fixture"})
    with pytest.raises(ValueError):
        store(b"other",raw,{"method":"fixture"})

def test_transit_api_period_and_missing_data(fixture_data):
    path=real_data.PROCESSED/"transit_stops.csv"
    write_new_csv(path,[{"city":"seoul","stop_id":"S","name":"역","type":"지하철","lat":37.5,"lon":127}],
                  ["city","stop_id","name","type","lat","lon"])
    write_new_csv(real_data.PROCESSED/"transit_hourly_seoul_verified.csv",
                  [{"date":"2026-10-25","hour":8,"total_count":10,"linked_count":4,"unknown_endpoint_count":0},
                   {"date":"2026-10-29","hour":8,"total_count":20,"linked_count":6,"unknown_endpoint_count":2}],
                  ["date","hour","total_count","linked_count","unknown_endpoint_count"])
    client=TestClient(app)
    result=client.get("/api/transit-linkage?city=seoul&date_start=2026-10-29").json()
    assert result["hourly_station_linkage"][0]["linkage_share"] == .3
    assert client.get("/api/transit-linkage?city=sejong").json()["available"] is False
    assert client.get("/api/transit-linkage?city=unknown").status_code == 404
    assert client.get("/api/transit-linkage?date_start=2026-10-29&date_end=2026-10-01").status_code==400

def test_five_minute_bins_are_not_hour_duplicates(tmp_path, monkeypatch):
    import zipfile, io
    from scripts.preprocess.build_transit_linkage import build_seoul_hourly
    from backend.services import transit
    monkeypatch.setattr(transit, "linkage", lambda city: {"stations":[
        {"station_id":"A","coordinate_valid":True,"subway_within_300m":1},
        {"station_id":"B","coordinate_valid":True,"subway_within_300m":1}]})
    fields=["기준_날짜","집계_기준","기준_시간대","시작_대여소_ID","종료_대여소_ID","전체_건수"]
    buf=io.StringIO()
    writer=csv.DictWriter(buf,fieldnames=fields);writer.writeheader()
    for slot,n in [("0800",3),("0805",4),("0800",3)]:
        writer.writerow(dict(zip(fields,["20261001","출발시간",slot,"A","B",n])))
    source=tmp_path/"od.zip"
    with zipfile.ZipFile(source,"w") as z:
        z.writestr("actual-shaped-fixture.csv",buf.getvalue().encode("cp949"))
    result=build_seoul_hourly(source,tmp_path/"hourly.csv")
    assert result["trip_count"] == 7
    assert result["linked_count"] == 7
    assert result["duplicate_rows"] == 1
