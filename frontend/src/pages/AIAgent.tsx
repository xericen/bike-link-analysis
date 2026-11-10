import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../services/api'
import type { ChatResult, Region } from '../types'
import { ErrorBox, Skeleton } from '../components/State'

const questions = [
  '서울에서 PageRank가 높은 대여소 TOP 5를 알려줘.',
  '대전에서 이용량과 연결 중심성이 다른 대여소를 찾아줘.',
  '서울과 대전의 이용 패턴을 비교해줘.',
  '세종에서 군집 분석이 가능한지 알려줘.',
  '서울에서 중요한 연결 거점의 운영 개선 방안을 제안해줘.',
]
type Message = { question: string; result: ChatResult }
export function AIAgent() {
  const [params]=useSearchParams()
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<Message[]>([])
  const [selected, setSelected] = useState<number | null>(null)
  const [region, setRegion] = useState('seoul')
  const [regions, setRegions] = useState<Region[]>([])
  const [configured, setConfigured] = useState<boolean>()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [lastQuestion, setLastQuestion] = useState('')
  useEffect(() => {
    api.agentStatus().then(x => setConfigured(x.configured)).catch(e => setError(e.message))
    api.regions().then(x => setRegions(x.regions)).catch(() => {})
  }, [])
  useEffect(()=>{const prompt=params.get('prompt');if(prompt)setQuestion(prompt)},[params])
  async function submit(event?: React.FormEvent, override?: string) {
    event?.preventDefault()
    const text = (override || question).trim()
    if (!text || loading || configured !== true) return
    const submitted = /서울|대전|세종/.test(text) ? text : regions.find(x => x.region_id === region)?.region_name + ' ' + text
    setQuestion('')
    setLastQuestion(submitted)
    setError('')
    setLoading(true)
    try {
      const result = await api.chat(submitted)
      setHistory(old => { const next = [...old, { question: submitted, result }]; setSelected(next.length - 1); return next })
    } catch (e) {
      setError(e instanceof Error ? e.message : '분석 요청 실패')
    } finally { setLoading(false) }
  }
  const active = selected === null ? null : history[selected]
  const report = active?.result.report
  return <>
    <div className="page-heading"><div><span className="section-label">AI ANALYSIS REPORT</span><h2>발견을 운영 검토 질문으로 연결하다</h2><p>Solar가 실제 분석 도구를 호출해 발견·근거·검토 조치·추가 검증을 구분합니다.</p></div><span className={configured ? 'mini-status good' : 'mini-status'}>{configured === undefined ? '연결 확인 중' : configured ? 'Solar API 설정됨' : 'Solar API 키 미설정'}</span></div>
    <div className="agent-workspace">
      <div className="agent-left">
        <section className="panel">
          <div className="panel-title"><h3>질문 입력</h3><span>서울 · 대전 · 세종</span></div>
          <label className="agent-label" htmlFor="agent-region">기본 분석 지역</label>
          <select id="agent-region" value={region} onChange={e => setRegion(e.target.value)}>{regions.map(x => <option key={x.region_id} value={x.region_id}>{x.region_name} · {x.service_name}</option>)}</select>
          <form onSubmit={e => void submit(e)} className="agent-question-form"><textarea aria-label="분석 질문" placeholder={configured === false ? 'Solar API 키 설정이 필요합니다' : '공공자전거 데이터에 대해 질문하세요'} value={question} disabled={configured === false} onChange={e => setQuestion(e.target.value)} rows={4}/><button className="button-primary" disabled={loading || configured !== true || !question.trim()}>{loading ? '분석 요청 중…' : '분석 보고서 생성 ↗'}</button></form>
          {configured === false && <div className="notice">UPSTAGE_API_KEY 미설정 상태입니다. AI 답변을 생성하지 않습니다.</div>}
          {loading && <div className="agent-progress" role="status"><Skeleton rows={2}/><p>Solar 요청 및 분석 도구 실행 중입니다. 실제 완료된 단계는 결과와 함께 표시됩니다.</p></div>}
          {error && <ErrorBox message={error} onRetry={() => { void submit(undefined, lastQuestion) }}/>}
        </section>
        <section className="panel"><h3>추천 질문</h3><div className="suggestion-grid">{questions.map(x => <button key={x} onClick={() => { setQuestion(x); if (configured) void submit(undefined, x) }}>{x}<span>↗</span></button>)}</div></section>
        <section className="panel"><h3>대화 기록</h3>{history.length ? <div className="agent-history">{history.map((item, i) => <button className={selected === i ? 'selected' : ''} key={i} onClick={() => setSelected(i)}><small>질문 {i + 1}</small><span>{item.question}</span><b>도구 {item.result.evidence.length}건 · {item.result.usage.total_tokens} 토큰</b></button>)}</div> : <p className="muted">아직 분석 기록이 없습니다.</p>}</section>
        <section className="panel"><h3>지역별 데이터 확보</h3><div className="agent-coverage">{regions.map(x => <div key={x.region_id}><b>{x.region_name}</b><span>{x.has_usage ? '이용 자료 확보' : x.availability === 'METADATA_ONLY' ? '운영 메타데이터' : '대여소별 자료 미확보'}</span><small>OD {x.has_od ? '확보' : '미확보'}</small></div>)}</div></section>
      </div>
      <div className="agent-right">
        {!active ? <section className="panel agent-placeholder"><span className="agent-symbol">✦</span><h3>분석 보고서</h3><p>질문을 입력하면 도구 호출 근거, 확인된 수치, Solar의 해석을 함께 표시합니다.</p></section> : <>
          <section className="panel"><div className="panel-title"><div><span className="section-label">SOLAR REPORT</span><h3>{report?.question_summary || active.question}</h3></div><span className="mini-status good">분석 완료</span></div>
            <div className="agent-step-list"><span>✓ 질문 전송</span><span>✓ 도구 실행 {active.result.evidence.length}건</span><span>✓ 결과 수신</span><span>✓ 보고서 구성</span></div>
            {report?.key_findings.length ? <div className="agent-findings">{report.key_findings.map((x, i) => <div key={i}><small>{x.label}</small><strong>{x.value.toLocaleString()} <em>{x.unit}</em></strong>{x.period && <small>{x.period}년</small>}</div>)}</div> : <div className="notice">수치로 확인된 핵심 발견이 없습니다. 도구 결과와 자료 한계를 확인하세요.</div>}
          </section>
          <section className="panel"><div className="panel-title"><h3>Solar 분석 및 운영 검토 의견</h3><span>{active.result.model}</span></div><div className="agent-answer">{active.result.answer}</div><p className="agent-note">AI 해석과 제안은 아래 실제 도구 결과를 참고해 검토하세요. 효과나 재고 상태는 검증된 수치가 아닙니다.</p></section>
          {active.result.grounding_validation&&<section className="panel"><div className="panel-title"><h3>응답 수치 대조</h3><span className={active.result.grounding_validation.passed?'mini-status good':'mini-status'}>{active.result.grounding_validation.passed?'도구 수치 일치':'불일치 검토 필요'}</span></div><p>검사 {active.result.grounding_validation.checked_numeric_tokens}개 · 일치 {active.result.grounding_validation.matched_numeric_tokens}개</p>{!active.result.grounding_validation.passed&&<p className="notice">도구 결과와 직접 일치하지 않은 수치: {active.result.grounding_validation.unmatched_numeric_tokens.join(', ')}</p>}<p className="muted">{active.result.grounding_validation.method}</p></section>}
          {report?.charts.map((chart, i) => <section className="panel" key={i}><div className="panel-title"><h3>{chart.title}</h3><span>도구 결과에서 생성</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart.points}><CartesianGrid stroke="#e6edf5" vertical={false}/><XAxis dataKey={chart.kind === 'ranking' ? 'station_id' : 'date'} interval={0} angle={-25} height={54} textAnchor="end" fontSize={10}/><YAxis/><Tooltip/><Bar dataKey={chart.kind === 'ranking' ? 'value' : 'rental_count'} fill="#3476d0" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>{chart.kind === 'ranking' && <p className="agent-note">전체 OD 그래프에서 계산한 {chart.metric}입니다. <Link to="/network">네트워크 화면 보기 ↗</Link></p>}</section>)}
          {report?.station_comparison.length ? <section className="panel"><h3>대여량과 연결 중심성 비교</h3><div className="agent-table-wrap"><table className="agent-table"><thead><tr><th>대여소</th><th>대여량</th><th>이용량 순위</th><th>중심성 지표</th><th>중심성 순위</th><th>순위 차이</th></tr></thead><tbody>{report.station_comparison.map(x => <tr key={x.station_id}><td>{x.station_id}<small>{x.station_name}</small></td><td>{x.rental_count?.toLocaleString() ?? 'N/A'}</td><td>{x.usage_rank ?? "N/A"}</td><td>{x.metric} {x.centrality}</td><td>{x.centrality_rank ?? "N/A"}</td><td>{x.rank_gap ?? "N/A"}</td></tr>)}</tbody></table></div><p className="agent-note">두 값은 단위가 다릅니다. 같은 기간의 실제 대여량과 전체 그래프 중심성입니다.</p></section> : null}
          {(report?.station_roles.length || report?.recommendations.length) ? <section className="panel"><h3>대여소 역할과 운영 검토 제안</h3>{report.station_roles.map((x, i) => <p className="agent-source" key={'role'+i}><b>{x.station_id}</b> · {x.role} (군집 {x.cluster_id})</p>)}{report.recommendations.map((x, i) => <div className="agent-recommendation" key={'rec'+i}><b>{x.feature}</b><p>근거: {x.evidence}</p><p>제안: {x.action}</p><p>활용: {x.value}</p><small>추가 검증: {x.validation}</small></div>)}</section> : null}
          <section className="panel"><h3>분석 근거와 출처</h3><div className="agent-meta"><span>분석 기간: {report?.periods.length ? report.periods.join(' ~ ') : '확인된 날짜 없음'}</span><span>사용 알고리즘: {report?.algorithms.length ? report.algorithms.join(', ') : '해당 없음'}</span></div>{report?.sources.length ? report.sources.map((x, i) => <p className="agent-source" key={i}>{x.source_url ? <a href={x.source_url} target="_blank" rel="noreferrer">{x.dataset_name} ↗</a> : x.dataset_name} · {x.verification_status}</p>) : <p className="muted">출처 메타데이터가 없습니다.</p>}
            <details><summary>실제 도구 호출 {active.result.evidence.length}건 보기</summary>{active.result.evidence.map((x, i) => <div className="evidence" key={i}><b>{x.tool}</b><pre>{JSON.stringify({ arguments: x.arguments, result: x.result }, null, 2)}</pre></div>)}</details>
          </section>
          <section className="panel"><h3>데이터 한계 및 주의사항</h3>{report?.limitations.length ? <ul className="agent-limits">{report.limitations.map((x, i) => <li key={i}>{x}</li>)}</ul> : <p className="muted">추가로 확인된 한계가 없습니다.</p>}</section>
        </>}
      </div>
    </div>
  </>
}
