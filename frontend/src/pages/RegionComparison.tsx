import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../services/api'
import type { ClusterResult, CompareResult, Region } from '../types'
import { Empty, ErrorBox, SourceNote } from '../components/State'

export function RegionComparison() {
  const [regions, setRegions] = useState<Region[]>([])
  const [ids, setIds] = useState(['seoul','daejeon','sejong','busan'])
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [data, setData] = useState<CompareResult>()
  const [clusters, setClusters] = useState<Record<string,ClusterResult>>({})
  const [quality, setQuality] = useState<Record<string,Record<string,unknown>>>({})
  const [error, setError] = useState('')
  useEffect(() => {
    api.regions().then(x => setRegions(x.regions)).catch(err => setError(err.message))
    api.quality().then(x => setQuality(x.quality as Record<string,Record<string,unknown>>)).catch(err => setError(err.message))
  }, [])
  useEffect(() => {
    let active = true
    setData(undefined); setError('')
    Promise.all([api.compare(ids,start,end),...ids.map(id => api.clusters(id,start,end))])
      .then(([comparison,...items]) => {
        if (active) {
          setData(comparison as CompareResult)
          setClusters(Object.fromEntries(ids.map((id,i) => [id,items[i] as ClusterResult])))
        }
      }).catch(err => { if (active) setError(err.message) })
    return () => { active = false }
  }, [ids.join(','),start,end])
  const chart = data ? Array.from({length:24},(_,hour) => ({
    hour:hour+'시',
    ...Object.fromEntries(data.regions.filter(r => r.hourly).map(r => [r.region_name, r.hourly![hour] / (r.total_rentals || 1) * 100]))
  })) : []
  const roleMap = Object.fromEntries(ids.map(id => [id, (clusters[id]?.clusters || []).reduce<Record<string,number>>((all,x) => {
    all[x.role]=(all[x.role]||0)+1; return all
  },{})]))
  const roleNames = [...new Set(Object.values(roleMap).flatMap(x => Object.keys(x)))]
  const roleChart = data?.regions.filter(r => clusters[r.region_id]?.available).map(r => ({
    name:r.region_name, ...roleMap[r.region_id]
  })) || []
  return <>
    <div className="page-heading"><div><span className="section-label">REGIONAL INSIGHTS</span><h2>지역 비교</h2><p>관측 기간과 데이터 범위를 함께 확인하세요.</p></div></div>
    <div className="compare-controls">
      {regions.map(r => <label key={r.region_id}><input type="checkbox" checked={ids.includes(r.region_id)} onChange={e => setIds(old => e.target.checked ? [...old,r.region_id] : old.filter(x => x !== r.region_id))}/>{r.region_name}</label>)}
      <label>시작일 <input type="date" value={start} onChange={e => setStart(e.target.value)}/></label>
      <label>종료일 <input type="date" value={end} onChange={e => setEnd(e.target.value)}/></label>
    </div>
    {error && <ErrorBox message={error}/>}
    {data ? <>
      <div className="grid-two">{data.regions.map(item => <section className="panel comparison-card" key={item.region_id}>
        <h3>{item.region_name} · {item.service_name}</h3>
        <strong>{item.total_rentals?.toLocaleString() || 'N/A'}<small> 건</small></strong>
        <p>대여소 {item.station_count?.toLocaleString() || 'N/A'}개소 · 대여소당 {item.average_per_station?.toLocaleString() || 'N/A'}건</p>
        <p>관측일 {item.observed_dates.join(', ') || 'N/A'}</p>
        <p>평일/주말 이용 비율: {item.weekday_share === null ? 'N/A' : (item.weekday_share*100).toFixed(1)+'%'} / {item.weekend_share === null ? 'N/A' : (item.weekend_share*100).toFixed(1)+'%'}</p>
        <p>PageRank 최고 대여소: {item.centrality_top?.station_name || 'N/A'} {item.centrality_top ? item.centrality_top.pagerank.toFixed(5) : ''}</p>
        <p>{item.coverage_note}</p>
        <p className="muted">품질: OD 행 {String(quality[item.region_id]?.od_rows ?? 'N/A')}, 좌표 결측 비율 {quality[item.region_id]?.missing_coordinate_ratio === undefined ? 'N/A' : String(quality[item.region_id]?.missing_coordinate_ratio)}</p>
        <SourceNote data={item}/>
      </section>)}</div>
      {chart.some(row => Object.keys(row).length > 1) ? <section className="panel"><div className="panel-title"><h3>시간대별 이용 비율</h3><span>각 지역 관측 건수 대비 %</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={chart}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="hour" interval={3} tick={{fontSize:11}}/><YAxis tick={{fontSize:11}}/><Tooltip/><Legend/>{data.regions.filter(r => r.hourly).map((r,i) => <Bar key={r.region_id} dataKey={r.region_name} fill={['#2563eb','#10b981','#f59e0b','#8b5cf6'][i]} radius={[3,3,0,0]}/>)}</BarChart></ResponsiveContainer></div></section> : <Empty>비교 가능한 시간대 자료가 없습니다.</Empty>}
      {roleChart.length ? <section className="panel"><div className="panel-title"><h3>군집 분포</h3><span>분석 가능 지역만 표시</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={roleChart}><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="name"/><YAxis/><Tooltip/><Legend/>{roleNames.map((role,i) => <Bar key={role} dataKey={role} fill={['#2563eb','#10b981','#f59e0b','#8b5cf6'][i%4]}/>)}</BarChart></ResponsiveContainer></div></section> : <Empty>군집을 비교할 자료가 없습니다.</Empty>}
      <section className="panel"><h3>비교 한계</h3><p>동일 관측일: {data.same_observed_dates ? '예' : '아니요 / 자료 미확보'}</p>{data.limitations.map(x => <p key={x} className="muted">{x}</p>)}</section>
    </> : <Empty>비교 데이터를 불러오는 중입니다.</Empty>}
  </>
}
