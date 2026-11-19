# 2단계 유형 분류 요약

- ① 같은 기간: 최고 모델 Random Forest Macro-F1 0.580±0.037 (Accuracy 0.566), 기준 최다 유형 0.102, 제품 유형·캐비티별 0.257
- ① 같은 기간 rf 유형별 F1 (fold 합산): short_shot 0.48, exfoliation 0.53, porosity 0.59, deformation 0.59, other 0.73
- ② 시간 순서: 최고 모델 Extra Trees Macro-F1 0.339±0.091 (Accuracy 0.427), 기준 최다 유형 0.136, 제품 유형·캐비티별 0.260
- ② 시간 순서 et 유형별 F1 (fold 합산): short_shot 0.42, exfoliation 0.50, porosity 0.39, deformation 0.44, other 0.13
- ③ 50 shot마다 재학습 Macro-F1 (평가 구간 합산): et 0.510, rf 0.476, type_group_mode 0.365, type_mode 0.229
- ③ 100 shot마다 재학습 Macro-F1 (평가 구간 합산): et 0.472, rf 0.441, type_group_mode 0.334, type_mode 0.224
- ③ 200 shot마다 재학습 Macro-F1 (평가 구간 합산): et 0.439, rf 0.441, type_group_mode 0.294, type_mode 0.215
- ③ 500 shot마다 재학습 Macro-F1 (평가 구간 합산): et 0.346, rf 0.365, type_group_mode 0.248, type_mode 0.137
- ① 같은 기간 연결 평가(상위 20% 검사, 1단계 xgb → 2단계 rf): 불량 포착 52%, 그중 유형 적중 55%, 전체 불량 대비 29%
- ① 같은 기간 연결 평가(상위 20% 검사, 1단계 xgb → 2단계 type_group_mode): 불량 포착 52%, 그중 유형 적중 35%, 전체 불량 대비 18%
- ② 시간 순서 연결 평가(상위 20% 검사, 1단계 recent_rate → 2단계 rf): 불량 포착 40%, 그중 유형 적중 42%, 전체 불량 대비 17%
- ② 시간 순서 연결 평가(상위 20% 검사, 1단계 recent_rate → 2단계 type_group_mode): 불량 포착 40%, 그중 유형 적중 27%, 전체 불량 대비 11%