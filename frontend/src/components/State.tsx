import type { SourceInfo } from '../types'
export const number = (value: number | null | undefined) => value === null || value === undefined ? 'N/A' : value.toLocaleString()
export function SourceBadge({ data, periodStart, periodEnd }: { data?: Partial<SourceInfo>; periodStart?: string | null; periodEnd?: string | null }) {
  const name = data?.source_names?.join(', ') || '출처 미확보'
  const sourceDates = data?.sources?.flatMap(s => [s.date_start,s.date_end]).filter((x): x is string => Boolean(x)).sort() || []
  return <div className="source-badge" title={name}><span className="status-dot"/> {data?.verification_status || 'UNAVAILABLE'}{data?.sources?.some(x=>x.origin==='user_upload')?' · 사용자 업로드 포함':''} <span className="source-period">{periodStart || data?.period_start || sourceDates[0] || '기간 미확인'} ~ {periodEnd || data?.period_end || sourceDates.at(-1) || '기간 미확인'}</span></div>
}
export function SourceNote({ data }: { data?: Partial<SourceInfo> }) {
  return <p className="source-note">출처: {data?.source_names?.join(', ') || '확보되지 않음'} <span>· 최종 수집 {data?.last_updated?.slice(0,10) || '미확인'}</span>{data?.sources?.some(x=>x.origin==='user_upload')&&<span> · 사용자 업로드는 스키마만 확인</span>}</p>
}
export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) { return <div className="error" role="alert"><b>불러오지 못했습니다.</b> {message} {onRetry && <button className="button-link" onClick={onRetry}>다시 시도</button>}</div> }
export function Empty({ children }: { children: React.ReactNode }) { return <div className="empty">{children}</div> }
export function Skeleton({ rows=3 }: { rows?: number }) { return <div className="skeleton" role="status" aria-label="데이터를 불러오는 중">{Array.from({length:rows},(_,i)=><span key={i}/>)}</div> }
