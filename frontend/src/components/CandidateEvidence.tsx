import {useEffect,useState} from 'react'
import {Link} from 'react-router-dom'
import {api} from '../services/api'
import type {DateFilter} from '../types'
export function CandidateEvidence({city,station,filter}:{city:string;station:string;filter:DateFilter}){
 const [value,setValue]=useState<{usage:string;cluster:string;similar:string}>(),[error,setError]=useState('')
 useEffect(()=>{let active=true;setValue(undefined);setError('')
 Promise.all([api.hiddenHubs(city,filter.start,filter.end),api.station(city,station,filter.start,filter.end),api.similarity(city,station,filter.start,filter.end)])
 .then(([h,s,similar])=>{if(active){const r=h.candidates.find(x=>x.station_id===station);setValue({usage:r?'이용량 '+r.usage_rank+'위 / PageRank '+r.pagerank_rank+'위 · 순위 차이 '+r.rank_gap:'선택 기간 연결 순위 미확보',cluster:s.cluster?.role||'군집 미확보',similar:JSON.stringify(similar)})}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}
 },[city,station,filter.start,filter.end])
 return <section className="panel"><h3>후보의 이용 역할 교차 확인 · {station}</h3><p>공간·수요 순위에 가산하지 않고 별도의 판단 근거로 확인합니다.</p>
 {error?<p role="alert">{error}</p>:!value?<p role="status">실제 연결·군집·유사 패턴 조회 중…</p>:<><p>계산 · {value.usage}</p><p>이용 패턴 군집: {value.cluster}. 군집은 네트워크 역할이나 이용 목적을 확정하지 않습니다.</p><details><summary>유사 대여소 · 정규화 패턴 근거</summary><pre>{value.similar}</pre></details></>}
 <Link to={'/stations?station='+encodeURIComponent(station)}>대여소·기간 안정성 상세</Link> · <Link to={'/network?station='+encodeURIComponent(station)}>주요 OD 연결 확인</Link> · <Link to={'/agent?station='+encodeURIComponent(station)+'&prompt='+encodeURIComponent(station+'의 개선 검토 근거와 추가 확인 사항을 설명해줘')}>선택 대여소 AI 보고서</Link>
 </section>
}
