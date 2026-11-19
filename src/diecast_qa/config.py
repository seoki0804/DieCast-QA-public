"""프로젝트 공통 설정: 데이터 스키마, 파일 경로, 난수 seed (기획서 2·3장)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

SEED = 42

PROJECT_ROOT = Path(__file__).resolve().parents[2]

PROCESS_COLS = (
    "Velocity_1", "Velocity_2", "Velocity_3", "High_Velocity",
    "Cylinder_Pressure", "Casting_Pressure", "Rapid_Rise_Time", "Pressure_Rise_Time",
    "Biscuit_Thickness", "Clamping_Force", "Cycle_Time",
    "Spray_Time", "Spray_1_Time", "Spray_2_Time",
)  # fmt: skip
SENSOR_COLS = (
    "Melting_Furnace_Temp", "Air_Pressure", "Coolant_Temp",
    "Coolant_Pressure", "Factory_Temp", "Factory_Humidity",
)  # fmt: skip
# 설정 상·하한: 값이 하나뿐인 상수 열이라 모델 입력에서 빼고 공정능력 규격으로만 쓴다 (2.3)
SPEC_COLS = tuple(
    f"{var}_{bound}"
    for var in ("Air_Pressure", "Coolant_Temp", "Factory_Temp", "Factory_Humidity")
    for bound in ("Min", "Max")
)
DEFECT_TYPES = (
    "Short_Shot", "Exfoliation", "Blow_Hole", "Deformation", "Stain", "Bubble", "Contamination",
    "Dent", "Impurity", "Buring_Mark", "Crack", "Scratch", "Inclusions",
)  # fmt: skip
CAVITIES = (1, 2)
DEFECT_TYPE_LABELS = {
    "Short_Shot": "미성형", "Exfoliation": "박리", "Blow_Hole": "기공", "Deformation": "변형",
    "Stain": "얼룩", "Bubble": "기포", "Contamination": "오염", "Dent": "찍힘",
    "Impurity": "이물", "Buring_Mark": "탄 자국", "Crack": "균열", "Scratch": "긁힘",
    "Inclusions": "개재물",
}  # fmt: skip

# 특성요인도 분류 (9장): 설비 = 사출 속도·압력, 재료 = 용탕, 방법 = 스프레이, 환경 = 공장 온습도,
# 금형 = 캐비티와 금형 냉각
CAUSE_CATEGORIES = {
    "설비": ("Velocity_1", "Velocity_2", "Velocity_3", "High_Velocity", "Cylinder_Pressure",
             "Casting_Pressure", "Rapid_Rise_Time", "Pressure_Rise_Time", "Biscuit_Thickness",
             "Clamping_Force", "Cycle_Time", "Air_Pressure"),
    "재료": ("Melting_Furnace_Temp",),
    "방법": ("Spray_Time", "Spray_1_Time", "Spray_2_Time"),
    "환경": ("Factory_Temp", "Factory_Humidity"),
    "금형": ("Cavity", "Coolant_Temp", "Coolant_Pressure"),
}  # fmt: skip

# 파생 변수를 만드는 주요 공정 변수 8개 (3.1 순서 7)
KEY_VARS = (
    "Casting_Pressure", "High_Velocity", "Cylinder_Pressure", "Biscuit_Thickness",
    "Melting_Furnace_Temp", "Cycle_Time", "Air_Pressure", "Spray_1_Time",
)  # fmt: skip
BASE_FEATURES = (*PROCESS_COLS, *SENSOR_COLS, "Product_Type", "Cavity", "Shot")

# 현장에서 설정·조정할 수 있는 변수: 공정 14개 + 용탕 온도·공기압·냉각수. 공장 온습도(환경),
# 캐비티(금형 구조), shot 번호(순번)는 관리 범위 대상이 아니다 (5장 ⑦)
CONTROL_VARS = (
    *PROCESS_COLS, "Melting_Furnace_Temp", "Air_Pressure", "Coolant_Temp", "Coolant_Pressure",
)  # fmt: skip
VARIABLE_LABELS = {
    "Velocity_1": "1단 사출 속도", "Velocity_2": "2단 사출 속도", "Velocity_3": "3단 사출 속도",
    "High_Velocity": "고속 사출 속도", "Cylinder_Pressure": "실린더 압력",
    "Casting_Pressure": "주조 압력", "Rapid_Rise_Time": "고속 상승 시간",
    "Pressure_Rise_Time": "증압 상승 시간", "Biscuit_Thickness": "비스킷 두께",
    "Clamping_Force": "형체력", "Cycle_Time": "사이클 타임", "Spray_Time": "스프레이 시간",
    "Spray_1_Time": "스프레이 1 시간", "Spray_2_Time": "스프레이 2 시간",
    "Melting_Furnace_Temp": "용탕 온도", "Air_Pressure": "공기압", "Coolant_Temp": "냉각수 온도",
    "Coolant_Pressure": "냉각수 압력", "Factory_Temp": "공장 온도", "Factory_Humidity": "공장 습도",
    "Product_Type": "제품 유형", "Cavity": "캐비티", "Shot": "shot 순번",
}  # fmt: skip

# 공정능력 규격 (원본의 _Min·_Max 상수 열). 공장 온도·습도는 규격이 18~22로 잘못 들어가 있어
# 실제 값(온도 27~37℃, 습도 45~72%)과 맞지 않으므로 제외한다 (2.3)
SPEC_LIMITS = {"Air_Pressure": (3.0, 9.0), "Coolant_Temp": (10.0, 50.0)}


@dataclass(frozen=True)
class DefectGroup:
    """2단계 분류의 불량 유형 한 개와, 그 유형에 묶이는 원본 불량 열."""

    code: str
    label: str
    members: tuple[str, ...]
    # 여러 유형이 함께 나온 제품의 유형을 정할 때 쓰는 건수 계산 방식.
    # "sum": 원본 값(같은 불량 1~3개)의 합, "presence": 나타난 원본 유형의 개수
    score: str = "sum"


# 순서가 곧 동점일 때의 우선순위다 (미성형 → 박리 → 기공 → 변형 → 기타, 2.4).
# 기타를 "presence"로 세야 기획서 2.5의 클래스 수(391/209/253/171/120)가 재현된다.
DEFECT_GROUPS = (
    DefectGroup("short_shot", "미성형", ("Short_Shot",)),
    DefectGroup("exfoliation", "박리", ("Exfoliation",)),
    DefectGroup("porosity", "기공", ("Blow_Hole", "Bubble")),
    DefectGroup("deformation", "변형", ("Deformation",)),
    DefectGroup(
        "other",
        "기타",
        ("Stain", "Contamination", "Dent", "Impurity", "Buring_Mark", "Crack", "Scratch",
         "Inclusions"),
        score="presence",
    ),
)  # fmt: skip
NORMAL = "normal"
TYPE5_LABELS = {NORMAL: "정상", **{g.code: g.label for g in DEFECT_GROUPS}}


@dataclass(frozen=True)
class Paths:
    """저장소 안의 입출력 경로 (12.2)."""

    root: Path = PROJECT_ROOT

    @property
    def raw_csv(self) -> Path:
        return self.root / "data" / "raw" / "DieCasting_Quality_Raw_Data.csv"

    @property
    def processed_dir(self) -> Path:
        return self.root / "data" / "processed"

    @property
    def parts_csv(self) -> Path:
        return self.processed_dir / "parts.csv"

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def figures_dir(self) -> Path:
        return self.results_dir / "figures"
