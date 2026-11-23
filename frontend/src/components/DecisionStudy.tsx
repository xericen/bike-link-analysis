import { analysisFetch } from '../services/individual'
import {useEffect,useState} from 'react'
type Study={available:boolean;matches_selected_period:boolean;period_start:string;period_end:string;top3:{site_id:string;selection_reason:string;feasibility_unchecked:string[]}[];top3_union:{added_area_m2:number;overlap_area_m2:number};route_audit:{candidate_id:string;routes:Record<string,{status:string;distance_m?:number}>}[];cluster_decision:string;planning_scope:string;pattern_case?:{cosine:number;decision:string};hidden_hub?:{station_id:string;decision:string}}
export function DecisionStudy({city,start,end}:{city:string;start:string;end:string}){
 const [value,setValue]=useState<Study>(),[error,setError]=useState('')
 useEffect(()=>{const controller=new AbortController();setValue(undefined);setError('')
 const q=new URLSearchParams({city,date_start:start,date_end:end})
 analysisFetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/decision-evidence?'+q,{signal:controller.signal}).then(async r=>{const v=await r.json();if(!r.ok)throw new Error(v.detail||'후보 근거 조회 실패');if(!v.matches_selected_period)throw new Error('선택 기간의 후보 3곳 근거 패키지가 없습니다. 다른 기간으로 대체하지 않습니다.');return v}).then(setValue).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()
 },[city,start,end])
 return <details className="panel"><summary>후보 3곳 검증 보고서 · 공간·이용 패턴·도로망</summary>
 {error?<p role="alert">{error}</p>:!value?<p role="status">검증된 후보 근거 조회 중…</p>:<>
 <p>관측 {value.period_start} ~ {value.period_end} · {value.planning_scope}</p>
 {value.top3.map(c=><article key={c.site_id}><h4>{c.site_id}</h4><p>{c.selection_reason}</p><p>현장 확인 필요: {c.feasibility_unchecked.join(' · ')}</p></article>)}
 <p>시나리오 · 중복 제거 추가 면적 {(value.top3_union.added_area_m2/1e6).toFixed(4)} km² · 중복 {(value.top3_union.overlap_area_m2/1e6).toFixed(4)} km²</p>
 {value.hidden_hub&&<p>별도 연결 역할 사례 · {value.hidden_hub.station_id}: {value.hidden_hub.decision}</p>}
 {value.pattern_case&&<p>별도 이용 패턴 사례 · Cosine {value.pattern_case.cosine.toFixed(4)}: {value.pattern_case.decision}</p>}
 <p>{value.cluster_decision}</p>
 <h4>도로망 감사 · 일부 후보만 검토</h4>
 {value.route_audit.map(r=><p key={r.candidate_id}>{r.candidate_id} · {Object.entries(r.routes).map(([m,v])=>(m==='foot'?'도보':'자전거')+': '+(v.status==='ok'?(v.distance_m??0).toFixed(0)+'m':'좌표 접속 오차 등으로 비교 제외')).join(' / ')}</p>)}
 <p>현재 OSM 도로망의 모델 거리이며 관측 당시 통행 가능성·실제 환승을 검증하지 않습니다. 위 별도 패턴·연결 사례를 신규 후보의 직접 관측값으로 해석하지 마세요.</p>
 </>}
 </details>
}
