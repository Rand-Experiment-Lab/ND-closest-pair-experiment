### Table 1: Speedup Statistics by Dataset Category

| Dataset_Class      | Count   | Mean     | StdDev   | Median | IQR     | Min    | Max      | Pct_Faster |
| ------------------ | ------- | -------- | -------- | ------ | ------- | ------ | -------- | ---------- |
| Adversarial        | 40.0000 | 118.9359 | 233.6469 | 4.2943 | 78.8249 | 0.9556 | 981.4715 | 87.5000    |
| OpenSky_Real_World | 91.0000 | 1.0203   | 0.0811   | 1.0070 | 0.0746  | 0.8209 | 1.3306   | 59.3407    |
| Synthetic_Sorted   | 39.0000 | 0.9771   | 0.2191   | 0.9791 | 0.1835  | 0.5678 | 1.7956   | 46.1538    |

### Table 2: Speedup Breakdown by Dataset Class and Input Order

| Dataset_Class      | Input_Order      | Count   | Mean     | StdDev   | Median  | IQR      | Min    | Max      | Pct_Faster |
| ------------------ | ---------------- | ------- | -------- | -------- | ------- | -------- | ------ | -------- | ---------- |
| Adversarial        | Ladder_of_Pairs  | 20.0000 | 236.1125 | 288.3506 | 89.2480 | 381.5034 | 2.5948 | 981.4715 | 100.0000   |
| Adversarial        | Sorted_X_Axis    | 20.0000 | 1.7592   | 1.6832   | 1.0275  | 0.5487   | 0.9556 | 7.5773   | 75.0000    |
| OpenSky_Real_World | Original         | 52.0000 | 1.0103   | 0.0768   | 1.0065  | 0.0554   | 0.8209 | 1.2298   | 55.7692    |
| OpenSky_Real_World | Sorted_Time      | 37.0000 | 1.0365   | 0.0858   | 1.0085  | 0.1002   | 0.8985 | 1.3306   | 64.8649    |
| OpenSky_Real_World | Sorted_Time_Axis | 2.0000  | 0.9796   | 0.0873   | 0.9796  | 0.0617   | 0.9178 | 1.0413   | 50.0000    |
| Synthetic_Sorted   | Sorted_X_Axis    | 39.0000 | 0.9771   | 0.2191   | 0.9791  | 0.1835   | 0.5678 | 1.7956   | 46.1538    |

### Table 3: Dimensional Scaling (D = 2 to 7) and Dilution Effects

| Dataset_Class      | Dimension | Count   | Mean     | StdDev   | Median   | IQR      | Min    | Max      | Pct_Faster |
| ------------------ | --------- | ------- | -------- | -------- | -------- | -------- | ------ | -------- | ---------- |
| Adversarial        | 2         | 10.0000 | 295.7611 | 370.2844 | 103.7176 | 531.8650 | 0.9556 | 981.4715 | 90.0000    |
| Adversarial        | 3         | 10.0000 | 154.6291 | 193.1529 | 54.8094  | 279.1201 | 1.0537 | 512.9265 | 100.0000   |
| Adversarial        | 5         | 10.0000 | 21.8973  | 26.3586  | 8.1766   | 39.0836  | 0.9890 | 70.4607  | 90.0000    |
| Adversarial        | 7         | 10.0000 | 3.4559   | 3.1689   | 1.8093   | 4.3678   | 0.9753 | 9.5601   | 70.0000    |
| OpenSky_Real_World | 4         | 91.0000 | 1.0203   | 0.0811   | 1.0070   | 0.0746   | 0.8209 | 1.3306   | 59.3407    |
| Synthetic_Sorted   | 2         | 10.0000 | 0.9471   | 0.3470   | 0.8806   | 0.2963   | 0.5953 | 1.7956   | 30.0000    |
| Synthetic_Sorted   | 3         | 10.0000 | 0.8955   | 0.1801   | 0.8974   | 0.1369   | 0.5678 | 1.1695   | 20.0000    |
| Synthetic_Sorted   | 5         | 10.0000 | 1.0619   | 0.1240   | 1.0218   | 0.0414   | 0.9722 | 1.4053   | 90.0000    |
| Synthetic_Sorted   | 7         | 9.0000  | 1.0070   | 0.1387   | 0.9895   | 0.1588   | 0.8626 | 1.2746   | 44.4444    |

### Table 4: Hash Grid Rebuild Statistics (W_variable) by Category

| Dataset_Class      | Pairs   | Det_Rebuilds_Mean | Det_Rebuilds_Med | Rand_Rebuilds_Mean | Rand_Rebuilds_Med | Rebuild_Ratio_Mean | Rebuild_Ratio_Med |
| ------------------ | ------- | ----------------- | ---------------- | ------------------ | ----------------- | ------------------ | ----------------- |
| Adversarial        | 40.0000 | 3767.1750         | 1301.5000        | 17.2200            | 17.2500           | 216.4950           | 84.7910           |
| OpenSky_Real_World | 91.0000 | 20.5055           | 20.0000          | 24.7829            | 24.6000           | 0.8338             | 0.7985            |
| Synthetic_Sorted   | 39.0000 | 16.5897           | 17.0000          | 21.8641            | 22.0000           | 0.7727             | 0.7500            |

### Table 5: Runtime Stability and Coefficient of Variation (CV)

| Dataset_Class      | Pairs   | Det_CV_Mean | Det_CV_Med | Rand_CV_Mean | Rand_CV_Med | CV_Ratio_Rand_over_Det |
| ------------------ | ------- | ----------- | ---------- | ------------ | ----------- | ---------------------- |
| Adversarial        | 40.0000 | 0.0164      | 0.0088     | 0.0652       | 0.0410      | 3.9851                 |
| OpenSky_Real_World | 91.0000 | 0.0396      | 0.0156     | 0.0551       | 0.0305      | 1.3915                 |
| Synthetic_Sorted   | 39.0000 | 0.0807      | 0.0480     | 0.0725       | 0.0614      | 0.8985                 |

### Table 6: OpenSky Real-World Benchmarks Detailed Breakdown

| Subtype                     | Pairs | Min_N     | Max_N     | Speedup_Mean | Speedup_Median | Speedup_IQR | Det_Rebuilds_Mean | Rand_Rebuilds_Mean |
| --------------------------- | ----- | --------- | --------- | ------------ | -------------- | ----------- | ----------------- | ------------------ |
| OpenSky_100M_10iter         | 1     | 133484198 | 133484198 | 0.9993       | 0.9993         | 0.0000      | 20.0000           | 34.0000            |
| OpenSky_100M_3iter          | 1     | 133484198 | 133484198 | 1.0140       | 1.0140         | 0.0000      | 20.0000           | 32.6700            |
| OpenSky_39M_002012          | 2     | 39037788  | 39037788  | 0.9328       | 0.9328         | 0.0150      | 26.0000           | 32.6000            |
| OpenSky_39M_231351          | 2     | 39037788  | 39037788  | 0.9756       | 0.9756         | 0.0657      | 26.0000           | 31.0000            |
| OpenSky_Cache_Slice         | 11    | 1000      | 5000000   | 1.0023       | 1.0052         | 0.0344      | 11.4545           | 20.6064            |
| OpenSky_Hourly_20190527     | 48    | 1077477   | 2184916   | 1.0315       | 1.0151         | 0.1133      | 19.9167           | 24.7104            |
| OpenSky_MultiDate_Hourly_v3 | 26    | 1419202   | 2425059   | 1.0184       | 1.0100         | 0.0410      | 24.6154           | 24.9462            |

