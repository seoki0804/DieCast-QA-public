// 작은 SVG 그림: 추세선(sparkline)과 σ 위치 막대. 색은 CSS 변수(토큰)로 칠한다.

/** 최근 값의 추세: 옅은 면 + 얇은 선 + 끝점. 끝점은 크기가 늘어나지 않게 둥근 선 끝으로 그린다. */
export function Sparkline({ values, height = 24, alarm = false, className = "" }) {
  const clean = values.filter((v) => v != null && Number.isFinite(v));
  if (clean.length < 2) return <svg className={`spark ${className}`} height={height} aria-hidden="true" />;
  const w = 100;
  const lo = Math.min(...clean);
  const hi = Math.max(...clean);
  const span = hi - lo || 1;
  const pts = clean.map((v, k) => [(k / (clean.length - 1)) * (w - 3) + 1.5, height - 3 - ((v - lo) / span) * (height - 6)]);
  const d = pts.map(([x, y], k) => `${k ? "L" : "M"}${x.toFixed(2)},${y.toFixed(2)}`).join("");
  const [ex, ey] = pts[pts.length - 1];
  return (
    <svg className={`spark ${className}`} viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" height={height} aria-hidden="true">
      <path className="spark-area" d={`${d}L${ex},${height}L1.5,${height}Z`} />
      <path className="spark-line" d={d} vectorEffect="non-scaling-stroke" />
      <path className={alarm ? "spark-end spark-end-alarm" : "spark-end"} d={`M${ex} ${ey}l0 0`} vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

/**
 * σ 위치 막대: −3σ~+3σ 구역(가운데일수록 진함), 평균 눈금, 관리 범위(안) 경계(파랑), 이번 값(▲).
 * edges = 범위 경계의 z 값들. 3.4σ 밖은 끝에 붙여 그린다.
 */
export function SigmaBar({ z, edges = [], beyond = false }) {
  const w = 200;
  const x = (v) => 6 + ((Math.max(-3.4, Math.min(3.4, v)) + 3.4) / 6.8) * (w - 12);
  const marker = x(z);
  return (
    <svg className="sigma" viewBox={`0 0 ${w} 16`} aria-hidden="true">
      <rect className="sigma-zone3" x={x(-3)} y="3" width={x(3) - x(-3)} height="6" rx="1" />
      <rect className="sigma-zone2" x={x(-2)} y="3" width={x(2) - x(-2)} height="6" />
      <rect className="sigma-zone1" x={x(-1)} y="3" width={x(1) - x(-1)} height="6" />
      <line className="sigma-mean" x1={x(0)} x2={x(0)} y1="2" y2="10" />
      {edges
        .filter((e) => Math.abs(e) < 3.4)
        .map((e) => (
          <line key={e} className="sigma-edge" x1={x(e)} x2={x(e)} y1="1" y2="11" />
        ))}
      <path className={beyond ? "sigma-mark sigma-mark-alarm" : "sigma-mark"} d={`M${marker} 9l4.5 6.5h-9z`} />
    </svg>
  );
}
