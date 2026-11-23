import { useEffect, useState } from 'react'
import { SectionCard, SimpleDataTable, StatCard } from './AnalysisUI'
import { Empty, ErrorBox, Skeleton, number } from './State'
import { cityName } from '../services/presentation'

type Row={month:string;region_id?:string;rental_count:number;daily_average:number;observed_days:number;expected_days:number;complete:boolean;missing_dates:string[];anchor_linked_ratio:number;unknown_endpoint_ratio:number;trend_height:number}
type Summary={rental_count:number;month_count:number;city_count?:number;daily_average:number;peak_hours:number[];hourly:{hour:number;count:number;height:number}[]}
type Trends={available:boolean;message?:string;selected_year:number;years:number[];available_month_count:number;months:Row[];display_start:string;display_end:string;summary:Summary;eligible_months:number;limitations:string[];repeated_candidates:{station_id:string;station_name:string;top10_months:number}[]}
export function MonthlyTrends({regionId}:{regionId:string}){
  const [year,setYear]=useState(0),[data,setData]=useState<Trends>(),[error,setError]=useState('')
  useEffect(()=>{setYear(0)},[regionId])
  useEffect(()=>{let active=true;setData(undefined);setError('')
    const mount=import.meta.env.BASE_URL.replace(/\/$/,'')
    fetch(mount+'/assets/bike-link/usage/'+encodeURIComponent(regionId)+'.json?v=20261123-usage2',{cache:'no-cache'}).then(async r=>{if(!r.ok)throw new Error('월별 집계 파일을 불러오지 못했습니다.');return r.json()}).then(x=>{if(active){const view=x.views[year||'all'];if(!view)throw new Error('조회 기간이 없습니다.');setData(view)}}).catch(e=>{if(active)setError(e.message)})
    return()=>{active=false}
  },[regionId,year])
  const pct=(x:number)=>Number.isFinite(x)?(100*x).toFixed(1)+'%':'미확인'
  const all=regionId==='all'
  return <SectionCard title={all?'세 도시 공통 12월 비교':'도시별 월간 변화'} note={all?'공통 2025년 12월':'도시 전체 이용 · 보유 기간 전체 조회'}>
    {error?<ErrorBox message={error}/>:!data?<Skeleton rows={3}/>:!data.available?<Empty>{data.message}</Empty>:<>
      {!all&&<label>조회 기간 <select aria-label="월간 변화 기간" value={year} onChange={e=>setYear(Number(e.target.value))}><option value={0}>전체 기간 · {data.available_month_count}개월</option>{data.years.map(y=><option key={y} value={y}>{y}년</option>)}</select></label>}
      <p className="muted">{all?'서울·대전·세종 공통':cityName(regionId)} · {data.display_start} ~ {data.display_end}</p>
      <div className="stats">
        <StatCard label="전체 대여" value={number(data.summary.rental_count)+'건'} note="표시된 도시·기간의 실제 이용"/>
        <StatCard label={all?'비교 도시':'조회 개월'} value={all?'3개 도시':data.summary.month_count+'개월'} note={all?'공통 2025년 12월':'선택 기간 전체'}/>
        <StatCard label="관측일당 평균 대여" value={number(Math.round(data.summary.daily_average))+'건'} note="미관측일은 0건으로 채우지 않음"/>
        <StatCard label="이용이 가장 많은 시간" value={data.summary.peak_hours.join('·')+'시'} note="표시된 기간의 시간대별 합계"/>
      </div>
      {!all&&<><h4>월별 이용 흐름</h4><p className="muted">관측일당 평균 대여 건수</p><div style={{overflowX:'auto'}}><div role="img" aria-label="전체 기간 월별 평균 대여" style={{display:'flex',gap:5,height:220,minWidth:data.months.length*34}}>{data.months.map(m=><div key={m.month} style={{flex:1,minWidth:28,height:'100%',display:'flex',flexDirection:'column',justifyContent:'flex-end'}}><i title={m.month+' · 평균 '+number(Math.round(m.daily_average))+'건'} style={{display:'block',height:m.trend_height+'%',background:'#328af3',borderRadius:'3px 3px 0 0'}}/><small style={{fontSize:9,whiteSpace:'nowrap',transform:'rotate(-45deg)',marginTop:12}}>{m.month}</small></div>)}</div></div></>}
      <h4>시간대별 전체 이용</h4>
      <div role="img" aria-label="선택 기간 전체 이용 시간대 분포" style={{display:'flex',gap:4,height:180,marginBottom:20}}>{data.summary.hourly.map(h=><div key={h.hour} style={{flex:1,height:'100%',display:'flex',flexDirection:'column',justifyContent:'flex-end'}}><i title={h.hour+'시 · '+number(h.count)+'건'} style={{display:'block',height:h.height+'%',background:'#328af3',borderRadius:3}}/><small>{h.hour%3===0?h.hour+'시':' '}</small></div>)}</div>
      <details open={all||undefined}><summary>{all?'도시별 공통 12월 수치':'월별 수치 전체 보기 · '+data.summary.month_count+'개월'}</summary>
        <SimpleDataTable headers={[all?'도시':'월','대여 건수','관측일당 평균','역·BRT 300m 주변 이용','위치 미연결 이용','자료 상태']} rows={data.months.map(m=>[all?cityName(m.region_id||''):m.month,number(m.rental_count)+'건',number(Math.round(m.daily_average))+'건',pct(m.anchor_linked_ratio),pct(m.unknown_endpoint_ratio),m.complete?m.observed_days+'일 관측':m.observed_days+'/'+m.expected_days+'일 · 미관측 '+m.missing_dates.join(', ')])}/>
      </details>
      {!all&&<details><summary>개선 후보의 반복성</summary><p className="muted">날짜가 모두 관측된 {data.eligible_months}개월 중 상위10에 든 횟수입니다.</p><SimpleDataTable headers={['기존 취약 대여소','반복 횟수']} rows={data.repeated_candidates.map(x=>[x.station_id+' · '+x.station_name,x.top10_months+'개월'])}/></details>}
      <details><summary>계산 기준과 한계</summary>{data.limitations.map((x,i)=><p className="muted" key={i}>{x}</p>)}</details>
    </>}
  </SectionCard>
}
