import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {MapContainer,TileLayer,CircleMarker,Tooltip} from 'react-leaflet'
const count=(v:number)=>v.toLocaleString('ko-KR')
export function ValidationReview({data,focus}:{data:any;focus?:{name:string}}){
 const [anchorName,setAnchorName]=useState(''),[selectedStation,setSelectedStation]=useState<any>()
 useEffect(()=>{if(focus){setAnchorName(focus.name);setSelectedStation(undefined);requestAnimationFrame(()=>document.getElementById('validation-anchor-'+data.city)?.scrollIntoView({block:'center'}))}},[focus,data.city])
 const support=data.followup
 if(!support)return <p>후속 검증·지도 자료가 미준비 상태입니다.</p>
 const locations=support.matrix_neighborhoods
 const chosen=locations.find((r:any)=>r.anchor_name===anchorName)
 const query=new URLSearchParams({reference:'2025-12',region:data.city})
 if(selectedStation)query.set('station',selectedStation.station_id)
 const prompt=(chosen?chosen.anchor_name+'과 주변 대여소의 연계 여건':'이 도시의 후보 선정 방법')+'을 get_method_validation 도구로 확인하고 실제 수치와 검증 한계를 설명해줘.'
 const aiQuery=new URLSearchParams(query);aiQuery.set('prompt',prompt)
 return <section className="validation-review">
 <div className="advanced-improvement"><h4>조건이 달라도 반복해서 나타나는 후보</h4>
 <p>{support.recurrence.definition} {support.recurrence.decision}</p>
 <div className="table-wrap"><table><thead><tr><th>기준 후보</th><th>같은 격자에서 유지</th><th>다른 격자의 근접 후보</th></tr></thead><tbody>
 {support.recurrence.items.map((r:any)=><tr key={r.site_id}><td>{r.district} · 기준{r.baseline_rank}위</td><td>{r.same_grid_hits}/{r.same_grid_tests}조건</td><td>{r.changed_grid_hits}/{r.changed_grid_tests}조건</td></tr>)}</tbody></table></div>
 <h4>공간 공백 조건에 맞춘 후속 가림 평가</h4>
 <p>{support.gap_backtest.definition}</p><p>{support.gap_backtest.preregistered_policy}</p>
 <p>경계 안 이용 대여소 {count(support.gap_backtest.eligibility.active_located)}곳 중 사전 공간 조건 충족 {count(support.gap_backtest.eligibility.eligible)}곳. 원래 실패 결과는 아래에 보존합니다.</p>
 {!support.gap_backtest.available?<p>{support.gap_backtest.message}</p>:<div className="table-wrap"><table><thead><tr><th>선택 방식</th><th>대상수</th><th>근처 후보 없음</th><th>후보는 있으나 TOP10 밖</th><th>복구</th><th>수요순위만 복구</th></tr></thead><tbody>
 {support.gap_backtest.folds.map((r:any)=><tr key={r.fold+r.seed}><td>{r.fold==='gap_high_usage'?'조건 충족 중 이용 상위':'조건 충족 중 무작위 표본'} · {r.seed}</td><td>{r.target_count}</td><td>{r.no_candidate_nearby}</td><td>{r.feasible_not_top10}</td><td>{r.full.hits}/{r.target_count}</td><td>{r.demand_only.hits}/{r.target_count}</td></tr>)}</tbody></table></div>}
 <p>표본을 바꿔 좋은 결과만 택하지 않습니다. 낮은 복구율은 기존 후보 순위의 한계이며 신규 수요 예측이나 운영 효과 검증 성공을 뜻하지 않습니다.</p>
 </div>{locations.length>0&&<h4>역 주변 대여소 확인</h4>}
 {locations.length?<><label id={'validation-anchor-'+data.city}>역 선택 <select aria-label="검증 점검 역" value={anchorName} onChange={e=>{setAnchorName(e.target.value);setSelectedStation(undefined)}}><option value="">주변 대여소를 볼 역 선택</option>{locations.map((r:any)=><option key={r.anchor_name}>{r.anchor_name}</option>)}</select></label>
 {chosen&&<><p>{chosen.anchor_name} · 공통2025년12월 승하차 {count(chosen.transit_total)}명 / 주변 자전거 활동 {count(chosen.bike_activity)}건</p>
 <MapContainer key={data.city+chosen.anchor_name} center={[chosen.latitude,chosen.longitude]} zoom={15} style={{height:300}} scrollWheelZoom={false}><TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>
 <CircleMarker center={[chosen.latitude,chosen.longitude]} radius={9} pathOptions={{color:'#173f6c',fillColor:'#2878c5',fillOpacity:.8}}><Tooltip>{chosen.anchor_name} · 지하철역</Tooltip></CircleMarker>
 {chosen.nearby_stations.map((s:any)=><CircleMarker key={s.station_id} center={[s.latitude,s.longitude]} radius={6} pathOptions={{color:'#c86c18',fillOpacity:.8}} eventHandlers={{click:()=>setSelectedStation(s)}}><Tooltip>{s.station_name||s.station_id} · 12월 대여 {count(s.rental_count||0)}건</Tooltip></CircleMarker>)}</MapContainer>
 <p>파랑: 선택 역 · 주황: 실제500m 내 대여소. 지도 점이나 목록을 누르면 아래에서12월 지표를 확인합니다.</p>
 <div className="table-wrap"><table><thead><tr><th>주변 대여소</th><th>역 거리(m)</th><th>12월 대여/반납</th></tr></thead><tbody>{chosen.nearby_stations.map((s:any)=><tr key={s.station_id}><td><button onClick={()=>setSelectedStation(s)}>{s.station_name||s.station_id}</button></td><td>{s.distance_to_selected_anchor_m.toFixed(1)}</td><td>{count(s.rental_count||0)}/{count(s.return_count||0)}</td></tr>)}</tbody></table></div>
 {selectedStation&&<p>선택 {selectedStation.station_name||selectedStation.station_id}: 2025-12 대여 {count(selectedStation.rental_count||0)}건 · 반납 {count(selectedStation.return_count||0)}건 · 역 거리 {selectedStation.distance_to_selected_anchor_m.toFixed(1)}m. <Link to={'/stations?'+query}>12월 대여소 상세</Link></p>}
 <Link to={'/agent?'+aiQuery}>선택한 12월 근거로 AI 보고서</Link></>}</>:null}
 </section>
}
