import { useEffect,useState } from 'react'
import { StationMap } from '../maps/StationMap'
import type { Station } from '../types'
export type TransitStop={city:string;stop_id:string;name:string;type:string;lat:number;lon:number}
export type TransitStation=Station & {nearest_stop_distance_m:number|null;stops_within_300m:number|null;bus_within_500m:number|null;subway_within_500m:number|null;nearest_stop_lat?:number;nearest_stop_lon?:number}
type Linkage={stations:TransitStation[];map_stops:TransitStop[];map_display_note:string}
function useLinkage(city:string,start?:string,end?:string) {
 const [value,setValue]=useState<Linkage>(),[error,setError]=useState('')
 useEffect(()=>{let active=true;setValue(undefined);setError('')
 const q=new URLSearchParams({city});if(start)q.set('date_start',start);if(end)q.set('date_end',end)
 fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/transit-linkage?'+q).then(async r=>{if(!r.ok)throw new Error('정류장 연계 자료 조회 실패');return r.json()}).then(x=>{if(active)setValue(x)}).catch(e=>{if(active)setError(e.message)})
 return()=>{active=false}
 },[city,start,end]);return {value,error}
}
export function TransitDashboardMap({city,start,end,stations}:{city:string;start?:string;end?:string;stations:Station[]}) {
 const {value,error}=useLinkage(city,start,end)
 return <><StationMap stations={stations} height={370} transitStops={value?.map_stops} transitStations={value?.stations}/><p className="muted">{error||value?.map_display_note||'정류장 연계 정보를 불러오는 중입니다.'}</p></>
}
export function TransitStationMetrics({city,start,end,stationId}:{city:string;start?:string;end?:string;stationId:string}) {
 const {value,error}=useLinkage(city,start,end)
 const row=value?.stations.find(x=>x.station_id===stationId)
 const count=(v:number|null|undefined)=>v==null?'N/A':v.toLocaleString()
 return <section className="panel transit-station-metrics"><h3>대중교통 연계 지표</h3>
 {error?<p role="alert">{error}</p>:<><p>최근접 정류장 {row?.nearest_stop_distance_m==null?'N/A':row.nearest_stop_distance_m.toFixed(1)+'m'}</p><p>300m 내 정류장 {count(row?.stops_within_300m)} · 500m 내 버스 {count(row?.bus_within_500m)} / 지하철 {count(row?.subway_within_500m)}</p></>}
 <p className="muted">{start} ~ {end} · m/개 · 국토교통부 전국버스·철도산업정보센터 역사정보. 직선거리이며 실제 환승률이 아닙니다. 대여소 좌표 미확보는 N/A입니다.</p></section>
}
