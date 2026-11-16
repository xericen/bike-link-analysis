import {useEffect,useState} from 'react'
import {MapContainer,TileLayer,GeoJSON,CircleMarker,Tooltip} from 'react-leaflet'
import type {GeoJsonObject} from 'geojson'
import {SectionCard,SimpleDataTable} from './AnalysisUI'
type Site={site_id:string;rank:number;district?:string;kind?:string;latitude:number;longitude:number;population_density_km2:number;facilities_within_500m:number;nearby_rentals_1000m:number;nearest_station_distance_m:number}
type State={selected_ids:string[];added_area_m2:number;overlap_area_m2:number;increase_ratio:number|null;added_geometry:GeoJsonObject}
type Plan={available:boolean;coverage_features:GeoJsonObject[];new_sites:Site[];scenario_pool:Site[];selection_states:State[];sensitivity:{distance_m:number;policy:string;candidate_count:number;top10_jaccard:number|null}[];relocation:{items:{station_id:string;net_outflow:number;peak_hour:number;peak_net_outflow:number}[]}}
const pct=(v:number|null)=>v==null?'N/A':(v*100).toFixed(3)+'%'
export function PlanningPanel({city,start,end}:{city:string;start?:string;end?:string}) {
 const [plan,setPlan]=useState<Plan>(),[error,setError]=useState(''),[ids,setIds]=useState<string[]>([])
 useEffect(()=>{const controller=new AbortController();setPlan(undefined);setIds([]);setError('')
 const q=new URLSearchParams({city});if(start)q.set('date_start',start);if(end)q.set('date_end',end)
 fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/planning?'+q,{signal:controller.signal}).then(async r=>{const body=await r.json();if(!r.ok)throw new Error(body.detail||'입지 자료 조회 실패');return body}).then(setPlan).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
 return()=>controller.abort()
 },[city,start,end])
 if(error)return <p role="alert">{error}</p>
 if(!plan)return <p>입지·시나리오 집계 조회 중…</p>
 if(!plan.available)return <p>선택 도시·기간의 입지 분석 자료 미확보</p>
 const state=plan.selection_states.find(s=>JSON.stringify(s.selected_ids)===JSON.stringify([...ids].sort()))
 const centre:[number,number]=city==='seoul'?[37.56,126.98]:city==='sejong'?[36.5,127.27]:[36.35,127.38]
 const toggle=(id:string)=>setIds(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id])
 return <SectionCard title="신규 입지·선택 시나리오·재배치 검토" note="구·시 인구밀도 · 공개 시설 · 주변 실제 대여 수요">
 <MapContainer key={city} center={centre} zoom={11} style={{height:340}} scrollWheelZoom={false}>
 <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
 {plan.coverage_features.map((g,i)=><GeoJSON key={i} data={g} style={{color:'#8b929a',weight:.5,fillOpacity:.18}}/>)}
 {state&&<GeoJSON key={ids.join(',')} data={state.added_geometry} style={{color:'#159b88',fillOpacity:.35}}/>}
 {plan.new_sites.map(s=><CircleMarker key={s.site_id} center={[s.latitude,s.longitude]} radius={5} pathOptions={{color:'#347fc4'}}><Tooltip>신규 {s.rank}위 · {s.district}</Tooltip></CircleMarker>)}
 </MapContainer>
 <SimpleDataTable headers={['신규 후보','인구밀도(명/km²)','시설500m','주변대여1km','최근접 대여소(m)']} rows={plan.new_sites.slice(0,10).map(s=>[s.rank+'위 · '+s.district,s.population_density_km2.toFixed(0),s.facilities_within_500m,s.nearby_rentals_1000m,s.nearest_station_distance_m.toFixed(1)])}/>
 <h4>상위 후보 조합</h4>{plan.scenario_pool.map(s=><label key={s.site_id} style={{display:'inline-flex',gap:8,margin:8}}><input type="checkbox" checked={ids.includes(s.site_id)} onChange={()=>toggle(s.site_id)}/>{s.kind} {s.rank}위</label>)}
 {state&&<p>추가 {(state.added_area_m2/1e6).toFixed(4)} km² · 중복 {(state.overlap_area_m2/1e6).toFixed(4)} km² · +{pct(state.increase_ratio)}</p>}
 <details><summary>거리·가중치 안정성</summary><SimpleDataTable headers={['거리','가중치','후보','TOP10 유사도']} rows={plan.sensitivity.map(s=>[s.distance_m+'m',s.policy,s.candidate_count,pct(s.top10_jaccard)])}/></details>
 <h4>재배치 검토</h4><p>재고 미확보로 실제 부족 여부와 이동 수량은 제안하지 않습니다.</p>
 <SimpleDataTable headers={['대여소','관측 순유출','변동 최대 시간','시간 순유출']} rows={plan.relocation.items.map(s=>[s.station_id,s.net_outflow,s.peak_hour+'시',s.peak_net_outflow])}/>
 <details><summary>자료 기준</summary><p>2020 SGIS 경계, 2026-10 구·시 인구밀도, 공개 도서관·공공개방시설 좌표를 사용합니다. 실측 격자인구·실제 환승 효과·설치 가능성은 검증하지 않았습니다.</p></details>
 </SectionCard>
}
