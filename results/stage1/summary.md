# 1단계 모델 요약

- ① 같은 기간: 최고 모델 XGBoost 0.762±0.019 / 52%, 최근 10 shot 규칙 0.732±0.013 / 48% (ROC-AUC / 상위 20% 포착률)
- ② 시간 순서: 최고 모델 Extra Trees 0.603±0.059 / 33%, 최근 10 shot 규칙 0.683±0.041 / 40% (ROC-AUC / 상위 20% 포착률)
- RF + drift 변수 (② 시간 순서): 0.586±0.052 / 30%
- RF + history 변수 (② 시간 순서): 0.600±0.031 / 32%
- RF 학습 데이터 drop_abnormal (② 시간 순서): 0.598±0.080 / 32%
- RF 학습 데이터 drop_missing (② 시간 순서): 0.590±0.070 / 30%
- ③ 50 shot마다 재학습 ROC-AUC (평가 구간 합산): et 0.714, lgbm 0.690, recent_rate 0.714, rf 0.697
- ③ 100 shot마다 재학습 ROC-AUC (평가 구간 합산): et 0.697, lgbm 0.663, recent_rate 0.714, rf 0.676
- ③ 200 shot마다 재학습 ROC-AUC (평가 구간 합산): et 0.659, lgbm 0.638, recent_rate 0.714, rf 0.648
- ③ 500 shot마다 재학습 ROC-AUC (평가 구간 합산): et 0.599, lgbm 0.593, recent_rate 0.714, rf 0.585
- 중복 포함 무작위 분할 ROC-AUC: logreg 0.723, rf 0.935, tree 0.757, xgb 0.825
- ② 조정 전 → 후 ROC-AUC: et 0.603→0.627, lgbm 0.586→0.592, logreg 0.581→0.568, rf 0.590→0.603, tree 0.572→0.604, xgb 0.568→0.604