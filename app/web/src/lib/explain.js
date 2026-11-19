// 판정 근거: SHAP 기여를 '조정 가능 변수'와 '시기·환경 변수'로 나눈다 (7단계 결론).

/** @param {[string, number, number][]} rows [변수, 값, SHAP] @param {Record<string, object>} variables */
export function groupContributions(rows, variables) {
  const groups = { controllable: [], context: [] };
  for (const [name, value, shap] of rows ?? []) {
    const info = variables[name] ?? { label: name, group: "context" };
    groups[info.group === "controllable" ? "controllable" : "context"].push({
      name,
      label: info.label,
      value,
      shap,
    });
  }
  for (const list of Object.values(groups)) list.sort((a, b) => Math.abs(b.shap) - Math.abs(a.shap));
  return groups;
}

// 예상 유형은 참고용이다: 유형 분류는 시간 순서 검증에서 정확도가 낮다(보고서 5장). 화면 안내 문구는 i18n의 'type.hint'.

/** 예상 불량 유형: 확률이 가장 큰 유형과 그 확률. */
export function predictedType(part, defectTypes) {
  let best = 0;
  part.tp.forEach((p, k) => {
    if (p > part.tp[best]) best = k;
  });
  return { ...defectTypes[best], probability: part.tp[best] };
}
