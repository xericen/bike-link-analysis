import { useEffect,useState } from 'react'
import { StationMap } from '../maps/StationMap'
import type { Station } from '../types'
import { anchorDistance } from '../services/anchorPresentation'
export type TransitStop={city:string;stop_id:string;name:string;type:string;lat:number;lon:number}
export type TransitStation=Station & {nearest_stop_distance_m:number|null;stops_within_300m:number|null;bus_within_500m:number|null;subway_within_500m:number|null;nearest_stop_lat?:number;nearest_stop_lon?:number}
type Linkage={stations:TransitStation[];map_stops:TransitStop[];map_display_note:string}
export function useLinkage(city:string,start?:string,end?:string,enabled=true) {
 const [value,setValue]=useState<Linkage>(),[error,setError]=useState('')
 useEffect(()=>{let active=true;setValue(undefined);setError('');if(!enabled)return()=>{active=false}
 const q=new URLSearchParams({city});if(start)q.set('date_start',start);if(end)q.set('date_end',end)
 fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/transit-linkage?'+q).then(async r=>{if(!r.ok)throw new Error('정류장 연계 자료 조회 실패');return r.json()}).then(x=>{if(active)setValue(x)}).catch(e=>{if(active)setError(e.message)})
 return()=>{active=false}
 },[city,start,end,enabled]);return {value,error}
}
export function TransitDashboardMap({city,start,end,stations}:{city:string;start?:string;end?:string;stations:Station[]}) {
 const {value,error}=useLinkage(city,start,end)
 return <><AnchorNotes city={city} start={start} end={end}/><StationMap stations={city==='sejong'?(value?.stations||[]):stations} unclustered={city==='sejong'} anchorCity={city} height={370} transitStops={value?.map_stops} transitStations={value?.stations}/><p className="muted">{error||value?.map_display_note||'정류장 연계 정보를 불러오는 중입니다.'}</p></>
}
export function TransitStationMetrics({city,start,end,stationId}:{city:string;start?:string;end?:string;stationId:string}) {
 const {value,error}=useLinkage(city,start,end)
 const row=value?.stations.find(x=>x.station_id===stationId)
 const count=(v:number|null|undefined)=>v==null?'N/A':v.toLocaleString()
 return <section className="panel transit-station-metrics"><h3>대중교통 연계 지표</h3><AnchorNotes city={city} start={start} end={end}/>
 {error?<p role="alert">{error}</p>:<><p>{anchorDistance(city)} {row?.nearest_stop_distance_m==null?'N/A':row.nearest_stop_distance_m.toFixed(1)+'m'}</p><p>300m 내 앵커 {count(row?.stops_within_300m)} · 500m 내 버스 {count(row?.bus_within_500m)} / 지하철 {count(row?.subway_within_500m)}</p></>}
 <p className="muted">{start} ~ {end} · m/개 · 도시별 앵커 원본은 위 출처 각주 참조. 앵커와의 직선거리이며 실제 환승률이 아닙니다. 대여소 좌표 미확보는 N/A입니다.</p></section>
}

export function AnchorNotes({city,start,end}:{city:string;start?:string;end?:string}) {
 const [context,setContext]=useState<{denominator_note:string;source_note:string;station_map_note:string}>()
 useEffect(()=>{let active=true;setContext(undefined);const p=new URLSearchParams({city});if(start)p.set("date_start",start);if(end)p.set("date_end",end)
 fetch(import.meta.env.BASE_URL.replace(/\/$/,"")+"/api/presentation-context?"+p).then(r=>r.ok?r.json():undefined).then(v=>{if(active)setContext(v)}).catch(()=>{})
 return()=>{active=false}},[city,start,end])
 return <>{context&&<><p className="muted denominator-note">{context.denominator_note}</p><p className="muted anchor-source-note">{city==='sejong'?'세종은 지하철 없이 BRT가 대중교통 축입니다. ':''}{context.source_note}</p>{city==="sejong"&&<p className="muted">{context.station_map_note} · 청록색 큰 원: BRT 정류장(앵커). 노선 선형 자료 미확보로 노선축을 표시하지 않습니다.</p>}</>}</>
}
