import { CircleMarker, MapContainer, Popup, TileLayer } from 'react-leaflet'
import type { Station } from '../types'
import 'leaflet/dist/leaflet.css'
export function StationMap({ stations }: { stations: Station[] }) {
  const located = stations.filter((s): s is Station & { latitude: number; longitude: number } => s.latitude !== null && s.longitude !== null)
  if (!located.length) return <div className="empty">좌표가 확인된 대여소가 없습니다.</div>
  const center: [number, number] = [located.reduce((n,s) => n+s.latitude,0)/located.length, located.reduce((n,s) => n+s.longitude,0)/located.length]
  return <div className="map"><MapContainer key={center.join(',')} center={center} zoom={11} scrollWheelZoom={false} style={{height:'100%',width:'100%'}}><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{located.map(station => <CircleMarker key={station.station_id} center={[station.latitude,station.longitude]} radius={5} pathOptions={{color:'#1d4ed8',fillColor:'#60a5fa',fillOpacity:.8}}><Popup><strong>{station.station_name || station.station_id}</strong><br/>공식 대여소 위치 · 이용량 {station.rental_count === undefined || station.rental_count === null ? 'N/A' : station.rental_count.toLocaleString()+'건'}</Popup></CircleMarker>)}</MapContainer></div>
}
