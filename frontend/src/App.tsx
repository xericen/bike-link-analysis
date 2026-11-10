import { lazy, Suspense, useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './services/api'
import type { DataSource, DateFilter, Region } from './types'
import { ErrorBox, Skeleton } from './components/State'
const Dashboard = lazy(() => import('./pages/Dashboard').then(m => ({default:m.Dashboard})))
const StationAnalysis = lazy(() => import('./pages/StationAnalysis').then(m => ({default:m.StationAnalysis})))
const NetworkAnalysis = lazy(() => import('./pages/NetworkAnalysis').then(m => ({default:m.NetworkAnalysis})))
const RegionComparison = lazy(() => import('./pages/RegionComparison').then(m => ({default:m.RegionComparison})))
const AIAgent = lazy(() => import('./pages/AIAgent').then(m => ({default:m.AIAgent})))
const DataStatus = lazy(() => import('./pages/DataStatus').then(m => ({default:m.DataStatus})))
const DemoMode = lazy(() => import('./pages/DemoMode').then(m => ({default:m.DemoMode})))


const initialRegions: Region[] = [
  {region_id:'seoul',region_name:'서울',service_name:'따릉이',operator:'',availability:'확인 중',has_usage:false,has_od:false},
  {region_id:'daejeon',region_name:'대전',service_name:'타슈',operator:'',availability:'확인 중',has_usage:false,has_od:false},
  {region_id:'sejong',region_name:'세종',service_name:'어울링',operator:'',availability:'확인 중',has_usage:false,has_od:false}
]
const navigation = [
  { path:'/dashboard', icon:'▦', label:'Overview', ko:'종합 현황' },
  { path:'/stations', icon:'◎', label:'Station Analysis', ko:'대여소 분석' },
  { path:'/network', icon:'⌁', label:'Network Analysis', ko:'이동 네트워크' },
  { path:'/regions', icon:'▤', label:'Region Comparison', ko:'지역 비교' },
  { path:'/agent', icon:'✦', label:'AI Agent', ko:'AI 분석' },
  { path:'/status', icon:'◉', label:'Data Status', ko:'데이터 현황' },
  { path:'/demo', icon:'◇', label:'Demo Mode', ko:'샘플 분리' }
]
const saved = (key:string, fallback:string) => { try { return localStorage.getItem(key)||fallback } catch { return fallback } }
function Layout() {
  const [regions,setRegions]=useState<Region[]>(initialRegions)
  const [sources,setSources]=useState<DataSource[]>([])
  const [regionId,setRegionId]=useState(()=>saved('bike.region','seoul'))
  const [filter,setFilter]=useState<DateFilter>(()=>({start:saved('bike.start',''),end:saved('bike.end','')}))
  const [error,setError]=useState('')
  const location=useLocation(), navigate=useNavigate()
  useEffect(()=>{ api.regions().then(x=>{setRegions(x.regions);if(!x.regions.some(r=>r.region_id===regionId))setRegionId('seoul')}).catch(e=>setError(e.message));api.sources().then(x=>setSources(x.data_sources)).catch(()=>{}) },[])
  useEffect(()=>{localStorage.setItem('bike.region',regionId)},[regionId])
  useEffect(()=>{localStorage.setItem('bike.start',filter.start);localStorage.setItem('bike.end',filter.end)},[filter])
  const current=regions.find(x=>x.region_id===regionId)
  const page=navigation.find(x=>x.path===location.pathname)
  const updated=sources.filter(s=>s.region_id===regionId&&s.verification_status==='VERIFIED').map(s=>s.collected_at).filter((x):x is string=>Boolean(x)).sort().at(-1)
  const setDate=(key:keyof DateFilter,value:string)=>setFilter(old=>({...old,[key]:value}))
  return <div className="shell">
    <aside className="sidebar"><div className="brand"><span className="brand-icon">↗</span><span>BIKE LINK<small>ANALYSIS · TEAM 234</small></span></div><p className="nav-caption">WORKSPACE</p><nav aria-label="주 메뉴">{navigation.map(item=><NavLink key={item.path} to={item.path} className={({isActive})=>`nav-item ${isActive?'active':''}`}><span className="nav-icon">{item.icon}</span><span><b>{item.label}</b><small>{item.ko}</small></span></NavLink>)}</nav><div className="sidebar-note"><b>DATA COVERAGE</b><p>{current?.region_name||'지역'} · {current?.has_usage?'이용 기록 확보':'이용 기록 미확보'}</p><p>OD {current?.has_od?'분석 가능':'미확보'} · {current?.availability||'확인 중'}</p></div></aside>
    <div className="main"><header className="topbar"><div className="header-title"><span className="eyebrow">CITY MOBILITY INTELLIGENCE</span><h1>{page?.label||'Bike Link Analysis'} <small>{page?.ko||''}</small></h1></div><div className="top-actions"><label>지역<select aria-label="분석 지역" value={location.pathname==='/regions'?'compare':regionId} onChange={e=>{if(e.target.value==='compare') navigate('/regions');else{setRegionId(e.target.value);if(location.pathname==='/regions')navigate('/dashboard')}}}>{regions.map(r=><option key={r.region_id} value={r.region_id}>{r.region_name} · {r.service_name}</option>)}<option value="compare">지역 비교</option></select></label><label>시작<input aria-label="분석 시작일" type="date" value={filter.start} onChange={e=>setDate('start',e.target.value)}/></label><label>종료<input aria-label="분석 종료일" type="date" value={filter.end} onChange={e=>setDate('end',e.target.value)}/></label><span className="header-update">갱신 {updated?.slice(0,10)||'미확인'}</span></div></header>
      <main className="content">{error&&<ErrorBox message={error}/>}<Suspense fallback={<Skeleton rows={4}/>}><Routes><Route path="/" element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Dashboard regionId={regionId} filter={filter}/>}/><Route path="/stations" element={<StationAnalysis regionId={regionId} filter={filter}/>}/><Route path="/network" element={<NetworkAnalysis regionId={regionId} filter={filter}/>}/><Route path="/regions" element={<RegionComparison filter={filter}/>}/><Route path="/agent" element={<AIAgent/>}/><Route path="/status" element={<DataStatus/>}/><Route path="/demo" element={<DemoMode/>}/></Routes></Suspense></main></div></div>
}
export default function App(){return <BrowserRouter><Layout/></BrowserRouter>}
