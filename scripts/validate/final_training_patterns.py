"""Training-only temporal-pattern examples, no cluster label added to operational score."""
import json,sqlite3
from collections import defaultdict
from pathlib import Path
import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scripts.validate.final_validation import TRAIN,ROOT,OUT,save
def run():
    results={}
    for city in ("seoul","daejeon","sejong"):
        with sqlite3.connect((ROOT/"data/individual"/city/"analysis.sqlite").resolve().as_uri()+"?mode=ro",uri=True) as db:
            rows=db.execute("SELECT station_id,hour,SUM(rental_count) FROM station_usage WHERE region_id=? AND substr(date,1,7) IN (?,?,?,?) GROUP BY 1,2",(city,*TRAIN)).fetchall()
        hours=defaultdict(lambda:np.zeros(24))
        for sid,h,n in rows:hours[sid][h]+=int(n)
        ids=sorted(sid for sid,v in hours.items() if v.sum()>=100)
        total=np.array([hours[sid].sum() for sid in ids]);X=np.array([hours[sid]/hours[sid].sum() for sid in ids])
        labels=KMeans(n_clusters=3,random_state=42,n_init=10).fit_predict(X)
        silhouette=float(silhouette_score(X,labels,sample_size=min(1000,len(X)),random_state=42))
        ix=np.argsort(total);choices=[]
        for a,b in zip(ix,ix[1:]):
            if total[b]/total[a]>1.1:continue
            cosine=float(np.dot(X[a],X[b])/(np.linalg.norm(X[a])*np.linalg.norm(X[b])))
            choices.append((cosine,int(a),int(b)))
        cosine,a,b=min(choices)
        pair=[{"station_id":ids[j],"training_rentals":int(total[j]),"peak_hour":int(X[j].argmax()),"cluster":int(labels[j]),"hourly_share":X[j].tolist()} for j in (a,b)]
        results[city]={"train_months":TRAIN,"minimum_training_rentals":100,"n_stations":len(ids),"silhouette":silhouette,
          "example_selection_rule":"훈련 수요 차이10%이내의 수요순 인접 쌍 중 코사인 유사도 최소. 평가기간 자료 미사용.",
          "similar_demand_different_pattern":pair,"cosine_similarity":cosine,
          "decision":"시간대가 다른 곳은 동일 이용량이어도 점검 시간대를 구분합니다. 군집은 유형 확정·설치 점수 항으로 사용하지 않습니다.",
          "operational_update":False}
        print(city,silhouette,[(r["station_id"],r["peak_hour"]) for r in pair],flush=True)
    save(OUT/"training-patterns.json",results)
if __name__=="__main__":run()
