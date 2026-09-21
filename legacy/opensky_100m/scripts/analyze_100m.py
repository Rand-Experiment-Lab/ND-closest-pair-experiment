#!/usr/bin/env python3
"""
OpenSky 100M Results Analyzer & Visualizer
=========================================
Generates comprehensive performance analytics, distribution bell curves,
and executive reports for the 100M benchmark.
"""

import sys
import os
import ast
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid", font_scale=1.1)
plt.rcParams['font.sans-serif'] = 'DejaVu Sans'

def parse_raw_array(val):
    if pd.isna(val):
        return []
    if isinstance(val, list):
        return val
    try:
        return ast.literal_eval(str(val).strip())
    except Exception:
        try:
            cleaned = str(val).strip(' "[]')
            return [float(x.strip()) for x in cleaned.split(',') if x.strip()]
        except Exception:
            return []

def df_to_markdown(df, index=False):
    try:
        return df.to_markdown(index=index)
    except Exception:
        table_df = df.reset_index() if index else df.copy()
        if isinstance(table_df.columns, pd.MultiIndex):
            table_df.columns = ['_'.join(str(c) for c in col if str(c)).strip('_') for col in table_df.columns.values]
        headers = [str(c) for c in table_df.columns]
        rows = [[str(val) for val in row] for row in table_df.values]
        widths = [max(len(h), max((len(r[i]) for r in rows), default=0)) for i, h in enumerate(headers)]
        header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
        sep_line = "| " + " | ".join("-" * widths[i] for i in range(len(headers))) + " |"
        body_lines = ["| " + " | ".join(row[i].ljust(widths[i]) for i, h in enumerate(headers)) + " |" for row in rows]
        return "\n".join([header_line, sep_line] + body_lines)

def analyze(csv_path, output_dir=None):
    if not os.path.isfile(csv_path):
        print(f"[Error] File not found: {csv_path}")
        sys.exit(1)

    csv_path = os.path.abspath(csv_path)
    csv_dir = os.path.dirname(csv_path)
    csv_filename = os.path.basename(csv_path)
    csv_name_no_ext = os.path.splitext(csv_filename)[0]

    if output_dir is None:
        output_dir = os.path.join(csv_dir, csv_name_no_ext)

    os.makedirs(output_dir, exist_ok=True)
    print(f"\n[Analyzer] Loading dataset: {csv_path}")
    print(f"[Analyzer] Output directory: {output_dir}")

    df = pd.read_csv(csv_path)
    if df.empty:
        print("[Error] CSV file is empty!")
        sys.exit(1)

    df['Mean_Time_s'] = df['Mean_Time_ms'] / 1000.0
    df['Median_Time_s'] = df['Median_Time_ms'] / 1000.0
    df['StdDev_Time_s'] = df['StdDev_Time_ms'] / 1000.0

    generated_files = []

    # 1. Execution Time Comparison Barplot
    plt.figure(figsize=(9, 5))
    ax = sns.barplot(
        data=df,
        x='Algorithm',
        y='Mean_Time_s',
        palette='tab10',
        edgecolor='black',
        alpha=0.85
    )
    for p in ax.patches:
        height = p.get_height()
        if not np.isnan(height):
            ax.annotate(f"{height:.1f} s\n({height/60.0:.2f} min)",
                        (p.get_x() + p.get_width() / 2., height / 2.),
                        ha='center', va='center', fontsize=11, fontweight='bold', color='white',
                        bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="none", alpha=0.6))

    plt.title(f"100M OpenSky Closest Pair Execution Time (Original Order)\n({csv_filename})", fontsize=13, fontweight='bold', pad=12)
    plt.xlabel("Algorithm Variant", fontweight='bold')
    plt.ylabel("Mean Execution Time (seconds)", fontweight='bold')
    plt.tight_layout()
    f1 = os.path.join(output_dir, "fig1_execution_time.png")
    plt.savefig(f1, dpi=300)
    plt.close()
    generated_files.append(f1)

    # 2. Rebuild Counts Comparison
    plt.figure(figsize=(9, 5))
    ax2 = sns.barplot(
        data=df,
        x='Algorithm',
        y='Mean_Rebuilds',
        palette='viridis',
        edgecolor='black',
        alpha=0.85
    )
    for p in ax2.patches:
        h = p.get_height()
        if not np.isnan(h):
            ax2.annotate(f"{h:.1f} rebuilds",
                         (p.get_x() + p.get_width() / 2., h / 2.),
                         ha='center', va='center', fontsize=11, fontweight='bold', color='white',
                         bbox=dict(boxstyle="round,pad=0.3", fc="black", ec="none", alpha=0.6))

    plt.title(f"Hash Grid Rebuild Counts Across 100M Points\n({csv_filename})", fontsize=13, fontweight='bold', pad=12)
    plt.xlabel("Algorithm Variant", fontweight='bold')
    plt.ylabel("Average Rebuild Count", fontweight='bold')
    plt.tight_layout()
    f2 = os.path.join(output_dir, "fig2_rebuild_counts.png")
    plt.savefig(f2, dpi=300)
    plt.close()
    generated_files.append(f2)

    # 3. Distribution Graph & Bell Curve Fitting
    normality_stats = []
    if 'Raw_Times_ms' in df.columns:
        fig, axes = plt.subplots(1, 2, figsize=(16, 6))
        fig.suptitle(f"100M Telemetry Iteration Distributions & Gaussian Bell Curves\n({csv_filename})",
                     fontsize=15, fontweight='bold', y=0.98)

        algos = df['Algorithm'].unique()
        for idx, algo in enumerate(algos):
            ax = axes[idx]
            df_a = df[df['Algorithm'] == algo]
            raw_t = []
            for _, r in df_a.iterrows():
                raw_t.extend(parse_raw_array(r.get('Raw_Times_ms', [])))

            arr = np.array(raw_t) / 1000.0  # seconds
            if len(arr) > 1:
                mu, sig = float(np.mean(arr)), max(float(np.std(arr, ddof=1)), 1e-6)
                med = float(np.median(arr))
                skew = float(np.mean((arr - mu)**3) / (sig**3))
                kurt = float((np.mean((arr - mu)**4) / (sig**4)) - 3.0)
                norm_status = "Approx. Normal (Bell-shaped)" if abs(skew) < 0.75 else ("Right-skewed" if skew > 0 else "Left-skewed")

                normality_stats.append({
                    'Algorithm': algo,
                    'Sample_Count': len(arr),
                    'Mean_Seconds': f"{mu:.2f} s",
                    'StdDev_Seconds': f"{sig:.2f} s",
                    'Median_Seconds': f"{med:.2f} s",
                    'Skewness': f"{skew:+.2f}",
                    'Excess_Kurtosis': f"{kurt:+.2f}",
                    'Profile': norm_status
                })

                color = '#1f77b4' if idx == 0 else '#ff7f0e'
                sns.histplot(arr, stat='density', kde=True, ax=ax, color=color, edgecolor='black', alpha=0.45, label='Empirical (Hist + KDE)')
                x_pts = np.linspace(min(arr) - 0.8 * sig, max(arr) + 0.8 * sig, 250)
                bell = (1.0 / (sig * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_pts - mu) / sig)**2)
                ax.plot(x_pts, bell, 'r--', lw=2.5, label=rf"Gaussian Bell $N(\mu={mu:.1f}, \sigma={sig:.1f})$")
                ax.axvline(mu, color='green', linestyle='-', lw=2, label=rf"Mean $\mu$ ({mu:.1f}s)")
                ax.axvline(med, color='purple', linestyle=':', lw=2, label=rf"Median ({med:.1f}s)")

                stats_box = (f"N = {len(arr)}\n"
                             rf"$\mu$ = {mu:.2f} s" + "\n"
                             rf"$\sigma$ = {sig:.2f} s" + "\n"
                             rf"Median = {med:.2f} s" + "\n"
                             rf"Skew = {skew:+.2f}" + "\n"
                             rf"Kurt = {kurt:+.2f}" + "\n"
                             f"Shape: {norm_status}")
                ax.text(0.97, 0.95, stats_box, transform=ax.transAxes, verticalalignment='top', horizontalalignment='right',
                        bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray'), fontsize=9)
                ax.set_title(f"{algo} - Execution Distribution", fontweight='bold', fontsize=12)
                ax.set_xlabel("Execution Time (seconds)", fontweight='bold')
                ax.set_ylabel("Probability Density", fontweight='bold')
                ax.legend(loc='upper left', fontsize=8)

        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        f3 = os.path.join(output_dir, "fig3_distribution_Original.png")
        plt.savefig(f3, dpi=300)
        plt.close()
        generated_files.append(f3)

    # 4. Summary Report
    rep_path = os.path.join(output_dir, "summary_report.md")
    with open(rep_path, 'w') as f_rep:
        f_rep.write("# OpenSky 100-Million 4D Closest Pair Report\n\n")
        f_rep.write(f"- **Dataset:** `{df['Dataset'].iloc[0]}`\n")
        f_rep.write(f"- **Points Evaluated:** `{df['Num_Points'].iloc[0]:,}`\n")
        f_rep.write(f"- **Input Ordering:** `Original Sequence (Temporal ADS-B Ingestion)`\n")
        f_rep.write(f"- **Minimum Separation Filter:** `{df['Min_Separation_m'].iloc[0]} meters`\n")
        f_rep.write(f"- **Closest Encounter Distance:** `{df['Min_Distance_m'].min():.3f} meters`\n\n")
        f_rep.write("---\n\n## Performance Summary\n\n")

        disp_cols = ['Algorithm', 'Iterations', 'Mean_Time_s', 'Median_Time_s', 'StdDev_Time_s', 'Mean_Rebuilds', 'Min_Distance_m']
        f_rep.write(df_to_markdown(df[[c for c in disp_cols if c in df.columns]], index=False))
        f_rep.write("\n")

        if normality_stats:
            f_rep.write("\n---\n\n## Distribution Profile & Normality Diagnostics\n\n")
            f_rep.write(df_to_markdown(pd.DataFrame(normality_stats), index=False))
            f_rep.write("\n")

    generated_files.append(rep_path)

    print(f"\n[Done] Analysis completed successfully!")
    print(f"  Destination Folder: {output_dir}")
    print(f"  Generated Assets ({len(generated_files)}):")
    for g in generated_files:
        print(f"    - {os.path.basename(g)}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_100m.py <path_to_csv> [output_dir]")
        sys.exit(1)
    analyze(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
