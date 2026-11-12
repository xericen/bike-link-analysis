import { useEffect, useState } from 'react'
import { StationMap } from '../maps/StationMap'
import { SectionCard, SimpleDataTable } from './AnalysisUI'
import { number } from './State'
import type { Station } from '../types'
type Row = Station & {nearest_stop_distance_m:number;rental_count:number;score:number;potential_added_area_m2:number}
type Result={available:boolean;message?:string;candidate_count:number;period_start?:string;period_end?:string;ranking:Row[];candidates:Row[];limitations:string[];scenario?:{baseline_area_m2:number;linked_area_m2:number;area_increase_ratio:number;baseline_station_count:number;linked_station_count:number}}
export function TransitPanel({city,start,end}:{city:string;start?:string;end?:string}) {
 const [result,setResult]=useState<Result>(),[error,setError]=useState(''),[visible,setVisible]=useState(true)
 useEffect(()=>{const controller=new AbortController();setResult(undefined);setError('')
 const q=new URLSearchParams({city});if(start)q.set('date_start',start);if(end)q.set('date_end',end)
 fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/vulnerability?'+q,{signal:controller.signal}).then(async r=>{if(!r.ok)throw new Error('연계 분석 요청 실패');return r.json()}).then(setResult).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
 return()=>controller.abort()
 },[city,start,end])
 return <SectionCard title="대중교통 연계 취약 후보와 접근 시나리오" note={(result?.period_start||start||'')+' ~ '+(result?.period_end||end||'')+' · m / km² / 건 · OA-15067·OA-22534'}>
 {error?<p role="alert">{error}</p>:!result?<p>정류장 공간 버퍼와 실제 이용량을 계산 중입니다…</p>:!result.available?<p>{result.message}</p>:<>
 <p>정류장 500m 밖이며 실제 대여량이 있는 후보 {number(result.candidate_count)}개. 실제 보행 경로나 환승 여부를 확정하지 않습니다.</p>
 <label><input type="checkbox" checked={visible} onChange={e=>setVisible(e.target.checked)}/> 취약 후보 지도 레이어</label>
 <StationMap stations={visible?result.candidates:[]} colorById={Object.fromEntries(result.candidates.map(x=>[x.station_id,'#df704f']))} height={320}/>
 <SimpleDataTable headers={['대여소','최근접 거리(m)','대여량(건)','검토 점수']} rows={result.ranking.map(x=>[x.station_id,x.nearest_stop_distance_m.toFixed(1),number(x.rental_count),x.score.toFixed(3)])}/>
 {result.scenario&&<p>공간 시나리오: {(result.scenario.baseline_area_m2/1e6).toFixed(3)} → {(result.scenario.linked_area_m2/1e6).toFixed(3)} km², 면적 +{(result.scenario.area_increase_ratio*100).toFixed(3)}%. 커버 대여소 {result.scenario.baseline_station_count} → {result.scenario.linked_station_count}개.</p>}
 <details><summary>가정·출처·해석 한계</summary>{result.limitations.map(x=><p key={x}>{x}</p>)}<p>점수는 취약도·수요·잠재 면적의 도시 내 백분위 동등 가중 평균입니다. 인구 효과는 N/A입니다.</p><a href="https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do">서울 버스정류소</a> · <a href="https://data.seoul.go.kr/dataList/OA-22534/F/1/datasetView.do">서울교통공사 역사 좌표</a></details>
 </>}
 </SectionCard>
}
