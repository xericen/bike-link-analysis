export const anchorType=(city:string)=>city==='sejong'?'BRT 정류장':'지하철역'
export const anchorDistance=(city:string)=>'최근접 '+anchorType(city)+'(앵커) 거리'
