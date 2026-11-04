import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { CentralityResult, Network } from '../types'
import { Empty, ErrorBox, SourceBadge, SourceNote } from '../components/State'

export function NetworkAnalysis({ regionId }: { regionId: string }) {
  const [network, setNetwork] = useState<Network>()
  const [centrality, setCentrality] = useState<CentralityResult>()
  const [error, setError] = useState('')
  useEffect(() => { let active = true; setNetwork(undefined); setCentrality(undefined); setError(''); Promise.all([api.network(regionId),api.centrality(regionId)]).then(([a,b]) => { if (active) { setNetwork(a); setCentrality(b) } }).catch(err => { if (active) setError(err.message) }); return () => { active = false } }, [regionId])
  if (error) return <ErrorBox message={error}/>
  if (!network || !centrality) return <Empty>네트워크를 불러오는 중입니다.</Empty>
  const names = Object.fromEntries(network.nodes.map(s => [s.station_id,s.station_name || s.station_id]))
  const edges = network.edges.slice(0,15)
  const ids = [...new Set(edges.flatMap(e => [e.origin_station_id,e.destination_station_id]))]
  const positions = Object.fromEntries(ids.map((id,i) => [id,{x:50+38*Math.cos(2*Math.PI*i/ids.length),y:50+38*Math.sin(2*Math.PI*i/ids.length)}]))
  return <><div className="page-heading"><div><span className="section-label">NETWORK ANALYSIS</span><h2>이동 네트워크</h2><p>실제 OD 집계의 방향과 가중치를 분석합니다.</p></div><SourceBadge data={network}/></div>{network.available ? <><div className="stats"><div className="stat"><span>관측 대여소</span><strong>{network.nodes.length.toLocaleString()}개</strong></div><div className="stat"><span>고유 연결</span><strong>{network.edge_count.toLocaleString()}개</strong></div><div className="stat"><span>약한 연결요소</span><strong>{centrality.components ?? 'N/A'}</strong></div></div><p className="muted">{network.message}</p><div className="grid-two"><section className="panel"><div className="panel-title"><h3>상위 OD 연결</h3><span>실제 이동 건수 상위 15개</span></div><svg className="network-graph" viewBox="0 0 100 100" role="img" aria-label="상위 대여소 이동 그래프"><defs><marker id="arrow" markerWidth="5" markerHeight="5" refX="4" refY="2.5" orient="auto"><path d="M0 0 L5 2.5 L0 5" fill="#60a5fa"/></marker></defs>{edges.map((e,i) => { const a=positions[e.origin_station_id], b=positions[e.destination_station_id]; return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="#60a5fa" strokeWidth={1.5} markerEnd="url(#arrow)"/> })}{ids.map(id => { const p=positions[id]; return <g key={id}><circle cx={p.x} cy={p.y} r="2.5" fill="#1d4ed8"/><title>{names[id] || id}</title></g> })}</svg><div className="station-list">{edges.map((e,i) => <div className="station-row" key={i}><span>{names[e.origin_station_id] || e.origin_station_id} → {names[e.destination_station_id] || e.destination_station_id}</span><strong>{e.trip_count.toLocaleString()}건</strong></div>)}</div></section><section className="panel"><div className="panel-title"><h3>핵심 연결 거점</h3><span>PageRank 순위</span></div><div className="ranking">{centrality.rankings.slice(0,20).map((item,i) => <div className="rank-row" key={item.station_id}><span className="rank">{String(i+1).padStart(2,'0')}</span><b>{item.station_name}</b><span>{item.pagerank.toFixed(5)}</span></div>)}</div><p className="muted">{centrality.message}</p><p className="muted">가중 출입차수와 표본 매개 중심성은 API 응답에 포함됩니다.</p></section></div></> : <Empty>{network.message}</Empty>}<SourceNote data={network}/></>
}
