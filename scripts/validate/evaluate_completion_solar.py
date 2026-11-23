"""Replay factual stress tests and payload sizes using actual stored tool evidence."""
import copy,json
from pathlib import Path
from backend.agents.completion_checks import check,compact
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/"docs/completion-20261123"
def run():
    cases=[];payload=[]
    for city in ("seoul","daejeon","sejong"):
        source=json.loads((ROOT/"docs/final-validation-20261123"/("solar-"+city+".json")).read_text())
        evidence=source["response"]["evidence"]
        calls=[e for e in evidence if e["tool"]=="get_project_conclusion" and e["result"].get("scope")=="individual_full"]
        packet=calls[0]["result"]["cities"][0];rows=packet["candidates"]
        for i,row in enumerate(rows):
            sid=row["site_id"];n=row["nearby_rentals_1000m"];other=rows[(i+1)%len(rows)]["nearby_rentals_1000m"]
            specimens=[("correct_candidate_value",f"{sid} 주변1km 관측 대여 {n}건.",True),
              ("wrong_candidate_same_global_number",f"{sid} 주변1km 관측 대여 {other}건.",other==n),
              ("unknown_id",f"grid-999999-999999 주변1km 관측 대여 {n}건.",False),
              ("wrong_area_unit",f"{sid} 추가 면적 {n}건.",False),
              ("unsupported_actual_transfer",f"{sid} 실제 환승률은12.3%입니다.",False),
              ("unsupported_installed_effect",f"{sid} 설치하면 이용량이20% 증가합니다.",False)]
            specimens.append(("translated_candidate_id",f"{sid.replace('grid-','격자-')} 주변1km 관측 대여{n}건.",False))
            sensitivity=row.get("additional_validation",{}).get("overhead_sensitivity",[])
            five=next((x for x in sensitivity if x["overhead_minutes"]==5 and x.get("gain_minutes") is not None),None)
            if five:
                g=five["gain_minutes"]
                specimens.extend([("correct_overhead_assumption",f"{sid} 5분 가정에서{g:.3f}분 단축.",True),("wrong_overhead_assumption",f"{sid} 5분 가정에서{g+3:.3f}분 단축.",False)])
            area=row.get("potential_added_area_m2")
            if area is not None:
                specimens.extend([("correct_candidate_area",f"{sid} 추가 면적{area/1000000:.6f}km².",True),("wrong_candidate_area",f"{sid} 추가 면적{area/1000000+1:.6f}km².",False)])
            gain=row["route"].get("improvement_minutes")
            if gain is not None:
                specimens.extend([("correct_basic_time",f"{sid} 기본 단축{gain:.3f}분.",True),("wrong_basic_time",f"{sid} 기본 단축{gain+3:.3f}분.",False)])
            if row["route"]["status"]!="model_connected":specimens.append(("unconfirmed_route_assertion",f"{sid} 경로가 확인되었습니다.",False))
            for kind,answer,expected in specimens:
                actual=check(answer,evidence)
                cases.append({"city":city,"kind":kind,"candidate_id":sid,"answer":answer,"expected_pass":expected,"passed":actual["passed"],"correct":actual["passed"]==expected,"validation":actual})
        multi=", ".join(f"{row['site_id']} 주변1km 관측 대여{row['nearby_rentals_1000m']}건" for row in rows)
        actual=check(multi,evidence)
        cases.append({"city":city,"kind":"correct_multiple_candidates_one_sentence","answer":multi,"expected_pass":True,"passed":actual["passed"],"correct":actual["passed"],"validation":actual})
        for e in evidence:
            small=compact(e["tool"],e["result"])
            payload.append({"city":city,"tool":e["tool"],"before_utf8_bytes":len(json.dumps(e["result"],ensure_ascii=False).encode()),
              "after_utf8_bytes":len(json.dumps(small,ensure_ascii=False).encode()),"details_withheld":small.get("details_withheld",False)})
    result={"case_count":len(cases),"correct":sum(r["correct"] for r in cases),"cases":cases,"payload_comparisons":payload,
      "evidence_kind":"Actual tool packets with deliberately constructed positive/negative test sentences; not new observations or live model answers.",
      "coverage":"Candidate ID/value association, area units, pending routes, actual-transfer and installed-effect assertions only; unrestricted prose truth remains unverified."}
    OUT.mkdir(parents=True,exist_ok=True);(OUT/"solar-replay.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(result["correct"],"/",result["case_count"]);print("bytes",sum(r["before_utf8_bytes"] for r in payload),sum(r["after_utf8_bytes"] for r in payload))
if __name__=="__main__":run()
