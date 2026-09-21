#!/usr/bin/env bash
#!/usr/bin/env python3
"""
Comprehensive Suspects Correlation Analyzer & Visualizer
=========================================================
Parses per-iteration metrics from OpenSky benchmark CSV:
- Suspect 1: Rebuild Work (Points Re-hashed, ∑ i_k)
- Suspect 2: Non-Empty Neighbor Cell Hits
- Suspect 3: 4D Euclidean Distance Evaluations
- Suspect 4: Randomization Shuffle Latency (ms)
- Suspect 5: Peak Occupied Cells (Hash Map Size / Cache Footprint)
Plus: Raw Rebuild Count

Outputs:
1. Full annotated Correlation Matrix Heatmap (300 DPI PNG)
2. Multi-panel Scatter Plot with Linear Regression Fits (300 DPI PNG)
3. Variance Explained (R^2) Bar Chart (300 DPI PNG)
4. Summary CSV with r, R^2, and statistical conclusions
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

def parse_benchmark_csv(csv_path):
    df = pd.read_csv(csv_path)
    records = []

    for idx, row in df.iterrows():
        algo = row['Algorithm']
        dataset = row['Dataset_Name']
        hour_label = dataset.replace('states_2019-05-27-', 'Hour ').replace('_4d', '')
        n_points = int(row['Num_Points'])
        
        meta = json.loads(row['Extra_Metadata_JSON'])
        raw_times = json.loads(row['Raw_Times_ms'])
        raw_works = meta.get('raw_rebuild_works', [])
        raw_hits = meta.get('raw_cell_hits', [])
        raw_evals = meta.get('raw_dist_evals', [])
        raw_shuffles = meta.get('raw_shuffle_ms', [0.0] * len(raw_times))
        peak_cells = meta.get('mean_peak_cells', n_points)
        mean_rebuilds = row['Mean_Rebuilds']
        
        num_iters = len(raw_times)
        for it in range(num_iters):
            records.append({
                'Dataset': dataset,
                'Hour': hour_label,
                'Algorithm': algo,
                'Iteration': it + 1,
                'Num_Points': n_points,
                'Time_ms': raw_times[it],
                'Time_s': raw_times[it] / 1000.0,
                'Rebuild_Work_Points': raw_works[it] if it < len(raw_works) else 0,
                'Rebuild_Work_M': (raw_works[it] if it < len(raw_works) else 0) / 1e6,
                'Rebuild_Count': mean_rebuilds,
                'Cell_Hits': raw_hits[it] if it < len(raw_hits) else 0,
                'Dist_Evals': raw_evals[it] if it < len(raw_evals) else 0,
                'Shuffle_Time_ms': raw_shuffles[it] if it < len(raw_shuffles) else 0.0,
                'Peak_Occupied_Cells': peak_cells
            })

    return pd.DataFrame(records)

def main():
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        candidates = sorted(glob.glob('refactored/storage/results/opensky/opensky_benchmark_*.csv'))
        if not candidates:
            candidates = sorted(glob.glob('storage/results/opensky/opensky_benchmark_*.csv'))
        if not candidates:
            print("Error: No benchmark CSV files found.")
            sys.exit(1)
        csv_path = candidates[-1]

    print(f"[Analyzer] Loading: {csv_path}")
    df_all = parse_benchmark_csv(csv_path)
    
    # Focus on Randomized Grid for multi-iteration variation (where random shuffle introduces variance)
    df_rand = df_all[df_all['Algorithm'] == 'Randomized Grid'].copy()
    if df_rand.empty:
        df_rand = df_all.copy()

    base_name = os.path.splitext(os.path.basename(csv_path))[0]
    output_dir = os.path.join(os.path.dirname(csv_path), f"{base_name}_analysis")
    os.makedirs(output_dir, exist_ok=True)
    print(f"[Analyzer] Output Directory: {output_dir}")

    sns.set_theme(style="whitegrid", font="sans-serif")
    palette = sns.color_palette("tab10", n_colors=df_rand['Hour'].nunique())
    hours = sorted(df_rand['Hour'].unique())

    # -------------------------------------------------------------
    # 1. Multi-Variable Correlation Matrix
    # -------------------------------------------------------------
    feature_cols = [
        'Time_s',
        'Rebuild_Work_M',
        'Cell_Hits',
        'Dist_Evals',
        'Shuffle_Time_ms',
        'Peak_Occupied_Cells'
    ]
    
    labels = [
        'Execution Time (s)',
        'Rebuild Work (M pts)',
        'Cell Hits (Suspect 2)',
        'Distance Evals (Suspect 3)',
        'Shuffle Time (Suspect 4)',
        'Peak Cells (Suspect 5)'
    ]

    corr_df = df_rand[feature_cols].corr()
    corr_df.columns = labels
    corr_df.index = labels

    plt.figure(figsize=(9, 7.5), dpi=300)
    sns.heatmap(corr_df, annot=True, fmt=".3f", cmap="vlag", vmin=-1, vmax=1,
                cbar_kws={'label': 'Pearson Correlation Coefficient (r)'},
                linewidths=1, linecolor='#e0e0e0', annot_kws={"size": 11, "weight": "bold"})
    plt.title("Correlation Matrix of Heavy Loader Suspects vs. Execution Time\n(OpenSky 4D Telemetry, 30 Iterations per Hour)",
              fontsize=13, fontweight='bold', pad=15)
    plt.tight_layout()
    heatmap_path = os.path.join(output_dir, "01_suspects_correlation_heatmap.png")
    plt.savefig(heatmap_path)
    plt.close()
    print(f"[1/4] Saved heatmap: {heatmap_path}")

    # -------------------------------------------------------------
    # 2. Multi-Panel Scatter Plots with Regression Fits
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    fig, axes = plt.subplots(2, 3, figsize=(18, 11), dpi=300)
    axes = axes.flatten()

    suspects_info = [
        ('Rebuild_Work_M', 'Rebuild Work ($W = \\sum i_k$) [Millions of Points]', 'Suspect 1: Points Re-hashed', '#1e88e5'),
        ('Peak_Occupied_Cells', 'Peak Occupied Cells (Hash Table Footprint)', 'Suspect 5: Hash Table Size', '#d81b60'),
        ('Shuffle_Time_ms', 'Shuffle Duration (ms)', 'Suspect 4: Permutation Latency', '#8e24aa'),
        ('Cell_Hits', 'Non-Empty Cell Hits (Probes dereferencing data)', 'Suspect 2: Neighbor Cell Hits', '#43a047'),
        ('Dist_Evals', 'Pairwise Distance Calculations performed', 'Suspect 3: 4D Distance Checks', '#fb8c00')
    ]

    summary_stats = []

    for idx, (col, xlabel, title, line_color) in enumerate(suspects_info):
        ax = axes[idx]
        for h_idx, h in enumerate(hours):
            sub = df_rand[df_rand['Hour'] == h]
            ax.scatter(sub[col], sub['Time_s'], label=h, color=palette[h_idx], alpha=0.75, s=40, edgecolors='none')

        # Fit line using pure numpy
        valid = df_rand[[col, 'Time_s']].dropna()
        if valid[col].std() > 0:
            poly = np.polyfit(valid[col], valid['Time_s'], 1)
            slope, intercept = poly[0], poly[1]
            r_val = float(np.corrcoef(valid[col], valid['Time_s'])[0, 1])
        else:
            slope, intercept = 0.0, float(valid['Time_s'].mean())
            r_val = 0.0
        r2 = r_val ** 2
        
        summary_stats.append({
            'Suspect': title.split(':')[0].strip(),
            'Feature': col,
            'Description': title.split(':')[1].strip(),
            'Pearson_r': round(r_val, 4),
            'R_Squared': round(r2, 4),
            'Variance_Pct': round(r2 * 100.0, 2),
            'Slope': slope,
            'Intercept_Baseline_s': intercept
        })

        x_vals = np.linspace(valid[col].min(), valid[col].max(), 100)
        ax.plot(x_vals, slope * x_vals + intercept, color=line_color, linestyle='--', linewidth=2.2,
                label=f'Linear Fit: r = {r_val:.3f} (R² = {r2*100:.1f}%)')

        ax.set_title(f"{title}\nr = {r_val:.4f} (Explains {r2*100:.1f}% of variance)",
                     fontsize=11, fontweight='bold', pad=8)
        ax.set_xlabel(xlabel, fontsize=10)
        ax.set_ylabel("Execution Time (seconds)", fontsize=10)
        ax.legend(frameon=True, fontsize=8.5, loc='upper left')

    # Hide unused 6th subplot
    axes[5].set_visible(False)

    plt.tight_layout()
    scatter_path = os.path.join(output_dir, "02_suspects_scatter_regression.png")
    plt.savefig(scatter_path)
    plt.close()
    print(f"[2/4] Saved scatter regression panels: {scatter_path}")

    # -------------------------------------------------------------
    # 3. Variance Explained (R^2) Bar Chart
    # -------------------------------------------------------------
    sum_df = pd.DataFrame(summary_stats).sort_values(by='R_Squared', ascending=False)
    
    plt.figure(figsize=(9, 5), dpi=300)
    bars = plt.barh(sum_df['Description'], sum_df['Variance_Pct'], color='#1976d2', edgecolor='#0d47a1', height=0.55)
    plt.xlabel('Proportion of Execution Time Variance Explained ($R^2$ %)', fontsize=11, fontweight='bold')
    plt.title('Attribution of Algorithmic Heavy Loaders on Runtime Variance\n(Coefficient of Determination $R^2$)',
              fontsize=12, fontweight='bold', pad=12)
    plt.xlim(0, 100)

    for bar in bars:
        w = bar.get_width()
        plt.text(w + 1.5, bar.get_y() + bar.get_height() / 2, f"{w:.1f}%",
                 ha='left', va='center', fontsize=10, fontweight='bold', color='#1a237e')

    plt.gca().invert_yaxis()
    plt.tight_layout()
    bar_path = os.path.join(output_dir, "03_suspects_variance_explained.png")
    plt.savefig(bar_path)
    plt.close()
    print(f"[3/4] Saved variance attribution bar chart: {bar_path}")

    # -------------------------------------------------------------
    # 4. Save Summary CSV
    # -------------------------------------------------------------
    summary_csv = os.path.join(output_dir, "suspects_correlation_summary.csv")
    sum_df.to_csv(summary_csv, index=False)
    print(f"[4/4] Saved summary statistics table: {summary_csv}")
    print("\n" + "="*80)
    print("                      HEAVY LOADERS CORRELATION SUMMARY                         ")
    print("="*80)
    print(sum_df[['Suspect', 'Description', 'Pearson_r', 'Variance_Pct']].to_string(index=False))
    print("="*80)

if __name__ == '__main__':
    main()
