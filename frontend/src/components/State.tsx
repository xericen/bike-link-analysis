import type { SourceInfo } from '../types'
export function SourceBadge({ data, periodStart, periodEnd }: { data?: Partial<SourceInfo>; periodStart?: string | null; periodEnd?: string | null }) {
  const name = data?.source_names?.join(', ') || '출처 미확보'
  const sourceDates = data?.sources?.map(s => [s.date_start,s.date_end]).flat().filter((x): x is string => Boolean(x)).sort() || []
  return <div className="badge" title={name}>{data?.verification_status || 'UNAVAILABLE'} · {periodStart || data?.period_start || sourceDates[0] || '기간 미확인'} ~ {periodEnd || data?.period_end || sourceDates[sourceDates.length-1] || '기간 미확인'} · 갱신 {data?.last_updated?.slice(0,10) || '미확인'}</div>
}
export function SourceNote({ data }: { data?: Partial<SourceInfo> }) {
  return <p className="muted">출처: {data?.source_names?.join(', ') || '확보되지 않음'} · 최종 수집: {data?.last_updated?.slice(0,10) || '미확인'}</p>
}
export function ErrorBox({ message }: { message: string }) { return <div className="error" role="alert">{message}</div> }
export function Empty({ children }: { children: React.ReactNode }) { return <div className="empty">{children}</div> }
