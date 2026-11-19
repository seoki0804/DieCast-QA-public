// 숫자 표기: 화면 전체에서 같은 규칙을 쓴다 (고정폭 숫자는 CSS tabular-nums).

const nf = (digits) =>
  new Intl.NumberFormat("ko-KR", { minimumFractionDigits: digits, maximumFractionDigits: digits });

export function pct(value, digits = 1) {
  if (value == null || Number.isNaN(value)) return "–";
  return `${nf(digits).format(value * 100)}%`;
}

export function num(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return "–";
  return nf(digits).format(value);
}

export function int(value) {
  if (value == null || Number.isNaN(value)) return "–";
  return new Intl.NumberFormat("ko-KR").format(Math.round(value));
}

/** 유효숫자 4자리 (공정 변수 값처럼 크기가 제각각인 수). */
export function sig(value) {
  if (value == null || Number.isNaN(value)) return "–";
  return Number(value.toPrecision(4)).toLocaleString("ko-KR");
}

export function signed(value, digits = 2) {
  if (value == null || Number.isNaN(value)) return "–";
  return `${value > 0 ? "+" : value < 0 ? "−" : ""}${nf(digits).format(Math.abs(value))}`;
}
