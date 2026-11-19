"""12단계 보고서 그림: 특성요인도 근거 문구와 그림 생성."""

import pandas as pd

from diecast_qa.viz.report import ReportCharts, evidence_marks


def _inputs():
    checklist = pd.DataFrame({
        "type5": ["short_shot", "exfoliation"],
        "variable": ["Biscuit_Thickness", "Biscuit_Thickness"],
        "direction": ["높음", "낮음"],
    })  # fmt: skip
    ranges = pd.DataFrame({
        "variable": ["Biscuit_Thickness", "Coolant_Pressure"], "Product_Type": [1, 1],
        "range_label": ["≥ 12", "≤ 2.67"], "verdict": ["candidate", "untestable"],
    })  # fmt: skip
    return checklist, ranges, pd.Series({1: 0.17, 2: 0.078})


def test_evidence_marks_combines_ranges_types_and_cavity():
    marks = evidence_marks(*_inputs())
    # 검증을 통과한 범위만 ★로, 유형 방향은 화살표로, 캐비티는 불량률로
    assert marks["Biscuit_Thickness"] == ["★유형1 ≥ 12", "미성형↑", "박리↓"]
    assert "Coolant_Pressure" not in marks
    assert marks["Cavity"] == ["캐비티1 17.0% vs 캐비티2 7.8%"]


def test_report_figures_render(tmp_path):
    charts = ReportCharts()
    fig = charts.fishbone(evidence_marks(*_inputs()), rate=0.124)
    assert fig.get_size_inches()[0] <= 10  # 본문 폭에 넣어도 글자가 6pt 이상
    assert charts.architecture().get_size_inches()[0] <= 10
