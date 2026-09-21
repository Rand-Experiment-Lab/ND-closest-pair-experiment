# OpenSky Experiment Analytics Report

- **Source CSV File:** `/media/vithurshan/vithu/rand/opensky_experiment/results/opensky_results_20260912_002012.csv`
- **Total Test Records Evaluated:** `4`
- **Unique Intervals/Days:** `1`
- **Total Points Evaluated:** `156,151,152`
- **Global Minimum Encounter Distance:** `0.250 meters`

---

## Scenario Performance Summary

| Test_Case                             | Mean_Time_ms_mean | Mean_Time_ms_min | Mean_Time_ms_max | Mean_Rebuilds_mean | Min_Distance_m_min |
| ------------------------------------- | ----------------- | ---------------- | ---------------- | ------------------ | ------------------ |
| Original - Deterministic Grid         | 348143.38         | 348143.38        | 348143.38        | 26.0               | 0.25               |
| Original - Randomized Grid            | 367306.29         | 367306.29        | 367306.29        | 34.5               | 0.25               |
| Sorted_Time_Axis - Deterministic Grid | 338086.1          | 338086.1         | 338086.1         | 26.0               | 0.25               |
| Sorted_Time_Axis - Randomized Grid    | 368350.35         | 368350.35        | 368350.35        | 30.7               | 0.25               |

---

## Complete Records Table

| Dataset | Input_Order      | Algorithm          | Num_Points | Mean_Time_ms | Median_Time_ms | StdDev_Time_ms | Mean_Rebuilds | Min_Distance_m |
| ------- | ---------------- | ------------------ | ---------- | ------------ | -------------- | -------------- | ------------- | -------------- |
| OpenSky | Original         | Deterministic Grid | 39037788   | 348143.384   | 337237.225     | 20145.428      | 26.0          | 0.25           |
| OpenSky | Original         | Randomized Grid    | 39037788   | 367306.29    | 368694.294     | 16041.405      | 34.5          | 0.25           |
| OpenSky | Sorted_Time_Axis | Deterministic Grid | 39037788   | 338086.101   | 338078.073     | 301.54         | 26.0          | 0.25           |
| OpenSky | Sorted_Time_Axis | Randomized Grid    | 39037788   | 368350.349   | 365505.664     | 10038.323      | 30.7          | 0.25           |

---

## Distribution Profile & Normality Assessment (Bell Curve Diagnostics)

| Input_Order      | Algorithm          | Sample_Count | Mean      | StdDev   | Median    | Skewness | Excess_Kurtosis | Distribution_Profile         |
| ---------------- | ------------------ | ------------ | --------- | -------- | --------- | -------- | --------------- | ---------------------------- |
| Original         | Deterministic Grid | 10           | 348.143 s | 20.145 s | 337.237 s | +1.26    | -0.04           | Right-skewed                 |
| Original         | Randomized Grid    | 10           | 367.306 s | 16.041 s | 368.694 s | -0.33    | -1.21           | Approx. Normal (Bell-shaped) |
| Sorted_Time_Axis | Deterministic Grid | 10           | 338.086 s | 0.302 s  | 338.078 s | +0.50    | -1.01           | Approx. Normal (Bell-shaped) |
| Sorted_Time_Axis | Randomized Grid    | 10           | 368.350 s | 10.038 s | 365.506 s | +1.04    | -0.62           | Right-skewed                 |
