"""불량 유형별 점검 항목 (5장 ⑦, 9장).

유형마다 두 가지 근거를 함께 본다.
- 구간 내 공정값 차이: 같은 생산 구간에서 그 유형이 나온 제품과 정상 shot의 제품을 비교한
  rank-biserial(구간별 값을 비교 쌍 수로 가중 평균). 시기 효과를 뺀 차이라 점검 항목의 근거로 쓴다.
- 2단계 모델 SHAP: 유형 분류 모델(Random Forest, 5단계와 같은 설정)이 그 유형을 고를 때 쓰는 변수.
  대시보드의 '예상 유형'이 어떤 변수에 기대는지 보여 준다.
점검 항목은 조정 가능한 변수 중 구간 내 차이가 큰 순서로 고른다.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from diecast_qa.analysis import Analysis, AnalysisResult
from diecast_qa.config import (
    CAUSE_CATEGORIES,
    CONTROL_VARS,
    PROCESS_COLS,
    SENSOR_COLS,
    TYPE5_LABELS,
    VARIABLE_LABELS,
)
from diecast_qa.eda.stats import rank_biserial_by_group, weighted_effect
from diecast_qa.interpret.explain import INTERP_FEATURES, TreeShap, importance_share
from diecast_qa.modeling.type_models import TYPE_CLASSES, TYPE_CODE, TYPE_MODELS

VARIABLES = (*PROCESS_COLS, *SENSOR_COLS)
CATEGORY = {v: c for c, members in CAUSE_CATEGORIES.items() for v in members}
# 변수가 벗어났을 때 현장에서 확인할 설비·조건
CHECK_POINTS = {
    "Velocity_1": "1단 사출 속도 설정", "Velocity_2": "2단 사출 속도 설정",
    "Velocity_3": "3단 사출 속도 설정", "High_Velocity": "고속 사출 속도·고속 전환 위치",
    "Cylinder_Pressure": "사출 실린더 유압", "Casting_Pressure": "증압(주조) 압력 설정",
    "Rapid_Rise_Time": "고속 전환 응답 시간", "Pressure_Rise_Time": "증압 응답 시간",
    "Biscuit_Thickness": "용탕 주입량(비스킷 두께)", "Clamping_Force": "형체력·금형 체결 상태",
    "Cycle_Time": "설비 대기·정지 여부(사이클 지연)", "Spray_Time": "이형제 스프레이 시간·도포량",
    "Spray_1_Time": "이형제 스프레이 1 시간", "Spray_2_Time": "이형제 스프레이 2 시간",
    "Melting_Furnace_Temp": "용해로·용탕 온도", "Air_Pressure": "공압 공급 압력",
    "Coolant_Temp": "금형 냉각수 온도", "Coolant_Pressure": "금형 냉각수 압력·유량",
}  # fmt: skip


class DefectTypeChecklist(Analysis):
    name = "checklist"

    def __init__(self, n_items: int = 3, min_effect: float = 0.05, min_group: int = 10) -> None:
        self.n_items = n_items
        # 구간 내 효과(rank-biserial)가 이보다 작으면 점검 항목으로 올리지 않는다
        self.min_effect = min_effect
        self.min_group = min_group

    def run(self, parts: pd.DataFrame) -> AnalysisResult:
        effects, runs, agree = self._within_run(parts)
        shap = self._type_shap(parts)
        tables = {
            "effects": effects,
            "effect_runs": runs,
            "effect_agree": agree,
            "shap": shap,
            "context": self._context(parts),
            "items": self._items(effects, runs, agree, shap),
        }
        return AnalysisResult(self.name, tables, self.notes(tables))

    def _within_run(self, parts: pd.DataFrame) -> tuple[pd.DataFrame, ...]:
        """유형별 × 변수별 구간 내 효과, 쓴 구간 수, 그중 평균과 같은 방향인 구간 수.

        비교 대상 '정상'은 두 캐비티가 모두 정상인 shot의 제품이다(같은 shot 값을 양쪽에 넣지 않음).
        비정상 shot은 뺀다.
        """
        clean = parts[~parts["is_abnormal"]]
        normal_shot = clean.groupby("order")["defect"].transform("sum").eq(0)
        effects, runs, agree = ({c: {} for c in TYPE_CLASSES} for _ in range(3))
        for code in TYPE_CLASSES:
            case = clean["type5"] == code
            rows = clean[case | normal_shot]
            for v in VARIABLES:
                by_run = rank_biserial_by_group(rows[v], case[rows.index], rows["run"],
                                                self.min_group)  # fmt: skip
                effects[code][v] = weighted_effect(by_run)
                runs[code][v] = len(by_run)
                agree[code][v] = int((np.sign(by_run["effect"]) == np.sign(effects[code][v])).sum())
        return tuple(pd.DataFrame(t).rename_axis("variable") for t in (effects, runs, agree))

    @staticmethod
    def _type_shap(parts: pd.DataFrame) -> pd.DataFrame:
        """2단계 유형 분류 모델(불량 제품 전체로 학습)의 유형별 평균 |SHAP| 비중."""
        bad = parts[parts["defect"] == 1]
        features = [*INTERP_FEATURES, "Product_Type"]
        model = TYPE_MODELS["rf"].factory(features).fit(bad, bad["type5"].map(TYPE_CODE))
        values = TreeShap(model).values(bad)
        return pd.DataFrame(
            {code: importance_share(values[..., k], features) for code, k in TYPE_CODE.items()}
        ).rename_axis("variable")

    @staticmethod
    def _context(parts: pd.DataFrame) -> pd.DataFrame:
        """유형마다 어디서 나오나: 제품 수, 제품 유형 1·캐비티1 비중, 가장 많은 구간과 비중."""
        rows = {}
        for code in TYPE_CLASSES:
            g = parts[parts["type5"] == code]
            run_share = g["run"].value_counts(normalize=True)
            rows[code] = {"parts": len(g), "product_type_1_share": (g["Product_Type"] == 1).mean(),
                          "cavity_1_share": (g["Cavity"] == 1).mean(),
                          "top_run": run_share.index[0], "top_run_share": run_share.iloc[0],
                          "runs_present": int((g["run"].value_counts() >= 10).sum())}  # fmt: skip
        return pd.DataFrame(rows).T.rename_axis("type5")

    def _items(self, effects, runs, agree, shap) -> pd.DataFrame:
        rows = []
        for code in TYPE_CLASSES:
            e = effects.loc[list(CONTROL_VARS), code].dropna()
            e = e[e.abs() >= self.min_effect]
            for rank, (v, effect) in enumerate(e.reindex(e.abs().sort_values(
                    ascending=False).index).head(self.n_items).items(), start=1):  # fmt: skip
                rows.append({"type5": code, "type_label": TYPE5_LABELS[code], "rank": rank,
                             "variable": v, "label": VARIABLE_LABELS[v], "category": CATEGORY[v],
                             "direction": "높음" if effect > 0 else "낮음", "effect": effect,
                             "runs": runs.loc[v, code], "runs_agree": agree.loc[v, code],
                             "type_shap_share": shap.loc[v, code],
                             "check_point": CHECK_POINTS[v]})  # fmt: skip
        return pd.DataFrame(rows).set_index(["type5", "rank"])

    def notes(self, tables: dict[str, pd.DataFrame]) -> tuple[str, ...]:
        notes = []
        context, items, shap = tables["context"], tables["items"], tables["shap"]
        for code in TYPE_CLASSES:
            c = context.loc[code]
            top_shap = shap[code].nlargest(3)
            head = (f"{TYPE5_LABELS[code]} ({c['parts']:.0f}개, 제품 유형 1 비중 "
                    f"{c['product_type_1_share']:.0%}, 캐비티1 {c['cavity_1_share']:.0%}, 구간 "
                    f"{c['top_run']:.0f}에 {c['top_run_share']:.0%})")  # fmt: skip
            listed = (items.loc[code] if code in items.index.get_level_values(0)
                      else pd.DataFrame())  # fmt: skip
            checks = "; ".join(
                f"{r.check_point}({r.label} 정상보다 {r.direction}, 효과 {r.effect:+.2f}, "
                f"구간 {r.runs_agree:.0f}/{r.runs:.0f})"
                for r in listed.itertuples()
            ) or f"구간 내 차이 {self.min_effect} 이상인 조정 가능 변수 없음"  # fmt: skip
            shap_text = ", ".join(f"{VARIABLE_LABELS[v]} {s:.0%}" for v, s in top_shap.items())
            notes.append(f"{head}: {checks}. 2단계 모델 SHAP 상위: {shap_text}")
        return tuple(notes)
