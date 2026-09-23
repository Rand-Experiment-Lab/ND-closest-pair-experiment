#!/usr/bin/env python3
"""
OpenSky Experiment Results Analyzer & Visualizer
=================================================
Reads any closest-pair benchmark result CSV (hourly, batch, or full-day),
creates a dedicated output folder named after the CSV file, and generates:
1. fig1_execution_time_comparison.png (Mean/Median execution times with error bars)
2. fig2_rebuild_counts.png (Hash grid rebuild counts & variance)
3. fig3_speedup_and_overhead.png (Speedup ratios and order comparison)
4. fig4_scaling_vs_points.png (Execution time vs. number of points)
5. fig5_closest_distance_consistency.png (Closest physical encounter distance)
6. fig6_raw_iterations_distribution.png (Boxplots of all iteration runs)
7. summary_report.md (Full executive summary and statistical table)
"""

import sys
import os
import ast
import json
import argparse
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

def analyze_and_plot(csv_path, output_dir=None):
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

    print(f"[Analyzer] Successfully loaded {len(df)} records.")

    # Harmonize identifier column (Hour_Tag or Dataset)
    if 'Hour_Tag' in df.columns:
        id_col = 'Hour_Tag'
    elif 'Dataset' in df.columns:
        id_col = 'Dataset'
    else:
        df['Scenario_ID'] = [f"Run_{i+1}" for i in range(len(df))]
        id_col = 'Scenario_ID'

    # Combine Order + Algorithm for clean legend labels
    order_col = 'Input_Order' if 'Input_Order' in df.columns else 'Order'
    algo_col = 'Algorithm' if 'Algorithm' in df.columns else 'Algo'

    df['Test_Case'] = df[order_col].astype(str) + " - " + df[algo_col].astype(str)
    df['Mean_Time_s'] = df['Mean_Time_ms'] / 1000.0
    df['Median_Time_s'] = df['Median_Time_ms'] / 1000.0
    df['StdDev_Time_s'] = df['StdDev_Time_ms'] / 1000.0

    generated_files = []

    # -------------------------------------------------------------
    # 1. Execution Time Comparison
    # -------------------------------------------------------------
    plt.figure(figsize=(12, 6))
    ax = sns.barplot(
        data=df,
        x=id_col,
        y='Mean_Time_ms',
        hue='Test_Case',
        palette='tab10',
        edgecolor='black',
        alpha=0.88
    )
    plt.title(f"Closest Pair Execution Time Comparison\n({csv_filename})", fontsize=14, fontweight='bold', pad=12)
    plt.xlabel("Surveillance Interval / Dataset", fontweight='bold')
    plt.ylabel("Mean Execution Time (ms)", fontweight='bold')
    if len(df[id_col].unique()) > 6:
        plt.xticks(rotation=45, ha='right', fontsize=9)
    plt.legend(title="Test Scenario", bbox_to_anchor=(1.02, 1), loc='upper left')
    plt.tight_layout()
    f1 = os.path.join(output_dir, "fig1_execution_time_comparison.png")
    plt.savefig(f1, dpi=300)
    plt.close()
    generated_files.append(f1)

    # -------------------------------------------------------------
    # 2. Hash Grid Rebuild Counts
    # -------------------------------------------------------------
    if 'Mean_Rebuilds' in df.columns:
        plt.figure(figsize=(12, 6))
        ax = sns.barplot(
            data=df,
            x=id_col,
            y='Mean_Rebuilds',
            hue='Test_Case',
            palette='viridis',
            edgecolor='black',
            alpha=0.88
        )
        plt.title(f"Hash Grid Rebuild Counts Across Test Scenarios\n({csv_filename})", fontsize=14, fontweight='bold', pad=12)
        plt.xlabel("Surveillance Interval / Dataset", fontweight='bold')
        plt.ylabel("Average Grid Rebuilds", fontweight='bold')
        if len(df[id_col].unique()) > 6:
            plt.xticks(rotation=45, ha='right', fontsize=9)
        plt.legend(title="Test Scenario", bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.tight_layout()
        f2 = os.path.join(output_dir, "fig2_rebuild_counts.png")
        plt.savefig(f2, dpi=300)
        plt.close()
        generated_files.append(f2)

    # -------------------------------------------------------------
    # 3. Execution Time vs. Number of Points (Scaling)
    # -------------------------------------------------------------
    if 'Num_Points' in df.columns and len(df['Num_Points'].unique()) > 1:
        plt.figure(figsize=(10, 6))
        sns.scatterplot(
            data=df,
            x='Num_Points',
            y='Mean_Time_ms',
            hue='Test_Case',
            style=algo_col,
            s=100,
            palette='tab10'
        )
        plt.title(f"Empirical Time Scaling vs Dataset Size (N Points)\n({csv_filename})", fontsize=14, fontweight='bold', pad=12)
        plt.xlabel("Total 4D Radar Points (N)", fontweight='bold')
        plt.ylabel("Mean Execution Time (ms)", fontweight='bold')
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.tight_layout()
        f3 = os.path.join(output_dir, "fig3_scaling_vs_points.png")
        plt.savefig(f3, dpi=300)
        plt.close()
        generated_files.append(f3)

    # -------------------------------------------------------------
    # 4. Closest Physical Encounter Distance Consistency
    # -------------------------------------------------------------
    if 'Min_Distance_m' in df.columns:
        plt.figure(figsize=(12, 5))
        ax = sns.lineplot(
            data=df,
            x=id_col,
            y='Min_Distance_m',
            hue='Test_Case',
            marker='o',
            linewidth=2,
            palette='Set1'
        )
        plt.title(f"Minimum 4D Separation Distance Consistency Across Scenarios\n({csv_filename})", fontsize=14, fontweight='bold', pad=12)
        plt.xlabel("Surveillance Interval / Dataset", fontweight='bold')
        plt.ylabel("Minimum 4D Distance (meters)", fontweight='bold')
        if len(df[id_col].unique()) > 6:
            plt.xticks(rotation=45, ha='right', fontsize=9)
        plt.legend(bbox_to_anchor=(1.02, 1), loc='upper left')
        plt.tight_layout()
        f4 = os.path.join(output_dir, "fig4_closest_distance_consistency.png")
        plt.savefig(f4, dpi=300)
        plt.close()
        generated_files.append(f4)

    # -------------------------------------------------------------
    # 5. Raw Iteration Time Distributions (Boxplots)
    # -------------------------------------------------------------
    if 'Raw_Times_ms' in df.columns:
        box_data = []
        for _, row in df.iterrows():
            raw_list = parse_raw_array(row['Raw_Times_ms'])
            test_tag = f"{row[id_col]}\n{row['Test_Case']}" if len(df) <= 8 else row['Test_Case']
            for val in raw_list:
                box_data.append({
                    'Scenario': test_tag,
                    'Test_Case': row['Test_Case'],
                    'Interval': row[id_col],
                    'Iteration_Time_ms': val
                })

        if box_data:
            df_box = pd.DataFrame(box_data)
            plt.figure(figsize=(12, 6))
            sns.boxplot(
                data=df_box,
                x='Test_Case',
                y='Iteration_Time_ms',
                hue='Test_Case',
                legend=False,
                palette='pastel',
                fliersize=3
            )
            plt.title(f"Run-to-Run Variance Across 10 Iterations\n({csv_filename})", fontsize=14, fontweight='bold', pad=12)
            plt.xlabel("Test Scenario", fontweight='bold')
            plt.ylabel("Iteration Execution Time (ms)", fontweight='bold')
            plt.xticks(rotation=15, ha='right')
            plt.tight_layout()
            f5 = os.path.join(output_dir, "fig5_raw_iterations_distribution.png")
            plt.savefig(f5, dpi=300)
            plt.close()
            generated_files.append(f5)

    # -------------------------------------------------------------
    # 6. Empirical and Theoretical Normal Distribution (Bell Curves) per Input Order
    # -------------------------------------------------------------
    normality_stats = []
    if 'Raw_Times_ms' in df.columns:
        unique_orders = df[order_col].unique()
        for order_val in unique_orders:
            df_order = df[df[order_col] == order_val]
            order_clean = str(order_val).replace(' ', '_').replace('/', '_')
            plot_name = f"fig6_distribution_{order_clean}.png"
            plot_path = os.path.join(output_dir, plot_name)

            algos = df_order[algo_col].unique()
            fig, axes = plt.subplots(2, 2, figsize=(16, 12))
            fig.suptitle(f"Empirical & Theoretical Normal Distributions - Input Order: {order_val}\n({csv_filename})",
                         fontsize=15, fontweight='bold', y=0.98)

            # Determine scaling
            all_raw = []
            for _, r in df_order.iterrows():
                all_raw.extend(parse_raw_array(r.get('Raw_Times_ms', [])))
            scale = 1000.0 if (len(all_raw) > 0 and np.mean(all_raw) >= 1000.0) else 1.0
            unit = "s" if scale == 1000.0 else "ms"

            # 1. Algorithm 1
            algo1 = algos[0] if len(algos) > 0 else 'Algorithm 1'
            df_a1 = df_order[df_order[algo_col] == algo1]
            t1 = []
            for _, r in df_a1.iterrows():
                t1.extend(parse_raw_array(r.get('Raw_Times_ms', [])))
            t1 = np.array(t1)
            t1_scaled = t1 / scale if len(t1) > 0 else np.array([])

            ax1 = axes[0, 0]
            if len(t1_scaled) > 1:
                mu1, sig1 = float(np.mean(t1_scaled)), max(float(np.std(t1_scaled, ddof=1)), 1e-6)
                med1 = float(np.median(t1_scaled))
                skew1 = float(np.mean((t1_scaled - mu1)**3) / (sig1**3))
                kurt1 = float((np.mean((t1_scaled - mu1)**4) / (sig1**4)) - 3.0)
                norm_status1 = "Approx. Normal (Bell-shaped)" if abs(skew1) < 0.75 else ("Right-skewed" if skew1 > 0 else "Left-skewed")

                normality_stats.append({
                    'Input_Order': str(order_val),
                    'Algorithm': str(algo1),
                    'Sample_Count': len(t1_scaled),
                    'Mean': f"{mu1:.3f} {unit}",
                    'StdDev': f"{sig1:.3f} {unit}",
                    'Median': f"{med1:.3f} {unit}",
                    'Skewness': f"{skew1:+.2f}",
                    'Excess_Kurtosis': f"{kurt1:+.2f}",
                    'Distribution_Profile': norm_status1
                })

                sns.histplot(t1_scaled, stat='density', kde=True, ax=ax1, color='#1f77b4', edgecolor='black', alpha=0.45, label='Empirical (Hist + KDE)')
                x_pts1 = np.linspace(min(t1_scaled) - 0.8 * sig1, max(t1_scaled) + 0.8 * sig1, 250)
                bell1 = (1.0 / (sig1 * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_pts1 - mu1) / sig1)**2)
                ax1.plot(x_pts1, bell1, 'r--', lw=2.5, label=rf"Gaussian Bell Fit $N(\mu={mu1:.2f}, \sigma={sig1:.2f})$")
                ax1.axvline(mu1, color='green', linestyle='-', lw=2, label=rf"Mean $\mu$ ({mu1:.2f}{unit})")
                ax1.axvline(med1, color='purple', linestyle=':', lw=2, label=rf"Median ({med1:.2f}{unit})")

                stats_box1 = (f"N = {len(t1_scaled)}\n"
                              rf"$\mu$ = {mu1:.3f} {unit}" + "\n"
                              rf"$\sigma$ = {sig1:.3f} {unit}" + "\n"
                              rf"Median = {med1:.3f} {unit}" + "\n"
                              rf"Skewness = {skew1:+.2f}" + "\n"
                              rf"Kurtosis = {kurt1:+.2f}" + "\n"
                              f"Profile: {norm_status1}")
                ax1.text(0.97, 0.95, stats_box1, transform=ax1.transAxes, verticalalignment='top', horizontalalignment='right',
                         bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray'), fontsize=9)
                ax1.set_title(f"{algo1} - Iteration Distribution", fontweight='bold', fontsize=12)
                ax1.set_xlabel(f"Execution Time ({unit})", fontweight='bold')
                ax1.set_ylabel("Probability Density", fontweight='bold')
                ax1.legend(loc='upper left', fontsize=8)

            # 2. Algorithm 2
            ax2 = axes[0, 1]
            if len(algos) > 1:
                algo2 = algos[1]
                df_a2 = df_order[df_order[algo_col] == algo2]
                t2 = []
                for _, r in df_a2.iterrows():
                    t2.extend(parse_raw_array(r.get('Raw_Times_ms', [])))
                t2 = np.array(t2)
                t2_scaled = t2 / scale if len(t2) > 0 else np.array([])
                if len(t2_scaled) > 1:
                    mu2, sig2 = float(np.mean(t2_scaled)), max(float(np.std(t2_scaled, ddof=1)), 1e-6)
                    med2 = float(np.median(t2_scaled))
                    skew2 = float(np.mean((t2_scaled - mu2)**3) / (sig2**3))
                    kurt2 = float((np.mean((t2_scaled - mu2)**4) / (sig2**4)) - 3.0)
                    norm_status2 = "Approx. Normal (Bell-shaped)" if abs(skew2) < 0.75 else ("Right-skewed" if skew2 > 0 else "Left-skewed")

                    normality_stats.append({
                        'Input_Order': str(order_val),
                        'Algorithm': str(algo2),
                        'Sample_Count': len(t2_scaled),
                        'Mean': f"{mu2:.3f} {unit}",
                        'StdDev': f"{sig2:.3f} {unit}",
                        'Median': f"{med2:.3f} {unit}",
                        'Skewness': f"{skew2:+.2f}",
                        'Excess_Kurtosis': f"{kurt2:+.2f}",
                        'Distribution_Profile': norm_status2
                    })

                    sns.histplot(t2_scaled, stat='density', kde=True, ax=ax2, color='#ff7f0e', edgecolor='black', alpha=0.45, label='Empirical (Hist + KDE)')
                    x_pts2 = np.linspace(min(t2_scaled) - 0.8 * sig2, max(t2_scaled) + 0.8 * sig2, 250)
                    bell2 = (1.0 / (sig2 * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_pts2 - mu2) / sig2)**2)
                    ax2.plot(x_pts2, bell2, 'r--', lw=2.5, label=rf"Gaussian Bell Fit $N(\mu={mu2:.2f}, \sigma={sig2:.2f})$")
                    ax2.axvline(mu2, color='green', linestyle='-', lw=2, label=rf"Mean $\mu$ ({mu2:.2f}{unit})")
                    ax2.axvline(med2, color='purple', linestyle=':', lw=2, label=rf"Median ({med2:.2f}{unit})")

                    stats_box2 = (f"N = {len(t2_scaled)}\n"
                                  rf"$\mu$ = {mu2:.3f} {unit}" + "\n"
                                  rf"$\sigma$ = {sig2:.3f} {unit}" + "\n"
                                  rf"Median = {med2:.3f} {unit}" + "\n"
                                  rf"Skewness = {skew2:+.2f}" + "\n"
                                  rf"Kurtosis = {kurt2:+.2f}" + "\n"
                                  f"Profile: {norm_status2}")
                    ax2.text(0.97, 0.95, stats_box2, transform=ax2.transAxes, verticalalignment='top', horizontalalignment='right',
                             bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.9, edgecolor='gray'), fontsize=9)
                    ax2.set_title(f"{algo2} - Iteration Distribution", fontweight='bold', fontsize=12)
                    ax2.set_xlabel(f"Execution Time ({unit})", fontweight='bold')
                    ax2.set_ylabel("Probability Density", fontweight='bold')
                    ax2.legend(loc='upper left', fontsize=8)

            # 3. Comparative Overlaid Distributions
            ax3 = axes[1, 0]
            if len(t1_scaled) > 1 and len(algos) > 1 and len(t2_scaled) > 1:
                sns.kdeplot(t1_scaled, ax=ax3, fill=True, color='#1f77b4', alpha=0.25, label=f"{algo1} Empirical KDE")
                sns.kdeplot(t2_scaled, ax=ax3, fill=True, color='#ff7f0e', alpha=0.25, label=f"{algo2} Empirical KDE")
                min_x = min(float(np.min(t1_scaled)), float(np.min(t2_scaled)))
                max_x = max(float(np.max(t1_scaled)), float(np.max(t2_scaled)))
                pad_x = 0.1 * (max_x - min_x) if max_x > min_x else 1.0
                all_x = np.linspace(min_x - pad_x, max_x + pad_x, 300)
                b1 = (1.0 / (sig1 * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((all_x - mu1) / sig1)**2)
                b2 = (1.0 / (sig2 * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((all_x - mu2) / sig2)**2)
                ax3.plot(all_x, b1, color='#1f77b4', linestyle='--', lw=2.2, label=f"{algo1} Gaussian Bell")
                ax3.plot(all_x, b2, color='#d95f02', linestyle='--', lw=2.2, label=f"{algo2} Gaussian Bell")
                ax3.set_title("Comparative Overlay: Empirical vs Theoretical Bell Curves", fontweight='bold', fontsize=12)
                ax3.set_xlabel(f"Execution Time ({unit})", fontweight='bold')
                ax3.set_ylabel("Probability Density", fontweight='bold')
                ax3.legend(fontsize=8, loc='upper right')
            else:
                ax3.set_visible(False)

            # 4. Per-Entry Results Distribution (Bell Shape per Entry)
            ax4 = axes[1, 1]
            colors = plt.cm.tab10.colors
            if len(df_order) <= 8:
                for idx, (_, row) in enumerate(df_order.iterrows()):
                    raw = parse_raw_array(row.get('Raw_Times_ms', []))
                    if not raw:
                        continue
                    arr = np.array(raw) / scale
                    mu_e = float(np.mean(arr))
                    sig_e = max(float(np.std(arr, ddof=1)), 1e-6)
                    x_e = np.linspace(mu_e - 3.2 * sig_e, mu_e + 3.2 * sig_e, 120)
                    bell_e = (1.0 / (sig_e * np.sqrt(2 * np.pi))) * np.exp(-0.5 * ((x_e - mu_e) / sig_e)**2)
                    ent_tag = str(row[id_col]).replace('_4d', '').replace('states_', '')
                    lbl = rf"{ent_tag} ({row[algo_col]}): $\mu={mu_e:.2f}, \sigma={sig_e:.2f}$"
                    ax4.plot(x_e, bell_e, lw=2, color=colors[idx % len(colors)], label=lbl)
                    ax4.fill_between(x_e, bell_e, alpha=0.15, color=colors[idx % len(colors)])
                ax4.set_title("Per-Entry Fitted Gaussian Bell Curves", fontweight='bold', fontsize=12)
                ax4.set_xlabel(f"Execution Time ({unit})", fontweight='bold')
                ax4.set_ylabel("Probability Density", fontweight='bold')
                ax4.legend(fontsize=7, loc='upper right')
            else:
                entry_records = []
                for _, row in df_order.iterrows():
                    raw = parse_raw_array(row.get('Raw_Times_ms', []))
                    for val in raw:
                        entry_records.append({
                            'Entry': str(row[id_col]).replace('_4d', '').replace('states_', ''),
                            'Time': val / scale,
                            'Algorithm': row[algo_col]
                        })
                if entry_records:
                    df_e = pd.DataFrame(entry_records)
                    sns.boxplot(data=df_e, x='Entry', y='Time', hue='Algorithm', ax=ax4, palette='Set2', fliersize=2)
                    ax4.set_title("Per-Entry Iteration Spread & Quantiles", fontweight='bold', fontsize=12)
                    ax4.set_xlabel("Surveillance Interval / Entry", fontweight='bold')
                    ax4.set_ylabel(f"Execution Time ({unit})", fontweight='bold')
                    if len(df_e['Entry'].unique()) > 6:
                        ax4.tick_params(axis='x', rotation=45)
                    ax4.legend(fontsize=8)

            plt.tight_layout(rect=[0, 0.03, 1, 0.95])
            plt.savefig(plot_path, dpi=300)
            plt.close()
            generated_files.append(plot_path)

    # -------------------------------------------------------------
    # 7. Executive Summary Report (Markdown + Text)
    # -------------------------------------------------------------
    report_path = os.path.join(output_dir, "summary_report.md")
    with open(report_path, 'w') as f_rep:
        f_rep.write(f"# OpenSky Experiment Analytics Report\n\n")
        f_rep.write(f"- **Source CSV File:** `{csv_path}`\n")
        f_rep.write(f"- **Total Test Records Evaluated:** `{len(df)}`\n")
        f_rep.write(f"- **Unique Intervals/Days:** `{len(df[id_col].unique())}`\n")
        if 'Num_Points' in df.columns:
            f_rep.write(f"- **Total Points Evaluated:** `{df['Num_Points'].sum():,}`\n")
        if 'Min_Distance_m' in df.columns:
            min_overall = df['Min_Distance_m'].min()
            f_rep.write(f"- **Global Minimum Encounter Distance:** `{min_overall:.3f} meters`\n")
        f_rep.write(f"\n---\n\n## Scenario Performance Summary\n\n")

        # Group by Test_Case
        summary_group = df.groupby('Test_Case').agg({
            'Mean_Time_ms': ['mean', 'min', 'max'],
            'Mean_Rebuilds': 'mean' if 'Mean_Rebuilds' in df.columns else lambda x: 0,
            'Min_Distance_m': 'min' if 'Min_Distance_m' in df.columns else lambda x: 0
        }).round(2)

        f_rep.write(df_to_markdown(summary_group, index=True))
        f_rep.write("\n\n---\n\n## Complete Records Table\n\n")

        disp_cols = [c for c in [id_col, order_col, algo_col, 'Num_Points', 'Mean_Time_ms', 'Median_Time_ms', 'StdDev_Time_ms', 'Mean_Rebuilds', 'Min_Distance_m'] if c in df.columns]
        f_rep.write(df_to_markdown(df[disp_cols], index=False))
        f_rep.write("\n")

        if normality_stats:
            f_rep.write("\n---\n\n## Distribution Profile & Normality Assessment (Bell Curve Diagnostics)\n\n")
            df_norm = pd.DataFrame(normality_stats)
            f_rep.write(df_to_markdown(df_norm, index=False))
            f_rep.write("\n")

    generated_files.append(report_path)

    print(f"\n[Done] Analysis completed successfully!")
    print(f"  Destination Folder: {output_dir}")
    print(f"  Generated Assets ({len(generated_files)}):")
    for g in generated_files:
        print(f"    - {os.path.basename(g)}")

    return output_dir

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python3 analyze_results.py <path_to_results.csv> [output_dir]")
        sys.exit(1)

    target_csv = sys.argv[1]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else None
    analyze_and_plot(target_csv, out_dir)
