import {HeadlineCI} from '../components/AdvancedResearch'
import { analysisFetch } from '../services/individual'
import {useEffect,useState} from 'react'
import {Link,useSearchParams} from 'react-router-dom'
import {TransitDashboardMap} from '../components/TransitLinkage'
import {RegionComparison} from './RegionComparison'
import {ErrorBox,Skeleton,number} from '../components/State'
import type {DateFilter,Station} from '../types'
type Linkage={stations:Station[];goal_metrics:{anchor_label:string;anchor_300m_ratio:number;outside_500m_active_count:number;linked_trip_share:number}}
type Candidate={station_id:string;station_name?:string;rental_count:number;nearest_stop_distance_m:number}
export function ResearchOverview({regionId,filter}:{regionId:string;filter:DateFilter}){
 const [params]=useSearchParams()
 const [recovery,setRecovery]=useState<number|null>(null)
 const [data,setData]=useState<Linkage>(),[top,setTop]=useState<Candidate[]>([]),[error,setError]=useState('')
 useEffect(()=>{const controller=new AbortController();setData(undefined);setTop([]);setRecovery(null);setError('')
 const q=new URLSearchParams({city:regionId,date_start:filter.start,date_end:filter.end})
 const get=async(path:string)=>{const r=await analysisFetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/'+path+'?'+q,{signal:controller.signal});const v=await r.json();if(!r.ok)throw new Error(v.detail||'조회 실패');return v}
 Promise.all([get('transit-linkage'),get('improvement-ranking')]).then(([l,v])=>{setData(l);setTop(v.ranking.slice(0,3));setRecovery(v.scenario?.uncovered_recovery_ratio??null)}).catch(e=>{if(e.name!=='AbortError')setError(e.message)});return()=>controller.abort()
 },[regionId,filter.start,filter.end])
 if(error)return <ErrorBox message={error}/>
 if(!data)return <Skeleton/>
 const m=data.goal_metrics
 return <><div className="page-heading"><div><h2>한눈에 보기</h2><p>실제 이용이 있지만 대중교통 거점과 먼 곳을 찾고, 공간 보완 가능성을 검토합니다.</p></div></div>
 <div className="stats">
 <div className="stat"><span>계산 · {m.anchor_label} 300m 내 대여소</span><strong>{(m.anchor_300m_ratio*100).toFixed(3)}%</strong></div>
 <div className="stat"><span>계산 · 거점 500m 밖 이용 대여소</span><strong>{number(m.outside_500m_active_count)}</strong></div>
 <div className="stat"><span>관측·계산 · 거점 인접 이동 비중</span><strong>{m.linked_trip_share==null?'N/A':(m.linked_trip_share*100).toFixed(2)+'%'}</strong><em>실제 환승률이 아닙니다</em></div>
 <div className="stat"><span>시나리오 · 접근 공백 면적 보완율</span><strong>{recovery==null?'N/A':(recovery*100).toFixed(2)+'%'}</strong><em>실제 교통 개선 효과가 아닙니다</em></div></div>
 <HeadlineCI city={regionId} filter={filter}/><section className="panel"><h3>자전거와 대중교통 연결 공백 지도</h3><TransitDashboardMap city={regionId} start={filter.start} end={filter.end} stations={data.stations}/></section>
 <section className="panel"><h3>개선 우선 검토 TOP 3</h3><p>거점까지 거리·실제 수요·공간 보완 면적을 함께 본 도시 내 순위입니다.</p>
 {top.map((c,i)=><article key={c.station_id} className="coverage-card"><b>{i+1}위 · {c.station_name||c.station_id}</b><p>최근접 {m.anchor_label} {(c.nearest_stop_distance_m).toFixed(1)}m · 관측 대여 {number(c.rental_count)}건</p>
 <Link to={'/improvements?station='+encodeURIComponent(c.station_id)}>선정 근거와 후보 상세</Link></article>)}</section>
 <details className="panel" open={params.get('comparison')==='1'}><summary>서울·대전·세종 간단 비교</summary><RegionComparison filter={filter}/></details></>
}
