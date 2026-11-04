import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { ChatResult, DataSource } from '../types'
import { ErrorBox } from '../components/State'

export function AIAgent() {
  const [question, setQuestion] = useState('')
  const [result, setResult] = useState<ChatResult>()
  const [sources, setSources] = useState<DataSource[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  useEffect(() => { api.sources().then(x => setSources(x.data_sources)).catch(() => {}) }, [])
  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (!question.trim() || loading) return
    setLoading(true); setError(''); setResult(undefined)
    try { setResult(await api.chat(question.trim())) }
    catch (err) { setError(err instanceof Error ? err.message : '요청 실패') }
    finally { setLoading(false) }
  }
  return <>
    <div className="page-heading"><div><span className="section-label">SOLAR AI AGENT</span><h2>AI 분석 에이전트</h2><p>실제 분석 도구의 결과를 근거로 답변합니다.</p></div><span className="badge">Solar API 키 필요</span></div>
    <section className="panel agent-panel">
      <div className="agent-intro"><span className="agent-symbol">✦</span><h3>무엇을 분석할까요?</h3><p>예: 서울에서 연결 중심성이 높은 대여소는? · 부산 자료로 어떤 분석이 가능한가요?</p></div>
      <form onSubmit={submit} className="chat-form"><input aria-label="분석 질문" placeholder="공공자전거 데이터에 대해 질문하세요" value={question} onChange={event => setQuestion(event.target.value)}/><button disabled={loading || !question.trim()}>{loading ? '분석 중...' : '분석 요청 ↗'}</button></form>
      {error && <ErrorBox message={error}/>}
      {result && <div className="agent-result"><h3>분석 답변</h3><p className="answer">{result.answer}</p><h4>도구 실행 과정과 분석 근거</h4>{result.evidence.length ? result.evidence.map((entry,i) => <details key={i}><summary>{i+1}. {entry.tool}</summary><pre>{JSON.stringify({ arguments: entry.arguments, result: entry.result }, null, 2)}</pre></details>) : <p className="muted">호출된 도구가 없습니다.</p>}</div>}
    </section>
    <section className="panel"><h3>연결 자료와 관측 기간</h3>{sources.length ? sources.map(source => <p className="muted" key={source.source_id}>{source.region_id} · {source.dataset_name} · {source.date_start || '기간 미확인'} ~ {source.date_end || '기간 미확인'} · 수집 {source.collected_at?.slice(0,10) || '미확인'} · {source.verification_status}</p>) : <p className="muted">출처 자료가 없습니다.</p>}</section>
    <p className="muted">키가 없으면 설정 안내를 반환합니다. 분석 자료가 없는 지역은 근거 부족을 알립니다.</p>
  </>
}
