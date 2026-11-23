import { individualScopes } from './services/individual'
import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { AuditDataInfo } from './components/AuditDataInfo'
import { api } from './services/api'
import type { DataSource, DateFilter, Region } from './types'
import { ErrorBox, Skeleton } from './components/State'
const Dashboard = lazy(() => import('./pages/ResearchOverview').then(m => ({default:m.ResearchOverview})))
const Improvements = lazy(() => import('./pages/Improvements').then(m => ({default:m.Improvements})))
const StationAnalysis = lazy(() => import('./pages/StationAnalysis').then(m => ({default:m.StationAnalysis})))
const NetworkAnalysis = lazy(() => import('./pages/NetworkAnalysis').then(m => ({default:m.NetworkAnalysis})))
const RegionComparison = lazy(() => import('./pages/RegionComparison').then(m => ({default:m.RegionComparison})))
const AIAgent = lazy(() => import('./pages/AIAgent').then(m => ({default:m.AIAgent})))
const Conclusion = lazy(() => import('./pages/Conclusion').then(m => ({default:m.Conclusion})))
const DataStatus = lazy(() => import('./pages/DataStatus').then(m => ({default:m.DataStatus})))
const DemoMode = lazy(() => import('./pages/DemoMode').then(m => ({default:m.DemoMode})))


const initialRegions: Region[] = [
  {region_id:'seoul',region_name:'서울',service_name:'따릉이',operator:'',availability:'확인 중',has_usage:false,has_od:false},
  {region_id:'daejeon',region_name:'대전',service_name:'타슈',operator:'',availability:'확인 중',has_usage:false,has_od:false},
  {region_id:'sejong',region_name:'세종',service_name:'어울링',operator:'',availability:'확인 중',has_usage:false,has_od:false}
]
const navigation = [
  { path:'/dashboard', icon:'▦', label:'한눈에 보기', ko:'종합 현황' },
  { path:'/improvements', icon:'◎', label:'개선 지역 찾기', ko:'기존·신규·재배치 검토' },
  { path:'/stations', icon:'⌁', label:'자전거 이용 분석', ko:'전체 이용·월별 추이' },
  { path:'/agent', icon:'✦', label:'AI 분석 리포트', ko:'근거 중심 운영 검토' },
  { path:'/conclusion', icon:'✓', label:'분석 결론', ko:'공통 비교·최종 검토 후보' }
]
const saved = (key:string, fallback:string) => { try { return localStorage.getItem(key)||fallback } catch { return fallback } }
function Layout() {
  const [regions,setRegions]=useState<Region[]>(initialRegions)
  const [sources,setSources]=useState<DataSource[]>([])
  const [regionId,setRegionId]=useState(()=>(['seoul','daejeon','sejong'].includes(saved('bike.region','seoul'))?saved('bike.region','seoul'):'seoul'))
  const [scopes,setScopes]=useState<any>()
  const [filter,setFilter]=useState<DateFilter>({start:'2025-12-01',end:'2025-12-31'})
  const [error,setError]=useState('')
  const location=useLocation(), navigate=useNavigate()
  useEffect(()=>{ api.regions().then(x=>{setRegions(x.regions.filter(r=>['seoul','daejeon','sejong'].includes(r.region_id)));if(!x.regions.some(r=>r.region_id===regionId))setRegionId('seoul')}).catch(e=>setError(e.message));api.sources().then(x=>setSources(x.data_sources)).catch(()=>{}) },[])
  useEffect(()=>{individualScopes().then(setScopes)},[])
  useEffect(()=>{localStorage.setItem('bike.region',regionId);if(scopes?.cities?.[regionId]){const s=scopes.cities[regionId];setFilter({start:s.start,end:s.end})}},[regionId,scopes])
  useEffect(()=>{localStorage.setItem('bike.start',filter.start);localStorage.setItem('bike.end',filter.end)},[filter])
  const referenceParams=new URLSearchParams(location.search)
  const referenceMode=referenceParams.get('reference')==='2025-12'
  const referenceRegion=referenceParams.get('region')||regionId
  const activeRegionId=referenceMode&&['seoul','daejeon','sejong'].includes(referenceRegion)?referenceRegion:regionId
  const comparisonMode=location.pathname==='/regions'||referenceParams.get('comparison')==='1'
  const activeFilter=(referenceMode||comparisonMode)?{start:'2025-12-01',end:'2025-12-31'}:filter
  const current=regions.find(x=>x.region_id===activeRegionId)
  const page=navigation.find(x=>x.path===(location.pathname==='/network'?'/stations':location.pathname))
  const updated=sources.filter(s=>s.region_id===regionId&&s.verification_status==='VERIFIED').map(s=>s.collected_at).filter((x):x is string=>Boolean(x)).sort().at(-1)
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-icon">↗</span><span>Bike Link Analysis<small>Team 234</small></span></div><p className="nav-caption">WORKSPACE</p><nav aria-label="주 메뉴">{navigation.map(item=><NavLink key={item.path} to={item.path} className={({isActive})=>`nav-item ${isActive||(item.path==='/stations'&&location.pathname==='/network')?'active':''}`}><span className="nav-icon">{item.icon}</span><span><b>{item.label}</b><small>{item.ko}</small></span></NavLink>)}</nav><div className="sidebar-note"><b>DATA COVERAGE</b><p>{current?.region_name||'지역'} · {current?.has_usage?'이용 기록 확보':'이용 기록 미확보'}</p><p>OD {current?.has_od?'분석 가능':'미확보'} · {current?.availability||'확인 중'}</p></div></aside>
    <div className="main"><header className="topbar"><div className="header-title"><span className="eyebrow">공공자전거 네트워크 인사이트</span><h1>{page?.label||'Bike Link Analysis'} <small>{page?.ko||''}</small></h1></div><div className="top-actions"><label>지역<select aria-label="분석 지역" value={location.pathname==='/regions'?'compare':activeRegionId} onChange={e=>{if(e.target.value==='compare') navigate('/dashboard?comparison=1');else{setRegionId(e.target.value);navigate(location.pathname);if(location.pathname==='/regions')navigate('/dashboard')}}}>{regions.map(r=><option key={r.region_id} value={r.region_id}>{r.region_name} · {r.service_name}</option>)}<option value="compare">지역 비교</option></select></label>{location.pathname!=='/conclusion'&&<span className="header-update">{activeFilter.start} ~ {activeFilter.end}</span>}<span className="header-update">갱신 {updated?.slice(0,10)||'미확인'}</span></div></header>
      <main className="content">{referenceMode&&<p className="notice">검증에서 선택한 공통2025년12월 상세입니다. 도시별 전체 기간과 구분합니다.</p>}{location.pathname!=='/conclusion'&&<p className="source-note">{location.pathname==='/stations'?'도시별 전체 이용·대여소·이동 연결은 '+activeFilter.start+' ~ '+activeFilter.end+' 기준입니다.':('관측 기간: '+activeFilter.start+' ~ '+activeFilter.end+' · 위치·시설·앵커 자료 기준일은 하단 정보 참조')}</p>}{['/stations','/network'].includes(location.pathname)&&<nav className="compare-controls" aria-label="자전거 이용 분석 하위 보기"><NavLink to={'/stations'+location.search}>도시 전체 이용</NavLink><NavLink to={'/network'+location.search}>이동 연결·패턴</NavLink></nav>}{error&&<ErrorBox message={error}/>}<Suspense fallback={<Skeleton rows={4}/>}><Routes><Route path="/" element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Dashboard regionId={activeRegionId} filter={activeFilter}/>}/><Route path="/improvements" element={<Improvements regionId={activeRegionId} filter={activeFilter}/>}/><Route path="/stations" element={<StationAnalysis regionId={activeRegionId} filter={activeFilter}/>}/><Route path="/network" element={<NetworkAnalysis regionId={activeRegionId} filter={activeFilter}/>}/><Route path="/regions" element={<RegionComparison filter={{start:'2025-12-01',end:'2025-12-31'}}/>}/><Route path="/agent" element={<AIAgent regionId={activeRegionId} filter={activeFilter}/>}/><Route path="/conclusion" element={<Conclusion regionId={activeRegionId}/>}/><Route path="/station-analysis" element={<Navigate to={'/stations'+location.search} replace/>}/><Route path="/movement-analysis" element={<Navigate to={'/network'+location.search} replace/>}/><Route path="/city-comparison" element={<Navigate to={'/regions'+location.search} replace/>}/><Route path="/ai-report" element={<Navigate to={'/agent'+location.search} replace/>}/><Route path="/status" element={<DataStatus/>}/><Route path="/demo" element={<DemoMode/>}/></Routes></Suspense>{location.pathname!=='/conclusion'&&<AuditDataInfo regionId={activeRegionId} filter={activeFilter}/>}<footer className="app-footer"><span className="status-dot"/> 공식 출처 확인 자료 · 가공 범위 표시 · 분석 후보는 추가 검토가 필요합니다.</footer></main></div></div>
}
export default function App(){return <BrowserRouter basename={import.meta.env.BASE_URL.replace(/\/$/, '') || '/'}><Layout/></BrowserRouter>}
