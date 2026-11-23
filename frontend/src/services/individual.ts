/** Read versioned full-history packets. No browser-side analytical recomputation. */
let manifestPromise: Promise<any> | undefined
const mount = import.meta.env.BASE_URL.replace(/\/$/, '')
export function individualScopes(): Promise<any> {
  return manifestPromise ||= fetch(mount+'/assets/bike-link/individual/scopes.json',{cache:'no-cache'}).then(r=>r.ok?r.json():{ready:false}).catch(()=>({ready:false}))
}
const packets = new Map<string,Promise<any>>()
async function packet(scope:any,action:string):Promise<any> {
 const path=mount+'/assets/bike-link/individual/'+scope.asset_path+'/'+action+'.json'
 if(!packets.has(path))packets.set(path,fetch(path,{cache:'no-cache'}).then(async r=>{if(!r.ok)throw new Error('전체 기간 집계 조회 실패');return r.json()}))
 return packets.get(path)!
}
const json=(value:unknown,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json'}})
export async function analysisFetch(input:string,options?:RequestInit):Promise<Response> {
 const url=new URL(input,window.location.origin)
 const path=url.pathname.slice(mount.length),q=url.searchParams
 if(path==='/api/compare'){q.set('date_start','2025-12-01');q.set('date_end','2025-12-31');return fetch(url,options)}
 const m=await individualScopes()
 if(!m.ready)return fetch(input,options)
 if(path==='/api/readiness')return json({revision:'individual-scopes',cities:Object.fromEntries(Object.entries(m.cities).map(([id,s]:[string,any])=>[id,{aggregates_ready:true,decision_evidence_ready:true,date_start:s.start,date_end:s.end,revision:s.revision}]))})
 const parts=path.match(/^\/api\/regions\/([^/]+)\/(.+)$/)
 const city=parts?decodeURIComponent(parts[1]):(q.get('city')||q.get('region_id'))
 const scope=m.cities[city||'']
 if(path==='/api/agent/chat'&&options?.body){
   const body=JSON.parse(String(options.body)),ctx=body.context
   const c=ctx?.region_ids?.length===1?ctx.region_ids[0]:null,s=m.cities[c]
   if(s&&ctx.date_start===s.start&&ctx.date_end===s.end)return fetch(mount+'/api/individual/'+c+'/chat',options)
 }
 if(!scope)return fetch(input,options)
 if(path==='/api/data-sources')return json({data_sources:(await packet(scope,'overview')).sources||[]})
 // Explicit common-period comparisons keep the independently preserved December data.
 if(q.get('date_start')==='2025-12-01'&&q.get('date_end')==='2025-12-31')return fetch(input,options)
 let action=(parts?parts[2]:path.replace('/api/','')).replace(/-/g,'_')
 const aliases:Record<string,string>={vulnerability:'vulnerability',improvement_ranking:'vulnerability',role_candidates:'research',hidden_hubs:'hidden_hubs',transit_linkage:'transit_linkage',transit_demand:'transit_demand'}
 action=aliases[action]||action
 let sid=q.get('station_id')||''
 const sm=parts?.[2].match(/^stations\/([^/]+)(?:\/(role-history|hidden-hub-validation))?$/)
 if(sm){sid=decodeURIComponent(sm[1]);action=sm[2]?(sm[2]==='role-history'?'station_history':'station_validation'):'station'}
 const supported=['overview','stations','station','similarity','clusters','cluster_stability','imbalance','network','centrality','research','hidden_hubs','transit_linkage','vulnerability','planning','presentation_context','decision_evidence','transit_demand','station_history','station_validation']
 if(!supported.includes(action))return fetch(input,options)
 if((q.get('date_start')&&q.get('date_start')!==scope.start)||(q.get('date_end')&&q.get('date_end')!==scope.end))return json({detail:'검증된 도시별 전체 기간만 조회할 수 있습니다.'},422)
 try{
  if(action==='station_history'||action==='station_validation')return json({available:false,windows:[],station_id:sid,message:'추가 단기창 검증은 미준비입니다.',period_start:scope.start,period_end:scope.end})
  if(action==='station'||action==='similarity'){
   const bucket=Array.from(sid).reduce((s,c)=>s+c.charCodeAt(0),0)%32
   const found=(await packet(scope,'station-bucket-'+bucket)).items[sid]
   if(!found)return json({detail:'전체 기간 자료에 없는 대여소입니다.'},404)
   return json(action==='similarity'?{...found.similarity,period_start:scope.start,period_end:scope.end}:found)
  }
  if(action==='network')return json(await packet(scope,'network_'+(q.get('node_limit')||'40')))
  return json(await packet(scope,action==='centrality'?'centrality_full':action))
 }catch(e){return json({detail:e instanceof Error?e.message:'전체 기간 집계 조회 실패'},503)}
}
