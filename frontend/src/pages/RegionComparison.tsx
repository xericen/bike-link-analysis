import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../services/api'
import type { ClusterResult, CompareResult, DateFilter, Region } from '../types'
import { Empty, ErrorBox, Skeleton, SourceNote, number } from '../components/State'
import { PageHeader, StatCard, SectionCard, InsightBanner, SummaryBulletCard, ComparisonDonutCard, SimpleDataTable } from '../components/AnalysisUI'
import { cityRatios, peakHour } from '../services/presentation'
import { sejongAnnual } from '../services/sejongAnnual'

const colors:Record<string,string>={seoul:'#2f6df6',daejeon:'#35a486'}
export function RegionComparison({filter}:{filter:DateFilter}) {
  const [regions,setRegions]=useState<Region[]>([]), [ids,setIds]=useState(['seoul','daejeon','sejong'])
  const [data,setData]=useState<CompareResult>(),[clusters,setClusters]=useState<Record<string,ClusterResult>>({})
  const [error,setError]=useState('')
  useEffect(()=>{api.regions().then(x=>setRegions(x.regions.filter(r=>['seoul','daejeon','sejong'].includes(r.region_id)))).catch(e=>setError(e.message))},[])
  useEffect(()=>{
    let active=true;setData(undefined);setClusters({});setError('')
    if(!ids.length)return
    api.compare(ids,filter.start,filter.end).then(async initial=>{
      let comparison=initial
      const observed=initial.regions.filter(r=>r.region_id!=='sejong'&&r.observed_dates.length)
      if(observed.length>=2&&!initial.common_period){
        const start=observed.map(r=>r.observed_dates[0]).sort().at(-1)!,end=observed.map(r=>r.observed_dates.at(-1)!).sort()[0]
        if(start<=end){
          if(observed.some(r=>r.observed_dates[0]!==start||r.observed_dates.at(-1)!==end))comparison=await api.compare(ids,start,end)
          comparison={...comparison,common_period:{date_start:start,date_end:end}}
        }
      }
      // Always use the actual aligned period returned by the API, even with explicit user dates.
      const start=comparison.common_period?.date_start||filter.start, end=comparison.common_period?.date_end||filter.end
      const groups=await Promise.all(ids.map(id=>api.clusters(id,start,end)))
      if(active){setData(comparison);setClusters(Object.fromEntries(ids.map((id,i)=>[id,groups[i]])))}
    }).catch(e=>{if(active)setError(e.message)})
    return()=>{active=false}
  },[ids.join(','),filter.start,filter.end])
  const comparable=data?.regions.filter(r=>r.region_id!=='sejong'&&r.hourly)||[]
  const hasWeekday=comparable.some(r=>r.weekday?.length)
  const common=data?.common_period
  const annual=sejongAnnual.map(x=>({...x,complete:x.complete_year?x.rental_count:null,partial:x.complete_year?null:x.rental_count}))
  return <>
    <PageHeader title="도시 간 비교" subtitle="공통 기간 기준 패턴 비교 · 시간대 비율 · 요일 분포 · 군집 구성 비교"/>
    <div className="compare-controls region-checks">{regions.map(r=><label key={r.region_id}><input type="checkbox" checked={ids.includes(r.region_id)} onChange={e=>setIds(old=>e.target.checked?[...old,r.region_id]:old.filter(x=>x!==r.region_id))}/>{r.region_name}</label>)}<span>도시를 선택해 함께 비교하세요.</span></div>
    {!ids.length?<Empty>비교할 도시를 하나 이상 선택하세요.</Empty>:error?<ErrorBox message={error}/>:!data?<Skeleton rows={5}/>:<>
      <div className="stats"><StatCard label="비교 도시 수" value={ids.length+'개'} note="서울 · 대전 · 세종 중 선택" icon="◎"/><StatCard label="공통 비교 지역" value={comparable.map(r=>r.region_name).join(' · ')||'비교 자료 없음'} note="시간대 기록이 있는 선택 도시" tone="mint" icon="⇄"/><StatCard label="공통 관측 기간" value={common?common.date_start.slice(5)+' ~ '+common.date_end.slice(5):'공통 기간 없음'} note={common?common.date_start+' ~ '+common.date_end:'선택 도시의 관측 범위를 확인하세요.'} tone="peach" icon="◷"/><StatCard label="세종 제공 범위" value="연간 추세" note="상세 OD / 군집 자료 미확보" tone="lavender" icon="⌁"/></div>
      <InsightBanner title="비교 해석 원칙"><p>{comparable.length>=2&&!common?'공통 관측 기간이 없습니다. 현재 표시는 관측 기간이 다른 참고 패턴입니다. ':''}서울/대전은 공통 관측 기간 기준 비율로 비교합니다. 세종은 연간 추세를 별도로 제공합니다. 총량 직접 비교보다 시간대·요일 비율을 확인하세요.</p></InsightBanner>
      <div className="grid-two">
        <SectionCard title="시간대 이용 비율 비교" note="도시 내부 대여량 대비 비율 · %">
          {comparable.length?<div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={cityRatios(data)}><CartesianGrid vertical={false} stroke="#e6edf5"/><XAxis dataKey="label" interval={3}/><YAxis unit="%"/><Tooltip formatter={v=>Number(v).toFixed(2)+'%'}/><Legend/>{comparable.map(r=><Line key={r.region_id} type="monotone" dataKey={r.region_id} name={r.region_name} stroke={colors[r.region_id]} strokeWidth={3} dot={false} isAnimationActive={false}/>)}</LineChart></ResponsiveContainer></div>:<Empty>시간대별 자료 미확보</Empty>}
          <div className="chart-callout">{comparable.map(r=><span key={r.region_id}>{r.region_name}: {peakHour(r.hourly)}시 대여 비중 최대</span>)}</div>
        </SectionCard>
        <SectionCard title="요일별 이용 비율 비교" note="도시 내부 대여량 대비 비율 · %">
          {hasWeekday?<div className="chart"><ResponsiveContainer width="100%" height="100%"><BarChart data={cityRatios(data,'weekday')}><CartesianGrid vertical={false} stroke="#e6edf5"/><XAxis dataKey="label"/><YAxis unit="%"/><Tooltip formatter={v=>Number(v).toFixed(2)+'%'}/><Legend/>{comparable.map(r=><Bar key={r.region_id} dataKey={r.region_id} name={r.region_name} fill={colors[r.region_id]} radius={[4,4,0,0]} isAnimationActive={false}/>)}</BarChart></ResponsiveContainer></div>:<Empty>요일별 이용 자료 미확보</Empty>}
        </SectionCard>
      </div>
      <div className="comparison-lower">
        <SectionCard title="K-means 군집 분포 비교" note="각 도시 독립 학습">
          <div className="donut-pair">{comparable.map(r=><div key={r.region_id}><b>{r.region_name}</b><ComparisonDonutCard data={clusters[r.region_id]}/></div>)}</div>
          <SimpleDataTable headers={['도시','k','실루엣','해석']} rows={comparable.map(r=>{const c=clusters[r.region_id];return [r.region_name,c?.selected_k??'N/A',c?.diagnostics.find(x=>x.k===c.selected_k)?.silhouette.toFixed(3)??'N/A',c?.interpretation_allowed?'탐색 해석':'유형 확정 보류']})}/>
          <p className="muted">같은 군집 번호가 같은 역할을 뜻하지 않습니다.</p>
        </SectionCard>
        <SectionCard title="핵심 차이 요약" note="선택 기간 실제 관측">
          {data.regions.map(r=><div className="city-summary" key={r.region_id}><span style={{background:colors[r.region_id]||'#a18acd'}}/><div><b>{r.region_name}</b><p>{r.region_id==='sejong'?'연간 추세만 제공 · 상세 패턴 비교 제외':r.hourly?peakHour(r.hourly)+'시 대여 비중 최대 · 도시 내부 패턴 참고':'시간대 자료 미확보'}</p><small>{r.coverage_note}</small></div></div>)}
        </SectionCard>
        <SectionCard title="세종 연간 이용 추세" note="2017~2026 · 건">
          {ids.includes('sejong')?<><div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={annual}><CartesianGrid vertical={false} stroke="#e6edf5"/><XAxis dataKey="year" fontSize={10} interval="preserveStartEnd" minTickGap={20} padding={{left:6,right:15}}/><YAxis tickFormatter={v=>(Number(v)/10000).toFixed(0)+'만'} width={45}/><Tooltip formatter={v=>number(Number(v))+'건'}/><Legend/><Line dataKey="complete" name="완결 연도" stroke="#8b6ec5" strokeWidth={2} dot={{r:3}} isAnimationActive={false}/><Line dataKey="partial" name="부분 연도" stroke="#ed9a60" dot={{r:5}} isAnimationActive={false}/></LineChart></ResponsiveContainer></div><p className="muted">공식 가공 CSV의 정적 스냅샷. 2026년은 8월 31일까지의 부분 집계이며 연간 실적과 직접 비교할 수 없습니다. 상단 분석 기간과 독립적입니다.</p></>:<Empty>세종을 선택하면 연간 추세를 표시합니다.</Empty>}
        </SectionCard>
      </div>
      <SummaryBulletCard title="비교 한계" items={['데이터 출처와 집계 정의가 다릅니다.','서울 OD 집계와 대전 Trip 기록은 해석 범위가 다릅니다.','도시 간 총건수 직접 비교와 중심성 점수 순위 비교는 제한됩니다.',...data.limitations]}/>
      <details className="panel"><summary>도시별 데이터 출처와 관측 범위</summary>{data.regions.map(r=><div key={r.region_id}><h4>{r.region_name}</h4><p className="muted">{r.observed_dates.length}일 관측 · 대여소 {number(r.station_count)}개</p><SourceNote data={r}/></div>)}</details>
    </>}
  </>
}
