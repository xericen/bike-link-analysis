import {useEffect,useState} from 'react'
import type {DateFilter} from '../types'
const names:Record<string,string>={seoul:'서울',daejeon:'대전',sejong:'세종'}
const pct=(v:number|null|undefined)=>v==null?'미산출':(v*100).toFixed(2)+'%'
const methods:Record<string,string>={score:'점수순',greedy:'탐욕법',mclp:'MCLP'}
export function AdvancedResearch({city,filter}:{city:string;filter:DateFilter}){
 const [value,setValue]=useState<any>(),[error,setError]=useState(''),[k,setK]=useState(3),[objective,setObjective]=useState('gap_area')
 const scope=city==='all'||(filter.start==='2025-12-01'&&filter.end==='2025-12-31')?'common':'individual'
 const mount=import.meta.env.BASE_URL.replace(/\/$/,'')
 useEffect(()=>{const c=new AbortController();setValue(undefined);setError('')
 fetch(mount+'/api/advanced-research?'+new URLSearchParams({city,scope,date_start:filter.start,date_end:filter.end}),{signal:c.signal,cache:'no-store'}).then(async r=>{const v=await r.json();if(!r.ok)throw new Error(v.detail||'연구 검증 조회 실패');return v}).then(setValue).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
 return()=>c.abort()
 },[city,filter.start,filter.end,scope,mount])
 if(error)return <p role="alert">{error}</p>
 if(!value)return <p role="status">입지 최적화·신뢰구간 결과 조회 중…</p>
 return <section className="panel advanced-research research-section"><div className="panel-heading"><div><h2>같은 수를 설치할 때, 어디가 더 효과적일까요?</h2><p className="research-intro">선택 방법에 따라 추가로 닿는 면적과 주변 이용량을 비교합니다.</p></div></div>
 <p>{value.period_start} ~ {value.period_end} · {scope==='common'?'세 도시 공통 기간':'선택 도시 전체 기간'} · 실험 결과이며 기존 추천 순위는 유지합니다.</p>
 <label className="research-filter">설치 수 <select aria-label="최적화 설치 수" value={k} onChange={e=>setK(Number(e.target.value))}>{[1,2,3].map(n=><option key={n} value={n}>{n}개</option>)}</select></label>{' '}
 <label className="research-filter">비교 기준 <select aria-label="최적화 목적" value={objective} onChange={e=>setObjective(e.target.value)}><option value="gap_area">추가 접근 면적</option><option value="nearby_observed_demand">주변 관측 이용</option></select></label>
 {value.cities.map((c:any)=>{const row=c.location.comparisons?.find((r:any)=>r.k===k&&r.objective===objective),ci=c.headline_ci,m=c.explanation
 return <section className="research-city" key={c.city}><h3>{names[c.city]}</h3>
 <p>역·BRT 근처에서 시작하거나 끝난 이용 {pct(ci.estimate)} · 날짜별 변동 95% 구간 {pct(ci.lower)} ~ {pct(ci.upper)}</p>
 {row&&<><p>후보 {c.location.original_candidates}곳 중 공간 조건으로 줄인 {c.location.reduced_candidates}곳 안에서 비교 · {row.solver.proven_optimal?'최적성 확인':'최적성 미확인'}</p>
 <div className="table-wrap"><table><thead><tr><th>선택 방법</th><th>추가 면적(km²)</th><th>주변 대여(중복 제거)</th><th>같은 목적 최적해 대비</th></tr></thead><tbody>{Object.entries(row.methods).map(([name,v]:[string,any])=><tr key={name}><td>{methods[name]}</td><td>{(v.gap_area_m2/1e6).toFixed(4)}</td><td>{v.nearby_rentals_unique.toLocaleString()}건</td><td>{pct(v.optimal_fraction)}</td></tr>)}</tbody></table></div>
 <details><summary>선정 위치와 계산 조건</summary><p>{c.location.demand_definition}</p><p>{c.location.area_definition}</p>{Object.entries(row.methods).map(([name,v]:[string,any])=><p key={name}>{methods[name]}: {v.sites.join(' · ')}</p>)}<p>앵커 1,500m 이내, 최대60개 후보. 최적성은 축소한 후보 집합 안에서만 성립합니다. 실제 설치 효과는 검증하지 않았습니다.</p></details></>}
 <details><summary>날짜에 따라 지표가 얼마나 달라지나요?</summary><p>{ci.interpretation}</p><p>{ci.limitation}</p><p>연월별 관측일 수 고정 · 주블록 2,000회 · 관측 누락 {ci.missing_days}일</p></details>
 {m.available&&<details><summary>관측 수요 설명 모델의 검증 결과</summary><p>훈련 종료 {m.train_end} · 검증 시작 {m.test_start} · 훈련 기간 고이용 대여소 50곳</p><p>평균 절대 오차: 설명 모델 {m.mae.toFixed(2)}건 / 단순 대여소 평균 {m.baseline_station_mean_mae.toFixed(2)}건 · {m.mae>m.baseline_station_mean_mae?'기준모델보다 오차가 큽니다.':'이 검증 구간에서는 오차가 작습니다.'}</p><p>{m.interpretation}</p><img alt={names[c.city]+' 설명 모델 변수 중요도와 부분 의존'} src={mount+'/assets/bike-link/advanced/model-'+c.city+'.png'} style={{maxWidth:'100%'}}/>{m.limitations.map((t:string)=><p key={t}>{t}</p>)}</details>}
 </section>})}
 <details><summary>대용량 처리 실측 · 별도 대전 OD 집계 실험</summary><p>pandas와 Spark가 같은 결과를 냈는지 검증했습니다. 단일 서버 local[2]의 집계 단계이며 전체 정규화나 분산 클러스터 성능은 아닙니다.</p><img alt="pandas와 Spark 데이터 크기·파티션별 처리 시간" src={mount+'/assets/bike-link/advanced/benchmark.png'} style={{maxWidth:'100%'}}/></details>
 <details><summary>Solar 보고서 평가 · 별도 전체 기간 실험</summary><p>3개 도시 × 근거 유무 × 2회, 최대12호출. 응답률·명시적 근거의 값/단위/기간 일치와 출력 형식 준수를 따로 평가했습니다. 자유 서술 전체의 사실성을 보증하지 않습니다.</p>{value.agent_evaluation?.summary?.map((r:any)=><p key={r.condition}>{r.condition==='grounded'?'실제 도구 근거 제공':'근거 미제공'} · 응답 범위 {pct(r.answer_coverage)} · 인용 근거 일치 {pct(r.citation_rate)} · field 형식 준수 {pct(r.schema_field_match_rate)}</p>)}</details>
 <p>{value.relocation.reason}</p>
 </section>
}

export function HeadlineCI({city,filter}:{city:string;filter:DateFilter}) {
 const [ci,setCI]=useState<any>();const mount=import.meta.env.BASE_URL.replace(/\/$/,'')
 useEffect(()=>{let active=true;setCI(undefined);const scope=city==='all'||(filter.start==='2025-12-01'&&filter.end==='2025-12-31')?'common':'individual'
 fetch(mount+'/api/advanced-research?'+new URLSearchParams({city,scope,date_start:filter.start,date_end:filter.end}),{cache:'no-store'}).then(r=>r.ok?r.json():undefined).then(v=>{if(active)setCI(v?.headline_ci)}).catch(()=>{})
 return()=>{active=false}},[city,filter.start,filter.end,mount])
 return ci?<p className="muted">역·BRT 인접 이동 비중의 날짜별 변동 95% 구간: {pct(ci.lower)} ~ {pct(ci.upper)} · 실제 환승률의 오차 범위는 아닙니다.</p>:null
}
