import {useEffect,useState} from 'react'
import {EvidencePanels,EvidenceLinks} from './EvidencePanels'
const names:Record<string,string>={seoul:'서울',daejeon:'대전',sejong:'세종'}
const pct=(v:number|null)=>v==null?'미확인':(v*100).toFixed(1)+'%'
const minutes=(v:number|null|undefined)=>v==null?'미확인':v.toFixed(1)+'분'
export function Conclusion({regionId}:{regionId:string}){
 const [scope,setScope]=useState('individual'),[data,setData]=useState<any>(),[error,setError]=useState(''),[metric,setMetric]=useState('anchor_linked_ratio')
 const mount=import.meta.env.BASE_URL.replace(/\/$/,'')
 useEffect(()=>setScope('individual'),[regionId])
 useEffect(()=>{const c=new AbortController();setData(undefined);setError('')
 fetch(mount+'/api/conclusion?'+new URLSearchParams({city:scope==='common'?'all':regionId,scope}),{signal:c.signal,cache:'no-store'}).then(async r=>{const v=await r.json();if(!r.ok)throw new Error(v.detail||'결론 조회 실패');return v}).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
 return()=>c.abort()},[regionId,scope,mount])
 return <div className="conclusion-page">
 <div className="page-heading"><div><h2>분석 결론</h2><p>공통 기간의 차이와 도로망 연결 경로를 바탕으로, 먼저 검토할 지역을 정리했습니다.</p></div></div>
 <div className="improvement-reading-mode"><button className={scope==='individual'?'active':''} onClick={()=>setScope('individual')}>{names[regionId]} 전체 기간</button><button className={scope==='common'?'active':''} onClick={()=>setScope('common')}>세 도시 공통 10개월</button></div>
 {error?<p role="alert">{error}</p>:!data?<p role="status">분석값과 경로 점검을 불러오는 중입니다…</p>:<>
 <section className="panel conclusion-lead"><span className="source-pill">{data.period_label}</span><h3>대중교통 연결 공백을 찾고, 공유자전거가 보완할 수 있는 조건을 분석했습니다.</h3><p>{data.project_goals.summary}</p></section>
 <EvidenceLinks data={data.evidence_dashboard}/>
 <section className="panel goal-conclusions"><h3>프로젝트 목표별 분석 결론</h3><p>다섯 가지 목표에 대해 확인한 결과와 남은 검증을 함께 정리했습니다.</p>
 <div className="goal-conclusion-grid">{data.project_goals.items.map((g:any)=><article className="goal-conclusion-card" key={g.number}><div className="panel-heading"><h4>{g.number}. {g.title}</h4><span className="goal-status">{g.status}</span></div><p>{g.finding}</p><p className="goal-evidence">{g.evidence}</p><details><summary>원래 목표와 남은 검증</summary><p>{g.objective}</p><p>{g.remaining}</p></details></article>)}</div></section>
 <EvidencePanels data={data.evidence_dashboard}/>
 <section className="panel"><h3>같은 기간으로 다시 비교했습니다</h3><p>{data.common_label} · 세 도시 각306일 관측. 날짜가 불완전한 2·3월은 이 비교에서 제외했습니다.</p>
 <label className="research-filter">비교 지표 <select aria-label="결론 도시 비교 지표" value={metric} onChange={e=>setMetric(e.target.value)}><option value="anchor_linked_ratio">역·BRT 인접 이용 비중</option><option value="daily_average">하루 평균 이용</option><option value="unknown_endpoint_ratio">위치 미연결 이동 비중</option></select></label>
 <div className="table-wrap ranking-scroll"><table className="data-table"><thead><tr><th>월</th>{Object.entries(names).map(([c,n])=><th key={c}>{n}</th>)}</tr></thead><tbody>{data.comparison.map((r:any)=><tr key={r.month}><td>{r.month}</td>{Object.keys(names).map(c=><td key={c}>{metric==='daily_average'?r.cities[c][metric].toLocaleString('ko-KR',{maximumFractionDigits:0})+'건/일':pct(r.cities[c][metric])}</td>)}</tr>)}</tbody></table></div>
 <p className="muted">서울·대전은 지하철, 세종은 BRT 기준입니다. 비중은 실제 환승률이 아니며 도시 규모·교통수단 차이를 운영 성과 순위로 해석하지 않습니다.</p></section>
 {data.cities.map((c:any)=><section className="panel conclusion-city" key={c.city}><h3>{names[c.city]} · 우선 검토할 신규 후보 3곳</h3><p>{c.period_label}</p><p className="muted">{c.selection_rule} 월별 반복성은 관측 날짜가 완전한 달만 계산합니다.</p>
 <div className="conclusion-findings">{c.findings.map((f:string)=><p key={f}>{f}</p>)}</div>
 {c.additional_validation?.routes&&<details><summary>상위 5곳 추가 경로 검토</summary><p className="muted">원래 점수순을 유지합니다. 별도 검토순서는 확인된 대안 중 대여·반납 2분 가정에서 도보보다 빠른 연결만 포함합니다. 전체 여정·실제 통행시간은 아닙니다.</p><div className="table-wrap ranking-scroll"><table className="data-table"><thead><tr><th>원래 순위</th><th>후보 ID</th><th>경로 판단</th><th>별도 검토순서</th><th>도보 → 연계 모델</th></tr></thead><tbody>{c.additional_validation.routes.checks.map((r:any)=><tr key={r.site_id}><td>{r.original_rank}</td><td>{r.site_id}</td><td>{r.status_label}</td><td>{r.review_rank||'보류'}</td><td>{r.before_minutes==null?'미확인':r.before_minutes.toFixed(1)+'분'} → {r.after_minutes==null?'미확인':r.after_minutes.toFixed(1)+'분'}</td></tr>)}</tbody></table></div></details>}
 {c.completion?.journey_rows&&<details><summary>대기시간까지 포함하면?</summary><p className="muted">대전 현행 평일 시간표를 적용한 대표 여정입니다. 출발 후보에서 반석역 출구까지 비교하며2025년 실제 여정 재현은 아닙니다. 대여·반납2분,역 진입·출구 각2분은 가정입니다. 철도 간 환승은 없는 여정입니다.</p><div className="table-wrap ranking-scroll"><table className="data-table"><thead><tr><th>기존 후보</th><th>출발 시각</th><th>승차역</th><th>도보 접근 시 대기</th><th>자전거 접근 시 대기</th><th>도보 + 지하철</th><th>자전거 + 지하철</th><th>차이</th></tr></thead><tbody>{c.completion.journey_rows.map((r:any,i:number)=><tr key={i}><td>{r.original_rank}순위</td><td>{r.departure}</td><td>{r.anchor}</td><td>{r.wait_before.toFixed(1)}분</td><td>{r.wait_after.toFixed(1)}분</td><td>{r.before.toFixed(1)}분</td><td>{r.after.toFixed(1)}분</td><td>{r.gain===0?'같음':Math.abs(r.gain).toFixed(1)+'분 '+(r.gain>0?'빠름':'느림')}</td></tr>)}</tbody></table></div><p className="muted">같은 열차를 타면 접근시간이 달라도 도착시간은 같을 수 있습니다. 한 노선의 모델이며 전체 교통망의 최단 여정·실측 통행시간은 아닙니다.</p></details>}
 {c.completion?.dock_master&&<details><summary>반납 대여소의 공식 거치대 정보</summary><p className="muted">2026년6월 공식 자료입니다. 당시 재고·2025년 거치 용량·신규 설치 가능성은 미확인입니다.</p><div className="table-wrap"><table className="data-table"><thead><tr><th>반납 대여소 ID</th><th>공식 명칭</th><th>LCD 거치대</th><th>QR 거치대</th></tr></thead><tbody>{c.completion.dock_master.map((r:any)=><tr key={r.site_id}><td>{r.dock_station_id}</td><td>{r.official_master?.name||'연결 미확인'}</td><td>{r.official_master?.lcd_rack_count??'미표기'}</td><td>{r.official_master?.qr_rack_count??'미표기'}</td></tr>)}</tbody></table></div></details>}
 <div className="conclusion-candidates">{c.candidates.map((s:any)=><article className="conclusion-candidate" key={s.site_id}>
 <div className="panel-heading"><h4>{s.rank}순위 · {s.district}</h4><span className={s.route.status==='model_connected'?'route-state connected':'route-state pending'}>{s.route.status==='model_connected'?'모델 경로 연결':'연결 확인 보류'}</span></div>
 <p>{s.route.anchor_name} 인근 · <a href={'https://www.openstreetmap.org/?mlat='+s.latitude+'&mlon='+s.longitude+'#map=17/'+s.latitude+'/'+s.longitude} target="_blank" rel="noreferrer">후보 위치 보기 ↗</a></p>
 <dl className="conclusion-facts"><div><dt>주변 1km 관측 대여</dt><dd>{s.nearby_rentals_1000m.toLocaleString()}건</dd></div><div><dt>월별 상위10위 재등장</dt><dd>{s.top10_months}/{s.eligible_months}개월</dd></div><div><dt>공간 모델상 추가 면적</dt><dd>{(s.potential_added_area_m2/1e6).toFixed(4)} km²</dd></div><div><dt>주변 500m 공개 시설</dt><dd>{s.facilities_within_500m}곳</dd></div></dl>
 <div className="connection-chain"><span>후보지</span><b>→</b><span>{s.route.dock_station_name||s.route.dock_station_id||'반납 대여소 미확인'}</span><b>→</b><span>{s.route.anchor_name}</span></div>
 <p>직접 도보 모델 {minutes(s.route.before_minutes)} · 자전거 연계 모델 {minutes(s.route.after_minutes)}</p><p className="muted">연계 모델은 자전거 이동·반납소→역 도보·대여/반납 2분 가정을 합한 값입니다. 실제 통행시간이 아닙니다.</p>
 <p className="candidate-action">{s.action}</p>
 <details><summary>근거와 현장 확인 항목</summary><p>{s.observed_demand_label}</p><p>{s.route.message}</p><p>도로망 조회일: {s.route_data_dates.join(' / ')||'미확인'}</p><p>최근접 앵커까지 직선거리 {s.route.straight_to_anchor_m.toFixed(0)}m · {s.site_id}</p><p>{s.unchecked.join(' · ')}</p><p>월별 순위: {s.monthly_ranks.map((r:any)=>r.month+' '+r.rank+'위').join(' / ')}</p></details>
 </article>)}</div>
 <details><summary>이동시간 기준을 바꾸면?</summary>{c.time_threshold_sensitivity.map((r:any)=><p key={r.minutes}>모델상 {r.minutes}분 이내: {r.candidate_count}/{r.evaluated}곳 · 연결 확인 후보만 계산</p>)}</details>
 </section>)}
 <section className="panel conclusion-next"><h3>최종 판단과 다음 단계</h3><p>{data.project_goals.final_judgment}</p><p>반복되는 관측 수요와 연결 경로는 현장 검토의 근거가 됩니다. 부지·통행·반납 용량을 확인한 뒤 설치 여부를 판단해야 합니다.</p><p>재배치는 과거 재고와 거치 용량이 없어 검토 후보로 유지합니다. 실제 환승 증가와 설치 후 이용량 증가는 아직 확인하지 못했습니다.</p><details><summary>자료 기준과 검증 범위</summary>{data.limitations.map((r:string)=><p key={r}>{r}</p>)}<p>{data.attribution} · <a href={data.route_source} target="_blank" rel="noreferrer">경로 자료</a> · <a href="https://www.openstreetmap.org/fixthemap" target="_blank" rel="noreferrer">지도 오류 제보</a></p></details></section>
 </>}
 </div>
}
