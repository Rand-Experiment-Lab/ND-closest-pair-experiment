#!/usr/bin/env python3
"""
Maria Empirical Benchmark Aggregator and Statistical Visualizer
==============================================================
Aggregates all valid experimental benchmarks according to strict filtering criteria:
- EXCLUDE: Synthetic Uniform/Normal with Input_Order == 'Original'
- INCLUDE: Synthetic Adversarial (D in [2..7], scales N)
           Synthetic Sorted (Sorted_X_Axis)
           Real-World OpenSky (133.5M, cache 5M, hourly slices v3, hourly 2019-05-27, 39M)

Produces:
- master_aggregated_results.csv
- matched_pairs_speedup.csv
- Publication-quality visualizations (fig1 through fig6)
- Markdown statistical tables
"""

import os
import glob
import ast
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid", font_scale=1.15)
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'
plt.rcParams['figure.autolayout'] = False
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['xtick.labelsize'] = 11
plt.rcParams['ytick.labelsize'] = 11

OUTPUT_DIR = "/media/vithurshan/vithu/rand/analyzer/maria_data_analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def df_to_markdown(df, index=False):
    table_df = df.reset_index() if index else df.copy()
    if isinstance(table_df.columns, pd.MultiIndex):
        table_df.columns = ['_'.join(str(c) for c in col if str(c)).strip('_') for col in table_df.columns.values]
    headers = [str(c) for c in table_df.columns]
    rows = []
    for row in table_df.values:
        row_str = []
        for val in row:
            if isinstance(val, (float, np.floating)):
                row_str.append(f"{val:.4f}")
            elif isinstance(val, (int, np.integer)):
                row_str.append(f"{val}")
            else:
                row_str.append(str(val))
        rows.append(row_str)
    widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
    body_lines = ["| " + " | ".join(row[i].ljust(widths[i]) for i, h in enumerate(headers)) + " |" for row in rows]
    return "\n".join([header_line, sep_line] + body_lines)

def load_and_standardize():
    records = []
    pairs = []
    
    # -------------------------------------------------------------
    # 1. Adversarial Benchmarks
    # -------------------------------------------------------------
    adv_file = '/media/vithurshan/vithu/rand/analyzer/experiment_results_20260911_182510/experiment_results_20260911_182510.csv'
    if os.path.exists(adv_file):
        df = pd.read_csv(adv_file)
        df = df[df['Space_Type'] == 'Adversarial'].copy()
        for (dim, n_pts, order), group in df.groupby(['Dimensions', 'Num_Points', 'Input_Order']):
            det_rows = group[group['Algorithm'] == 'Deterministic Grid']
            rand_rows = group[group['Algorithm'] == 'Randomized Grid']
            if len(det_rows) > 0 and len(rand_rows) > 0:
                d_row = det_rows.iloc[0]
                r_row = rand_rows.iloc[0]
                
                t_det = float(d_row['Mean_Time_ms'])
                t_rand = float(r_row['Mean_Time_ms'])
                speedup = t_det / t_rand if t_rand > 0 else np.nan
                
                reb_det = float(d_row['Mean_Rebuilds'])
                reb_rand = float(r_row['Mean_Rebuilds'])
                
                pair_rec = {
                    'Dataset_Class': 'Adversarial',
                    'Subtype': 'Adversarial_' + str(order),
                    'Source_File': os.path.basename(adv_file),
                    'Dimension': int(dim),
                    'Num_Points': int(n_pts),
                    'Input_Order': str(order),
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Speedup': speedup,
                    'Det_Rebuilds': reb_det,
                    'Rand_Rebuilds': reb_rand,
                    'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                    'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                    'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                    'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                    'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                    'Iterations': int(d_row['Iterations'])
                }
                pairs.append(pair_rec)
                
                for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                    records.append({
                        'Dataset_Class': 'Adversarial',
                        'Subtype': 'Adversarial_' + str(order),
                        'Source_File': os.path.basename(adv_file),
                        'Dimension': int(dim),
                        'Num_Points': int(n_pts),
                        'Input_Order': str(order),
                        'Algorithm': algo,
                        'Mean_Time_ms': float(row['Mean_Time_ms']),
                        'Speedup': speedup,
                        'Rebuilds': float(row['Mean_Rebuilds']),
                        'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                        'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                        'Iterations': int(row['Iterations'])
                    })

    # -------------------------------------------------------------
    # 2. Synthetic Sorted Benchmarks (194655 and 095849)
    # -------------------------------------------------------------
    synth_sorted_files = [
        ('/media/vithurshan/vithu/rand/analyzer/experiment_results_20260912_194655/experiment_results_20260912_194655.csv', 'Synth_Sorted_194655'),
        ('/media/vithurshan/vithu/rand/analyzer/experiment_results_20260911_095849/experiment_results_20260911_095849.csv', 'Synth_Sorted_095849')
    ]
    for s_file, label in synth_sorted_files:
        if os.path.exists(s_file):
            df = pd.read_csv(s_file)
            # STRICT FILTERING DIRECTIVE: ONLY Sorted_X_Axis (EXCLUDE Original)
            df = df[df['Input_Order'] == 'Sorted_X_Axis'].copy()
            for (dim, n_pts), group in df.groupby(['Dimensions', 'Num_Points']):
                det_rows = group[group['Algorithm'] == 'Deterministic Grid']
                rand_rows = group[group['Algorithm'] == 'Randomized Grid']
                if len(det_rows) > 0 and len(rand_rows) > 0:
                    d_row = det_rows.iloc[0]
                    r_row = rand_rows.iloc[0]
                    
                    t_det = float(d_row['Mean_Time_ms'])
                    t_rand = float(r_row['Mean_Time_ms'])
                    speedup = t_det / t_rand if t_rand > 0 else np.nan
                    reb_det = float(d_row['Mean_Rebuilds'])
                    reb_rand = float(r_row['Mean_Rebuilds'])
                    
                    pair_rec = {
                        'Dataset_Class': 'Synthetic_Sorted',
                        'Subtype': label,
                        'Source_File': os.path.basename(s_file),
                        'Dimension': int(dim),
                        'Num_Points': int(n_pts),
                        'Input_Order': 'Sorted_X_Axis',
                        'Det_Time_ms': t_det,
                        'Rand_Time_ms': t_rand,
                        'Speedup': speedup,
                        'Det_Rebuilds': reb_det,
                        'Rand_Rebuilds': reb_rand,
                        'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                        'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                        'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                        'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                        'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                        'Iterations': int(d_row['Iterations'])
                    }
                    pairs.append(pair_rec)
                    
                    for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                        records.append({
                            'Dataset_Class': 'Synthetic_Sorted',
                            'Subtype': label,
                            'Source_File': os.path.basename(s_file),
                            'Dimension': int(dim),
                            'Num_Points': int(n_pts),
                            'Input_Order': 'Sorted_X_Axis',
                            'Algorithm': algo,
                            'Mean_Time_ms': float(row['Mean_Time_ms']),
                            'Speedup': speedup,
                            'Rebuilds': float(row['Mean_Rebuilds']),
                            'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                            'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                            'Iterations': int(row['Iterations'])
                        })

    # -------------------------------------------------------------
    # 3. OpenSky Real-World 100M
    # -------------------------------------------------------------
    opensky_100m_files = [
        ('/media/vithurshan/vithu/rand/analyzer/opensky_100M_results/opensky_100M_results.csv', 'OpenSky_100M_3iter'),
        ('/media/vithurshan/vithu/rand/analyzer/opensky_100M_results_v1/opensky_100M_results.csv', 'OpenSky_100M_10iter')
    ]
    for o_file, label in opensky_100m_files:
        if os.path.exists(o_file):
            df = pd.read_csv(o_file)
            det_rows = df[df['Algorithm'] == 'Deterministic Grid']
            rand_rows = df[df['Algorithm'] == 'Randomized Grid']
            if len(det_rows) > 0 and len(rand_rows) > 0:
                d_row = det_rows.iloc[0]
                r_row = rand_rows.iloc[0]
                
                t_det = float(d_row['Mean_Time_ms'])
                t_rand = float(r_row['Mean_Time_ms'])
                speedup = t_det / t_rand if t_rand > 0 else np.nan
                reb_det = float(d_row['Mean_Rebuilds'])
                reb_rand = float(r_row['Mean_Rebuilds'])
                dim = int(d_row['Dimensions'])
                n_pts = int(d_row['Num_Points'])
                order = str(d_row['Input_Order'])
                
                pair_rec = {
                    'Dataset_Class': 'OpenSky_Real_World',
                    'Subtype': label,
                    'Source_File': os.path.basename(o_file),
                    'Dimension': dim,
                    'Num_Points': n_pts,
                    'Input_Order': order,
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Speedup': speedup,
                    'Det_Rebuilds': reb_det,
                    'Rand_Rebuilds': reb_rand,
                    'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                    'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                    'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                    'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                    'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                    'Iterations': int(d_row['Iterations'])
                }
                pairs.append(pair_rec)
                
                for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                    records.append({
                        'Dataset_Class': 'OpenSky_Real_World',
                        'Subtype': label,
                        'Source_File': os.path.basename(o_file),
                        'Dimension': dim,
                        'Num_Points': n_pts,
                        'Input_Order': order,
                        'Algorithm': algo,
                        'Mean_Time_ms': float(row['Mean_Time_ms']),
                        'Speedup': speedup,
                        'Rebuilds': float(row['Mean_Rebuilds']),
                        'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                        'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                        'Iterations': int(row['Iterations'])
                    })

    # -------------------------------------------------------------
    # 4. OpenSky Cache Benchmark (5M points continuous slice)
    # -------------------------------------------------------------
    cache_file = '/media/vithurshan/vithu/rand/analyzer/opensky_cache_results/opensky_cache_results.csv'
    if os.path.exists(cache_file):
        df = pd.read_csv(cache_file)
        for (dim, n_pts, order), group in df.groupby(['Dimensions', 'Num_Points', 'Input_Order']):
            det_rows = group[group['Algorithm'] == 'Deterministic Grid']
            rand_rows = group[group['Algorithm'] == 'Randomized Grid']
            if len(det_rows) > 0 and len(rand_rows) > 0:
                d_row = det_rows.iloc[0]
                r_row = rand_rows.iloc[0]
                
                t_det = float(d_row['Mean_Time_ms'])
                t_rand = float(r_row['Mean_Time_ms'])
                speedup = t_det / t_rand if t_rand > 0 else np.nan
                reb_det = float(d_row['Mean_Rebuilds'])
                reb_rand = float(r_row['Mean_Rebuilds'])
                
                pair_rec = {
                    'Dataset_Class': 'OpenSky_Real_World',
                    'Subtype': 'OpenSky_Cache_Slice',
                    'Source_File': os.path.basename(cache_file),
                    'Dimension': int(dim),
                    'Num_Points': int(n_pts),
                    'Input_Order': str(order),
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Speedup': speedup,
                    'Det_Rebuilds': reb_det,
                    'Rand_Rebuilds': reb_rand,
                    'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                    'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                    'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                    'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                    'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                    'Iterations': int(d_row['Iterations'])
                }
                pairs.append(pair_rec)
                
                for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                    records.append({
                        'Dataset_Class': 'OpenSky_Real_World',
                        'Subtype': 'OpenSky_Cache_Slice',
                        'Source_File': os.path.basename(cache_file),
                        'Dimension': int(dim),
                        'Num_Points': int(n_pts),
                        'Input_Order': str(order),
                        'Algorithm': algo,
                        'Mean_Time_ms': float(row['Mean_Time_ms']),
                        'Speedup': speedup,
                        'Rebuilds': float(row['Mean_Rebuilds']),
                        'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                        'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                        'Iterations': int(row['Iterations'])
                    })

    # -------------------------------------------------------------
    # 5. OpenSky Multi-Date Hourly v3
    # -------------------------------------------------------------
    v3_file = '/media/vithurshan/vithu/rand/analyzer/opensky_all_dates_results_20260912_081335_v3/opensky_all_dates_results_20260912_081335.csv'
    if os.path.exists(v3_file):
        df = pd.read_csv(v3_file)
        dim = 4
        for (tag, order), group in df.groupby(['Hour_Tag', 'Input_Order']):
            det_rows = group[group['Algorithm'] == 'Deterministic Grid']
            rand_rows = group[group['Algorithm'] == 'Randomized Grid']
            if len(det_rows) > 0 and len(rand_rows) > 0:
                d_row = det_rows.iloc[0]
                r_row = rand_rows.iloc[0]
                
                t_det = float(d_row['Mean_Time_ms'])
                t_rand = float(r_row['Mean_Time_ms'])
                speedup = t_det / t_rand if t_rand > 0 else np.nan
                reb_det = float(d_row['Mean_Rebuilds'])
                reb_rand = float(r_row['Mean_Rebuilds'])
                n_pts = int(d_row['Num_Points'])
                
                pair_rec = {
                    'Dataset_Class': 'OpenSky_Real_World',
                    'Subtype': 'OpenSky_MultiDate_Hourly_v3',
                    'Source_File': os.path.basename(v3_file),
                    'Dimension': dim,
                    'Num_Points': n_pts,
                    'Input_Order': str(order),
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Speedup': speedup,
                    'Det_Rebuilds': reb_det,
                    'Rand_Rebuilds': reb_rand,
                    'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                    'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                    'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                    'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                    'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                    'Iterations': int(d_row['Iterations']),
                    'Tag': str(tag)
                }
                pairs.append(pair_rec)
                
                for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                    records.append({
                        'Dataset_Class': 'OpenSky_Real_World',
                        'Subtype': 'OpenSky_MultiDate_Hourly_v3',
                        'Source_File': os.path.basename(v3_file),
                        'Dimension': dim,
                        'Num_Points': n_pts,
                        'Input_Order': str(order),
                        'Algorithm': algo,
                        'Mean_Time_ms': float(row['Mean_Time_ms']),
                        'Speedup': speedup,
                        'Rebuilds': float(row['Mean_Rebuilds']),
                        'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                        'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                        'Iterations': int(row['Iterations'])
                    })

    # -------------------------------------------------------------
    # 6. OpenSky Hourly Results (2019-05-27 full 24 hours)
    # -------------------------------------------------------------
    hourly_file = '/media/vithurshan/vithu/rand/analyzer/opensky_hourly_results_20260912_082011/opensky_hourly_results_20260912_082011.csv'
    if os.path.exists(hourly_file):
        df = pd.read_csv(hourly_file)
        dim = 4
        for (tag, order), group in df.groupby(['Hour_Tag', 'Input_Order']):
            det_rows = group[group['Algorithm'] == 'Deterministic Grid']
            rand_rows = group[group['Algorithm'] == 'Randomized Grid']
            if len(det_rows) > 0 and len(rand_rows) > 0:
                d_row = det_rows.iloc[0]
                r_row = rand_rows.iloc[0]
                
                t_det = float(d_row['Mean_Time_ms'])
                t_rand = float(r_row['Mean_Time_ms'])
                speedup = t_det / t_rand if t_rand > 0 else np.nan
                reb_det = float(d_row['Mean_Rebuilds'])
                reb_rand = float(r_row['Mean_Rebuilds'])
                n_pts = int(d_row['Num_Points'])
                
                pair_rec = {
                    'Dataset_Class': 'OpenSky_Real_World',
                    'Subtype': 'OpenSky_Hourly_20190527',
                    'Source_File': os.path.basename(hourly_file),
                    'Dimension': dim,
                    'Num_Points': n_pts,
                    'Input_Order': str(order),
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Speedup': speedup,
                    'Det_Rebuilds': reb_det,
                    'Rand_Rebuilds': reb_rand,
                    'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                    'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                    'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                    'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                    'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                    'Iterations': int(d_row['Iterations']),
                    'Tag': str(tag)
                }
                pairs.append(pair_rec)
                
                for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                    records.append({
                        'Dataset_Class': 'OpenSky_Real_World',
                        'Subtype': 'OpenSky_Hourly_20190527',
                        'Source_File': os.path.basename(hourly_file),
                        'Dimension': dim,
                        'Num_Points': n_pts,
                        'Input_Order': str(order),
                        'Algorithm': algo,
                        'Mean_Time_ms': float(row['Mean_Time_ms']),
                        'Speedup': speedup,
                        'Rebuilds': float(row['Mean_Rebuilds']),
                        'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                        'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                        'Iterations': int(row['Iterations'])
                    })

    # -------------------------------------------------------------
    # 7. OpenSky 39M Point Daily Benchmarks (231351 and 002012)
    # -------------------------------------------------------------
    opensky_39m_files = [
        ('/media/vithurshan/vithu/rand/analyzer/opensky_results_20260911_231351/opensky_results_20260911_231351.csv', 'OpenSky_39M_231351'),
        ('/media/vithurshan/vithu/rand/analyzer/opensky_results_20260912_002012/opensky_results_20260912_002012.csv', 'OpenSky_39M_002012')
    ]
    for o_file, label in opensky_39m_files:
        if os.path.exists(o_file):
            df = pd.read_csv(o_file)
            dim = int(df['Dimensions'].iloc[0])
            for order, group in df.groupby('Input_Order'):
                det_rows = group[group['Algorithm'] == 'Deterministic Grid']
                rand_rows = group[group['Algorithm'] == 'Randomized Grid']
                if len(det_rows) > 0 and len(rand_rows) > 0:
                    d_row = det_rows.iloc[0]
                    r_row = rand_rows.iloc[0]
                    
                    t_det = float(d_row['Mean_Time_ms'])
                    t_rand = float(r_row['Mean_Time_ms'])
                    speedup = t_det / t_rand if t_rand > 0 else np.nan
                    reb_det = float(d_row['Mean_Rebuilds'])
                    reb_rand = float(r_row['Mean_Rebuilds'])
                    n_pts = int(d_row['Num_Points'])
                    
                    pair_rec = {
                        'Dataset_Class': 'OpenSky_Real_World',
                        'Subtype': label,
                        'Source_File': os.path.basename(o_file),
                        'Dimension': dim,
                        'Num_Points': n_pts,
                        'Input_Order': str(order),
                        'Det_Time_ms': t_det,
                        'Rand_Time_ms': t_rand,
                        'Speedup': speedup,
                        'Det_Rebuilds': reb_det,
                        'Rand_Rebuilds': reb_rand,
                        'Rebuild_Ratio': reb_det / reb_rand if reb_rand > 0 else np.nan,
                        'Det_StdDev_ms': float(d_row['StdDev_Time_ms']),
                        'Rand_StdDev_ms': float(r_row['StdDev_Time_ms']),
                        'Det_CV': float(d_row['StdDev_Time_ms']) / t_det if t_det > 0 else np.nan,
                        'Rand_CV': float(r_row['StdDev_Time_ms']) / t_rand if t_rand > 0 else np.nan,
                        'Iterations': int(d_row['Iterations'])
                    }
                    pairs.append(pair_rec)
                    
                    for row, algo in [(d_row, 'Deterministic Grid'), (r_row, 'Randomized Grid')]:
                        records.append({
                            'Dataset_Class': 'OpenSky_Real_World',
                            'Subtype': label,
                            'Source_File': os.path.basename(o_file),
                            'Dimension': dim,
                            'Num_Points': n_pts,
                            'Input_Order': str(order),
                            'Algorithm': algo,
                            'Mean_Time_ms': float(row['Mean_Time_ms']),
                            'Speedup': speedup,
                            'Rebuilds': float(row['Mean_Rebuilds']),
                            'StdDev_Time_ms': float(row['StdDev_Time_ms']),
                            'StdDev_Rebuilds': float(row['StdDev_Rebuilds']),
                            'Iterations': int(row['Iterations'])
                        })

    master_df = pd.DataFrame(records)
    pairs_df = pd.DataFrame(pairs)
    return master_df, pairs_df

def compute_statistics(pairs_df):
    stats = {}
    
    def calc_stats(series):
        return pd.Series({
            'Count': len(series),
            'Mean': series.mean(),
            'StdDev': series.std(),
            'Median': series.median(),
            'IQR': series.quantile(0.75) - series.quantile(0.25),
            'Min': series.min(),
            'Max': series.max(),
            'Pct_Faster': (series > 1.0).mean() * 100.0
        })
    
    stats['by_class'] = pairs_df.groupby('Dataset_Class')['Speedup'].apply(calc_stats).unstack()
    stats['by_class_order'] = pairs_df.groupby(['Dataset_Class', 'Input_Order'])['Speedup'].apply(calc_stats).unstack()
    stats['by_dim'] = pairs_df.groupby(['Dataset_Class', 'Dimension'])['Speedup'].apply(calc_stats).unstack()
    
    def calc_reb_stats(df_group):
        return pd.Series({
            'Pairs': len(df_group),
            'Det_Rebuilds_Mean': df_group['Det_Rebuilds'].mean(),
            'Det_Rebuilds_Med': df_group['Det_Rebuilds'].median(),
            'Rand_Rebuilds_Mean': df_group['Rand_Rebuilds'].mean(),
            'Rand_Rebuilds_Med': df_group['Rand_Rebuilds'].median(),
            'Rebuild_Ratio_Mean': df_group['Rebuild_Ratio'].mean(),
            'Rebuild_Ratio_Med': df_group['Rebuild_Ratio'].median()
        })
    stats['rebuilds_by_class'] = pairs_df.groupby('Dataset_Class').apply(calc_reb_stats)
    stats['rebuilds_by_order'] = pairs_df.groupby(['Dataset_Class', 'Input_Order']).apply(calc_reb_stats)
    
    def calc_cv_stats(df_group):
        return pd.Series({
            'Pairs': len(df_group),
            'Det_CV_Mean': df_group['Det_CV'].mean(),
            'Det_CV_Med': df_group['Det_CV'].median(),
            'Rand_CV_Mean': df_group['Rand_CV'].mean(),
            'Rand_CV_Med': df_group['Rand_CV'].median(),
            'CV_Ratio_Rand_over_Det': df_group['Rand_CV'].mean() / df_group['Det_CV'].mean() if df_group['Det_CV'].mean() > 0 else np.nan
        })
    stats['cv_by_class'] = pairs_df.groupby('Dataset_Class').apply(calc_cv_stats)
    
    return stats

def plot_all(pairs_df, master_df):
    class_palette = {
        'Adversarial': '#D9381E',
        'Synthetic_Sorted': '#2A75D3',
        'OpenSky_Real_World': '#1B9E77'
    }
    
    # -------------------------------------------------------------
    # Figure 1: Speedup Distribution by Dataset Class (Box & Violin)
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    sns.boxplot(
        data=pairs_df,
        x='Dataset_Class',
        y='Speedup',
        hue='Dataset_Class',
        palette=class_palette,
        ax=ax1,
        showmeans=True,
        meanprops={"marker":"o", "markerfacecolor":"white", "markeredgecolor":"black", "markersize":"8"}
    )
    ax1.set_yscale('log')
    ax1.axhline(1.0, color='gray', linestyle='--', linewidth=1.5, label='Parity (1.0x)')
    ax1.set_title('(A) Speedup Distribution across Dataset Classes (Log Scale)', fontweight='bold')
    ax1.set_xlabel('Dataset Category')
    ax1.set_ylabel('Speedup (T_det / T_rand) [Log10 Scale]')
    ax1.legend(loc='upper right')
    
    non_adv = pairs_df[pairs_df['Dataset_Class'].isin(['Synthetic_Sorted', 'OpenSky_Real_World'])].copy()
    sns.violinplot(
        data=non_adv,
        x='Dataset_Class',
        y='Speedup',
        hue='Dataset_Class',
        palette=class_palette,
        inner="quartile",
        cut=0,
        ax=ax2
    )
    sns.stripplot(
        data=non_adv,
        x='Dataset_Class',
        y='Speedup',
        color='black',
        alpha=0.35,
        jitter=0.2,
        size=4,
        ax=ax2
    )
    ax2.axhline(1.0, color='red', linestyle='--', linewidth=1.5, label='Parity (1.0x)')
    ax2.set_title('(B) Empirical Parity in Real & Sorted Data (Linear Scale)', fontweight='bold')
    ax2.set_xlabel('Dataset Category')
    ax2.set_ylabel('Speedup (T_det / T_rand)')
    ax2.set_ylim(0.4, 2.0)
    ax2.legend(loc='upper right')
    
    plt.tight_layout()
    fig1_path = os.path.join(OUTPUT_DIR, 'fig1_speedup_distribution_by_class.png')
    plt.savefig(fig1_path, dpi=300)
    plt.close()
    print(f"Generated: {fig1_path}")

    # -------------------------------------------------------------
    # Figure 2: Scaling with Scale N (Speedup vs N from 1k to 133.5M)
    # -------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(12, 7))
    
    sky_data = pairs_df[pairs_df['Dataset_Class'] == 'OpenSky_Real_World']
    ax.scatter(
        sky_data['Num_Points'], sky_data['Speedup'],
        color='#1B9E77', alpha=0.75, s=60, edgecolors='black', linewidth=0.5,
        label='OpenSky Real-World (N=1k -> 133.5M)', zorder=4
    )
    
    sorted_data = pairs_df[pairs_df['Dataset_Class'] == 'Synthetic_Sorted']
    ax.scatter(
        sorted_data['Num_Points'], sorted_data['Speedup'],
        color='#2A75D3', alpha=0.75, s=60, marker='s', edgecolors='black', linewidth=0.5,
        label='Synthetic Sorted (N=50k -> 500k)', zorder=4
    )
    
    adv_ladder = pairs_df[(pairs_df['Dataset_Class'] == 'Adversarial') & (pairs_df['Input_Order'] == 'Ladder_of_Pairs')]
    adv_sorted = pairs_df[(pairs_df['Dataset_Class'] == 'Adversarial') & (pairs_df['Input_Order'] == 'Sorted_X_Axis')]
    
    ax.scatter(
        adv_ladder['Num_Points'], adv_ladder['Speedup'],
        color='#D9381E', alpha=0.85, s=80, marker='^', edgecolors='black', linewidth=0.7,
        label='Adversarial (Ladder of Pairs - O(N) Speedup)', zorder=5
    )
    ax.scatter(
        adv_sorted['Num_Points'], adv_sorted['Speedup'],
        color='#E67E22', alpha=0.85, s=70, marker='v', edgecolors='black', linewidth=0.7,
        label='Adversarial (Sorted X-Axis)', zorder=4
    )
    
    ax.axhline(1.0, color='black', linestyle='--', linewidth=1.5, label='Parity Baseline (1.0x)')
    ax.set_xscale('log')
    ax.set_yscale('log')
    ax.set_title('Speedup (T_det / T_rand) vs Scale N across All Benchmarks (1k to 133.5M)', fontweight='bold')
    ax.set_xlabel('Scale N (Number of Points) [Log Scale]')
    ax.set_ylabel('Speedup (T_det / T_rand) [Log Scale]')
    ax.grid(True, which='both', linestyle=':', alpha=0.6)
    
    sky_100m = pairs_df[(pairs_df['Dataset_Class'] == 'OpenSky_Real_World') & (pairs_df['Num_Points'] > 100_000_000)]
    if len(sky_100m) > 0:
        row = sky_100m.iloc[0]
        ax.annotate(
            f"OpenSky 100M (N=133.5M)\nSpeedup = {row['Speedup']:.4f}x\nDet: {row['Det_Time_ms']/1000:.1f}s | Rand: {row['Rand_Time_ms']/1000:.1f}s",
            xy=(row['Num_Points'], row['Speedup']),
            xytext=(row['Num_Points']*0.08, row['Speedup']*0.25),
            arrowprops=dict(facecolor='#1B9E77', arrowstyle='->', lw=1.8),
            bbox=dict(boxstyle="round,pad=0.4", fc="#E8F8F5", ec="#1B9E77", lw=1.2),
            fontweight='bold', fontsize=10
        )
        
    adv_max = adv_ladder.loc[adv_ladder['Speedup'].idxmax()]
    ax.annotate(
        f"Max Adversarial Speedup:\n{adv_max['Speedup']:.1f}x (D={adv_max['Dimension']}, N={adv_max['Num_Points']:,})\nDet: {adv_max['Det_Time_ms']/1000:.1f}s vs Rand: {adv_max['Rand_Time_ms']:.1f}ms",
        xy=(adv_max['Num_Points'], adv_max['Speedup']),
        xytext=(adv_max['Num_Points']*0.25, adv_max['Speedup']*0.4),
        arrowprops=dict(facecolor='#D9381E', arrowstyle='->', lw=1.8),
        bbox=dict(boxstyle="round,pad=0.4", fc="#FDEDEC", ec="#D9381E", lw=1.2),
        fontweight='bold', fontsize=10
    )
    
    ax.legend(loc='lower left', frameon=True, framealpha=0.9)
    plt.tight_layout()
    fig2_path = os.path.join(OUTPUT_DIR, 'fig2_scaling_speedup_vs_N.png')
    plt.savefig(fig2_path, dpi=300)
    plt.close()
    print(f"Generated: {fig2_path}")

    # -------------------------------------------------------------
    # Figure 3: Rebuild Counts vs N and Seidel Theoretical Curve
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    ax1.scatter(
        adv_ladder['Num_Points'], adv_ladder['Det_Rebuilds'],
        color='#D9381E', marker='^', s=80, label='Det Adversarial (W ≈ N/2)', zorder=5
    )
    ax1.scatter(
        adv_ladder['Num_Points'], adv_ladder['Rand_Rebuilds'],
        color='#E74C3C', marker='o', s=60, label='Rand Adversarial (W ≈ 2 ln N)', zorder=4
    )
    ax1.scatter(
        sky_data['Num_Points'], sky_data['Det_Rebuilds'],
        color='#1B9E77', marker='s', s=50, alpha=0.8, label='Det OpenSky (W <= 34)', zorder=4
    )
    ax1.scatter(
        sky_data['Num_Points'], sky_data['Rand_Rebuilds'],
        color='#2ECC71', marker='x', s=50, alpha=0.8, label='Rand OpenSky (W ≈ 2 ln N)', zorder=4
    )
    
    n_space = np.logspace(3, 8.2, 200)
    seidel_curve = 2 * np.log(n_space)
    ax1.plot(n_space, seidel_curve, 'k--', linewidth=2, label='Seidel Bound: 2 ln(N)', zorder=6)
    ax1.plot(n_space, n_space / 2, 'r:', linewidth=1.5, label='Worst-Case Bound: N / 2', zorder=2)
    
    ax1.set_xscale('log')
    ax1.set_yscale('log')
    ax1.set_title('(A) Hash Grid Rebuilds across All Scales (Log-Log)', fontweight='bold')
    ax1.set_xlabel('Scale N (Number of Points)')
    ax1.set_ylabel('Number of Grid Rebuilds (W_variable)')
    ax1.legend(loc='upper left', fontsize=10)
    ax1.grid(True, which='both', linestyle=':', alpha=0.6)
    
    non_adv_pairs = pairs_df[pairs_df['Dataset_Class'].isin(['Synthetic_Sorted', 'OpenSky_Real_World'])].copy()
    ax2.scatter(
        non_adv_pairs['Num_Points'], non_adv_pairs['Det_Rebuilds'],
        color='#2980B9', marker='o', s=60, alpha=0.75, edgecolors='black', linewidth=0.5,
        label='Deterministic Grid (Empirical Real/Sorted)'
    )
    ax2.scatter(
        non_adv_pairs['Num_Points'], non_adv_pairs['Rand_Rebuilds'],
        color='#27AE60', marker='^', s=60, alpha=0.75, edgecolors='black', linewidth=0.5,
        label='Randomized Grid (Empirical Real/Sorted)'
    )
    ax2.plot(n_space, seidel_curve, 'k--', linewidth=2, label='Theoretical Expectation: 2 ln(N)')
    
    ax2.set_xscale('log')
    ax2.set_ylim(0, 50)
    ax2.set_title('(B) Empirical Rebuild Counts vs Seidel Bound (Non-Adversarial)', fontweight='bold')
    ax2.set_xlabel('Scale N (Number of Points)')
    ax2.set_ylabel('Number of Grid Rebuilds')
    ax2.legend(loc='upper left', fontsize=10)
    ax2.grid(True, which='both', linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    fig3_path = os.path.join(OUTPUT_DIR, 'fig3_rebuild_counts_vs_N.png')
    plt.savefig(fig3_path, dpi=300)
    plt.close()
    print(f"Generated: {fig3_path}")

    # -------------------------------------------------------------
    # Figure 4: Dimensional Dilution (D in [2..7])
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
    
    adv_ladder_data = pairs_df[(pairs_df['Dataset_Class'] == 'Adversarial') & (pairs_df['Input_Order'] == 'Ladder_of_Pairs')]
    sns.lineplot(
        data=adv_ladder_data,
        x='Dimension',
        y='Speedup',
        hue='Num_Points',
        marker='o',
        markersize=9,
        linewidth=2.5,
        palette='Spectral_r',
        ax=ax1
    )
    ax1.set_yscale('log')
    ax1.set_title('(A) Adversarial Speedup Dilution vs Dimension (D = 2 to 7)', fontweight='bold')
    ax1.set_xlabel('Dimension D')
    ax1.set_ylabel('Speedup (T_det / T_rand) [Log Scale]')
    ax1.grid(True, which='both', linestyle=':', alpha=0.6)
    ax1.legend(title='Scale N', loc='upper right')
    
    d_vals = np.array([2, 3, 4, 5, 6, 7])
    cells_searched = 3 ** d_vals
    adv_25k = adv_ladder_data[adv_ladder_data['Num_Points'] == 25000].sort_values('Dimension')
    
    ax2_twin = ax2.twinx()
    l1 = ax2.plot(d_vals, cells_searched, 'ro--', linewidth=2.5, label='Search Neighborhood Size: 3^D Cells')
    l2 = ax2_twin.plot(adv_25k['Dimension'], adv_25k['Speedup'], 'bs-', linewidth=2.5, label='Empirical Speedup (N=25k)')
    
    ax2.set_yscale('log')
    ax2_twin.set_yscale('log')
    ax2.set_title('(B) Dilution Mechanism: Exponential Growth of 3^D Query Cost', fontweight='bold')
    ax2.set_xlabel('Dimension D')
    ax2.set_ylabel('Adjacent Grid Cells Checked (3^D) [Log Scale]', color='r')
    ax2_twin.set_ylabel('Adversarial Speedup (T_det / T_rand) [Log Scale]', color='b')
    ax2.tick_params(axis='y', labelcolor='r')
    ax2_twin.tick_params(axis='y', labelcolor='b')
    ax2.grid(True, which='both', linestyle=':', alpha=0.6)
    
    lines = l1 + l2
    labels = [l.get_label() for l in lines]
    ax2.legend(lines, labels, loc='center right')
    
    plt.tight_layout()
    fig4_path = os.path.join(OUTPUT_DIR, 'fig4_dimensional_dilution.png')
    plt.savefig(fig4_path, dpi=300)
    plt.close()
    print(f"Generated: {fig4_path}")

    # -------------------------------------------------------------
    # Figure 5: In-Depth OpenSky Real-World Multi-Panel Breakdown
    # -------------------------------------------------------------
    fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(16, 12))
    
    hourly_pairs = pairs_df[pairs_df['Subtype'].str.contains('Hourly|MultiDate', na=False)].copy()
    sns.boxplot(
        data=hourly_pairs,
        x='Subtype',
        y='Speedup',
        hue='Input_Order',
        palette={'Original': '#1B9E77', 'Sorted_Time': '#D95F02'},
        ax=ax1
    )
    ax1.axhline(1.0, color='red', linestyle='--', linewidth=1.5, label='Parity (1.0x)')
    ax1.set_title('(A) OpenSky Hourly Speedup: Chronological vs Sorted Time', fontweight='bold')
    ax1.set_xlabel('Experiment Batch')
    ax1.set_ylabel('Speedup (T_det / T_rand)')
    ax1.set_ylim(0.75, 1.4)
    ax1.legend(loc='upper right')
    
    sns.scatterplot(
        data=hourly_pairs,
        x='Det_Time_ms',
        y='Rand_Time_ms',
        hue='Input_Order',
        palette={'Original': '#1B9E77', 'Sorted_Time': '#D95F02'},
        s=70,
        ax=ax2
    )
    max_t = max(hourly_pairs['Det_Time_ms'].max(), hourly_pairs['Rand_Time_ms'].max()) * 1.05
    ax2.plot([0, max_t], [0, max_t], 'k--', label='Identity Line (T_det = T_rand)')
    ax2.set_title('(B) Deterministic vs Randomized Runtimes (Hourly Slices)', fontweight='bold')
    ax2.set_xlabel('Deterministic Mean Time (ms)')
    ax2.set_ylabel('Randomized Mean Time (ms)')
    ax2.legend(loc='lower right')
    
    cache_pairs = pairs_df[pairs_df['Subtype'] == 'OpenSky_Cache_Slice'].sort_values('Num_Points')
    ax3.plot(cache_pairs['Num_Points'], cache_pairs['Det_Time_ms'], 'o-', color='#1B9E77', label='Deterministic Grid', linewidth=2)
    ax3.plot(cache_pairs['Num_Points'], cache_pairs['Rand_Time_ms'], 's--', color='#E74C3C', label='Randomized Grid', linewidth=2)
    ax3.set_xscale('log')
    ax3.set_yscale('log')
    ax3.set_title('(C) Continuous OpenSky Cache Scaling (N = 1k to 5M)', fontweight='bold')
    ax3.set_xlabel('Number of Aircraft State Vectors N')
    ax3.set_ylabel('Mean Execution Time (ms)')
    ax3.legend(loc='upper left')
    ax3.grid(True, which='both', linestyle=':', alpha=0.6)
    
    ax4.plot(cache_pairs['Num_Points'], cache_pairs['Det_Rebuilds'], 'o-', color='#1B9E77', label='Deterministic Rebuilds', linewidth=2)
    ax4.plot(cache_pairs['Num_Points'], cache_pairs['Rand_Rebuilds'], 's--', color='#E74C3C', label='Randomized Rebuilds', linewidth=2)
    ax4.plot(cache_pairs['Num_Points'], 2 * np.log(cache_pairs['Num_Points']), 'k:', label='Theoretical 2 ln(N)', linewidth=1.5)
    ax4.set_xscale('log')
    ax4.set_title('(D) OpenSky Cache Benchmark Rebuilds (W_variable)', fontweight='bold')
    ax4.set_xlabel('Number of Aircraft State Vectors N')
    ax4.set_ylabel('Grid Rebuild Count')
    ax4.legend(loc='upper left')
    ax4.grid(True, which='both', linestyle=':', alpha=0.6)
    
    plt.tight_layout()
    fig5_path = os.path.join(OUTPUT_DIR, 'fig5_runtime_and_rebuild_distributions_opensky.png')
    plt.savefig(fig5_path, dpi=300)
    plt.close()
    print(f"Generated: {fig5_path}")

    # -------------------------------------------------------------
    # Figure 6: Variance and Stability (Coefficient of Variation)
    # -------------------------------------------------------------
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6))
    
    cv_records = []
    for _, row in pairs_df.iterrows():
        cv_records.append({
            'Dataset_Class': row['Dataset_Class'],
            'Algorithm': 'Deterministic Grid',
            'CV': row['Det_CV']
        })
        cv_records.append({
            'Dataset_Class': row['Dataset_Class'],
            'Algorithm': 'Randomized Grid',
            'CV': row['Rand_CV']
        })
    cv_df = pd.DataFrame(cv_records).dropna()
    
    sns.boxplot(
        data=cv_df,
        x='Dataset_Class',
        y='CV',
        hue='Algorithm',
        palette={'Deterministic Grid': '#2A75D3', 'Randomized Grid': '#E74C3C'},
        showmeans=True,
        meanprops={"marker":"o", "markerfacecolor":"white", "markeredgecolor":"black", "markersize":"7"},
        ax=ax1
    )
    ax1.set_title('(A) Coefficient of Variation (StdDev / Mean Time)', fontweight='bold')
    ax1.set_xlabel('Dataset Category')
    ax1.set_ylabel('Coefficient of Variation (CV = σ / μ)')
    ax1.set_ylim(0, 0.35)
    ax1.legend(loc='upper right')
    
    sns.scatterplot(
        data=pairs_df,
        x='Det_CV',
        y='Rand_CV',
        hue='Dataset_Class',
        palette=class_palette,
        s=60,
        alpha=0.8,
        ax=ax2
    )
    max_cv = max(pairs_df['Det_CV'].max(), pairs_df['Rand_CV'].max())
    ax2.plot([0, 0.3], [0, 0.3], 'k--', label='Equal Noise Line (Det CV = Rand CV)')
    ax2.set_title('(B) Paired Noise Comparison (Det CV vs Rand CV)', fontweight='bold')
    ax2.set_xlabel('Deterministic CV (σ / μ)')
    ax2.set_ylabel('Randomized CV (σ / μ)')
    ax2.set_xlim(0, 0.25)
    ax2.set_ylim(0, 0.25)
    ax2.legend(loc='upper left')
    
    plt.tight_layout()
    fig6_path = os.path.join(OUTPUT_DIR, 'fig6_variance_and_stability_cv.png')
    plt.savefig(fig6_path, dpi=300)
    plt.close()
    print(f"Generated: {fig6_path}")

def generate_markdown_tables(stats, pairs_df):
    tables_txt = ""
    
    # 1. Dataset Class Overview
    df_class = stats['by_class'].reset_index()
    tables_txt += "### Table 1: Speedup Statistics by Dataset Category\n\n"
    tables_txt += df_to_markdown(df_class, index=False)
    tables_txt += "\n\n"
    
    # 2. Dataset Class and Input Order
    df_class_order = stats['by_class_order'].reset_index()
    tables_txt += "### Table 2: Speedup Breakdown by Dataset Class and Input Order\n\n"
    tables_txt += df_to_markdown(df_class_order, index=False)
    tables_txt += "\n\n"
    
    # 3. Dimensional Breakdown
    df_dim = stats['by_dim'].reset_index()
    tables_txt += "### Table 3: Dimensional Scaling (D = 2 to 7) and Dilution Effects\n\n"
    tables_txt += df_to_markdown(df_dim, index=False)
    tables_txt += "\n\n"
    
    # 4. Rebuild Counts
    df_reb = stats['rebuilds_by_class'].reset_index()
    tables_txt += "### Table 4: Hash Grid Rebuild Statistics (W_variable) by Category\n\n"
    tables_txt += df_to_markdown(df_reb, index=False)
    tables_txt += "\n\n"
    
    # 5. Stability & CV
    df_cv = stats['cv_by_class'].reset_index()
    tables_txt += "### Table 5: Runtime Stability and Coefficient of Variation (CV)\n\n"
    tables_txt += df_to_markdown(df_cv, index=False)
    tables_txt += "\n\n"
    
    # 6. OpenSky Specific Benchmark Summary
    sky_pairs = pairs_df[pairs_df['Dataset_Class'] == 'OpenSky_Real_World']
    sky_summary = sky_pairs.groupby('Subtype').agg(
        Pairs=('Speedup', 'count'),
        Min_N=('Num_Points', 'min'),
        Max_N=('Num_Points', 'max'),
        Speedup_Mean=('Speedup', 'mean'),
        Speedup_Median=('Speedup', 'median'),
        Speedup_IQR=('Speedup', lambda x: x.quantile(0.75) - x.quantile(0.25)),
        Det_Rebuilds_Mean=('Det_Rebuilds', 'mean'),
        Rand_Rebuilds_Mean=('Rand_Rebuilds', 'mean')
    ).reset_index()
    tables_txt += "### Table 6: OpenSky Real-World Benchmarks Detailed Breakdown\n\n"
    tables_txt += df_to_markdown(sky_summary, index=False)
    tables_txt += "\n\n"
    
    summary_path = os.path.join(OUTPUT_DIR, 'summary_tables.md')
    with open(summary_path, 'w') as f:
        f.write(tables_txt)
    print(f"Generated: {summary_path}")
    return tables_txt

def main():
    print("Ingesting and standardizing benchmark data...")
    master_df, pairs_df = load_and_standardize()
    print(f"Master runs count: {len(master_df)}")
    print(f"Matched pairs count: {len(pairs_df)}")
    
    master_path = os.path.join(OUTPUT_DIR, 'master_aggregated_results.csv')
    pairs_path = os.path.join(OUTPUT_DIR, 'matched_pairs_speedup.csv')
    
    master_df.to_csv(master_path, index=False)
    pairs_df.to_csv(pairs_path, index=False)
    print(f"Saved: {master_path}")
    print(f"Saved: {pairs_path}")
    
    stats = compute_statistics(pairs_df)
    plot_all(pairs_df, master_df)
    tables_md = generate_markdown_tables(stats, pairs_df)
    print("Aggregation and visualization completed successfully!")

if __name__ == '__main__':
    main()
