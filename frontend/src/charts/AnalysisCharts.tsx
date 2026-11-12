import { CartesianGrid, Legend, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Station } from '../types'
import { stationHours } from '../services/presentation'
import { Empty } from '../components/State'
export function StationPatternChart({station}:{station?:Station}) {
  if(!station?.hourly?.length)return <Empty>시간대별 이용 자료 미확보</Empty>
  const data=stationHours(station), peak=data.reduce((best,x)=>((x.rental??0)>(best.rental??0)?x:best),data[0])
  return <><div className="chart"><ResponsiveContainer width="100%" height="100%"><LineChart data={data}><CartesianGrid stroke="#e6edf5" vertical={false}/><XAxis dataKey="hour" interval={3} fontSize={11}/><YAxis fontSize={11}/><Tooltip formatter={v=>Number(v).toLocaleString()+'건'}/><Legend/><ReferenceLine x={peak.hour} stroke="#7c66cc" strokeDasharray="4 4" label={{value:peak.hour+' 대여 집중',fontSize:10}}/><Line dataKey="rental" name="대여량" stroke="#2f6df6" dot={false} strokeWidth={2} isAnimationActive={false}/><Line dataKey="returns" name="반납량" stroke="#40a68d" dot={false} strokeWidth={2} isAnimationActive={false}/><Line dataKey="total" name="총 이용량" stroke="#a78bda" dot={false} strokeWidth={2} isAnimationActive={false}/></LineChart></ResponsiveContainer></div><p className="muted">단위: 건 · 반납 시간대는 대여량 − 순유출로 복원하며 미확보 값은 그리지 않습니다.</p></>
}
