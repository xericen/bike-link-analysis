import type { CentralityResult, ChatResult, ClusterResult, CompareResult, DataSource, Network, Overview, Region, SimilarityResult, SourceInfo, Station } from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `요청 실패 (${response.status})`
    try { const body = await response.json(); message = body.detail || message } catch { /* keep status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
const dates = (start?: string, end?: string) => {
  const p = new URLSearchParams()
  if (start) p.set('date_start', start)
  if (end) p.set('date_end', end)
  return p.toString() ? '?' + p : ''
}
const base = (id: string) => '/api/regions/' + encodeURIComponent(id)
export const api = {
  regions: () => request<{ regions: Region[] }>('/api/regions'),
  overview: (id: string, start?: string, end?: string) => request<Overview>(base(id) + '/overview' + dates(start, end)),
  stations: (id: string, q?: string) => request<SourceInfo & { stations: Station[]; total: number; available: boolean; message: string | null }>(base(id) + '/stations?limit=10000' + (q ? '&q=' + encodeURIComponent(q) : '')),
  station: (id: string, stationId: string) => request<SourceInfo & { station: Station; cluster: ClusterResult['clusters'][number] | null }>(base(id) + '/stations/' + encodeURIComponent(stationId)),
  clusters: (id: string, start?: string, end?: string) => request<ClusterResult>(base(id) + '/clusters' + dates(start, end)),
  network: (id: string, start?: string, end?: string) => request<Network>(base(id) + '/network' + dates(start, end)),
  centrality: (id: string, start?: string, end?: string) => request<CentralityResult>(base(id) + '/centrality' + dates(start, end)),
  similarity: (id: string, stationId: string) => request<SimilarityResult>(base(id) + '/similarity?station_id=' + encodeURIComponent(stationId)),
  compare: (ids: string[], start?: string, end?: string) => { const p = new URLSearchParams(dates(start,end).replace(/^\?/, '')); p.set('region_ids', ids.join(',')); return request<CompareResult>('/api/compare?' + p) },
  sources: (id?: string) => request<{ data_sources: DataSource[] }>('/api/data-sources' + (id ? '?region_id=' + encodeURIComponent(id) : '')),
  quality: (id?: string) => request<{ quality: Record<string, unknown> }>('/api/data-quality' + (id ? '?region_id=' + encodeURIComponent(id) : '')),
  upload: (id: string, kind: string, datasetName: string, file: File) => { const body = new FormData(); body.set('kind', kind); body.set('dataset_name', datasetName); body.set('file', file); return request<{ rows: number; message: string }>(base(id) + '/upload', { method: 'POST', body }) },
  chat: (message: string) => request<ChatResult>('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) }),
  demoOverview: (id = 'seoul') => request<{ metadata: { source: string; period_start: string; period_end: string }; total_rentals: number; station_count: number }>('/api/demo/overview?region_id=' + id)
}
