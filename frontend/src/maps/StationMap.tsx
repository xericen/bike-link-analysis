import { useEffect, useMemo, useState } from 'react'
import { CircleMarker, MapContainer, Marker, Popup, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import { divIcon } from 'leaflet'
import type { Station } from '../types'
import { clusterColor } from '../components/colors'
import { number } from '../components/State'
import 'leaflet/dist/leaflet.css'

type Props = { stations: Station[]; selectedId?: string; onSelect?: (id: string) => void; clusterById?: Record<string,number>; height?: number }
function MapWatcher({ setZoom }: {setZoom:(n:number)=>void}) { useMapEvents({zoomend: e => setZoom(e.target.getZoom())}); return null }
function Focus({ station }: {station?: Station}) { const map=useMap(); useEffect(() => { if (station?.latitude != null && station?.longitude != null) map.flyTo([station.latitude,station.longitude],14) }, [station?.station_id,map]); return null }
export function StationMap({ stations, selectedId, onSelect, clusterById={}, height=350 }: Props) {
  const located = useMemo(() => stations.filter((s): s is Station & {latitude:number;longitude:number} => s.latitude != null && s.longitude != null),[stations])
  const [zoom,setZoom] = useState(11)
  const selected = located.find(s => s.station_id === selectedId)
  const center: [number,number] = located.length ? [located.reduce((n,s)=>n+s.latitude,0)/located.length,located.reduce((n,s)=>n+s.longitude,0)/located.length] : [37.5665,126.978]
  const groups = useMemo(() => {
    if (zoom >= 13) return located.map(s => [s])
    const cell = zoom < 10 ? .08 : zoom < 12 ? .03 : .012
    const buckets = new Map<string,typeof located>()
    for (const station of located) {
      const key = Math.floor(station.latitude/cell)+':'+Math.floor(station.longitude/cell)
      const list=buckets.get(key)||[];list.push(station);buckets.set(key,list)
    }
    return [...buckets.values()]
  },[located,zoom])
  if (!located.length) return <div className="empty">좌표가 확인된 대여소가 없습니다.</div>
  return <div className="map" style={{height}}><MapContainer key={stations[0]?.region_id || 'map'} center={center} zoom={11} scrollWheelZoom style={{height:'100%',width:'100%'}}><MapWatcher setZoom={setZoom}/><Focus station={selected}/><TileLayer attribution='&copy; OpenStreetMap contributors' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"/>{groups.map((group,i) => {
    if (group.length > 1) {
      const lat=group.reduce((n,s)=>n+s.latitude,0)/group.length, lon=group.reduce((n,s)=>n+s.longitude,0)/group.length
      const icon=divIcon({className:'map-cluster',html:'<span>'+group.length+'</span>',iconSize:[34,34]})
      return <Marker key={'group-'+i} position={[lat,lon]} icon={icon} eventHandlers={{click:e => e.target._map.flyTo([lat,lon],Math.min(zoom+2,15))}}><Tooltip>{group.length}개 대여소 · 클릭하여 확대</Tooltip></Marker>
    }
    const s=group[0];const color=clusterColor(clusterById[s.station_id])
    return <CircleMarker key={s.station_id} center={[s.latitude,s.longitude]} radius={s.station_id===selectedId?9:6} pathOptions={{color,fillColor:color,fillOpacity:.82,weight:2}} eventHandlers={{click:()=>onSelect?.(s.station_id)}}><Popup><b>{s.station_name||s.station_id}</b><br/>{s.station_id}<br/>대여 {number(s.rental_count)}건</Popup><Tooltip direction="top" offset={[0,-8]}>{s.station_name||s.station_id}</Tooltip></CircleMarker>
  })}</MapContainer></div>
}
