import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../services/api'
import type { ChatResult, DateFilter, RoleCandidatesResult } from '../types'
import { Empty, ErrorBox, Skeleton, number } from '../components/State'
import { PageHeader, StatCard, SectionCard, ReportBlock, SimpleDataTable, SummaryBulletCard, RoleTag } from '../components/AnalysisUI'
import { cityName } from '../services/presentation'

const questions=[
  '이용량은 적지만 연결상 중요한 대여소는 어디인가?',
  '어떤 대여소에 반복적인 순유출이 나타나는가?',
  '어떤 대여소의 중요도가 기간별로 유지되는가?',
  '운영 담당자가 먼저 검토해야 하는 대여소는 어디인가?'
]
type Message={question:string;result:ChatResult;executedAt:string;elapsed:number;context:string}
export function AIAgent({regionId,filter}:{regionId:string;filter:DateFilter}) {
  const [params]=useSearchParams()
  const [question,setQuestion]=useState(questions[0])
  const [history,setHistory]=useState<Message[]>([]),[selected,setSelected]=useState<number|null>(null)
  const [configured,setConfigured]=useState<boolean>(),[error,setError]=useState(''),[loading,setLoading]=useState(false)
  const [candidates,setCandidates]=useState<RoleCandidatesResult>(),[candidateError,setCandidateError]=useState('')
  const context=[regionId,filter.start,filter.end].join('|')
  useEffect(()=>{api.agentStatus().then(x=>setConfigured(x.configured)).catch(e=>setError(e.message))},[])
  useEffect(()=>{let active=true;setCandidates(undefined);setCandidateError('');api.roleCandidates(regionId,filter.start,filter.end).then(x=>{if(active)setCandidates(x)}).catch(e=>{if(active)setCandidateError(e.message)});return()=>{active=false}},[regionId,filter.start,filter.end])
  useEffect(()=>{const prompt=params.get('prompt');if(prompt)setQuestion(prompt)},[params])
  async function submit(event:React.FormEvent) {
    event.preventDefault()
    const text=question.trim()
    if(!text||loading||configured!==true)return
    const submitted=cityName(regionId)+' / 분석 기간: '+(filter.start||'확보된 전체 기간')+' ~ '+(filter.end||'최신 관측일')+'\n'+text
    const started=performance.now(), requestContext=context
    setError('');setLoading(true)
    try {
      const result=await api.chat(submitted)
      const message={question:submitted,result,executedAt:new Date().toLocaleString('ko-KR'),elapsed:(performance.now()-started)/1000,context:requestContext}
      setHistory(old=>{const next=[...old,message];setSelected(next.length-1);return next})
    } catch(e){setError(e instanceof Error?e.message:'분석 요청 실패')} finally{setLoading(false)}
  }
  const active=selected===null?undefined:history[selected], report=active?.result.report
  const hidden=candidates?.types.low_usage_high_connectivity[0], concentrated=candidates?.types.time_concentrated[0], imbalance=candidates?.types.persistent_imbalance[0]
  const operational=[
    ...(candidates?.types.low_usage_high_connectivity||[]).slice(0,2).map(x=>({id:x.station_id,name:x.station_name,focus:'숨은 연결 후보 · 이용 '+number(x.usage_rank)+'위 / PR '+number(x.pagerank_rank)+'위'})),
    ...(candidates?.types.persistent_imbalance||[]).slice(0,2).map(x=>({id:x.station_id,name:x.station_name,focus:'반복 불균형 · 순유출 '+number(x.net_outflow)+'건'})),
    ...(candidates?.types.time_concentrated||[]).slice(0,1).map(x=>({id:x.station_id,name:x.station_name,focus:'시간대 집중 · '+x.peak_hour+'시 / '+(x.peak_hour_share*100).toFixed(1)+'%'}))
  ]
  const tools=[...new Set(active?.result.evidence.map(x=>x.tool)||[])]
  const limitations=['불균형만으로 재고 부족을 확정할 수 없습니다.','중심성만으로 인과적 중요성을 확정할 수 없습니다.',...(report?.limitations||[])]
  return <>
    <PageHeader title="AI 분석 리포트" subtitle="Upstage Solar 기반 근거 중심 분석 요약 · 운영 검토 제안"><RoleTag>{configured===undefined?'연결 확인 중':configured?'Solar API 설정됨':'Solar API 키 미설정'}</RoleTag></PageHeader>
    <div className="stats">
      <StatCard label="분석 대상 도시" value={cityName(regionId)} note="현재 선택한 도시와 기간으로 요청" icon="◎"/>
      <StatCard label="사용 도구 수" value={active?tools.length+'개':'실행 대기'} note="실제 응답에 포함된 도구 기준" tone="mint" icon="⚙"/>
      <StatCard label="핵심 발견 수" value={report?report.key_findings.length+'개':'실행 대기'} note="도구 근거가 있는 보고서 발견" tone="lavender" icon="✦"/>
      <StatCard label="운영 검토 후보 수" value={candidates?.available?new Set([...candidates.types.low_usage_high_connectivity,...candidates.types.persistent_imbalance,...candidates.types.time_concentrated,...candidates.types.role_changed].map(x=>x.station_id)).size.toLocaleString()+'개':'자료 미확보'} note="목적별 후보의 중복 대여소 제외" tone="peach" icon="◈"/>
    </div>
    <div className="report-layout"><div>
      <SectionCard title="질문 입력 및 실행 상태" note="버튼을 누를 때만 Solar 호출">
        <form className="report-question" onSubmit={e=>void submit(e)}><label className="sr-only" htmlFor="report-question">분석 질문</label><input id="report-question" value={question} onChange={e=>setQuestion(e.target.value)} placeholder={questions[0]} disabled={loading}/><button className="button-primary" disabled={loading||configured!==true||!question.trim()}>{loading?'분석 중…':'분석 실행 →'}</button></form>
        <div className="execution-state" role="status"><span className={active?'mini-status good':'mini-status'}>{loading?'분석 요청 및 도구 실행 중':active?'분석 실행 완료':'분석 실행 대기'}</span><span>소요 시간 {active?active.elapsed.toFixed(1)+'초':'—'}</span><span>실행 시각 {active?.executedAt||'—'}</span></div>
        <div className="tool-tags">{(tools.length?tools:['get_hidden_hubs','get_station_imbalance','get_station_role_history']).map(x=><RoleTag key={x}>{x}</RoleTag>)}</div>
        {!active&&<p className="muted">위 태그는 사용 가능한 도구 예시입니다. 실제 사용 도구는 실행 후 표시됩니다.</p>}
        {configured===false&&<div className="notice">UPSTAGE_API_KEY 설정이 필요합니다. 생성된 AI 결과를 대신 표시하지 않습니다.</div>}
        {active&&active.context!==context&&<div className="notice">아래 보고서는 이전 도시 또는 기간의 실행 결과입니다. 현재 조건으로 보려면 다시 분석하세요.</div>}
        {loading&&<Skeleton rows={2}/>}
        {error&&<ErrorBox message={error}/>}
      </SectionCard>
      <SectionCard title="Solar AI 분석 결과" note={active?.result.model||'실행 전 · 보고서 구성 미리보기'}>
        {active&&<div className="report-question-summary">{active.question}</div>}
        <ReportBlock icon="✦" title="핵심 발견" items={report?.key_findings.map(x=>x.label+': '+number(x.value)+' '+x.unit+(x.period?' · '+x.period:''))||[]}/>
        <ReportBlock icon="◷" title="분석 대상 및 기간" items={report?['요청: '+active?.question,'분석 기간: '+(report.periods.join(' ~ ')||'확인된 기간 없음')]:[]}/>
        <ReportBlock icon="▤" title="실제 수치와 근거" items={report?.station_comparison.map(x=>x.station_id+' '+(x.station_name||'이름 미확보')+' · 대여 '+number(x.rental_count)+'건 · '+x.metric+' '+x.centrality+' · 순위 차이 '+number(x.rank_gap))||[]}/>
        <ReportBlock icon="◎" title="운영상 우선 검토 대상" items={report?.recommendations.map(x=>x.feature+' · '+x.action+' / 근거: '+x.evidence)||[]}/>
        <ReportBlock icon="◇" title="추가 검증 필요 사항" items={report?.recommendations.map(x=>x.validation)||[]}/>
        <ReportBlock icon="ⓘ" title="데이터 출처 및 한계" items={report?[...report.sources.map(x=>x.dataset_name+' · '+x.verification_status),...report.limitations]:[]}/>
        {active&&<><details open><summary>Solar 원문 응답과 운영 검토 의견</summary><div className="agent-answer">{active.result.answer}</div></details>
          {active.result.grounding_validation&&<div className="notice"><b>{active.result.grounding_validation.passed?'응답 수치 대조 통과':'응답 수치 불일치 · 검토 필요'}</b><p>검사 {active.result.grounding_validation.checked_numeric_tokens}개 · 일치 {active.result.grounding_validation.matched_numeric_tokens}개</p>{!active.result.grounding_validation.passed&&<p>불일치: {active.result.grounding_validation.unmatched_numeric_tokens.join(', ')}</p>}<p>{active.result.grounding_validation.method}</p></div>}
          <p className="muted">실제 API 호출 1회 · 도구 {active.result.evidence.length}건 · 사용 토큰 {number(active.result.usage.total_tokens)} (입력 {number(active.result.usage.prompt_tokens)} / 출력 {number(active.result.usage.completion_tokens)})</p>
          {report?.sources.map((x,i)=>x.source_url?<p key={i} className="muted"><a href={x.source_url} target="_blank" rel="noreferrer">{x.dataset_name} ↗</a></p>:null)}
        </>}
      </SectionCard>
    </div><aside>
      <SectionCard title="근거 데이터 카드" note="선택 기간 API 결과 · AI 생성 아님">
        {candidateError?<ErrorBox message={candidateError}/>:!candidates?<Skeleton rows={3}/>:<>
        {[{id:hidden?.station_id,name:hidden?.station_name,title:'숨은 연결 거점',value:hidden?'이용 '+number(hidden.usage_rank)+'위 · PageRank '+number(hidden.pagerank_rank)+'위':null,tone:'mint'},{id:concentrated?.station_id,name:concentrated?.station_name,title:'시간대 집중',value:concentrated?concentrated.peak_hour+'시 · '+(concentrated.peak_hour_share*100).toFixed(1)+'%':null,tone:'lavender'},{id:imbalance?.station_id,name:imbalance?.station_name,title:'반복 불균형 거점',value:imbalance?'순유출 '+number(imbalance.net_outflow)+'건':null,tone:'peach'}].map(x=><div className={'evidence-card tone-'+x.tone} key={x.title}><RoleTag>{x.title} 후보</RoleTag><h3>{x.id||'확인된 후보 없음'}</h3><small>{x.name}</small><p>{x.value||'선정 규칙을 충족하는 자료가 없습니다.'}</p>{x.id&&<Link to={'/stations?station='+encodeURIComponent(x.id)}>대여소 분석 ↗</Link>}</div>)}
        <p className="muted">{candidates.period_start||'미확인'} ~ {candidates.period_end||'미확인'}</p></>}
      </SectionCard>
      <SectionCard title="운영 검토 대상 Top 5" note="목적별 표시 순서 · 종합 점수 아님"><SimpleDataTable headers={['순서','대여소','운영 검토 초점']} rows={operational.slice(0,5).map((x,i)=>[i+1,<Link to={'/stations?station='+encodeURIComponent(x.id)} title={x.name||x.id}>{x.id}</Link>,x.focus])}/></SectionCard>
      <SectionCard title="분석 기록" note={history.length+'회 · 현재 세션'}>{history.length?<div className="agent-history">{history.map((x,i)=><button key={i} className={selected===i?'selected':''} onClick={()=>setSelected(i)}><span>{x.question}</span><small>{x.executedAt} · {number(x.result.usage.total_tokens)} 토큰</small></button>)}</div>:<Empty>직접 실행한 분석이 없습니다.</Empty>}</SectionCard>
    </aside></div>
    <div className="grid-three">
      <SectionCard title="도구 호출 요약" note={active?'실제 완료 내역':'아직 호출되지 않음'}>
        <SimpleDataTable headers={['function','역할 / 입력','실행 결과']} rows={(active?.result.evidence||[]).map(x=>[x.tool,JSON.stringify(x.arguments),x.result.available===false?'자료 미확보':'응답 수신'])}/>
        {active&&<details><summary>원본 도구 결과 보기</summary>{active.result.evidence.map((x,i)=><pre className="tool-result" key={i}>{JSON.stringify(x,null,2)}</pre>)}</details>}
      </SectionCard>
      <SectionCard title="질문 예시" note="클릭하면 입력창에 반영"><div className="suggestion-grid">{questions.map(x=><button key={x} onClick={()=>{setQuestion(x);document.getElementById('report-question')?.focus()}}>{x}<span>↗</span></button>)}</div></SectionCard>
      <SummaryBulletCard title="한계 및 주의사항" items={limitations}/>
    </div>
  </>
}
