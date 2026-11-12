import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../services/api'
import type { Cluster, ClusterResult, ClusterStability, DateFilter, RoleHistory, SimilarityResult, SourceInfo, Station } from '../types'
import { Empty, ErrorBox, Skeleton, SourceBadge, SourceNote, number } from '../components/State'
import { StationPatternChart } from '../charts/AnalysisCharts'
import { PageHeader, StatCard, SectionCard, InsightBanner, RoleTag, SimpleDataTable, SummaryBulletCard, ComparisonDonutCard } from '../components/AnalysisUI'
import { peakHour, clusterSilhouette } from '../services/presentation'
import type { HiddenHubsResult } from '../types'
import { StationMap } from '../maps/StationMap'

export function StationAnalysis({regionId,filter}:{regionId:string;filter:DateFilter}) {
  const [showMap,setShowMap]=useState(false)
  const [hubs,setHubs]=useState<HiddenHubsResult>()
  useEffect(()=>{let active=true;setHubs(undefined);api.hiddenHubs(regionId,filter.start,filter.end).then(x=>{if(active)setHubs(x)}).catch(()=>{});return()=>{active=false}},[regionId,filter.start,filter.end])
  const [params]=useSearchParams()
  const requested=params.get('station')||''
  const [stations,setStations]=useState<Station[]>([])
  const [source,setSource]=useState<SourceInfo>()
  const [groups,setGroups]=useState<ClusterResult>()
  const [stability,setStability]=useState<ClusterStability>()
  const [selected,setSelected]=useState(requested)
  const [detail,setDetail]=useState<{station:Station;cluster:Cluster|null}>()
  const [similar,setSimilar]=useState<SimilarityResult>()
  const [history,setHistory]=useState<RoleHistory>()
  const [search,setSearch]=useState(''),[searchTerm,setSearchTerm]=useState('')
  const [clusterFilter,setClusterFilter]=useState('all')
  const [sort,setSort]=useState('desc')
  const [error,setError]=useState(''),[loading,setLoading]=useState(true)
  useEffect(()=>{const timer=setTimeout(()=>setSearchTerm(search.trim().toLowerCase()),250);return()=>clearTimeout(timer)},[search])
  useEffect(()=>{let active=true;setStations([]);setSelected(requested);setDetail(undefined);setSimilar(undefined);setHistory(undefined);setSource(undefined);setGroups(undefined);setStability(undefined);setLoading(true);setError('');Promise.all([api.stations(regionId,filter.start,filter.end),api.clusters(regionId,filter.start,filter.end),api.imbalance(regionId,filter.start,filter.end)]).then(([a,b,c])=>{if(active){const flow=Object.fromEntries(c.stations.map(x=>[x.station_id,x]));setStations(a.stations.map(s=>({...s,...flow[s.station_id]})));setSource(a);setGroups(b);setLoading(false)}}).catch(e=>{if(active){setError(e.message);setLoading(false)}});return()=>{active=false}},[regionId,filter.start,filter.end,requested])
  useEffect(()=>{let active=true;setStability(undefined);api.clusterStability(regionId,filter.end).then(x=>{if(active)setStability(x)}).catch(()=>{});return()=>{active=false}},[regionId,filter.end])
  const clusterById=useMemo(()=>Object.fromEntries((groups?.clusters||[]).map(x=>[x.station_id,x.cluster_id])),[groups])
  const roles=useMemo(()=>[...new Map((groups?.clusters||[]).map(x=>[x.cluster_id,x.role])).entries()],[groups])
  const imbalanceColors=useMemo(()=>Object.fromEntries(stations.map(s=>[s.station_id,(s.imbalance_ratio??0)>.05?'#d95050':(s.imbalance_ratio??0)<-.05?'#3278ce':'#8795a8'])),[stations])
  const shown=useMemo(()=>stations.filter(s=>{
    const match=!searchTerm||(s.station_name||'').toLowerCase().includes(searchTerm)||s.station_id.toLowerCase().includes(searchTerm)
    return match&&(clusterFilter==='all'||clusterById[s.station_id]===Number(clusterFilter))
  }).sort((a,b)=>sort==='asc'?(a.rental_count??-1)-(b.rental_count??-1):(b.rental_count??-1)-(a.rental_count??-1)),[stations,searchTerm,clusterFilter,sort,clusterById])
  useEffect(()=>{if(loading)return;if(!selected||!stations.some(s=>s.station_id===selected))setSelected(stations.some(s=>s.station_id===requested)?requested:shown[0]?.station_id||'')},[shown,selected,stations,loading,requested])
  useEffect(()=>{
    if(!selected||!stations.some(s=>s.station_id===selected))return
    let active=true;setDetail(undefined);setSimilar(undefined);setHistory(undefined)
    api.station(regionId,selected,filter.start,filter.end).then(x=>{if(active)setDetail(x)}).catch(e=>{if(active)setError(e.message)})
    api.similarity(regionId,selected,filter.start,filter.end).then(x=>{if(active)setSimilar(x)}).catch(e=>{if(active)setError(e.message)})
    api.roleHistory(regionId,selected,filter.end).then(x=>{if(active)setHistory(x)}).catch(e=>{if(active)setError(e.message)})
    return()=>{active=false}
  },[regionId,selected,filter.start,filter.end,stations])
  const mapStations=regionId==='seoul'?stations.filter(s=>s.latitude!=null):shown
  const selectedFlow=stations.find(x=>x.station_id===selected)
  const hub=hubs?.candidates.find(x=>x.station_id===selected)
  const peak=peakHour(detail?.station.hourly)
  const silhouette=clusterSilhouette(groups)
  const windows=history?.windows||[]
  if(error)return <ErrorBox message={error}/>
  return <>
    <PageHeader title="대여소 이용 특성 분석" subtitle="시간대 패턴 · 군집 유형 · 유사 대여소 · 기간별 변화 분석"><SourceBadge data={source}/></PageHeader>
    <div className="stats">
      <StatCard label="선택 대여소" value={selected||'선택 대기'} note="분석의 기준이 되는 대여소입니다." icon="◎"/>
      <StatCard label="군집 유형" value={groups?.interpretation_allowed?(detail?.cluster?.role||'자료 미확보'):'유형 해석 보류'} note={groups?.confidence_warning||'다른 대여소와 시간대 패턴을 비교합니다.'} tone="mint" icon="◈"/>
      <StatCard label="집중 시간" value={peak===null?(detail?'자료 미확보':'확인 중'):peak+'시'} note="하루 중 대여량이 가장 높은 시간" tone="peach" icon="◷"/>
      <StatCard label="유사 대여소" value={!similar?'확인 중':similar.available?similar.similar.slice(0,5).length+'개':'자료 미확보'} note="코사인 유사도 기준 상위 결과" tone="lavender" icon="⌁"/>
    </div>
    <SectionCard title="분석 대여소 선택" note={number(shown.length)+'개 · 확인된 좌표만 지도 표시'}>
      <div className="station-controls"><input className="search" aria-label="대여소 검색" placeholder="대여소 이름 또는 ID 검색" value={search} onChange={e=>setSearch(e.target.value)}/>
      <select aria-label="선택 대여소" value={selected} onChange={e=>setSelected(e.target.value)}><option value="" disabled>대여소 선택</option>{shown.slice(0,150).map(s=><option value={s.station_id} key={s.station_id}>{s.station_id} · {s.station_name||'이름 미확보'}</option>)}{selected&&!shown.slice(0,150).some(s=>s.station_id===selected)&&<option value={selected}>{selected}</option>}</select>
      <select aria-label="군집 선택" value={clusterFilter} onChange={e=>setClusterFilter(e.target.value)}><option value="all">전체 군집</option>{roles.map(([id])=><option key={id} value={id}>군집 {id+1}</option>)}</select><select aria-label="이용량 정렬" value={sort} onChange={e=>setSort(e.target.value)}><option value="desc">이용량 많은 순</option><option value="asc">이용량 적은 순</option></select></div>
      <details className="map-details" onToggle={e=>setShowMap(e.currentTarget.open)}><summary>대여소 지도에서 선택 · 순유출 비율 확인</summary>{showMap&&<StationMap stations={mapStations} selectedId={selected} onSelect={setSelected} clusterById={clusterById} colorById={imbalanceColors} height={340}/>}<p className="muted">빨강: 순유출 비율 5% 초과 · 파랑: 순유입 비율 5% 초과 · 회색: 그 외</p></details>
    </SectionCard>
    {loading?<Skeleton rows={4}/>:!selected?<Empty>선택 기간의 대여소 자료가 없습니다.</Empty>:<>
    <div className="grid-two station-overview">
      <SectionCard title="선택 대여소 핵심 해석" note={detail?.station.station_name||'이름 확인 중'}>
        <InsightBanner title={selected}><p>{hub?.candidate?'이용량에 비해 연결 중심성이 높아 숨은 연결 거점 후보로 해석됩니다.':hub?'이용량과 연결 순위를 함께 확인하세요. 현재 엄격한 숨은 연결 후보 규칙을 충족하지 않습니다.':'네트워크 근거가 부족해 연결 역할을 확정하지 않습니다.'}</p></InsightBanner>
        <div className="tri-metrics"><div><small>이용량 순위</small><strong>{hub?number(hub.usage_rank)+'위':'미확보'}</strong></div><div><small>PageRank 순위</small><strong>{hub?number(hub.pagerank_rank)+'위':'미확보'}</strong></div><div><small>순위 차이</small><strong>{hub?number(hub.rank_gap):'미확보'}</strong></div></div>
        <p className="muted">대여 {number(detail?.station.rental_count)}건 · 반납 {number(detail?.station.return_count)}건. 순위 차이만으로 운영 중요도를 확정하지 않습니다.</p>
      </SectionCard>
      <SectionCard title="K-means 군집 정보" note="정규화된 특징 기준">
        <div className="panel-title"><RoleTag>{groups?.interpretation_allowed?(detail?.cluster?.role||'미확보'):'탐색 군집 · 유형 확정 보류'}</RoleTag><span>실루엣 {silhouette?.toFixed(3)??'N/A'}</span></div>
        <ComparisonDonutCard data={groups}/>
        <ul className="summary-bullets"><li>{detail?.cluster?.description||'군집 설명을 확인 중입니다.'}</li><li>{groups?.confidence_warning||'군집은 운영 목적이나 인과 관계를 의미하지 않습니다.'}</li></ul>
      </SectionCard>
    </div>
    <div className="grid-two"><SectionCard title="시간대별 이용 패턴" note="24시간 · 대여 / 반납 / 총 이용">{detail?<StationPatternChart station={detail.station}/>:<Skeleton rows={3}/>}</SectionCard>
    <SectionCard title="유사 대여소 TOP 5" note="코사인 유사도 · 최대 1">
      <SimpleDataTable headers={['순위','대여소 ID','대여소 위치 / 이름','코사인 유사도']} rows={(similar?.similar||[]).slice(0,5).map((x,i)=>[i+1,<button className="text-button" onClick={()=>setSelected(x.station_id)}>{x.station_id}</button>,x.station_name||'미확보',x.score.toFixed(3)])}/>
      <p className="muted">절대 이용량이 아닌 시간대 패턴 유사도입니다.</p>
    </SectionCard></div>
    <div className="grid-four">
      <SectionCard title="최근 7일 vs 30일 패턴 비교" note="동일 종료일 · 실제 관측">
        {windows.length?windows.filter(w=>[7,30].includes(w.days)).map(w=><div className="period-tile" key={w.days}><RoleTag>{w.days}일</RoleTag><strong>{number(w.rental_count)}건</strong><p>집중 {w.peak_hour===null?'미확보':w.peak_hour+'시'} · 관측 {w.observed_day_count}일</p><small>{w.date_start} ~ {w.date_end}</small></div>):<Empty>기간별 자료 미확보</Empty>}
        <p className="muted">서로 다른 기간의 총량은 직접 비교하지 않습니다.</p>
      </SectionCard>
      <SectionCard title="기간별 역할 변화" note="유형은 탐색적 해석">
        {windows.length?windows.map(w=><div className="period-tile" key={w.days}><RoleTag>{w.days}일</RoleTag><b>{groups?.interpretation_allowed?(w.cluster_role||'미확보'):'군집 유형 해석 보류'}</b><p>집중 {w.peak_hour===null?'N/A':w.peak_hour+'시'} · 가중 연결 {w.weighted_degree_rank??'N/A'}위</p></div>):<Empty>역할 변화 자료 미확보</Empty>}
      </SectionCard>
      <SectionCard title="선택 대여소 네트워크 요약" note="실제 OD 연결 · 상위 5개">
        {hub?.top_connections.length?<svg viewBox="0 0 300 220" className="station-mini-network" role="img" aria-label="선택 대여소와 주요 연결 노드">{hub.top_connections.slice(0,5).map((x,i)=>{const a=i*Math.PI*2/5;const x2=150+Math.cos(a)*95,y2=105+Math.sin(a)*75;return <g key={i}><line x1="150" y1="105" x2={x2} y2={y2} stroke="#a5c5ee" strokeWidth="2"/><circle cx={x2} cy={y2} r="13" fill="#a9c4f8"/><text x={x2} y={y2+26} textAnchor="middle" fontSize="10">{x.station_id}</text><title>{x.direction==='out'?'출발 연결':'도착 연결'} · {number(x.trip_count)}건</title></g>})}<circle cx="150" cy="105" r="24" fill="#2f6df6"/><text x="150" y="109" fill="white" textAnchor="middle" fontSize="10">{selected}</text></svg>:<Empty>연결 자료 미확보</Empty>}
        <Link className="cta-link" to={'/network?station='+encodeURIComponent(selected)}>이동 패턴 자세히 보기 ↗</Link>
      </SectionCard>
      <SummaryBulletCard title="분석 해석 요약" items={[peak===null?'시간대 자료가 부족합니다.':peak+'시에 대여가 가장 집중됩니다.',groups?.interpretation_allowed?'군집 결과는 탐색적 유형입니다.':'군집 품질이 낮아 유형 부여를 보류합니다.',hub?.candidate?'연결 거점 후보로 기간 안정성 검토가 필요합니다.':'중심성과 이용량을 함께 검토하세요.','불균형은 실제 자전거 부족을 뜻하지 않습니다.']}><Link className="cta-box" to={'/agent?prompt='+encodeURIComponent(selected+' 대여소의 운영 검토 이유를 분석해줘')}>다음 단계로 이동해 보세요 →</Link></SummaryBulletCard>
    </div>
    <div className="grid-two"><SectionCard title="대여·반납 불균형 상세" note="순유출 = 대여 − 반납">
      <SimpleDataTable headers={['구분','순유출','불균형 비율']} rows={selectedFlow?.weekday?[['평일',number(selectedFlow.weekday.net_outflow)+'건',selectedFlow.weekday.imbalance_ratio==null?'N/A':(selectedFlow.weekday.imbalance_ratio*100).toFixed(1)+'%'],['주말',number(selectedFlow.weekend?.net_outflow)+'건',selectedFlow.weekend?.imbalance_ratio==null?'N/A':(selectedFlow.weekend.imbalance_ratio*100).toFixed(1)+'%']]:[]}/>
      <p className="muted">양수: 순유출 · 음수: 순유입. 동일 방향 반복 {selectedFlow?.persistence_ratio==null?'N/A':(selectedFlow.persistence_ratio*100).toFixed(1)+'%'} · {selectedFlow?.low_volume_warning?'적은 이용량 · 해석 주의':'최소 관측량과 기간을 함께 확인하세요.'}</p>
    </SectionCard><SectionCard title="K-means 기간 안정성" note="공통 대여소 ARI">
      <SimpleDataTable headers={['기간 비교','공통 대여소','ARI']} rows={(stability?.comparisons||[]).map(x=>[x.left_days+'일 ↔ '+x.right_days+'일',number(x.common_station_count),x.ari?.toFixed(3)??'N/A'])}/>
      <p className="muted">{stability?.message||'기간 안정성 자료 미확보'}</p>
      <details><summary>특징 조합별 품질 비교</summary><SimpleDataTable headers={['입력 특징','k','Silhouette']} rows={(stability?.windows.at(-1)?.feature_comparisons||[]).map(x=>[x.label,x.selected_k,x.best_silhouette.toFixed(3)])}/></details>
    </SectionCard></div>
    </>}<SourceNote data={source}/>
  </>
}
