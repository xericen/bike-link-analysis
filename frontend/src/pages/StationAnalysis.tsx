import { useEffect, useMemo, useState } from 'react'
import { api } from '../services/api'
import type { Cluster, ClusterResult, DateFilter, SimilarityResult, SourceInfo, Station } from '../types'
import { clusterColor } from '../components/colors'
import { Empty, ErrorBox, Skeleton, SourceBadge, SourceNote, number } from '../components/State'
import { HourlyChart } from '../charts/HourlyChart'
import { StationMap } from '../maps/StationMap'

export function StationAnalysis({regionId,filter}:{regionId:string;filter:DateFilter}) {
  const [stations,setStations]=useState<Station[]>([])
  const [source,setSource]=useState<SourceInfo>()
  const [groups,setGroups]=useState<ClusterResult>()
  const [selected,setSelected]=useState('')
  const [detail,setDetail]=useState<{station:Station;cluster:Cluster|null}>()
  const [similar,setSimilar]=useState<SimilarityResult>()
  const [search,setSearch]=useState(''),[searchTerm,setSearchTerm]=useState('')
  const [clusterFilter,setClusterFilter]=useState('all')
  const [sort,setSort]=useState('desc')
  const [error,setError]=useState(''),[loading,setLoading]=useState(true)
  useEffect(()=>{const timer=setTimeout(()=>setSearchTerm(search.trim().toLowerCase()),250);return()=>clearTimeout(timer)},[search])
  useEffect(()=>{let active=true;setStations([]);setSelected('');setDetail(undefined);setSimilar(undefined);setSource(undefined);setGroups(undefined);setLoading(true);setError('');Promise.all([api.stations(regionId,filter.start,filter.end),api.clusters(regionId,filter.start,filter.end)]).then(([a,b])=>{if(active){setStations(a.stations);setSource(a);setGroups(b);setLoading(false)}}).catch(e=>{if(active){setError(e.message);setLoading(false)}});return()=>{active=false}},[regionId,filter.start,filter.end])
  const clusterById=useMemo(()=>Object.fromEntries((groups?.clusters||[]).map(x=>[x.station_id,x.cluster_id])),[groups])
  const roles=useMemo(()=>[...new Map((groups?.clusters||[]).map(x=>[x.cluster_id,x.role])).entries()],[groups])
  const shown=useMemo(()=>stations.filter(s=>{
    const match=!searchTerm||(s.station_name||'').toLowerCase().includes(searchTerm)||s.station_id.toLowerCase().includes(searchTerm)
    return match&&(clusterFilter==='all'||clusterById[s.station_id]===Number(clusterFilter))
  }).sort((a,b)=>sort==='asc'?(a.rental_count??-1)-(b.rental_count??-1):(b.rental_count??-1)-(a.rental_count??-1)),[stations,searchTerm,clusterFilter,sort,clusterById])
  useEffect(()=>{if(!selected||!stations.some(s=>s.station_id===selected))setSelected(shown[0]?.station_id||'')},[shown,selected,stations])
  useEffect(()=>{if(!selected)return;let active=true;setDetail(undefined);setSimilar(undefined);api.station(regionId,selected,filter.start,filter.end).then(x=>{if(active)setDetail(x)}).catch(e=>{if(active)setError(e.message)});api.similarity(regionId,selected,filter.start,filter.end).then(x=>{if(active)setSimilar(x)}).catch(()=>{if(active)setSimilar(undefined)});return()=>{active=false}},[regionId,selected,filter.start,filter.end])
  const mapStations=regionId==='seoul'?stations.filter(s=>s.latitude!=null):shown
  if(error)return <ErrorBox message={error}/>
  return <><div className="page-heading"><div><span className="section-label">STATION INTELLIGENCE</span><h2>대여소의 하루를 분석하다</h2><p>이용 패턴과 군집, 유사 대여소를 함께 확인합니다.</p></div><SourceBadge data={source}/></div>
    {regionId==='seoul'&&<div className="notice">서울 위치 자료의 대여소 ID와 OD 분석 ID가 일치하지 않습니다. 지도는 위치 목록, 아래 분석은 OD 대여소이며 서로 임의로 연결하지 않습니다.</div>}
    <div className="station-workspace"><section className="panel station-picker"><div className="panel-title"><h3>대여소 선택</h3><span>{number(shown.length)}개 표시</span></div><input className="search" aria-label="대여소 검색" placeholder="대여소명 또는 ID 검색" value={search} onChange={e=>setSearch(e.target.value)}/><div className="filter-row"><select aria-label="군집 선택" value={clusterFilter} onChange={e=>setClusterFilter(e.target.value)}><option value="all">전체 군집</option>{roles.map(([id,role])=><option key={id} value={id}>{role} · {id+1}군집</option>)}</select><select aria-label="이용량 정렬" value={sort} onChange={e=>setSort(e.target.value)}><option value="desc">이용량 많은 순</option><option value="asc">이용량 적은 순</option></select></div>{loading?<Skeleton/>:<div className="select-list">{shown.slice(0,100).map(s=><button key={s.station_id} className={selected===s.station_id?'selected':''} onClick={()=>setSelected(s.station_id)}><span className="cluster-dot" style={{background:clusterColor(clusterById[s.station_id])}}/><span><b>{s.station_name||s.station_id}</b><small>{s.station_id} · 대여 {number(s.rental_count)}건</small></span></button>)}{!shown.length&&<Empty>조건에 맞는 대여소가 없습니다.</Empty>}</div>}<p className="muted">목록은 상위 100개까지 표시합니다. 검색·군집 필터로 좁혀보세요.</p></section>
      <section className="panel station-map-panel"><div className="panel-title"><h3>대여소 지도</h3><span>확인된 좌표만 표시</span></div><StationMap stations={mapStations} selectedId={selected} onSelect={setSelected} clusterById={clusterById} height={510}/><div className="cluster-legend">{roles.map(([id,role])=><span key={id}><i style={{background:clusterColor(id)}}/>{role}</span>)}<span><i style={{background:clusterColor(undefined)}}/>군집 미확인</span></div></section>
      <div className="station-detail">{detail?<><section className="panel"><span className="section-label">STATION PROFILE</span><h3>{detail.station.station_name||detail.station.station_id}</h3><p className="muted">{detail.station.station_id} · {detail.station.latitude==null?'좌표 미확보':'위치 확인됨'}</p><div className="detail-grid"><div><small>대여량</small><strong>{number(detail.station.rental_count)}</strong></div><div><small>반납량</small><strong>{number(detail.station.return_count)}</strong></div></div><p><span className="cluster-dot" style={{background:clusterColor(detail.cluster?.cluster_id)}}/> {detail.cluster?.role||'군집 N/A'}</p><p className="muted">{detail.cluster?.description||'분석 가능한 이용 기록이 없습니다.'}</p></section><section className="panel"><h3>시간대별 대여 패턴</h3>{detail.station.hourly?<HourlyChart values={detail.station.hourly}/>:<Empty>시간대별 이용 자료 미확보</Empty>}</section><section className="panel"><h3>유사 대여소 TOP 5</h3>{similar?.available?<div className="ranking">{similar.similar.slice(0,5).map(x=><button className="similar-row" key={x.station_id} onClick={()=>setSelected(x.station_id)}><span>{x.station_name||x.station_id}<small>대여 {number(x.rental_count)}건</small></span><b>{x.score.toFixed(3)}</b></button>)}</div>:<Empty>패턴 유사도 자료 미확보</Empty>}<p className="muted">점수는 정규화된 이용 패턴의 유사도이며 절대 이용량과 다릅니다.</p></section></>:<section className="panel">{loading?<Skeleton/>:<Empty>대여소를 선택하세요.</Empty>}</section>}</div></div><SourceNote data={source}/></>
}
