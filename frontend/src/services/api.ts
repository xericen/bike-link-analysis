import type { CentralityResult, ChatResult, ClusterResult, CompareResult, DataSource, Network, Overview, Region, SimilarityResult, SourceInfo, Station, Validation } from '../types'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(path, options)
  if (!response.ok) {
    let message = `요청 실패 (${response.status})`
    try { const body = await response.json(); message = body.detail || message } catch { /* keep status */ }
    throw new Error(message)
  }
  return response.json() as Promise<T>
}
const query = (start?: string, end?: string, extra?: Record<string,string>) => {
  const p = new URLSearchParams(extra)
  if (start) p.set('date_start', start)
  if (end) p.set('date_end', end)
  return p.toString() ? '?' + p : ''
}
const base = (id: string) => '/api/regions/' + encodeURIComponent(id)
export const api = {
  regions: () => request<{ regions: Region[] }>('/api/regions'),
  overview: (id: string, start?: string, end?: string) => request<Overview>(base(id) + '/overview' + query(start, end)),
  stations: (id: string, start?: string, end?: string, q?: string) => request<SourceInfo & { stations: Station[]; total: number; available: boolean; message: string | null }>(base(id) + '/stations' + query(start,end,{limit:'10000', ...(q ? {q} : {})})),
  station: (id: string, stationId: string, start?: string, end?: string) => request<SourceInfo & { station: Station; cluster: ClusterResult['clusters'][number] | null }>(base(id) + '/stations/' + encodeURIComponent(stationId) + query(start,end)),
  clusters: (id: string, start?: string, end?: string) => request<ClusterResult>(base(id) + '/clusters' + query(start, end)),
  network: (id: string, start?: string, end?: string, nodeLimit=40) => request<Network>(base(id) + '/network' + query(start, end, {node_limit:String(nodeLimit)})),
  centrality: (id: string, start?: string, end?: string) => request<CentralityResult>(base(id) + '/centrality' + query(start, end)),
  similarity: (id: string, stationId: string, start?: string, end?: string) => request<SimilarityResult>(base(id) + '/similarity' + query(start,end,{station_id:stationId})),
  compare: (ids: string[], start?: string, end?: string) => request<CompareResult>('/api/compare' + query(start,end,{region_ids:ids.join(',')})),
  sources: (id?: string) => request<{ data_sources: DataSource[] }>('/api/data-sources' + (id ? '?region_id=' + encodeURIComponent(id) : '')),
  quality: (id?: string) => request<{ quality: Record<string, unknown> }>('/api/data-quality' + (id ? '?region_id=' + encodeURIComponent(id) : '')),
  validation: () => request<Validation>('/api/data-validation'),
  upload: (id: string, kind: string, datasetName: string, file: File) => { const body = new FormData(); body.set('kind', kind); body.set('dataset_name', datasetName); body.set('file', file); return request<{ rows: number; message: string }>(base(id) + '/upload', { method: 'POST', body }) },
  agentStatus: () => request<{configured:boolean;provider:string}>('/api/agent/status'),
  chat: (message: string) => request<ChatResult>('/api/agent/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ message }) }),
  demoOverview: (id = 'seoul') => request<{ metadata: { source: string; period_start: string; period_end: string }; total_rentals: number; station_count: number }>('/api/demo/overview?region_id=' + id)
}
