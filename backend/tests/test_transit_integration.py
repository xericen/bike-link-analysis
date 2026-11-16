import io,zipfile,csv
from datetime import datetime
from scripts.preprocess.integrate_transit_uploads import normalize_uploads,within_box
from scripts.preprocess.normalize_sejong_details import normalize_member
from backend.analysis.transit import match_stations
def test_source_city_mapping_and_latest_rail_identity():
 bus=[{"도시명":label,"정류장번호":str(i),"정류장명":"정류장","위도":lat,"경도":lon} for i,(label,lat,lon) in enumerate([("서울특별시",37.5,127),("대전광역시",36.35,127.38),("세종특별자치시",36.5,127.27)])]
 base={"역사도로명주소":"서울특별시 동작구","운영기관명":"공사","노선번호":"7","역번호":"0736","역사명":"옛이름","역위도":37.5,"역경도":127,"데이터기준일자":"2024-12-31"}
 rows,stats,warnings=normalize_uploads(bus,[base,{**base,"역사명":"최신이름","데이터기준일자":datetime(2025,12,31)}])
 assert stats["bus"]=={"seoul":1,"daejeon":1,"sejong":1}
 assert stats["rail_before"]["seoul"]==2 and stats["rail_after"]["seoul"]==1
 assert rows[-1]["name"]=="최신이름"
 assert len({(x["city"],x["type"],x["stop_id"]) for x in rows})==4
 assert not within_box("seoul",36.5,127)
def test_counts_and_missing_station_coordinate_remain_null():
 rows=match_stations([{"station_id":"S","latitude":37.5,"longitude":127},{"station_id":"U","latitude":None,"longitude":None}],
 [{"stop_id":"B","name":"B","type":"버스","lat":37.5,"lon":127},{"stop_id":"R","name":"R","type":"지하철","lat":37.5,"lon":127}])
 assert rows[0]["stops_within_300m"]==2 and rows[0]["bus_within_500m"]==1
 assert rows[1]["stops_within_300m"] is None
def test_sejong_source_ids_and_period_not_guessed(tmp_path):
 source=tmp_path/"source.zip";buf=io.StringIO()
 writer=csv.DictWriter(buf,fieldnames=["순번","시작 대여소","대여시간","반납 대여소","반납시간","주행시간"]);writer.writeheader()
 for n,day,a,b in [("1","2025-10-01","SJ_001","SJ-001"),("2","2025-11-01","SJ_001","SJ_002")]:
  writer.writerow({"순번":n,"시작 대여소":a,"대여시간":day+" 08:00:00","반납 대여소":b,"반납시간":day+" 08:10:00","주행시간":"10"})
 with zipfile.ZipFile(source,"w") as z:z.writestr("source.csv",buf.getvalue().encode("cp949"))
 with zipfile.ZipFile(source) as z:rows,stats,enc=normalize_member(z,"source.csv","2025-10-01","2025-10-31")
 assert len(rows)==1 and rows[0][1:3]==("SJ_001","SJ-001")
 assert stats["selected_raw_rows"]==1
