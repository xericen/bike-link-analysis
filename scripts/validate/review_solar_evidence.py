"""Offline evidence checks; no external API requests."""
import hashlib,json,math,sqlite3,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.agents import solar
from backend.services import real_data
OUT=ROOT/"docs/solar-verification-20261112"
log=json.loads((OUT/"execution.json").read_text())
c=sqlite3.connect("file:"+str(ROOT/"data/processed/analysis.sqlite")+"?mode=ro",uri=True)
daily=c.execute("SELECT date,SUM(rental_count) FROM station_usage WHERE region_id=? AND date BETWEEN ? AND ? GROUP BY date ORDER BY date",("seoul","2026-10-01","2026-10-31")).fetchall()
station=c.execute("SELECT SUM(rental_count),SUM(return_count) FROM station_usage WHERE region_id=? AND station_id=? AND date BETWEEN ? AND ?",("seoul","ST-1481","2026-10-01","2026-10-31")).fetchone()
q1=log["questions"][0]["response"]
q3=log["questions"][2]["response"]
q4=log["questions"][3]["response"]
overview=q1["evidence"][0]["result"]
similar=q3["evidence"][0]["result"]["similar"][0]
detail=q4["evidence"][0]["result"]
profiles=real_data.profiles("seoul","2026-10-01","2026-10-31")
a=next(p for p in profiles if p["station_id"]=="ST-1481")
def vector(p):
    return [v/p["rental_count"] for v in p["hourly"]]+[p["weekend_share"]]
def cosine(x,y):
    return sum(i*j for i,j in zip(x,y))/math.sqrt(sum(i*i for i in x)*sum(j*j for j in y))
scores=sorted(((p["station_id"],round(cosine(vector(a),vector(p)),5)) for p in profiles
    if p["station_id"]!="ST-1481" and p["rental_count"]>0 and p["hourly"] is not None),key=lambda p:p[1],reverse=True)
checks={
"tool_count":len(solar.TOOLS),"tool_names":list(solar.TOOL_DEFINITIONS),
"source_files_unchanged":all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in log["source_sha256"].items()),
"sql":{"total_rentals":sum(n for d,n in daily),"observed_days":len(daily),"period_start":daily[0][0],"period_end":daily[-1][0],
       "minimum_day":min(daily,key=lambda p:p[1]),"maximum_day":max(daily,key=lambda p:p[1]),
       "ST-1481":{"rental_count":station[0],"return_count":station[1]}},
"q1":{"total_and_period_match":overview["total_rentals"]==sum(n for d,n in daily) and overview["period_start"]==daily[0][0] and overview["period_end"]==daily[-1][0],
      "daily_tool_matches_sql":overview["daily"]==[{"date":d,"rental_count":n} for d,n in daily],
      "answer_maximum_claim_correct":False,"explanation":"Solar says 2026-10-08 / 165625 is maximum; SQL and tool show 2026-10-02 / 166657."},
"q3":{"independent_cosine_top":scores[0],"tool_top_matches":list(scores[0])==[similar["station_id"],similar["score"]],
      "answer_id_score_count_ratio_match":all(s in q3["answer"] for s in ("ST-20","0.9881","1,835","1.982"))},
"q4":{"tool_counts_match_sql":detail["station"]["rental_count"]==station[0] and detail["station"]["return_count"]==station[1],
      "raw_answer_counts_match":all(s in q4["solar_answer"] for s in ("926","1322")),
      "observed_days_claim_valid":len(detail["observed_dates"])==31,
      "raw_answer_withheld":q4["answer_basis"]=="tool_summary","default_answer_contains_requested_counts":all(s in q4["answer"] for s in ("926","1322"))},
"successful_questions":sum(q.get("wiz_code")==200 for q in log["questions"]),
"failed_question_ids":[q["id"] for q in log["questions"] if q.get("wiz_code")!=200],
"period_arguments_match":all(e["arguments"].get("date_range")=={"date_start":"2026-10-01","date_end":"2026-10-31"}
  for q in log["questions"] for e in (q.get("response") or {}).get("evidence",[]) if "date_range" in e["arguments"]),
"paid_requests_added_by_this_script":0}
assert checks["source_files_unchanged"] and checks["tool_count"]==14
assert checks["q1"]["total_and_period_match"] and checks["q1"]["daily_tool_matches_sql"]
assert checks["q3"]["tool_top_matches"] and checks["q3"]["answer_id_score_count_ratio_match"]
assert checks["q4"]["tool_counts_match_sql"] and checks["q4"]["observed_days_claim_valid"]
(OUT/"evidence-checks.json").write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(checks,ensure_ascii=False,indent=2))
