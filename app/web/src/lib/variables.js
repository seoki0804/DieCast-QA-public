// 공정 변수 표시 정보: 한/영 이름, 단위, 소수 자리.
// KAMP 자료(가이드북 포함)에는 단위가 없어 값 범위로 추정했다. 화면에서는 '추정 단위'라고 밝힌다.

export const VARIABLES = {
  Velocity_1: { ko: "1단 사출 속도", en: "Velocity 1", unit: "m/s", digits: 3 },
  Velocity_2: { ko: "2단 사출 속도", en: "Velocity 2", unit: "m/s", digits: 3 },
  Velocity_3: { ko: "3단 사출 속도", en: "Velocity 3", unit: "m/s", digits: 3 },
  High_Velocity: { ko: "고속 사출 속도", en: "High velocity", unit: "m/s", digits: 3 },
  Cylinder_Pressure: { ko: "실린더 압력", en: "Cylinder pressure", unit: "bar", digits: 0 },
  Casting_Pressure: { ko: "주조 압력", en: "Casting pressure", unit: "bar", digits: 0 },
  Rapid_Rise_Time: { ko: "고속 상승 시간", en: "Rapid rise time", unit: "s", digits: 3 },
  Pressure_Rise_Time: { ko: "증압 상승 시간", en: "Pressure rise time", unit: "s", digits: 3 },
  Biscuit_Thickness: { ko: "비스킷 두께", en: "Biscuit thickness", unit: "mm", digits: 0 },
  Clamping_Force: { ko: "형체력", en: "Clamping force", unit: "t", digits: 0 },
  Cycle_Time: { ko: "사이클 타임", en: "Cycle time", unit: "s", digits: 1 },
  Spray_Time: { ko: "스프레이 시간", en: "Spray time", unit: "s", digits: 1 },
  Spray_1_Time: { ko: "스프레이 1 시간", en: "Spray 1 time", unit: "s", digits: 1 },
  Spray_2_Time: { ko: "스프레이 2 시간", en: "Spray 2 time", unit: "s", digits: 1 },
  Melting_Furnace_Temp: { ko: "용탕 온도", en: "Melt temperature", unit: "℃", digits: 1 },
  Air_Pressure: { ko: "공기압", en: "Air pressure", unit: "bar", digits: 1 },
  Coolant_Temp: { ko: "냉각수 온도", en: "Coolant temperature", unit: "℃", digits: 1 },
  Coolant_Pressure: { ko: "냉각수 압력", en: "Coolant pressure", unit: "bar", digits: 2 },
  Factory_Temp: { ko: "공장 온도", en: "Factory temperature", unit: "℃", digits: 1 },
  Factory_Humidity: { ko: "공장 습도", en: "Factory humidity", unit: "%", digits: 1 },
  Cavity: { ko: "캐비티", en: "Cavity", unit: "", digits: 0 },
  Shot: { ko: "shot 순번", en: "Shot number", unit: "", digits: 0 },
  Product_Type: { ko: "제품 유형", en: "Product type", unit: "", digits: 0 },
};

/** 운영 현황의 공정 변수 칸: 사출·압력·시간·온도에서 고른 10개 (모두 조정 가능 변수). */
export const PANEL_VARIABLES = [
  "Casting_Pressure",
  "High_Velocity",
  "Velocity_3",
  "Cylinder_Pressure",
  "Clamping_Force",
  "Biscuit_Thickness",
  "Cycle_Time",
  "Melting_Furnace_Temp",
  "Coolant_Temp",
  "Air_Pressure",
];

/** 변수의 소수 자리 (모르는 변수는 유효숫자 4자리에 맞춘다). */
export function digitsOf(name, value) {
  const info = VARIABLES[name];
  if (info) return info.digits;
  const magnitude = Math.floor(Math.log10(Math.abs(value) || 1));
  return Math.max(0, 3 - magnitude);
}

export function unitOf(name) {
  return VARIABLES[name]?.unit ?? "";
}
