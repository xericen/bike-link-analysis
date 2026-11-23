const names:Record<string,string>={seoul:'서울',daejeon:'대전',sejong:'세종'}
export function RecoveryProgress({data}:{data:any}){
 if(!data)return null
 if(!data.available)return <p>{data.message}</p>
 return <section className="recovery-progress">
 <h3>추천 방법, 여기까지 점검했습니다</h3>
 <p className="recovery-service-period"><strong>서비스 공통 기준: 2025년 12월 유지</strong> · 아래 추가 실험과는 별개입니다.</p>
 <p>후보 생성 방식·순위 {data.checked_conditions}조건을 비교하고, {data.matching_checks}개 매칭 지표를 점검했습니다.</p>
 <div className="recovery-period-note"><strong>별도 연구 실험</strong> · 2025년 6월에 방법 선택 → 7월에 별도 평가</div>
 <p>교통 공백 조건에 맞는 실제 대여소를 숨긴 뒤, 추천 TOP10이 300m 안에서 다시 찾은 수입니다.</p>
 <div className="table-wrap"><table className="recovery-comparison"><thead><tr><th>도시</th><th>7월 기존 방법</th><th>7월 시험 방법</th><th>판단</th></tr></thead><tbody>{data.cities.map((r:any)=><tr key={r.city}><td>{names[r.city]}</td><td>{r.comparison.baseline_hits}/{r.comparison.target_count}곳</td><td>{r.comparison.selected_hits}/{r.comparison.target_count}곳</td><td>{r.comparison.selected_hits>r.comparison.baseline_hits?'일부 증가':r.comparison.selected_hits<r.comparison.baseline_hits?'감소':'같음'}</td></tr>)}</tbody></table></div>
 <p className="recovery-decision"><strong>{data.decision}</strong></p>
 <p>월·대상이 달라 아래 12월 0/10과 직접 비교할 수 없습니다. 설치 효과나 실제 환승 증가를 검증한 결과도 아닙니다.</p>
 <div className="advanced-improvement"><h4>12월 실패 원인은 무엇이었나요?</h4>
 <div className="table-wrap"><table className="recovery-failures"><thead><tr><th>도시</th><th>주변 후보 없음</th><th>후보는 있으나 복구 실패</th></tr></thead><tbody>{data.cities.map((r:any)=><tr key={r.city}><td>{names[r.city]}</td><td>{r.original.no_candidate}/{r.original.n}곳</td><td>{r.original.possible_not_matched_top10}/{r.original.n}곳</td></tr>)}</tbody></table></div>
 <p>250m 격자는 주변 후보가 생길 기회를 늘렸지만, 상위 추천의 정확도를 일관되게 높이지는 못했습니다. 다음 검증은 후보의 공간 중복을 줄이는 방식과 별도 기간 평가입니다.</p>
 </div></section>
}
