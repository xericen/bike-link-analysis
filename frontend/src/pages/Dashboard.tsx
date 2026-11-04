import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../services/api'
import type { Overview } from '../types'
import { Empty, ErrorBox, SourceBadge, SourceNote } from '../components/State'
import { HourlyChart } from '../charts/HourlyChart'
import { StationMap } from '../maps/StationMap'

export function Dashboard({ regionId }: { regionId: string }) {
  const [data, setData] = useState<Overview>()
  const [error, setError] = useState('')
  const [revision, setRevision] = useState(0)
  const [kind, setKind] = useState('stations')
  const [datasetName, setDatasetName] = useState('')
  const [file, setFile] = useState<File>()
  const [uploadMessage, setUploadMessage] = useState('')
  useEffect(() => { let active = true; setData(undefined); setError(''); api.overview(regionId).then(x => { if (active) setData(x) }).catch(err => { if (active) setError(err.message) }); return () => { active = false } }, [regionId,revision])
  async function upload(event: React.FormEvent) {
    event.preventDefault()
    if (!file || !datasetName.trim()) return
    try { const result = await api.upload(regionId,kind,datasetName,file); setUploadMessage(result.message + ` (${result.rows}행)`); setRevision(v => v+1) }
    catch (err) { setUploadMessage(err instanceof Error ? err.message : '업로드 실패') }
  }
  if (error) return <ErrorBox message={error}/>
  if (!data) return <Empty>대시보드 데이터를 불러오는 중입니다.</Empty>
  const peak = data.hourly ? data.hourly.indexOf(Math.max(...data.hourly)) : null
  return <><div className="page-heading"><div><span className="section-label">OVERVIEW</span><h2>{data.region_name} 공공자전거 대시보드</h2><p>{data.service_name} · {data.operator}</p></div><SourceBadge data={data} periodStart={data.period_start} periodEnd={data.period_end}/></div><div className="stats"><div className="stat"><span>관측 이용량</span><strong>{data.total_rentals?.toLocaleString() || 'N/A'}<small> 건</small></strong><em>관측일 기준</em></div><div className="stat"><span>대여소 수</span><strong>{data.station_count?.toLocaleString() || 'N/A'}<small> 개소</small></strong><em>{data.total_rentals === null ? '위치 목록 기준 또는 미확보' : '이용 기록 기준'}</em></div><div className="stat"><span>대여소당 평균</span><strong>{data.average_per_station?.toLocaleString() || 'N/A'}</strong><em>관측 기간 이용 건수</em></div><div className="stat"><span>주요 시간</span><strong>{peak === null ? 'N/A' : `${peak}시`}</strong><em>시간대 정보 확보 시</em></div></div><p className="muted">{data.coverage_note}</p>{data.observed_dates.length > 0 && <p className="muted">실제 관측일: {data.observed_dates.join(', ')}</p>}{data.annual_latest && <section className="panel"><h3>별도 연간 집계</h3><p>{data.annual_latest.year}년 어울링 이용 건수 {data.annual_latest.rental_count.toLocaleString()}건. 대여소별 이용량과 직접 비교하지 않습니다.</p></section>}{data.daily.length ? <section className="panel"><div className="panel-title"><h3>관측일별 이용량</h3><span>확보한 날짜만 표시</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={data.daily}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="date"/><YAxis/><Tooltip/><Bar dataKey="rental_count" name="대여 건수" fill="#2563eb"/></BarChart></ResponsiveContainer></div></section> : <Empty>일별 이용 추이 데이터 미확보</Empty>}<div className="grid-two"><section className="panel"><div className="panel-title"><h3>시간대별 이용량</h3><span>실제 대여 기록 집계</span></div>{data.hourly ? <HourlyChart values={data.hourly}/> : <Empty>시간대별 이용 데이터 미확보</Empty>}</section><section className="panel"><div className="panel-title"><h3>공식 대여소 위치</h3><span>좌표 확보 {data.inventory_station_count || 0}개소</span></div><StationMap stations={data.map_stations}/></section></div><section className="panel"><h3>로컬 CSV 업로드</h3><p className="muted">정규화된 CSV 스키마를 사용합니다. 대여소 파일을 먼저 올려야 이용·OD 기록을 가져올 수 있습니다.</p><form onSubmit={upload} className="compare-controls"><select aria-label="자료 종류" value={kind} onChange={e => setKind(e.target.value)}><option value="stations">대여소</option><option value="station_usage">대여소 이용</option><option value="od_daily">OD 집계</option><option value="trips">개별 Trip</option></select><input aria-label="데이터셋 이름" placeholder="데이터셋 이름" value={datasetName} onChange={e => setDatasetName(e.target.value)}/><input aria-label="CSV 파일" type="file" accept=".csv" onChange={e => setFile(e.target.files?.[0])}/><button type="submit">가져오기</button></form>{uploadMessage && <p role="status">{uploadMessage}</p>}</section><SourceNote data={data}/></>
}
