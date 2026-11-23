"""Independent checks and Korean report for the archived broad experiment."""
import csv,json,math
from collections import Counter
import numpy as np
from sklearn.neighbors import BallTree
from backend.research import recovery_breadth as b, method_validation as m

LABELS={"original":"기존 균등점수","rental1000":"주변1km 대여","activity500":"주변500m 대여·반납",
        "kde300":"수요 평활화","facilities500":"주변시설","balanced":"균형점수","anchor_demand":"역 인접 수요",
        "diverse300":"수요·후보분산300m","diverse600":"수요·후보분산600m","cover500":"중복제거 수요커버"}
POOL_LABELS={"legacy500":"기존500m격자","grid250":"250m격점","grid125":"125m다중위치",
             "diagnostic125_50":"50m간격진단","facility_mix_50":"시설점추가50m진단"}

def label(key):
    pool,method=key.split(":")
    return POOL_LABELS[pool]+" / "+LABELS[method]

def audit():
    out=b.OUT
    r=json.loads((out/"results.json").read_text())
    inputs=json.loads((out/"inputs.json").read_text())
    for rel,value in inputs.items():
        path=m.ROOT/rel;st=path.stat()
        assert (st.st_size,st.st_mtime_ns)==(value["size"],value["mtime_ns"])
        if path.suffix!=".sqlite":assert m.sha(path)==value["sha256"]
    checked=0
    for city,c in r["cities"].items():
        with (m.ROOT/"data/individual"/city/"stations.csv").open() as f:master=list(csv.DictReader(f))
        seen={sid for stage in ("development","exploration") for fold in c[stage] for sid in fold["hidden_ids"]}
        test={sid for fold in c["evaluation"] for sid in fold["hidden_ids"]}
        assert not seen&test
        for stage in ("development","exploration","evaluation"):
            for fold in c[stage]:
                audit=fold["audit"]
                assert audit["source_od_trips"]==audit["retained_od_trips"]+audit["removed_od_trips"]
                assert audit["hidden_station_count_in_training"]==0
                assert audit["source_od_trips"]==c[stage+"_info"]["trips"]
                located=[s for s in master if s["station_id"] not in fold["hidden_ids"] and s["latitude"] and s["longitude"]]
                tree=BallTree(np.radians([[float(s["latitude"]),float(s["longitude"])] for s in located]),metric="haversine")
                for key,value in fold["methods"].items():
                    top=value["top"]
                    if top:
                        d=tree.query(np.radians([[p["latitude"],p["longitude"]] for p in top]),k=1)[0][:,0]*m.EARTH_M
                        assert min(d)>(300 if key in b.STRICT else 50),(city,stage,key,min(d))
                    assert len({p["site_id"] for p in top})==len(top)
                    for k,match in value["matches"].items():
                        assert match["hits"]==len(match["pairs"])
                        assert len({p["site_id"] for p in match["pairs"]})==match["hits"]
                        assert len({p["station_id"] for p in match["pairs"]})==match["hits"]
                        assert all(p["distance_m"]<=300 for p in match["pairs"])
                        actual=m.geographic_matches(fold["targets"],top[:int(k)])
                        assert actual["hits"]==match["hits"]
                        assert math.isclose(match["recall"],match["hits"]/fold["target_count"])
                        checked+=1
        # Frozen selections must reproduce the development-only criterion.
        assert b.select(c["development"],b.STRICT)[0]==c["selection"]["strict"]
        assert b.select(c["development"],b.DIAGNOSTIC)[0]==c["selection"]["diagnostic"]
        assert json.loads((out/(city+"-selection-lock.json")).read_text())==c["selection"]
    result={"passed":True,"matching_checks":checked,"input_metadata_unchanged":True,
            "small_input_sha256_matches":True,"strict_spacing_verified":True,
            "diagnostic_spacing_verified":True,"no_evaluation_hidden_id_overlap":True,
            "artifacts":{name:m.sha(out/name) for name in ("results.json","inputs.json","protocol.json")},
            "operational_update":False}
    if (out/"audit.json").exists():raise FileExistsError("Keep prior audit evidence")
    (out/"audit.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    report(r,out/"RESULTS.md")
    print(json.dumps(result,ensure_ascii=False))
    return result

def report(r,path):
    names={"seoul":"서울","daejeon":"대전","sejong":"세종"}
    lines=["# 46개 조합 재발견 탐색·별도 검증","",
           "서비스 공통기간은2025년12월이다. 이미 결과를 확인한12월 자료의 최고값은 **탐색 최고값**이며 독립 검증 성능이 아니다.",
           "같은 원래 인기대여소10곳·좌표·이용량·OD총합을 대조했고 기존 방법0/10을 실제 재현했다. 평가 반경300m·일대일 매칭은 바꾸지 않았다.",
           "","## 같은12월 인기대여소10곳","",
           "|도시|기존방법|300m간격 유지 탐색 최고|방법|50m진단 탐색 최고|방법|",
           "|---|---:|---:|---|---:|---|"]
    for city,c in r["cities"].items():
        f=c["exploration"][0]
        choose=lambda keys:max(keys,key=lambda k:f["methods"][k]["matches"]["10"]["hits"])
        strict,diag=choose(b.STRICT),choose(b.DIAGNOSTIC)
        lines.append(f"|{names[city]}|0/10|{f['methods'][strict]['matches']['10']['hits']}/10|{label(strict)}|{f['methods'][diag]['matches']['10']['hits']}/10|{label(diag)}|")
    lines+=["","**50m진단은 기존 대여소와의300m 설치 간격 조건을 완화한 별도 목적이다. 신규 설치 성능 개선으로 주장하지 않는다.**",
            "300m간격 유지 방법도 설치 가능 토지·보행 접근성·실제 운영 효과는 검증하지 않았다.",
            "","## 방법을 고정한 후8월 평가","",
            "12월1~21일만으로 간격유지/진단 방법을 각각 선택해 잠근 뒤8월OD를 로드했다.8월은 과거의 다른 월에 대한 회고적 검사이지 미래 예측이 아니다.",
            "개발/12월탐색에서 숨겼던ID는8월 평가 대상에서 제외했다.1km구역은 개발구역에서2km이상 떨어지도록 정했다.",
            "12월과8월의 평가 대상이 다르므로 두 달의 수치를 직접 개선률로 계산하지 않는다.","",
            "|도시|평가 대상|N|기존방법 복구@10|잠금300m방법|잠금50m진단|",
            "|---|---|---:|---:|---:|---:|"]
    types={"high_usage":"미사용 이용상위","gap_high_usage":"공백조건 이용상위","spatial_block":"1km구역 전체"}
    for city,c in r["cities"].items():
        for f in c["evaluation"]:
            hit=lambda k:f["methods"][k]["matches"]["10"]["hits"]
            lines.append(f"|{names[city]}|{types[f['name']]}|{f['target_count']}|{hit('legacy500:original')}|{hit(c['selection']['strict'])}|{hit(c['selection']['diagnostic'])}|")
    lines+=["","## 비교한 방법","",
            "- 후보풀5종: 기존500m격자,250m격점,125m다중위치,50m간격진단125m격점,실제공공시설점추가50m진단.",
            "- 선정9종:1km대여량,500m대여·반납,커널수요평활화,시설수,균형점수,역인접수요,후보간300m분산,600m분산,중복제거수요커버.",
            "- 후보풀5×선정9+기존방법1=46조합. 동일 후보풀별 무작위30회도 별도 비교했으며 무작위 결과로 방법을 고르지 않았다.",
            "- 후보 생성 입력은 남은 대여소·남은OD·정적시설·앵커·경계다. 가린 대여소 좌표는 최종 평가에만 사용하며 후보로 직접 삽입하지 않았다.",
            "- 125m/250m격점은 경계 내 고정 격점이다. 숨긴 위치에 격자를 맞추거나 평가반경을 늘리지 않았다.",
            "- cover500은 선택 후보500m안의 남은 관측 대여+반납을 중복 제거한 값이다. 미충족 잠재수요·설치 후 신규 이용량 추정치가 아니다.",
            "- 직선거리·고정 인프라/시설 참조를 사용했다. 과거 위치 동일성·실제 환승·재고·설치효과는 미검증이며 운영점수는 유지한다.",
            "","## 모든12월 조합 결과","",
            "|도시|조합|원래인기10 복구@10|공백조건10 복구@10|1km구역 복구@10|",
            "|---|---|---:|---:|---:|"]
    for city,c in r["cities"].items():
        for key in b.CONFIGS:
            values=[f["methods"][key]["matches"]["10"]["hits"] for f in c["exploration"]]
            lines.append(f"|{names[city]}|{label(key)}|{values[0]}/10|{values[1]}/10|{values[2]}/{c['exploration'][2]['target_count']}|")
    path.write_text("\n".join(lines)+"\n")

if __name__=="__main__":audit()
