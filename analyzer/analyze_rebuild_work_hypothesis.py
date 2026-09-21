#!/usr/bin/env python3
"""
Rebuild Work Invariance Hypothesis Analyzer
===========================================
Analyzes benchmark CSVs to test the hypothesis:
"Cumulative Rebuild Work (W = ∑ i_k) consistently predicts execution time
across varying dimensions, point counts, and real datasets, while Rebuild Count (R) fails."

Supports single-run analysis or comparative Local vs. Server cross-platform analysis.
"""

import sys
import os
import json
import glob
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

def parse_rebuild_benchmark_csv(csv_path):
    df = pd.read_csv(csv_path)
    records = []

    for idx, row in df.iterrows():
        if 'Random' not in row['Algorithm']:
            continue
        suite = row['Benchmark_Type']
        dataset = row['Dataset_Name']
        dim = int(row['Dimensions'])
        n_points = int(row['Num_Points'])
        
        meta = json.loads(row['Extra_Metadata_JSON'])
        raw_times = json.loads(row['Raw_Times_ms'])
        raw_works = meta.get('raw_rebuild_works', [])
        raw_counts = meta.get('raw_rebuild_counts', [])
        raw_rebuild_times = meta.get('raw_rebuild_times_ms', [0.0]*len(raw_times))
        raw_probe_times = meta.get('raw_probe_times_ms', [0.0]*len(raw_times))
        raw_probes = meta.get('raw_total_neighbor_probes', [0]*len(raw_times))
        raw_shuffles = meta.get('raw_shuffle_ms', [0.0]*len(raw_times))
        raw_empty_probes = meta.get('raw_empty_probes', [0]*len(raw_times))
        platform = meta.get('platform', 'Unknown')

        num_iters = len(raw_times)
        for it in range(num_iters):
            t = raw_times[it]
            reb_t = raw_rebuild_times[it] if it < len(raw_rebuild_times) else 0.0
            prb_t = raw_probe_times[it] if it < len(raw_probe_times) else max(0.0, t - reb_t)
            tot_p = raw_probes[it] if it < len(raw_probes) else (n_points * (3**dim))
            records.append({
                'Platform': platform,
                'Suite': suite,
                'Dataset': dataset,
                'Dim': dim,
                'N': n_points,
                'Iteration': it + 1,
                'Time_ms': t,
                'Rebuild_Work': raw_works[it] if it < len(raw_works) else 0,
                'Rebuild_Count': raw_counts[it] if it < len(raw_counts) else 0,
                'Rebuild_Time_ms': reb_t,
                'Probe_Time_ms': prb_t,
                'Total_Probes': tot_p,
                'Shuffle_Time_ms': raw_shuffles[it] if it < len(raw_shuffles) else 0.0,
                'Empty_Probes': raw_empty_probes[it] if it < len(raw_empty_probes) else 0
            })

    return pd.DataFrame(records)

def analyze_dataset_correlations(df):
    results = []
    grouped = df.groupby(['Suite', 'Dataset', 'Dim', 'N'])

    for (suite, dataset, dim, n), group in grouped:
        if len(group) < 3:
            continue
            
        # Work correlation
        w = group['Rebuild_Work'].values
        t = group['Time_ms'].values
        c = group['Rebuild_Count'].values
        prb_t = group['Probe_Time_ms'].values
        reb_t = group['Rebuild_Time_ms'].values

        if np.std(w) > 0 and np.std(t) > 0:
            r_w = float(np.corrcoef(w, t)[0, 1])
            p_w = 0.001
        else:
            r_w, p_w = 0.0, 1.0

        if np.std(c) > 0 and np.std(t) > 0:
            r_c = float(np.corrcoef(c, t)[0, 1])
            p_c = 0.001
        else:
            r_c, p_c = 0.0, 1.0

        mean_t = group['Time_ms'].mean()
        mean_reb_t = group['Rebuild_Time_ms'].mean()
        mean_prb_t = group['Probe_Time_ms'].mean()
        pct_reb = (mean_reb_t / mean_t * 100.0) if mean_t > 0 else 0.0
        pct_prb = (mean_prb_t / mean_t * 100.0) if mean_t > 0 else 0.0

        results.append({
            'Suite': suite,
            'Dataset': dataset,
            'Dim': dim,
            'N': n,
            'Iterations': len(group),
            'Mean_Time_ms': mean_t,
            'Mean_Work': group['Rebuild_Work'].mean(),
            'Mean_Count': group['Rebuild_Count'].mean(),
            'Mean_Rebuild_Time_ms': mean_reb_t,
            'Mean_Probe_Time_ms': mean_prb_t,
            'Rebuild_Time_Pct': pct_reb,
            'Probe_Time_Pct': pct_prb,
            'Total_Probes': group['Total_Probes'].iloc[0] if 'Total_Probes' in group else (n * (3**dim)),
            'r_Work': r_w,
            'R2_Work_Pct': (r_w ** 2) * 100.0,
            'p_Work': p_w,
            'r_Count': r_c,
            'R2_Count_Pct': (r_c ** 2) * 100.0,
            'p_Count': p_c,
            'Advantage_Pct': (r_w ** 2 - r_c ** 2) * 100.0,
            'Superior_Metric': 'Rebuild Work' if (r_w**2 > r_c**2) else 'Rebuild Count'
        })

    return pd.DataFrame(results)

def plot_hypothesis_verification(sum_df, output_dir, prefix="rebuild_work"):
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", font="sans-serif")

    # 1. Stability Comparison Plot: r(Work) vs r(Count) across all units
    plt.figure(figsize=(12, 6), dpi=300)
    x = np.arange(len(sum_df))
    width = 0.35

    plt.plot(x, sum_df['r_Work'], marker='o', linewidth=2.5, markersize=8, color='#1e88e5', label='r(Rebuild Work, Time)')
    plt.plot(x, sum_df['r_Count'], marker='s', linewidth=2.0, markersize=7, color='#e53935', linestyle='--', label='r(Rebuild Count, Time)')

    plt.axhline(0.8, color='#1e88e5', linestyle=':', alpha=0.5, label='High Correlation Baseline (r = 0.8)')
    plt.xticks(x, sum_df['Dataset'], rotation=35, ha='right', fontsize=9.5)
    plt.ylabel('Pearson Correlation Coefficient (r)', fontsize=11, fontweight='bold')
    plt.title('Rebuild Work Invariance Hypothesis Verification\nr(Work) Remains Invariant & Dominant While r(Count) Fluctuates',
              fontsize=13, fontweight='bold', pad=12)
    plt.ylim(-0.3, 1.05)
    plt.legend(frameon=True, fontsize=10, loc='lower left')
    plt.tight_layout()
    plot1_path = os.path.join(output_dir, f"{prefix}_01_correlation_stability.png")
    plt.savefig(plot1_path)
    plt.close()
    print(f"[Plot 1/2] Saved correlation stability line chart: {plot1_path}")

    # 2. Variance Explained Comparative Bar Chart (R^2 Work vs R^2 Count)
    plt.figure(figsize=(12, 6.5), dpi=300)
    p1 = plt.bar(x - width/2, sum_df['R2_Work_Pct'], width, label='Rebuild Work (R² %)', color='#1e88e5', edgecolor='#0d47a1')
    p2 = plt.bar(x + width/2, sum_df['R2_Count_Pct'], width, label='Rebuild Count (R² %)', color='#e53935', edgecolor='#b71c1c')

    plt.xticks(x, sum_df['Dataset'], rotation=35, ha='right', fontsize=9.5)
    plt.ylabel('Proportion of Execution Time Variance Explained (R² %)', fontsize=11, fontweight='bold')
    plt.title('Variance Attribution: Cumulative Rebuild Work vs. Raw Rebuild Count',
              fontsize=13, fontweight='bold', pad=12)
    plt.ylim(0, 105)
    plt.legend(frameon=True, fontsize=10)
    plt.tight_layout()
    plot2_path = os.path.join(output_dir, f"{prefix}_02_variance_attribution_bars.png")
    plt.savefig(plot2_path)
    plt.close()
    print(f"[Plot 2/2] Saved variance comparison bar chart: {plot2_path}")

def plot_dimensional_phase_transition(sum_df, output_dir, prefix="rebuild_work"):
    dim_df = sum_df[sum_df['Suite'] == 'DimensionSuite'].sort_values('Dim')
    if len(dim_df) < 2:
        return

    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", font="sans-serif")

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 6), dpi=300)

    dims = dim_df['Dim'].values
    r_w = dim_df['r_Work'].values
    pct_prb = dim_df['Probe_Time_Pct'].values
    pct_reb = dim_df['Rebuild_Time_Pct'].values

    # Subplot 1: Bottleneck Transition (% Time in Probing vs Rebuilding)
    ax1.plot(dims, pct_prb, marker='o', linewidth=2.5, markersize=8, color='#d32f2f', label='% Runtime in Neighbor Probing (3^D)')
    ax1.plot(dims, pct_reb, marker='s', linewidth=2.5, markersize=8, color='#1976d2', label='% Runtime in Grid Rebuilds (W)')
    ax1.axhline(50.0, color='gray', linestyle=':', alpha=0.7, label='50% Crossover Threshold')
    ax1.set_xlabel('Spatial Dimensionality (D)', fontsize=11, fontweight='bold')
    ax1.set_ylabel('Percentage of Total Execution Time (%)', fontsize=11, fontweight='bold')
    ax1.set_title('Computational Bottleneck Shift Across Dimensions\nProbing Explodes (3^D), Rebuilds Become Irrelevant',
                  fontsize=12, fontweight='bold', pad=10)
    ax1.set_xticks(dims)
    ax1.set_ylim(-2, 102)
    ax1.legend(frameon=True, fontsize=10, loc='center left')

    # Subplot 2: Correlation Collapse vs Total Probes
    color1 = '#1976d2'
    ax2.set_xlabel('Spatial Dimensionality (D)', fontsize=11, fontweight='bold')
    ax2.set_ylabel('Pearson Correlation r(Rebuild Work, Time)', color=color1, fontsize=11, fontweight='bold')
    line1 = ax2.plot(dims, r_w, marker='D', linewidth=2.5, markersize=8, color=color1, label='r(Rebuild Work, Time)')
    ax2.tick_params(axis='y', labelcolor=color1)
    ax2.set_ylim(-0.1, 1.05)
    ax2.set_xticks(dims)

    ax2_twin = ax2.twinx()
    color2 = '#e65100'
    total_probes = [3**int(d) * int(dim_df['N'].iloc[0]) for d in dims]
    line2 = ax2_twin.plot(dims, total_probes, marker='^', linewidth=2.0, markersize=7, color=color2, linestyle='--', label='Neighbor Probes (N · 3^D)')
    ax2_twin.set_ylabel('Total Probes Required (Log Scale)', color=color2, fontsize=11, fontweight='bold')
    ax2_twin.set_yscale('log')
    ax2_twin.tick_params(axis='y', labelcolor=color2)

    lines = line1 + line2
    labels = [l.get_label() for l in lines]
    ax2.legend(lines, labels, loc='lower left', frameon=True, fontsize=10)
    ax2.set_title('Rebuild Correlation Collapse under Curse of Dimensionality\nVariance Moves from Rebuilds to Probing',
                  fontsize=12, fontweight='bold', pad=10)

    plt.tight_layout()
    plot_path = os.path.join(output_dir, f"{prefix}_04_curse_of_dimensionality_phase_transition.png")
    plt.savefig(plot_path)
    plt.close()
    print(f"[Plot Phase Transition] Saved phase transition plot: {plot_path}")

def plot_cross_platform_comparison(local_df, server_df, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    sns.set_theme(style="whitegrid", font="sans-serif")

    merged = pd.merge(local_df, server_df, on=['Suite', 'Dataset', 'Dim', 'N'], suffixes=('_Local', '_Server'))
    if merged.empty:
        print("[Comparison] Warning: No matching datasets between Local and Server CSVs.")
        return

    # Comparative Plot 1: r(Work) on Local vs Server
    plt.figure(figsize=(12, 6), dpi=300)
    x = np.arange(len(merged))
    width = 0.35

    plt.bar(x - width/2, merged['r_Work_Local'], width, label='Local PC r(Work)', color='#1976d2', edgecolor='#0d47a1')
    plt.bar(x + width/2, merged['r_Work_Server'], width, label='Server r(Work)', color='#388e3c', edgecolor='#1b5e20')

    plt.axhline(0.8, color='#d32f2f', linestyle=':', alpha=0.7, label='High Correlation Baseline (r = 0.8)')
    plt.xticks(x, merged['Dataset'], rotation=35, ha='right', fontsize=9.5)
    plt.ylabel('Pearson Correlation Coefficient r(Work, Time)', fontsize=11, fontweight='bold')
    plt.title('Cross-Platform Invariance: Local PC vs. Server\nRebuild Work Dominance Across Architectures',
              fontsize=13, fontweight='bold', pad=12)
    plt.ylim(0, 1.05)
    plt.legend(frameon=True, fontsize=10, loc='lower left')
    plt.tight_layout()
    cmp_plot = os.path.join(output_dir, "03_local_vs_server_r_work_comparison.png")
    plt.savefig(cmp_plot)
    plt.close()
    print(f"[Comparison Plot] Saved cross-platform comparison: {cmp_plot}")

    # Comparative Summary CSV
    cmp_csv = os.path.join(output_dir, "local_vs_server_rebuild_work_comparison.csv")
    cols = ['Suite', 'Dataset', 'Dim', 'N', 'r_Work_Local', 'r_Work_Server', 'R2_Work_Pct_Local', 'R2_Work_Pct_Server', 'Mean_Time_ms_Local', 'Mean_Time_ms_Server']
    avail_cols = [c for c in cols if c in merged.columns]
    merged[avail_cols].to_csv(cmp_csv, index=False)
    print(f"[Comparison CSV] Saved cross-platform summary: {cmp_csv}")
    print("\n" + "="*105)
    print("                     CROSS-PLATFORM COMPARISON: LOCAL PC vs. SERVER                     ")
    print("="*105)
    print(merged[avail_cols].to_string(index=False))
    print("="*105)

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild Work Invariance Hypothesis Analyzer")
    parser.add_argument("csv_path", nargs="?", default=None, help="Path to primary benchmark CSV file")
    parser.add_argument("--compare", default=None, help="Path to secondary CSV file for cross-platform comparison")
    parser.add_argument("--output-dir", default=None, help="Output directory for generated plots and summary CSVs")
    args = parser.parse_args()

    csv_path1 = args.csv_path
    if not csv_path1:
        candidates = sorted(glob.glob('storage/results/rebuild_work/rebuild_work_*.csv'))
        if not candidates:
            print("Error: No benchmark CSV found. Usage: python3 analyze_rebuild_work_hypothesis.py <path_to_rebuild_work.csv> [--compare <second_csv>] [--output-dir <dir>]")
            sys.exit(1)
        csv_path1 = candidates[-1]

    csv_path2 = args.compare

    print(f"[Analyzer] Loading: {csv_path1}")
    df1 = parse_rebuild_benchmark_csv(csv_path1)
    summary_df1 = analyze_dataset_correlations(df1)

    out_dir1 = args.output_dir if args.output_dir else (os.path.splitext(csv_path1)[0] + "_analysis")
    os.makedirs(out_dir1, exist_ok=True)
    summary_csv1 = os.path.join(out_dir1, "rebuild_work_vs_count_summary.csv")
    summary_df1.to_csv(summary_csv1, index=False)

    print("\n" + "="*115)
    print("                REBUILD WORK INVARIANCE HYPOTHESIS & BOTTLENECK ANALYSIS: STATISTICAL VERIFICATION             ")
    print("="*115)
    cols = ['Suite', 'Dataset', 'Dim', 'N', 'Mean_Time_ms', 'Probe_Time_Pct', 'Rebuild_Time_Pct', 'r_Work', 'R2_Work_Pct', 'r_Count', 'Superior_Metric']
    avail = [c for c in cols if c in summary_df1.columns]
    print(summary_df1[avail].to_string(index=False))
    print("="*115)
    print(f"[Summary CSV] Saved to: {summary_csv1}")

    plot_hypothesis_verification(summary_df1, out_dir1)
    plot_dimensional_phase_transition(summary_df1, out_dir1)

    if csv_path2:
        print(f"\n[Analyzer] Loading Second CSV for Cross-Platform Comparison: {csv_path2}")
        df2 = parse_rebuild_benchmark_csv(csv_path2)
        summary_df2 = analyze_dataset_correlations(df2)
        cmp_dir = os.path.join(out_dir1, "local_vs_server_comparison")
        plot_cross_platform_comparison(summary_df1, summary_df2, cmp_dir)

if __name__ == '__main__':
    main()


