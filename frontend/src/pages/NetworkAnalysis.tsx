import { useEffect, useMemo, useState } from 'react'
import { TransitPanel } from '../components/TransitPanel'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from '../services/api'
import type { Centrality, CentralityResult, DateFilter, HiddenHubValidation, HiddenHubsResult, Network, Station } from '../types'
import { PageHeader, StatCard, SectionCard, InsightBanner, SimpleDataTable, SummaryBulletCard } from '../components/AnalysisUI'
import { cityName } from '../services/presentation'
import type { RoleCandidatesResult, RoleHistory } from '../types'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Empty, ErrorBox, Skeleton, SourceBadge, SourceNote, number } from '../components/State'

type Metric='pagerank'|'weighted_out_degree'|'weighted_in_degree'|'betweenness'
const metrics: {id:Metric;name:string}[]=[{id:'pagerank',name:'PageRank'},{id:'weighted_out_degree',name:'가중 출차수'},{id:'weighted_in_degree',name:'가중 입차수'},{id:'betweenness',name:'매개 중심성'}]
export function NetworkAnalysis({regionId,filter}:{regionId:string;filter:DateFilter}) {
  const [changeHistory,setChangeHistory]=useState<RoleHistory>()
  const [roles,setRoles]=useState<RoleCandidatesResult>()
  const [graphMode,setGraphMode]=useState<'all'|'focus'>('focus')
  const [params]=useSearchParams(), requested=params.get('station')||''
  const [network,setNetwork]=useState<Network>(),[centrality,setCentrality]=useState<CentralityResult>()
  const [hidden,setHidden]=useState<HiddenHubsResult>()
  const [selected,setSelected]=useState(requested),[station,setStation]=useState<Station>(),[validation,setValidation]=useState<HiddenHubValidation>()
  const [nodeLimit,setNodeLimit]=useState(40),[metric,setMetric]=useState<Metric>('pagerank')
  const [error,setError]=useState('')
  useEffect(()=>{let active=true;setNetwork(undefined);setCentrality(undefined);setHidden(undefined);setRoles(undefined);setSelected(requested);setError('');Promise.all([api.network(regionId,filter.start,filter.end,nodeLimit),api.hiddenHubs(regionId,filter.start,filter.end),api.roleCandidates(regionId,filter.start,filter.end)]).then(([a,b,c])=>{if(active){setNetwork(a);setHidden(b);setRoles(c);setCentrality({...b,rankings:b.candidates,components:b.components??null});setSelected(requested||b.candidates[0]?.station_id||'')}}).catch(e=>{if(active)setError(e.message)});return()=>{active=false}},[regionId,filter.start,filter.end,nodeLimit,requested])
  useEffect(()=>{
    if(!selected)return
    let active=true;setStation(undefined);setValidation(undefined)
    api.station(regionId,selected,filter.start,filter.end,false).then(x=>{if(active)setStation(x.station)}).catch(()=>{if(active)setStation(undefined)})
    api.hiddenHubValidation(regionId,selected,filter.end).then(x=>{if(active)setValidation(x)}).catch(()=>{if(active)setValidation(undefined)})
    return()=>{active=false}
  },[regionId,selected,filter.start,filter.end])
  const changedStationId=roles?.types.role_changed[0]?.station_id
  useEffect(()=>{
    let active=true;setChangeHistory(undefined)
    if(changedStationId)api.roleHistory(regionId,changedStationId,filter.end).then(x=>{if(active)setChangeHistory(x)}).catch(()=>{})
    return()=>{active=false}
  },[regionId,changedStationId,filter.end])
  const ranks=useMemo(()=>[...(centrality?.rankings||[])].sort((a,b)=>b[metric]-a[metric]),[centrality,metric])
  const byId=useMemo(()=>Object.fromEntries([...(centrality?.rankings||[]),...(hidden?.candidates||[])].map(x=>[x.station_id,x])) as Record<string,Centrality>,[centrality,hidden])
  const focusHub=hidden?.candidates.find(x=>x.station_id===selected)
  const focusEdges=(focusHub?.top_connections||[]).map(x=>({origin_station_id:x.direction==='out'?selected:x.station_id,destination_station_id:x.direction==='out'?x.station_id:selected,trip_count:x.trip_count}))
  const focusIds=[selected,...new Set((focusHub?.top_connections||[]).map(x=>x.station_id))].filter(Boolean)
  const displayNodes=graphMode==='all'?(network?.nodes||[]):focusIds.map(id=>network?.nodes.find(x=>x.station_id===id)||{region_id:regionId,station_id:id,station_name:hidden?.candidates.find(x=>x.station_id===id)?.station_name||id,latitude:null,longitude:null,capacity:null})
  const positions=useMemo(()=>Object.fromEntries(displayNodes.map((s,i)=>{
    const angle=i*2.399963, radius=i===0?0:Math.sqrt(i/(displayNodes.length||1))*235
    return [s.station_id,{x:450+Math.cos(angle)*radius,y:280+Math.sin(angle)*radius}]
  })) as Record<string,{x:number;y:number}>,[displayNodes])
  if(error)return <ErrorBox message={error}/>
  if(!network||!centrality||!hidden)return <Skeleton rows={5}/>
  if(!network.available)return <><PageHeader title="이동 패턴 분석" subtitle="OD 연결 구조 · 중심성 · 불균형 · 숨은 연결 거점 분석"><SourceBadge data={network}/></PageHeader><div className="stats"><StatCard label="OD 이동 건수" value="미확보" note="임의 경로를 생성하지 않습니다."/><StatCard label="분석 간선 수" value="미확보" note="선택 기간의 OD 자료가 필요합니다." tone="mint"/><StatCard label="숨은 연결 후보 수" value="판정 불가" note="네트워크 자료가 필요합니다." tone="lavender"/><StatCard label="불균형 후보 수" value="판정 불가" note="대여·반납 자료가 필요합니다." tone="peach"/></div><Empty>{network.message}</Empty><TransitPanel city={regionId} start={filter.start} end={filter.end}/><SourceNote data={network}/></>
  const drawn=graphMode==='all'?network.edges.slice(0,250):focusEdges, maxFlow=Math.max(1,...drawn.map(x=>x.trip_count))
  const maxRank=Math.max(...centrality.rankings.map(x=>x.pagerank),0.0000001)
  const odTotal=centrality.rankings.length?centrality.rankings.reduce((sum,x)=>sum+x.weighted_out_degree,0):null
  const selectedRank=byId[selected]
  const selectedHidden=hidden.candidates.find(x=>x.station_id===selected)
  const selectedEdges=network.edges.filter(e=>e.origin_station_id===selected||e.destination_station_id===selected).sort((a,b)=>b.trip_count-a.trip_count).slice(0,8)
  const fallbackEdges=(selectedHidden?.top_connections||[]).map(x=>x.direction==='out'?{origin_station_id:selected,destination_station_id:x.station_id,trip_count:x.trip_count}:{origin_station_id:x.station_id,destination_station_id:selected,trip_count:x.trip_count})
  const detailEdges=selectedEdges.length?selectedEdges:fallbackEdges
  const names=Object.fromEntries(network.nodes.map(x=>[x.station_id,x.station_name||x.station_id]))
  const hiddenTop=hidden.candidates.filter(x=>x.candidate).slice(0,5)
  const imbalanceTop=roles?.types.persistent_imbalance.slice(0,5)||[]
  const change=roles?.types.role_changed[0]
  const lead=hiddenTop[0], flow=imbalanceTop[0]
  const direction=(days:number)=>{
    const w=changeHistory?.windows.find(x=>x.days===days)
    if(w?.rental_count==null||w.return_count==null)return '확인 중 / 미확보'
    const net=w.rental_count-w.return_count
    return (net>0?'대여 우세':net<0?'반납 우세':'균형')+' (순유출 '+number(net)+'건)'
  }
  return <>
    <PageHeader title="이동 패턴 분석" subtitle="OD 연결 구조 · 중심성 · 불균형 · 숨은 연결 거점 분석"><SourceBadge data={network}/></PageHeader>
    <div className="stats">
      <StatCard label="OD 이동 건수" value={number(odTotal)} note="좌표·ID가 확인된 그래프 내 OD 합계 · 건" icon="↗"/>
      <StatCard label="분석 간선 수" value={number(network.edge_count)} note="선택 기간의 고유 OD 연결" tone="mint" icon="⌁"/>
      <StatCard label="숨은 연결 후보 수" value={number(hidden.candidates.filter(x=>x.candidate).length)} note="이용량과 중심성 규칙 기준" tone="lavender" icon="◈"/>
      <StatCard label="불균형 후보 수" value={roles?.available?number(roles.counts.persistent_imbalance):'미확보'} note="크기와 방향 반복성 기준" tone="peach" icon="⇄"/>
    </div>
    <div className="insight-grid">
      <InsightBanner title="숨은 연결 거점" tone="mint"><h3>{lead?.station_id||'확인된 후보 없음'}</h3><p>{lead?'이용량 '+number(lead.usage_rank)+'위 / PageRank '+number(lead.pagerank_rank)+'위 / 차이 '+number(lead.rank_gap):'현재 기간의 후보 규칙을 확인하세요.'}</p></InsightBanner>
      <InsightBanner title="불균형 후보" tone="peach"><h3>{flow?.station_id||'확인된 후보 없음'}</h3><p>{flow?'순유출 '+number(flow.net_outflow)+'건 · 대여 '+number(flow.rental_count)+' / 반납 '+number(flow.return_count):'순유출 = 대여 − 반납'}</p></InsightBanner>
      <InsightBanner title="역할 변화 후보" tone="lavender"><h3>{change?.station_id||'확인된 후보 없음'}</h3><p>{change?'30일 '+direction(30)+' → 7일 '+direction(7):'기간별 변화가 관측된 경우에만 표시합니다.'}</p></InsightBanner>
    </div>
    <div className="notice">{network.message} {network.node_selection_basis}. 중심성은 전체 OD 그래프에서 계산했고, 아래 시각화는 상위 {nodeLimit}개 대여소의 연결 중 이동량 상위 250개까지만 표시합니다.</div>
    <div className="network-toolbar"><label>노드 범위<select aria-label="네트워크 TOP N" value={nodeLimit} onChange={e=>setNodeLimit(Number(e.target.value))}><option value={30}>TOP 30</option><option value={40}>TOP 40</option><option value={50}>TOP 50</option></select></label><label>중심성 순위<select aria-label="중심성 지표" value={metric} onChange={e=>setMetric(e.target.value as Metric)}>{metrics.map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label><span>분석 기간: {network.period_start||'N/A'} ~ {network.period_end||'N/A'}</span></div>
    <div className="network-layout"><section className="panel graph-panel"><div className="panel-title"><h3>{cityName(regionId)} 공공자전거 이동 네트워크</h3><span>노드를 누르면 상세 정보를 표시합니다</span></div><div className="graph-tabs"><button className={graphMode==='all'?'selected':''} onClick={()=>setGraphMode('all')}>전체 네트워크</button><button className={graphMode==='focus'?'selected':''} disabled={!focusEdges.length} onClick={()=>setGraphMode('focus')}>{selected||'선택 대여소'} 주변</button></div><div className="network-stage"><aside className="network-info"><b>네트워크 정보</b><p>표시 노드 <strong>{number(displayNodes.length)}</strong></p><p>전체 간선 <strong>{number(network.edge_count)}</strong></p><p>표시 간선 <strong>{number(drawn.length)}</strong></p><p>확인 그래프 OD <strong>{number(odTotal)}건</strong></p><hr/><p>● 파랑: 연결 노드</p><p className="orange-text">● 주황: 선택 노드</p><small>선 굵기: 이동 건수<br/>도식의 위치는 지리적 좌표가 아닙니다.</small></aside><svg className="network-graph" viewBox="0 0 900 560" role="img" aria-label={`TOP ${nodeLimit} 대여소 이동 네트워크`}><defs><marker id="link-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0 0 L8 4 L0 8" fill="#8ab2e4"/></marker></defs>{drawn.map((e,i)=>{const a=positions[e.origin_station_id],b=positions[e.destination_station_id];if(!a||!b)return null;return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={e.origin_station_id===selected||e.destination_station_id===selected?'#3278ce':'#9dc0e7'} strokeOpacity={e.origin_station_id===selected||e.destination_station_id===selected ? .7 : .2} strokeWidth={.7+Math.sqrt(e.trip_count/maxFlow)*4} markerEnd="url(#link-arrow)"><title>{names[e.origin_station_id]||e.origin_station_id} → {names[e.destination_station_id]||e.destination_station_id}: {number(e.trip_count)}건</title></line>})}{displayNodes.map(s=>{const p=positions[s.station_id],rank=byId[s.station_id];if(!p)return null;const r=rank?6+Math.sqrt(rank.pagerank/maxRank)*13:7;return <g key={s.station_id} role="button" tabIndex={0} aria-label={`${s.station_name||s.station_id} 상세 보기`} onClick={()=>setSelected(s.station_id)} onKeyDown={e=>{if(e.key==='Enter')setSelected(s.station_id)}} className="graph-node"><circle cx={p.x} cy={p.y} r={r} fill={selected===s.station_id?'#f08b43':'#256bc0'} stroke="white" strokeWidth="2"/><title>{s.station_name||s.station_id} · PageRank {rank?.pagerank.toFixed(5)??'미확보'}</title><text x={p.x} y={p.y+24} textAnchor="middle" fontSize="11" fill="#31547d">{s.station_id}</text></g>})}</svg></div><p className="muted">노드 크기: 전체 PageRank · 선 굵기: 실제 이동 건수 · 화살표: 이동 방향. 위치 좌표를 배치에 사용하지 않은 네트워크 도식입니다.</p></section>
      <div><SectionCard title="숨은 연결 거점 후보 Top 5" note="순위 차이는 검토 근거"><SimpleDataTable headers={['대여소','이용 / PR 순위','차이']} rows={hiddenTop.map(x=>[<button className="text-button" onClick={()=>{setSelected(x.station_id);setGraphMode('focus')}}>{x.station_id}</button>,number(x.usage_rank)+' / '+number(x.pagerank_rank),number(x.rank_gap)])}/></SectionCard><SectionCard title="대여·반납 불균형 후보" note="건 · 양수 순유출 / 음수 순유입"><SimpleDataTable headers={['대여소','순유출','반복성']} rows={imbalanceTop.map(x=>[<button className="text-button" onClick={()=>setSelected(x.station_id)}>{x.station_id}</button>,number(x.net_outflow),((x.persistence_ratio||0)*100).toFixed(1)+'%'])}/></SectionCard><details className="panel network-details"><summary>선택 대여소 상세</summary>{selectedRank?<><h4>{selectedRank.station_name||selected}</h4><div className="metric-list"><p><span>PageRank</span><b>{selectedRank.pagerank.toFixed(6)}</b></p><p><span>가중 출차수</span><b>{number(selectedRank.weighted_out_degree)}</b></p><p><span>가중 입차수</span><b>{number(selectedRank.weighted_in_degree)}</b></p><p><span>매개 중심성 (표본)</span><b>{selectedRank.betweenness.toFixed(6)}</b></p><p><span>실제 대여량</span><b>{number(station?.rental_count)}</b></p></div><h4>주요 이동 관계</h4>{detailEdges.length?detailEdges.map((e,i)=><p className="edge-item" key={i}>{names[e.origin_station_id]||e.origin_station_id} → {names[e.destination_station_id]||e.destination_station_id} <b>{number(e.trip_count)}건</b></p>):<Empty>확인된 연결 없음</Empty>}<div className="roles"><Link to={`/stations?station=${encodeURIComponent(selected)}`}>이용 패턴 확인</Link><Link to={`/agent?prompt=${encodeURIComponent(selected+' 연결 중요도와 불균형을 분석해줘')}`}>Solar 분석</Link></div></>:<Empty>노드를 선택하세요.</Empty>}</details><details className="panel network-details"><summary>{metrics.find(x=>x.id===metric)?.name} 순위</summary><div className="ranking compact">{ranks.slice(0,10).map((x,i)=><button className="rank-row" key={x.station_id} onClick={()=>setSelected(x.station_id)}><span className="rank">{i+1}</span><b>{x.station_name||x.station_id}</b><span>{metric==='weighted_in_degree'||metric==='weighted_out_degree'?number(x[metric]):x[metric].toFixed(5)}</span></button>)}</div><p className="muted">매개 중심성은 최대 {centrality.betweenness_sample_nodes||'N/A'}개 노드 표본 기반 근사입니다.</p></details></div></div>
    {hidden.available&&<details className="panel"><summary>저이용·고연결 후보 더 보기 · 이용량 순위 − PageRank 순위</summary><div className="metric-table">{hidden.candidates.filter(x=>x.candidate).slice(0,10).map(x=><button className="rank-row" key={x.station_id} onClick={()=>setSelected(x.station_id)}><b>{x.station_name||x.station_id}</b><span>이용 {x.usage_rank}위 · PageRank {x.pagerank_rank}위</span><span>순위 차이 +{x.rank_gap}</span></button>)}</div><p className="muted">판정: {hidden.selection_rule?.basis}. {hidden.message} 주요 연결은 실제 OD 가중치로 계산합니다.</p></details>}
    <div className="grid-two movement-bottom"><SectionCard title="주요 OD 연결 Top 10" note="시각화 대상 간 실제 OD · 건"><SimpleDataTable headers={['출발','도착','이동 건수']} rows={[...network.edges].sort((a,b)=>b.trip_count-a.trip_count).slice(0,10).map(x=>[x.origin_station_id,x.destination_station_id,number(x.trip_count)])}/></SectionCard><SectionCard title="중심성 지표 비교" note="전체 그래프 기준 · 표본 근사 포함"><SimpleDataTable headers={['대여소','PageRank','매개 중심성']} rows={ranks.slice(0,5).map(x=>[x.station_id,x.pagerank.toFixed(5),x.betweenness.toFixed(5)])}/></SectionCard><SummaryBulletCard title="해석 가이드" items={['중심성이 높다고 운영 중요도가 확정되는 것은 아닙니다.','순유출은 대여 − 반납입니다. 실제 재고 부족을 뜻하지 않습니다.','매개 중심성은 표본 근사이며 오차를 고려해야 합니다.','후보의 관측량과 기간 안정성을 함께 검토하세요.']}/>
    <SectionCard title="시간대별 순유출 변화" note="선택 대여소 · 대여 − 반납 · 건">
      {station?.hourly_net_outflow?.length?<div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={station.hourly_net_outflow.map((value,hour)=>({hour:hour+'시',value}))}><CartesianGrid stroke="#e6edf5" vertical={false}/><XAxis dataKey="hour" interval={2}/><YAxis/><Tooltip formatter={v=>number(Number(v))+'건'}/><Bar dataKey="value" name="순유출" fill="#d78369" isAnimationActive={false}/></BarChart></ResponsiveContainer></div>:<Empty>선택 대여소 시간대별 불균형 자료를 확인 중이거나 미확보 상태입니다.</Empty>}
      <p className="muted">양수는 순유출, 음수는 순유입입니다. 실제 재고 부족을 뜻하지 않습니다.</p>
    </SectionCard>
    </div>
    {validation?.available&&<section className="panel"><div className="panel-title"><h3>숨은 연결 거점 검증</h3><span>{validation.role}</span></div><div className="metric-table">{validation.windows.map(w=><div key={w.days}><b>{w.days}일 · PageRank {w.pagerank_rank??'N/A'}위</b><span>이용량 {w.usage_rank??'N/A'}위 · 백분위 {w.pagerank_percentile==null?'N/A':(w.pagerank_percentile*100).toFixed(1)+'%'}</span><span>대여 {number(w.rental_count)} · 반납 {number(w.return_count)} · 최소 관측 {w.minimum_observation_pass?'충족':'미충족'}</span></div>)}</div><p>{validation.why_not_usage_top}</p><p className="muted">3개 기간 중 후보 판정 {validation.sensitivity.candidate_windows}회 · PageRank 순위 범위 {validation.sensitivity.pagerank_rank_span}위. {validation.message}</p><details><summary>검증 한계</summary><ul>{validation.limitations.map(x=><li key={x}>{x}</li>)}</ul></details></section>}
    <div className="notice">연결 중심성이 높은 대여소는 이용량이 많다는 의미와 반드시 같지 않으며, 이동 네트워크에서 중요한 연결 역할을 수행할 수 있습니다.</div><SourceNote data={network}/></>
}
