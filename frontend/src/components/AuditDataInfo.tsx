import { analysisFetch } from '../services/individual'
import {useEffect,useState} from 'react'
import {api} from '../services/api'
import type {DateFilter,DataSource} from '../types'
export function AuditDataInfo({regionId,filter}:{regionId:string;filter:DateFilter}){
 const [sources,setSources]=useState<DataSource[]>([]),[status,setStatus]=useState('확인 중'),[revision,setRevision]=useState('')
 useEffect(()=>{let active=true;setSources([]);setStatus('확인 중');setRevision('')
 Promise.all([api.sources(regionId),analysisFetch(import.meta.env.BASE_URL.replace(/\/$/,'')+'/api/readiness').then(r=>{if(!r.ok)throw new Error();return r.json()})])
 .then(([s,r])=>{if(active){setSources(s.data_sources);const c=r.cities[regionId];setStatus(c?.aggregates_ready&&c?.decision_evidence_ready&&c?.date_start===filter.start&&c?.date_end===filter.end?'자료·사전 집계·후보 근거 일치':'선택 기간의 후보 근거 패키지 또는 집계 재검증 필요');setRevision(c?.revision||r.revision)}})
 .catch(()=>{if(active)setStatus('자료 상태 확인 실패')});return()=>{active=false}
 },[regionId,filter.start,filter.end])
 return <details className="panel data-information"><summary><span>분석에 사용한 자료</span><small>관측 기간 · 출처 · 해석할 때 주의할 점</small></summary>
 <p>선택 관측 기간: {filter.start} ~ {filter.end} · {status}</p><details className="research-detail"><summary>자료 버전 확인</summary><p>{revision||'확인 불가'}</p></details>
 <p>관측: 공개 이용 기록. 계산: 거리·중심성·군집. 시나리오: 버퍼 면적. AI: 도구 근거의 해석과 제안.</p>
 <p>공간 보완율은 실제 환승률·이용량 증가율이 아닙니다. 재고·거치 용량이 없어 재배치 필요 수량은 산출하지 않습니다.</p>
 <p>세종 이용 이력과 2026년 5월 위치 마스터는 시점이 다르며 과거 위치 동일성은 미검증입니다. 위치·시설·인구 자료의 기준일은 각 원본에 따릅니다.</p>
 {sources.map(s=><p key={s.source_id}><a href={s.source_url||undefined} target="_blank" rel="noreferrer">{s.dataset_name}</a> · {s.verification_status} · 수집 {s.collected_at||'미확인'} · 원본 기간 {s.date_start||'미확인'} ~ {s.date_end||'미확인'}</p>)}
 <a href={import.meta.env.BASE_URL+'status'}>출처·품질 전체표</a>
 </details>
}
