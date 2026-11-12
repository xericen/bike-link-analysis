import type { ReactNode } from 'react'
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Empty } from './State'
import { clusterColor } from './colors'
import type { ClusterResult } from '../types'

export function PageHeader({title,subtitle,children}:{title:string;subtitle:string;children?:ReactNode}) {
  return <div className="page-heading"><div><span className="section-label">BIKE LINK ANALYSIS / TEAM 234</span><h2>{title}</h2><p>{subtitle}</p></div>{children}</div>
}
export function StatCard({label,value,note,icon='◈',tone='blue'}:{label:string;value:ReactNode;note:string;icon?:string;tone?:string}) {
  return <article className={'stat stat-'+tone}><span className="stat-icon" aria-hidden="true">{icon}</span><span>{label}</span><strong className="stat-text">{value}</strong><em>{note}</em></article>
}
export function SectionCard({title,note,children,className=''}:{title:string;note?:string;children:ReactNode;className?:string}) {
  return <section className={'panel '+className}><div className="panel-title"><h3>{title}</h3>{note&&<span>{note}</span>}</div>{children}</section>
}
export function InsightBanner({title,children,tone='blue'}:{title:string;children:ReactNode;tone?:string}) {
  return <div className={'insight-banner tone-'+tone}><span className="insight-symbol" aria-hidden="true">✧</span><div><b>{title}</b><div>{children}</div></div></div>
}
export function RoleTag({children}:{children:ReactNode}) {return <span className="role-tag">{children}</span>}
export function SimpleDataTable({headers,rows,empty='확인된 자료가 없습니다.'}:{headers:string[];rows:ReactNode[][];empty?:string}) {
  return rows.length?<div className="data-table-wrap"><table className="data-table"><thead><tr>{headers.map(h=><th key={h} scope="col">{h}</th>)}</tr></thead><tbody>{rows.map((r,i)=><tr key={i}>{r.map((c,j)=><td key={j}>{c}</td>)}</tr>)}</tbody></table></div>:<Empty>{empty}</Empty>
}
export function SummaryBulletCard({title,items,children}:{title:string;items:string[];children?:ReactNode}) {
  return <SectionCard title={title}><ul className="summary-bullets">{items.map((x,i)=><li key={i}>{x}</li>)}</ul>{children}</SectionCard>
}
export function ComparisonDonutCard({data}:{data?:ClusterResult}) {
  const groups=Object.values((data?.clusters||[]).reduce<Record<number,{name:string;value:number;id:number}>>((a,x)=>{a[x.cluster_id]??={name:'군집 '+(x.cluster_id+1),value:0,id:x.cluster_id};a[x.cluster_id].value++;return a},{}))
  if(!groups.length)return <Empty>군집 분포 자료 미확보</Empty>
  return <><div className="donut-chart" role="img" aria-label={groups.map(x=>x.name+' '+x.value+'개').join(', ')}><ResponsiveContainer width="100%" height="100%"><PieChart><Pie data={groups} dataKey="value" nameKey="name" innerRadius="52%" outerRadius="78%" paddingAngle={3} isAnimationActive={false}>{groups.map(x=><Cell key={x.id} fill={clusterColor(x.id)}/>)}</Pie><Tooltip formatter={v=>Number(v).toLocaleString()+'개'}/><Legend/></PieChart></ResponsiveContainer></div><p className="muted">{data?.interpretation_allowed?'탐색적 군집 해석':'군집 품질 낮음 · 유형 확정 보류'} · 단위: 대여소 수</p></>
}
export function ReportBlock({icon,title,items}:{icon:string;title:string;items:string[]}) {
  return <div className="report-block"><span aria-hidden="true">{icon}</span><div><h4>{title}</h4>{items.length?<ul className="summary-bullets">{items.map((x,i)=><li key={i}>{x}</li>)}</ul>:<p className="muted">분석 실행 후 확인된 근거가 표시됩니다.</p>}</div></div>
}
