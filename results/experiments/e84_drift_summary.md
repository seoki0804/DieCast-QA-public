# e84_drift

- 구간 1→2: 구별 AUC 1.00 (공정 변수만 0.99, 기여 상위 Factory_Humidity, Factory_Temp, Coolant_Pressure), PSI 0.25 초과 변수 10개 ['Factory_Temp', 'Factory_Humidity', 'Coolant_Pressure']
- 구간 2→3: 구별 AUC 1.00 (공정 변수만 1.00, 기여 상위 Coolant_Pressure, Spray_2_Time, Casting_Pressure), PSI 0.25 초과 변수 14개 ['Coolant_Pressure', 'Coolant_Temp', 'Spray_Time']
- 구간 4→5: 구별 AUC 1.00 (공정 변수만 1.00, 기여 상위 Factory_Humidity, High_Velocity, Factory_Temp), PSI 0.25 초과 변수 12개 ['High_Velocity', 'Factory_Temp', 'Factory_Humidity']
- 구간 5→7: 구별 AUC 1.00 (공정 변수만 0.94, 기여 상위 Coolant_Pressure, Factory_Humidity, Coolant_Temp), PSI 0.25 초과 변수 11개 ['Coolant_Pressure', 'Factory_Humidity', 'Coolant_Temp']
- ② fold별 학습 구간 vs 평가 구간 구별 AUC: 중앙값 1.00, 최소 1.00
- 구간 1 SHAP 상위: Cavity 30%, Melting_Furnace_Temp 12%, Air_Pressure 8%
- 구간 2 SHAP 상위: Coolant_Temp 10%, Biscuit_Thickness 10%, Cavity 9%
- 구간 5 SHAP 상위: Cavity 40%, Coolant_Temp 8%, Air_Pressure 7%
- 구간 7 SHAP 상위: Cavity 17%, Melting_Furnace_Temp 10%, High_Velocity 7%
- 구간 사이 SHAP 순위 상관(Spearman) 중앙값 0.68, 상위 5개 겹침 중앙값 2개