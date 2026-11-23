export function IndividualRecovery({data}:{data:any}){
 const s=data.summary
 return <section className="panel method-validation individual-recovery">
 <h2>추천 방법을 확인해 봤습니다</h2>
 {!data.available?<p role="status">{data.message}</p>:<>
 <p className="individual-recovery-period">{data.period_start} ~ {data.period_end} · 도시 전역</p>
 <p className="research-intro">실제 대여소 위치를 가린 뒤, 분석이 그 위치를 다시 찾는지 확인했습니다.</p>
 <div className="research-meta"><span>관측 이동 {s.trips.toLocaleString('ko-KR')}건</span><span>{s.observed_days.toLocaleString('ko-KR')}일</span><span>{data.combination_count}개 조건 비교</span></div>
 <div className="recovery-result-grid">
 {[{label:'기존 기준',value:s.baseline,note:'현재 추천 방법'},{label:'간격을 유지한 탐색',value:s.strict,note:'기존 대여소와 300m 이상'},{label:'가까운 위치까지 탐색',value:s.diagnostic,note:'50m 간격 · 진단용'}].map((r,i)=><article className={'recovery-result '+(i===2?'diagnostic-result':'')} key={r.label}><span>{r.label}</span><strong>{r.value.hits} / {r.value.target_count}곳</strong><small>{r.note}</small></article>)}
 </div>
 <p className="research-takeaway">이용 상위 {s.baseline.target_count}곳 중 다시 찾은 수입니다. 탐색 결과는 실제 설치 효과를 뜻하지 않습니다.</p>
 <details className="research-detail"><summary>결과를 읽는 기준</summary><p>두 탐색 결과는 전체 기간의 조건별 최고값입니다. 50m 진단은 신규 설치 추천이 아니며 현재 운영 추천 점수는 바꾸지 않았습니다.</p><p>간격 유지: {s.strict.label} · 진단: {s.diagnostic.label}</p><p>고정 위치·시설 자료의 과거 동일성과 실제 설치 효과는 미검증입니다.</p></details>
 </>}
 </section>
}
