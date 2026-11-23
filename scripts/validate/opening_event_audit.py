"""Read-only opening-date alignment and matched pre/post descriptive evidence; not causal installation effects."""
import json,sqlite3,hashlib
from pathlib import Path
import numpy as np,pandas as pd
from sklearn.neighbors import BallTree
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/visibility-20261123"
EARTH=6371000
def run():
    OUT.mkdir(parents=True,exist_ok=True)
    raw=ROOT/"data/raw/seoul-stations-202606.xlsx"
    official=pd.read_excel(raw,header=None).iloc[5:].copy()
    master=pd.read_csv(ROOT/"data/individual/seoul/stations.csv")
    located=master.dropna(subset=["latitude","longitude"]).reset_index(drop=True)
    tree=BallTree(np.radians(located[["latitude","longitude"]].to_numpy(float)),metric="haversine")
    mapped={};unmatched=[];all_new=0
    for _,row in official.iterrows():
        date=pd.to_datetime(row[6],errors="coerce")
        is_new=not pd.isna(date) and date.year==2025
        all_new+=int(is_new)
        try:point=np.array([[float(row[4]),float(row[5])]])
        except (ValueError,TypeError):continue
        if not np.isfinite(point).all():continue
        ix=tree.query_radius(np.radians(point),r=5/EARTH)[0]
        matches=[int(j) for j in ix if "".join(str(located.iloc[int(j)].station_name).split())=="".join(str(row[1]).split())]
        if len(matches)!=1:
            if is_new:unmatched.append({"official_number":str(row[0]),"station_name":str(row[1]),"installed_at":date.strftime("%Y-%m-%d"),"reason":"이름·좌표5m·유일 매칭 조건을 충족하지 못함"})
            continue
        sid=str(located.iloc[matches[0]].station_id)
        mapped[sid]={"station_id":sid,"station_name":str(row[1]).strip(),"district":str(row[2]),"latitude":float(row[4]),"longitude":float(row[5]),"installed_at":date.strftime("%Y-%m-%d") if not pd.isna(date) else None,"official_number":str(row[0])}
    db=ROOT/"data/individual/seoul/analysis.sqlite"
    with sqlite3.connect(db.resolve().as_uri()+"?mode=ro",uri=True) as conn:
        frame=pd.read_sql_query("SELECT station_id,date,SUM(rental_count) rentals FROM station_usage WHERE region_id='seoul' GROUP BY station_id,date",conn)
    frame["date"]=pd.to_datetime(frame.date);pivot=frame.pivot(index="date",columns="station_id",values="rentals").fillna(0)
    assert len(pivot)==365
    first=frame[frame.rentals>0].groupby("station_id").date.min()
    last=frame[frame.rentals>0].groupby("station_id").date.max()
    # Same 1km neighborhood, fixed current coordinates, no population inference.
    near={}
    for sid,row in mapped.items():
        ix=tree.query_radius(np.radians([[row["latitude"],row["longitude"]]]),r=1000/EARTH)[0]
        near[sid]=[str(located.iloc[int(j)].station_id) for j in ix if str(located.iloc[int(j)].station_id) in pivot.columns]
    def window(series,start,end):
        values=series.loc[start:end]
        return float(values.mean()),int((values>0).sum())
    def series(sid):return pivot[near[sid]].sum(axis=1)
    candidates=[r for r in mapped.values() if r["installed_at"] and r["installed_at"].startswith("2025")]
    results=[];excluded=[]
    for row in sorted(candidates,key=lambda r:(r["installed_at"],r["station_id"])):
        sid=row["station_id"];date=pd.Timestamp(row["installed_at"]);event=first.get(sid)
        why=None
        if event is None:why="해당 ID의 대여 이력 없음"
        elif abs((event-date).days)>14:why="설치일과 첫 이용일 차이가14일 초과"
        elif event-pd.Timedelta(days=28)<pivot.index.min() or event+pd.Timedelta(days=27)>pivot.index.max():why="전후28일이 관측 범위를 벗어남"
        if not why:
            nearby_ids=tree.query_radius(np.radians([[row["latitude"],row["longitude"]]]),r=30/EARTH)[0]
            if any(str(located.iloc[int(i)].station_id)!=sid and str(located.iloc[int(i)].station_id) in first and first[str(located.iloc[int(i)].station_id)]<event for i in nearby_ids):why="30m 내 사전 이용이 있는 다른ID: 재개설·ID변경 가능성 배제"
        if why:excluded.append({**row,"reason":why});continue
        before_start=event-pd.Timedelta(days=28);before_end=event-pd.Timedelta(days=1);after_end=event+pd.Timedelta(days=27)
        target=series(sid);pre,pre_days=window(target,before_start,before_end);post,post_days=window(target,event,after_end)
        if pre<=0 or pre_days<21 or post_days<21:excluded.append({**row,"reason":"주변 수요의 전후 관측일 또는 수요 부족"});continue
        controls=[]
        for cid,c in mapped.items():
            if cid==sid or c["district"]!=row["district"] or cid not in first:continue
            if first[cid]>pd.Timestamp("2025-01-31") or last[cid]<pd.Timestamp("2025-12-01"):continue
            lat1,lon1,lat2,lon2=np.radians([row["latitude"],row["longitude"],c["latitude"],c["longitude"]])
            distance=2*EARTH*np.arcsin(np.sqrt(np.sin((lat1-lat2)/2)**2+np.cos(lat1)*np.cos(lat2)*np.sin((lon1-lon2)/2)**2))
            if distance<2500:continue
            reference=series(cid);b,bd=window(reference,before_start,before_end);a,ad=window(reference,event,after_end)
            if b<=0 or bd<21 or ad<21 or not .5<=b/pre<=2:continue
            # Match only pre-period demand, never post-period gain.
            controls.append((abs(np.log(b/pre)),cid,b,a))
        if not controls:excluded.append({**row,"reason":"같은 구·2.5km 밖·사전 수요 유사 조건의 비교지역 없음"});continue
        _,cid,cpre,cpost=min(controls,key=lambda x:(x[0],x[1]))
        opened=float(pivot[sid].loc[event:after_end].sum())
        results.append({**row,"event_date":event.strftime("%Y-%m-%d"),"first_trip_date":event.strftime("%Y-%m-%d"),
          "before_start":before_start.strftime("%Y-%m-%d"),"before_end":before_end.strftime("%Y-%m-%d"),"after_end":after_end.strftime("%Y-%m-%d"),
          "neighborhood_radius_m":1000,"pre_daily_rentals":pre,"post_daily_rentals":post,"new_station_post_rentals":int(opened),
          "control_station_id":cid,"control_station_name":mapped[cid]["station_name"],"control_pre_daily":cpre,"control_post_daily":cpost,
          "difference_in_changes_daily":(post-pre)-(cpost-cpre),"control_weight":1,
          "coverage_before_days":pre_days,"coverage_after_days":post_days,"causal_effect_verified":False})
    from backend.presentation.individual import scope
    report={"source_revision":scope("seoul")["revision"],"available":bool(results),"city":"seoul","reference_master_date":"2026-06","analysis_period":"2025-01-01 ~ 2025-12-31",
      "mapped_station_count":len(mapped),"raw_2025_opening_count":all_new,"unmatched_openings":unmatched,"opening_2025_mapped_count":len(candidates),"eligible_count":len(results),"examples":results[:3],"all_events":results,"excluded":excluded,
      "selection":"2025설치·첫이용일±14일·전후28일·30m내기존ID없음·같은구2.5km밖·비교지역사전수요0.5~2배. 비교지역은 사전수요 차이 최소로 결정. 사례는 개설일순3곳.",
      "interpretation":"기존 대여소 개설 전후의 주변 관측 이용 변화와 비교지역 변화의 차이. 제안 후보의 설치 효과·신규 수요 예측·인과 효과로 사용하지 않음.",
      "limitations":["설치일은2026년6월 마스터의 기재값이며 과거 위치 변경·ID 변경은 완전히 검증하지 못함.","날씨·행사·시설 변화·다른 신설의 영향을 통제하지 않은 탐색적 비교임.","고정 현재 위치의 주변1km 이용을 집계하며 창 안의 미기록 대여소 일자는0으로 취급한다. 관측일 기준은 해당 지역 양수 수요일이므로 실제 서비스 운영일 보증은 아님.","인접 분석지역의 수요가 중복될 수 있어 사례별 수치를 합산하지 않음.","동일한 대조지역이 여러 사례에 사용될 수 있다. 외부 독립 검증이나 평행추세 검정은 수행하지 않음."],
      "raw_master_sha256":hashlib.file_digest(raw.open("rb"),"sha256").hexdigest(),"operational_update":False}
    (OUT/"opening-events.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False))
    print("mapped",len(mapped),"2025",len(candidates),"eligible",len(results),"excluded",len(excluded),flush=True)
    print([(r["station_id"],r["event_date"],r["difference_in_changes_daily"]) for r in results[:3]],flush=True)
if __name__=="__main__":run()
