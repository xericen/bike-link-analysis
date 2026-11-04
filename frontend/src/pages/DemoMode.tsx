import { useEffect, useState } from 'react'
import { api } from '../services/api'
import { Empty, ErrorBox } from '../components/State'
export function DemoMode() {
  const [data,setData] = useState<Awaited<ReturnType<typeof api.demoOverview>>>()
  const [error,setError] = useState('')
  useEffect(() => { api.demoOverview().then(setData).catch(err => setError(err.message)) }, [])
  return <><div className="page-heading"><div><span className="section-label">DEMO MODE</span><h2>합성 데모 데이터</h2><p>실제 공공데이터 분석과 분리된 예시입니다.</p></div></div>{error && <ErrorBox message={error}/ >}{data ? <section className="panel"><h3>{data.metadata.source}</h3><p>기간 {data.metadata.period_start} ~ {data.metadata.period_end}</p><p>합성 이용량 {data.total_rentals.toLocaleString()}건 · 가상 대여소 {data.station_count}개소</p></section> : <Empty>데모를 불러오는 중입니다.</Empty>}</>
}
