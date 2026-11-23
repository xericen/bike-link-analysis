import {IndividualRecovery} from './IndividualRecovery'
import {BreadthProgress} from './BreadthProgress'
import {RecoveryProgress} from './RecoveryProgress'
import {ValidationReview} from './ValidationReview'
import {useEffect,useState} from 'react'
const colors:Record<string,string>={high_high:'#2869bf',high_low:'#d87919',low_high:'#168779',low_low:'#8a97a8'}
const names:Record<string,string>={seoul:'서울',daejeon:'대전',sejong:'세종'}
const pct=(n:number|null|undefined)=>n==null?'N/A':(n*100).toFixed(1)+'%'
const n=(v:number)=>v.toLocaleString('ko-KR')
export function MethodValidation({city}:{city:string}){
 const [anchorFocus,setAnchorFocus]=useState<{city:string;name:string}>()
 const [report,setReport]=useState<any>(),[error,setError]=useState(''),[retry,setRetry]=useState(0)
 useEffect(()=>{const controller=new AbortController();setReport(undefined);setError('')
 fetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/method-validation?city='+encodeURIComponent(city)+'&scope='+(city==='all'?'common':'individual'),{signal:controller.signal})
 .then(async r=>{const v=await r.json();if(!r.ok)throw new Error(v.detail||'방법 검증 조회 실패');return v}).then(setReport).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
 return()=>controller.abort()
 },[city,retry])
 if(report?.scope==='individual_full')return <IndividualRecovery data={report}/>
 return <section className="panel method-validation">
 <h2>이 추천은 얼마나 믿을 수 있나요?</h2>
 <p>{city==='all'?'기본 검증은 공통 2025년 12월 자료입니다. 추가 실험은 별도 기간으로 구분해 표시합니다.':'선택 도시의 보유 전체 기간·도시 전역을 조회합니다.'}</p>
 {error?<p role="alert">{error}<button onClick={()=>setRetry(v=>v+1)}>다시 조회</button></p>:!report?<p role="status">오프라인 검증 결과를 조회 중입니다…</p>:<>
 <BreadthProgress data={report.breadth_evaluation}/>
 <div className={report.breadth_evaluation?.available?"advanced-improvement":""}><RecoveryProgress data={report.recovery_evaluation}/></div>
 <p>아래는 기존 방법의 12월 점검입니다. 위의 다방법 탐색 결과와 구분합니다.</p>
 {report.cities.map((c:any)=><section key={c.city}><h3>{names[c.city]} · 12월 확인 결과</h3>
 <div className="simple-validation-summary simple-only">{(()=>{const t=c.backtest.find((r:any)=>r.fold==='high_usage');return t?<><p><strong>12월 위치 재발견: {t.methods.full.hits}/{t.target_count}곳</strong></p><p>원인: 주변에 추천 후보가 없던 곳 {t.target_count-t.feasible_within_match_radius_count}곳 · 후보는 있었으나 복구하지 못한 곳 {t.feasible_within_match_radius_count-t.methods.full.hits}곳</p></>:null})()}{c.demand_matrix.available?<p><strong>연계 여건을 살펴볼 역 {c.demand_matrix.counts.high_low}곳</strong> · 승하차에 비해 주변 자전거 활동이 낮은 역입니다.</p>:<p>12월 BRT 승하차 자료 미확보 · 역별 비교 보류</p>}</div>
 {c.finding_summary?.map((text:string)=><p className="notice advanced-improvement" key={text}>{text}</p>)}
 <p className="advanced-improvement">{report.evaluation_purpose}</p>
 {report.followup_available?<ValidationReview key={c.city} data={c} focus={anchorFocus?.city===c.city?anchorFocus:undefined}/>:<p>{report.followup_message}</p>}
 <div className="advanced-improvement"><section><h4>조건을 바꾸면 상위 후보가 얼마나 유지되나요?</h4>
 <p>기준: 앵커500m·격자500m·균등가중. 지리 중첩은 기준 TOP10과 변경 TOP10의 위치가 300m 안에서 일대일로 대응하는 비율입니다.</p>
 <div className="table-wrap"><table><thead><tr><th>앵커/격자(m)</th><th>가중치·후보 버퍼</th><th>후보 수</th><th>위치 중첩</th><th>추가 면적(km²)</th></tr></thead><tbody>
 {c.sensitivity.map((r:any,i:number)=><tr key={i}><td>{r.anchor_radius_m}/{r.grid_step_m}</td><td>{({equal:'균등',demand:'주변수요 우선',gap:'공백 우선'} as Record<string,string>)[r.policy]} · {r.candidate_buffer_m}m</td><td>{n(r.candidate_count)}</td><td>{pct(r.geographic_top10_overlap)}</td><td>{(r.union_added_area_m2/1e6).toFixed(4)}</td></tr>)}</tbody></table></div>
 <p>후보 버퍼500m는 면적만 바꾸며 점수 입력이 아닙니다. 이 경우 순위 유지 자체를 검증 성과로 세지 않습니다.</p></section>
 <h4>대중교통 수요 × 주변 자전거 활동</h4>
 {!c.demand_matrix.available?<p>{c.demand_matrix.message}</p>:<DemandPlot matrix={c.demand_matrix} onSelect={name=>setAnchorFocus({city:c.city,name})}/>}
 <section><h4>숨긴 실제 대여소를 다시 찾을 수 있나요?</h4>
 <p>숨긴 위치·관련 OD를 모두 제외한 뒤 주변 수요를 재집계했습니다. TOP10 후보와 숨긴 위치를 300m 이내 일대일로 연결합니다. 전체 재발견률이 주 지표입니다. 인접 구역 실험은 1km 격자 안 대여소를 전부 가리므로 N이 다르며, N&gt;10이면 재발견률 상한은 10/N입니다.</p>
 <div className="table-wrap"><table><thead><tr><th>가림 방식</th><th>숨긴 수/후보생성 가능</th><th>전체 방법</th><th>주변수요만</th><th>시설·인구만</th><th>무작위 평균</th></tr></thead><tbody>
 {c.backtest.map((r:any,i:number)=><tr key={i}><td>{({high_usage:'이용 상위',stratified:'이용량 구간 표본',spatial_1km_block:'인접1km 구역'} as Record<string,string>)[r.fold]} · {r.seed}</td><td>{r.target_count}/{r.feasible_within_match_radius_count}</td><td>{r.methods.full.hits}/{r.target_count} ({pct(r.methods.full.recall)})</td><td>{r.methods.demand_only.hits}/{r.target_count}</td><td>{r.methods.facilities_population_only.hits}/{r.target_count}</td><td>{pct(r.random_recall_mean)}</td></tr>)}</tbody></table></div>
 <p>후보를 생성할 수 없는 위치도 전체 분모에서 제외하지 않았습니다. 낮은 결과는 방법의 한계로 공개하며 신규 설치 후 수요·환승 증가를 보증하지 않습니다.</p></section>
 </div></section>)}
 <section className="advanced-improvement"><h4>검증 조건·자료 버전·한계</h4><p>생성 {report.built_at} · 자료 버전 {report.revision}</p>{report.limitations.map((x:string)=><p key={x}>{x}</p>)}</section>
 </>}
 </section>
}
function DemandPlot({matrix:m,onSelect}:{matrix:any;onSelect:(name:string)=>void}){
 const rows=m.rows,maxT=Math.max(1,...rows.map((r:any)=>r.transit_total)),maxB=Math.max(1,...rows.map((r:any)=>r.bike_activity_500m))
 const x=(v:number)=>45+270*Math.log1p(v)/Math.log1p(maxT),y=(v:number)=>205-190*Math.log1p(v)/Math.log1p(maxB)
 const potential=rows.filter((r:any)=>r.quadrant==='high_low').sort((a:any,b:any)=>b.transit_total-a.transit_total).slice(0,5)
 return <><p>도시 내 중앙값: 승하차 {n(m.transit_median)}명 / 자전거 활동 {n(m.bike_median)}건. 점1개=연결된 역1곳, 점선=중앙값, 동률은 높음으로 분류하되 0은 낮음입니다.</p>
 <svg viewBox="0 0 340 250" style={{width:'100%',maxWidth:620}} role="img" aria-label="역별 대중교통 수요와 주변 자전거 활동 사분면">
 <path d="M45 15V205H320" fill="none" stroke="#8595a8"/><path d={`M${x(m.transit_median)} 15V205 M45 ${y(m.bike_median)}H320`} stroke="#9aa9bd" strokeDasharray="4 3"/>
 {rows.map((r:any,i:number)=><circle key={i} cx={x(r.transit_total)} cy={y(r.bike_activity_500m)} r={3.2} fill={colors[r.quadrant]}><title>{r.station_name}: 승하차 {n(r.transit_total)}명 / 자전거 {n(r.bike_activity_500m)}건 · {r.interpretation}</title></circle>)}
 <text x="90" y="233" fontSize="10">지하철 승하차(명, log(1+x) 축)</text><text x="2" y="10" fontSize="9">자전거 활동(건, log(1+x) 축)</text></svg>
 <p>파랑: 두 이용 높음 {m.counts.high_high}곳 · 주황: 대중교통 높음/자전거 낮음 {m.counts.high_low}곳 · 초록: 반대 {m.counts.low_high}곳 · 회색: 두 이용 낮음 {m.counts.low_low}곳</p>
 <p>위치 연결 {m.linked_station_count}개 중 비교 가능한 {m.matched_count}개 역명 기준(원자료 {m.source_station_names}개). 300/500m 분류 유지 {m.radius_comparison?.unchanged_count}/{m.radius_comparison?.common_stations}곳.</p>
 {m.excluded_rows?.map((r:any)=><p key={r.station_name}>분류 보류: {r.station_name} · {r.reason}</p>)}
 <div className="table-wrap"><table><thead><tr><th>연계 여건 점검 예시</th><th>승하차(명)</th><th>자전거(건)</th><th>대여소 수</th><th>대여소당 활동</th></tr></thead><tbody>{potential.map((r:any)=><tr key={r.station_name}><td><button onClick={()=>onSelect(r.station_name)}>{r.station_name} · 지도 확인</button></td><td>{n(r.transit_total)}</td><td>{n(r.bike_activity_500m)}</td><td>{r.bike_station_count_500m}</td><td>{r.bike_per_station==null?'N/A':r.bike_per_station.toFixed(1)}</td></tr>)}</tbody></table></div>
 <p>연계 여건 점검 대상이며 신규 설치 필요를 확정하지 않습니다. 같은 대여소가 여러 역에 중복 포함될 수 있어 역별 활동량을 도시 총량으로 합산하지 않습니다.</p></>
}
