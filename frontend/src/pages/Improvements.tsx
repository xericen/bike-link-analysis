import {AdvancedResearch} from '../components/AdvancedResearch'
import {MethodValidation} from '../components/MethodValidation'
import {useState} from 'react'
import {useSearchParams} from 'react-router-dom'
import {TransitPanel} from '../components/TransitPanel'
import {PlanningPanel} from '../components/PlanningPanel'
import {DecisionStudy} from '../components/DecisionStudy'
import {CandidateEvidence} from '../components/CandidateEvidence'
import type {DateFilter} from '../types'
export function Improvements({regionId,filter}:{regionId:string;filter:DateFilter}){
 const [simple,setSimple]=useState(true)
 const [tab,setTab]=useState<'existing'|'new'|'relocation'>('existing')
 const [params]=useSearchParams(),station=params.get('station')
 return <div className={'improvements-page '+(simple?'easy-improvement':'')}><h2>개선 지역 찾기</h2>
 <p>자전거 연결을 보완하거나 운영을 점검할 곳입니다. 설치·재배치가 확정된 곳은 아닙니다.</p>
 <nav className="improvement-reading-mode" aria-label="화면 설명 수준"><button aria-pressed={simple} className={simple?'active':''} onClick={()=>setSimple(true)}>핵심만 보기</button><button aria-pressed={!simple} className={!simple?'active':''} onClick={()=>setSimple(false)}>분석 근거까지 보기</button></nav>
 {simple&&<p className="simple-improvement-note">① 유형 선택 → ② 지도와 우선3곳 확인 → ③ 관심 있는 곳의 상세 확인</p>}<div className="compare-controls" role="tablist" aria-label="개선 판단 구분">
 {(['existing','new','relocation'] as const).map((t,i)=><button key={t} role="tab" aria-selected={tab===t} className={tab===t?'button-primary':'button-link'} onClick={()=>setTab(t)}>{['기존 대여소 보완','새 대여소 후보','자전거 재배치 점검'][i]}</button>)}</div>
 <p>{tab==='existing'?'실제 이용이 있지만 지하철역·BRT에서 먼 곳입니다.':tab==='new'?'교통거점·대여소가 드문 곳 중 주변 수요와 시설을 확인합니다.':'대여·반납 차이가 큰 곳을 점검합니다. 실제 자전거 부족을 뜻하지 않습니다.'}</p>
 {tab==='existing'?<TransitPanel city={regionId} start={filter.start} end={filter.end} compact={simple}/>:<PlanningPanel city={regionId} start={filter.start} end={filter.end} mode={tab} compact={simple}/>}
 {!simple&&tab==='new'&&<DecisionStudy city={regionId} start={filter.start} end={filter.end}/>}
 {station&&tab==='existing'&&<CandidateEvidence city={regionId} station={station} filter={filter}/>}
 <AdvancedResearch city={regionId} filter={filter}/>{regionId==='all'&&<MethodValidation city={regionId}/>}</div>
}
