const names:Record<string,string>={seoul:'서울',daejeon:'대전',sejong:'세종'}
export function BreadthProgress({data}:{data:any}){
 if(!data?.available)return null
 return <section className="recovery-progress breadth-progress">
 <h3>12월 같은 대여소를 여러 방법으로 다시 찾아봤습니다</h3>
 <p><strong>공통 분석 기준: 2025년 12월 · {data.combination_count}개 조합 비교</strong></p>
 <p>{data.notice}</p>
 <div className="table-wrap"><table className="breadth-comparison"><thead><tr><th>도시</th><th>기존 방법</th><th>300m 간격 유지</th><th>50m 간격 진단</th></tr></thead><tbody>{data.cities.map((r:any)=><tr key={r.city}><td>{names[r.city]}</td><td>{r.baseline.hits}/{r.baseline.target_count}곳</td><td title={r.strict.label}>{r.strict.hits}/{r.strict.target_count}곳<small style={{display:'block'}}>{r.strict.label}</small></td><td title={r.diagnostic.label}>{r.diagnostic.hits}/{r.diagnostic.target_count}곳</td></tr>)}</tbody></table></div>
 <p><strong>두 새 열은 12월 탐색 최고값입니다.</strong> 방법을 미리 고정한 별도 평가와 구분합니다.</p>
 <p>{data.diagnostic_notice}</p>
 <p className="recovery-decision">재발견 가능한 방법은 찾았지만 운영 추천은 유지합니다. 실제 설치 효과는 입증하지 않았습니다.</p>
 <div className="advanced-improvement">
 <h4>어떤 방법을 비교했나요?</h4><p>기존500m·250m·125m 다중 위치와 공공시설 위치, 주변 대여·반납·시설·수요 평활화·역 인접 수요·후보 분산·중복 제거 수요 커버를 비교했습니다. 숨긴 위치와 관련 이동은 입력에서 제외했습니다.</p>
 <h4>방법 고정 후 별도 8월 평가</h4><p>{data.evaluation_start} ~ {data.evaluation_end}. 12월로 방법을 고정한 뒤 읽은 과거 다른 달입니다. 서비스 기준을 8월로 바꾸지 않았습니다.</p>
 {data.cities.map((c:any)=><div key={c.city}><h4>{names[c.city]}</h4><p>간격 유지: {c.locked_strict_method} · 진단: {c.locked_diagnostic_method}</p><div className="table-wrap"><table><thead><tr><th>대상</th><th>기존</th><th>간격 유지</th><th>간격 완화 진단</th></tr></thead><tbody>{c.evaluation.map((r:any)=><tr key={r.fold}><td>{({high_usage:'미사용 이용 상위',gap_high_usage:'공백 조건 이용 상위',spatial_block:'1km 구역 전체'} as Record<string,string>)[r.fold]}</td><td>{r.baseline_hits}/{r.target_count}</td><td>{r.strict_hits}/{r.target_count}</td><td>{r.diagnostic_hits}/{r.target_count}</td></tr>)}</tbody></table></div></div>)}
 <p>관측 위치의 회복 실험입니다. 미충족 수요·실제 환승·재배치 효과를 검증하지 않았습니다. 전체 결과와 간격·일대일 매칭 {data.matching_checks}개 점검은 별도 기록으로 보존했습니다.</p>
 </div></section>
}
