import { useEffect, useState } from 'react'
import { BrowserRouter, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { api } from './services/api'
import type { Region } from './types'
import { Dashboard } from './pages/Dashboard'
import { StationAnalysis } from './pages/StationAnalysis'
import { NetworkAnalysis } from './pages/NetworkAnalysis'
import { RegionComparison } from './pages/RegionComparison'
import { AIAgent } from './pages/AIAgent'
import { DemoMode } from './pages/DemoMode'

const navigation = [
  { path: '/dashboard', icon: '◫', label: '종합 대시보드' },
  { path: '/stations', icon: '◎', label: '대여소 분석' },
  { path: '/network', icon: '⌁', label: '이동 네트워크' },
  { path: '/regions', icon: '▤', label: '지역 비교' },
  { path: '/agent', icon: '✦', label: 'AI 분석 에이전트' },
  { path: '/demo', icon: '◇', label: 'Demo Mode' }
]
function Layout() {
  const [regions, setRegions] = useState<Region[]>([])
  const [regionId, setRegionId] = useState('seoul')
  const [error, setError] = useState('')
  const navigate = useNavigate()
  const location = useLocation()
  useEffect(() => { api.regions().then(result => setRegions(result.regions)).catch(err => setError(err.message)) }, [])
  const current = regions.find(r => r.region_id === regionId)
  return <div className="shell"><aside className="sidebar"><div className="brand"><span className="brand-icon">↗</span><span>BIKE LINK<small>ANALYSIS · TEAM 234</small></span></div><p className="nav-caption">WORKSPACE</p><nav>{navigation.map(item => <NavLink key={item.path} to={item.path} className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}><span className="nav-icon">{item.icon}</span>{item.label}</NavLink>)}</nav><div className="sidebar-note"><b>데이터 상태</b><p>{current?.region_name || '지역'}: {current?.availability || '확인 중'} · 이용 기록 {current?.has_usage ? '확보' : '미확보'} · OD {current?.has_od ? '확보' : '미확보'}</p></div></aside><div className="main"><header className="topbar"><div><div className="eyebrow">PUBLIC BIKE INTELLIGENCE</div><h1>Bike Link Analysis</h1></div><div className="top-actions"><label className="region-select">지역 <select value={location.pathname === '/regions' ? 'compare' : regionId} onChange={event => { if (event.target.value === 'compare') navigate('/regions'); else { setRegionId(event.target.value); if (location.pathname === '/regions') navigate('/dashboard') } }}>{regions.map(region => <option key={region.region_id} value={region.region_id}>{region.region_name} · {region.service_name}</option>)}<option value="compare">지역 비교</option></select></label></div></header><main className="content">{error && <p role="alert">{error}</p>}<Routes><Route path="/" element={<Navigate to="/dashboard" replace/>}/><Route path="/dashboard" element={<Dashboard regionId={regionId}/>}/><Route path="/stations" element={<StationAnalysis regionId={regionId}/>}/><Route path="/network" element={<NetworkAnalysis regionId={regionId}/>}/><Route path="/regions" element={<RegionComparison/>}/><Route path="/agent" element={<AIAgent/>}/><Route path="/demo" element={<DemoMode/>}/></Routes></main></div></div>
}
export default function App() { return <BrowserRouter><Layout/></BrowserRouter> }
