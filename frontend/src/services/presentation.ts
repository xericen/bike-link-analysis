import type { ClusterResult, CompareResult, Station } from '../types'

// Presentation adapters retain missing values; they never synthesize an observed count.
export const cityName=(id:string)=>({seoul:'서울',daejeon:'대전',sejong:'세종'}[id]||id)
export const peakHour=(values?:number[]|null)=>values?.length?values.indexOf(Math.max(...values)):null
export function stationHours(station?:Station) {
  return Array.from({length:24},(_,hour)=>{
    const rental=station?.hourly?.[hour]??null
    const net=station?.hourly_net_outflow?.[hour]
    const returns=rental!==null&&net!==undefined?rental-net:null
    return {hour:hour+'시',rental,returns,total:rental!==null&&returns!==null?rental+returns:null}
  })
}
export function cityRatios(data?:CompareResult,kind:'hourly'|'weekday'='hourly') {
  return Array.from({length:kind==='hourly'?24:7},(_,i)=>{
    const point:Record<string,string|number|null>={label:kind==='hourly'?i+'시':['월','화','수','목','금','토','일'][i]}
    data?.regions.filter(r=>r.region_id!=='sejong').forEach(r=>{
      const values=kind==='hourly'?r.hourly:r.weekday?.map(x=>x.rental_count)
      const total=values?.reduce((a,b)=>a+b,0)||0
      point[r.region_id]=values&&total?values[i]/total*100:null
    })
    return point
  })
}
export const clusterSilhouette=(data?:ClusterResult)=>data?.diagnostics.find(x=>x.k===data.selected_k)?.silhouette??null
