# OpenSky Experiment Analytics Report

- **Source CSV File:** `/media/vithurshan/vithu/rand/opensky_experiment/results/opensky_hourly_results_20260912_082011.csv`
- **Total Test Records Evaluated:** `7`
- **Unique Intervals/Days:** `2`
- **Total Points Evaluated:** `8,776,567`
- **Global Minimum Encounter Distance:** `1.146 meters`

---

## Scenario Performance Summary

| Test_Case                        | Mean_Time_ms_mean | Mean_Time_ms_min | Mean_Time_ms_max | Mean_Rebuilds_mean | Min_Distance_m_min |
| -------------------------------- | ----------------- | ---------------- | ---------------- | ------------------ | ------------------ |
| Original - Deterministic Grid    | 10609.78          | 9675.18          | 11544.37         | 23.5               | 1.15               |
| Original - Randomized Grid       | 9795.92           | 9244.15          | 10347.69         | 22.15              | 1.15               |
| Sorted_Time - Deterministic Grid | 10523.43          | 10490.62         | 10556.24         | 27.0               | 1.15               |
| Sorted_Time - Randomized Grid    | 10538.61          | 10538.61         | 10538.61         | 22.6               | 2.42               |

---

## Complete Records Table

| Hour_Tag                | Input_Order | Algorithm          | Num_Points | Mean_Time_ms | Median_Time_ms | StdDev_Time_ms | Mean_Rebuilds | Min_Distance_m |
| ----------------------- | ----------- | ------------------ | ---------- | ------------ | -------------- | -------------- | ------------- | -------------- |
| states_2019-05-27-00_4d | Original    | Deterministic Grid | 1280803    | 9675.176     | 9580.387       | 292.381        | 24.0          | 2.424          |
| states_2019-05-27-00_4d | Original    | Randomized Grid    | 1280803    | 9244.147     | 9068.98        | 480.733        | 20.7          | 2.424          |
| states_2019-05-27-00_4d | Sorted_Time | Deterministic Grid | 1280803    | 10556.244    | 9701.971       | 1549.823       | 22.0          | 2.424          |
| states_2019-05-27-00_4d | Sorted_Time | Randomized Grid    | 1280803    | 10538.61     | 9687.365       | 1677.899       | 22.6          | 2.424          |
| states_2019-05-27-01_4d | Original    | Deterministic Grid | 1217785    | 11544.374    | 11938.372      | 1662.198       | 23.0          | 1.146          |
| states_2019-05-27-01_4d | Original    | Randomized Grid    | 1217785    | 10347.687    | 10550.803      | 1492.781       | 23.6          | 1.146          |
| states_2019-05-27-01_4d | Sorted_Time | Deterministic Grid | 1217785    | 10490.62     | 10508.403      | 1673.362       | 32.0          | 1.146          |

---

## Distribution Profile & Normality Assessment (Bell Curve Diagnostics)

| Input_Order | Algorithm          | Sample_Count | Mean     | StdDev  | Median  | Skewness | Excess_Kurtosis | Distribution_Profile         |
| ----------- | ------------------ | ------------ | -------- | ------- | ------- | -------- | --------------- | ---------------------------- |
| Original    | Deterministic Grid | 20           | 10.610 s | 1.506 s | 9.849 s | +0.75    | -1.18           | Right-skewed                 |
| Original    | Randomized Grid    | 20           | 9.796 s  | 1.219 s | 9.404 s | +0.60    | -0.77           | Approx. Normal (Bell-shaped) |
| Sorted_Time | Deterministic Grid | 20           | 10.523 s | 1.570 s | 9.752 s | +0.62    | -1.01           | Approx. Normal (Bell-shaped) |
| Sorted_Time | Randomized Grid    | 10           | 10.539 s | 1.678 s | 9.687 s | +0.55    | -1.65           | Approx. Normal (Bell-shaped) |
