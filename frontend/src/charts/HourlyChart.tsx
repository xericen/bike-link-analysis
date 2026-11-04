import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
export function HourlyChart({ values }: { values: number[] }) {
  const chart = values.map((value, hour) => ({ hour: `${hour}시`, value }))
  return <div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart} margin={{ top: 12, right: 12, bottom: 0, left: -14 }}><defs><linearGradient id="areaColor" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#3b82f6" stopOpacity={0.35}/><stop offset="100%" stopColor="#3b82f6" stopOpacity={0.02}/></linearGradient></defs><CartesianGrid stroke="#e2e8f0" vertical={false}/><XAxis dataKey="hour" tick={{ fontSize: 11 }} interval={3}/><YAxis tick={{ fontSize: 11 }}/><Tooltip/><Area isAnimationActive={false} type="monotone" dataKey="value" name="이용량" stroke="#2563eb" strokeWidth={3} fill="url(#areaColor)"/></AreaChart></ResponsiveContainer></div>
}
