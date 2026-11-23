"""Remote official-master checks and explicit outstanding field-evidence register."""
import csv,json,math,re,hashlib
from pathlib import Path
import pandas as pd
from scripts.validate.final_validation import source,BoundedRouter,audit_routes,save
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123"
def clean(s):return re.sub(r"\s+","",str(s))
def run():
    OUT.mkdir(exist_ok=True,parents=True);results={}
    # Give Sejong a separate bounded request budget instead of a budget exhausted in Seoul.
    s,folder,data,boundary,districts,facilities,anchors=source("sejong","individual")
    from backend.research import method_validation as m
    from shapely.geometry import Point
    from shapely.ops import unary_union
    baseline=unary_union([Point(*m.PROJECT(a["lon"],a["lat"])).buffer(500,quad_segs=16) for a in anchors]).intersection(boundary)
    candidates,_=m.grid_candidates(boundary,baseline,data["stations"],facilities,districts,use_population=False)
    router=BoundedRouter();sejong=audit_routes(candidates,data["stations"],anchors,router)
    save(OUT/"sejong-routes.json",{"source_revision":s["revision"],"new_requests":router.requests,"routes":sejong})
    raw=ROOT/"data/raw/seoul-stations-202606.xlsx";table=pd.read_excel(raw,header=None).iloc[5:]
    master=pd.read_csv(ROOT/"data/individual/seoul/stations.csv").set_index("station_id")
    previous=json.loads((ROOT/"docs/final-validation-20261123/seoul.json").read_text())["routes"]["candidates"]
    matches=[]
    for candidate in previous:
        route=candidate.get("best_checked_route") or candidate["original_route"]
        sid=route.get("dock_station_id");row=master.loc[sid] if sid in master.index else None
        found=[]
        if row is not None:
            for _,r in table.iterrows():
                try:
                    if not math.isfinite(float(r[4])) or not math.isfinite(float(r[5])):continue
                    from scripts.collect.audit_candidate_routes import metres
                    distance=metres((float(row.latitude),float(row.longitude)),(float(r[4]),float(r[5])))
                    if distance<=5 and clean(row.station_name)==clean(r[1]):
                        found.append({"official_station_number":str(r[0]),"name":str(r[1]),"distance_m":distance,
                          "lcd_rack_count":None if pd.isna(r[7]) else int(r[7]),"qr_rack_count":None if pd.isna(r[8]) else int(r[8])})
                except (TypeError,ValueError):continue
        matches.append({"site_id":candidate["site_id"],"dock_station_id":sid,"unique_name_and_5m_match":len(found)==1,
          "official_master":found[0] if len(found)==1 else None,"source_date":"2026-06",
          "is_historical_2025_inventory":False,"field_verified":False})
    results={"seoul_dock_master":matches,"master_sha256":hashlib.file_digest(raw.open("rb"),"sha256").hexdigest(),
      "matching_rule":"공식 이름 공백 제거 후 동일 + 좌표5m 이내 + 유일 매칭. 근접 좌표만으로 ID를 강제 연결하지 않음.",
      "field_verification_complete":False,"reason":"현장 방문·부지 사용 권한·시점별 재고·설치 전후 실측 기록 미제공. 공식 마스터의 거치대 열을 재고로 해석하지 않음."}
    save(OUT/"site-audit.json",results)
    rows=[]
    for city in ("seoul","daejeon","sejong"):
        source_report=json.loads((ROOT/"docs/final-validation-20261123"/(city+".json")).read_text())
        for r in source_report["routes"]["candidates"]:
            rows.append({"city":city,"site_id":r["site_id"],"visit_at":"","observer":"","path_passable":"","site_permission":"",
              "rack_capacity_at_visit":"","available_bikes_at_visit":"","evidence_file_sha256":"","before_after_effect_evidence":"","status":"현장 미검증"})
    with (OUT/"field-evidence-register.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=rows[0]);w.writeheader();w.writerows(rows)
    print("official unique matches",sum(r["unique_name_and_5m_match"] for r in matches),"Sejong requests",router.requests)
if __name__=="__main__":run()
