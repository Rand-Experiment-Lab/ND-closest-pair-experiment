#!/usr/bin/env python3
"""
OpenSky Benchmark Master Analyzer & Visualizer
==============================================
Universal analyzer for OpenSky closest-pair benchmarks.
Supports both multi-slice scaling benchmarks (e.g. 24-hour datasets)
and large single-scale multi-iteration benchmarks (e.g. 100M datasets).

Creates a dedicated output folder named after the CSV file inside analyzer/
(with automatic versioning _v1, _v2, ... if the directory already exists),
copies the input CSV, and generates the complete suite of academic-grade analytic
artifacts matching the exact specification of analyzer/analitic_sampl/:

Artifacts Generated:
  1. 01_timing_deterministic_original.png
  2. 02_timing_deterministic_sorted.png
  3. 03_timing_randomized_original.png
  4. 04_timing_randomized_sorted.png
  5. 05_compare_algo_original.png
  6. 06_compare_algo_sorted.png
  7. 07_compare_all_combined.png
  8. 08_compare_order_deterministic.png
  9. 09_compare_order_randomized.png
 10. 10_speedup_plot.png
 11. 11_speedup_heatmap.png
 12. 12_speedup_heatmap_binned.png
 13. summary_metrics.csv
 14. summary_speedup.csv
 15. timing_all_individual_4panel.png
 Plus (for multi-iteration benchmarks):
 16. 16_iteration_breakdown.png

Usage:
  python3 run_analyzer.py <path_to_csv> [--output-dir <custom_dir>]
"""

import sys
import os
import re
import ast
import shutil
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import seaborn as sns

# Visual Theme Configuration matching IEEE/ACM publication standards
sns.set_theme(style="whitegrid")
plt.rcParams['font.sans-serif'] = ['DejaVu Sans', 'Arial', 'Helvetica', 'sans-serif']
plt.rcParams['font.family'] = 'sans-serif'
plt.rcParams['axes.edgecolor'] = '#b0bec5'
plt.rcParams['axes.linewidth'] = 1.1
plt.rcParams['grid.color'] = '#eceff1'
plt.rcParams['grid.linestyle'] = '-'
plt.rcParams['grid.alpha'] = 0.85

PALETTE = {
    ('Deterministic Grid', 'Original'): {
        'color': '#1f77b4', 'marker': 'o', 'linestyle': '-',
        'label': 'Deterministic Grid (Original Order)'
    },
    ('Deterministic Grid', 'Sorted_Time'): {
        'color': '#2ca02c', 'marker': 's', 'linestyle': '--',
        'label': 'Deterministic Grid (Sorted_Time Order)'
    },
    ('Randomized Grid', 'Original'): {
        'color': '#d62728', 'marker': '^', 'linestyle': '-.',
        'label': 'Randomized Grid (Original Order)'
    },
    ('Randomized Grid', 'Sorted_Time'): {
        'color': '#e6a100', 'marker': 'd', 'linestyle': ':',
        'label': 'Randomized Grid (Sorted_Time Order)'
    }
}

def resolve_versioned_output_dir(base_dir, csv_name):
    """
    Creates a folder named after the CSV.
    If the folder already exists, assigns an incremented version tag (_v1, _v2, ...).
    """
    clean_stem = re.sub(r'\.csv$', '', csv_name, flags=re.IGNORECASE)
    primary_dir = os.path.join(base_dir, clean_stem)
    
    if not os.path.exists(primary_dir):
        os.makedirs(primary_dir, exist_ok=True)
        return primary_dir

    existing_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d))]
    pattern = re.compile(rf'^{re.escape(clean_stem)}_v(\d+)$')
    
    versions = []
    for d in existing_dirs:
        m = pattern.match(d)
        if m:
            versions.append(int(m.group(1)))
            
    next_v = max(versions) + 1 if versions else 1
    versioned_dir = os.path.join(base_dir, f"{clean_stem}_v{next_v}")
    os.makedirs(versioned_dir, exist_ok=True)
    return versioned_dir

def parse_list_column(val):
    if pd.isna(val):
        return []
    if isinstance(val, list):
        return val
    try:
        return ast.literal_eval(str(val).strip())
    except Exception:
        return []

def load_and_preprocess_csv(csv_path):
    df = pd.read_csv(csv_path)
    for col in ['Algorithm', 'Input_Order', 'Hour_Tag']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
    if 'Input_Order' in df.columns:
        df['Input_Order'] = df['Input_Order'].replace({'Sorted_Time_Axis': 'Sorted_Time'})
            
    if 'Mean_Time_ms' in df.columns:
        df['Mean_Time_s'] = df['Mean_Time_ms'] / 1000.0
    if 'Median_Time_ms' in df.columns:
        df['Median_Time_s'] = df['Median_Time_ms'] / 1000.0
    if 'StdDev_Time_ms' in df.columns:
        df['StdDev_Time_s'] = df['StdDev_Time_ms'] / 1000.0
    else:
        df['StdDev_Time_s'] = 0.0

    df['Num_Points_M'] = df['Num_Points'] / 1e6
    
    # Parse raw iteration arrays if available
    if 'Raw_Times_ms' in df.columns:
        df['Raw_Times_s'] = df['Raw_Times_ms'].apply(lambda x: [float(t) / 1000.0 for t in parse_list_column(x)])
    else:
        df['Raw_Times_s'] = [[] for _ in range(len(df))]

    if 'Raw_Rebuilds' in df.columns:
        df['Raw_Rebuilds_Parsed'] = df['Raw_Rebuilds'].apply(parse_list_column)
    else:
        df['Raw_Rebuilds_Parsed'] = [[] for _ in range(len(df))]

    return df

def draw_placeholder_card(ax, title, reason):
    """Draws a clean, styled informational card when a configuration was not evaluated."""
    ax.set_facecolor('#f8f9fa')
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_color('#cfd8dc')
        spine.set_linestyle('--')
        spine.set_linewidth(1.2)
        
    ax.text(0.5, 0.65, title, transform=ax.transAxes, ha='center', va='center',
            fontsize=12, fontweight='bold', color='#455a64')
    ax.text(0.5, 0.40, reason, transform=ax.transAxes, ha='center', va='center',
            fontsize=9.5, color='#78909c', style='italic', wrap=True)

def generate_individual_timing_plots(df, out_dir):
    """
    Generates Figures 01 through 04 and the combined 4-panel figure.
    Plots measured times with +/- 1 sigma error bars and theoretical complexity reference curves:
      - O(n)
      - O(n log n)
      - O(n^2)
    Anchored at the baseline point or measured point with proper domain scaling.
    """
    configs = [
        ('Deterministic Grid', 'Original', '01_timing_deterministic_original.png', 'Deterministic Grid (Original Order)'),
        ('Deterministic Grid', 'Sorted_Time', '02_timing_deterministic_sorted.png', 'Deterministic Grid (Sorted_Time Order)'),
        ('Randomized Grid', 'Original', '03_timing_randomized_original.png', 'Randomized Grid (Original Order)'),
        ('Randomized Grid', 'Sorted_Time', '04_timing_randomized_sorted.png', 'Randomized Grid (Sorted_Time Order)'),
    ]

    fig_4panel, axes_4panel = plt.subplots(2, 2, figsize=(13.5, 11), dpi=300)
    axes_flat = axes_4panel.flatten()

    for idx, (algo, order, fname, title) in enumerate(configs):
        sub = df[(df['Algorithm'] == algo) & (df['Input_Order'] == order)].copy()
        ax_panel = axes_flat[idx]

        if sub.empty:
            # Standalone placeholder
            fig_ph, ax_ph = plt.subplots(figsize=(7.5, 5.5), dpi=300)
            reason_text = (
                f"Configuration: {algo} ({order})\n"
                "Not Evaluated at this Scale / Configuration\n\n"
                "Note: Sorting 100M+ 4D points requires massive RAM overhead.\n"
                "Randomized Grid natively provides O(n) expected runtime on Original order."
            )
            draw_placeholder_card(ax_ph, title, reason_text)
            fig_ph.tight_layout()
            fig_ph.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig_ph)

            # 4-panel placeholder
            draw_placeholder_card(ax_panel, title, "Not Evaluated for this Scale\n(Omitted to optimize benchmark RAM)")
            continue

        sub.sort_values('Num_Points', inplace=True)
        x_pts = sub['Num_Points_M'].to_numpy()
        y_pts = sub['Mean_Time_s'].to_numpy()
        y_err = sub['StdDev_Time_s'].to_numpy()
        raw_times_list = sub['Raw_Times_s'].iloc[0] if len(sub['Raw_Times_s'].iloc[0]) > 0 else []

        x0, y0 = x_pts[0], y_pts[0]
        pcfg = PALETTE[(algo, order)]

        is_single_point = (len(np.unique(x_pts)) == 1)

        if is_single_point:
            # Anchor curves across a synthetic domain around the single point
            x_min_domain = max(1.0, x0 * 0.5)
            x_max_domain = x0 * 1.3
            x_dense = np.linspace(x_min_domain, x_max_domain, 200)

            c1 = y0 / x0
            ref_lin = c1 * x_dense

            c2 = y0 / (x0 * np.log2(x0 * 1e6))
            ref_nlogn = c2 * (x_dense * np.log2(x_dense * 1e6))

            c3 = y0 / (x0 ** 2)
            ref_quad = c3 * (x_dense ** 2)

            y_min_plot = max(0.0, y0 * 0.4)
            y_max_plot = y0 * 1.45
            x_lim = (x_min_domain * 0.95, x_max_domain * 1.05)
        else:
            x_dense = np.linspace(x_pts.min(), x_pts.max(), 200)
            c1 = y0 / x0
            ref_lin = c1 * x_dense
            c2 = y0 / (x0 * np.log2(x0 * 1e6))
            ref_nlogn = c2 * (x_dense * np.log2(x_dense * 1e6))
            c3 = y0 / (x0 ** 2)
            ref_quad = c3 * (x_dense ** 2)

            y_max = max(y_pts.max() * 1.08, ref_nlogn.max() * 1.08)
            y_max_plot = min(y_max * 1.8, ref_quad.max())
            y_min_plot = y_pts.min() * 0.7
            x_lim = None

        # 1. Standalone figure
        plt.figure(figsize=(8.0, 5.8), dpi=300)
        plt.plot(x_dense, ref_lin, color='#7c4dff', linestyle='--', linewidth=2.0, label='Reference $O(n)$')
        plt.plot(x_dense, ref_nlogn, color='#0097a7', linestyle='-.', linewidth=2.0, label='Reference $O(n\\log n)$')
        plt.plot(x_dense, ref_quad, color='#78909c', linestyle=':', linewidth=2.0, label='Reference $O(n^2)$')

        plt.errorbar(x_pts, y_pts, yerr=y_err, fmt=pcfg['marker'],
                     color=pcfg['color'], linewidth=2.2, markersize=8.5, capsize=4, capthick=1.5,
                     label=f'Measured Mean Time (±1σ: {y_err[0]:.2f}s)')

        if is_single_point and len(raw_times_list) > 1:
            for i_idx, r_t in enumerate(raw_times_list):
                plt.scatter([x0], [r_t], color=pcfg['color'], alpha=0.65, edgecolors='black',
                            s=55, zorder=5, label=f'Iteration {i_idx+1}: {r_t:.1f}s')

            # Stat Callout Box
            pts_int = int(sub['Num_Points'].iloc[0])
            throughput = pts_int / y0
            reb_val = sub['Mean_Rebuilds'].iloc[0] if 'Mean_Rebuilds' in sub.columns else 0
            box_text = (
                f"N = {pts_int:,} (4D points)\n"
                f"Mean Time: {y0:.2f} s ({y0/60.0:.2f} min)\n"
                f"StdDev: ±{y_err[0]:.2f} s\n"
                f"Rebuilds: {reb_val:.1f}\n"
                f"Throughput: {throughput:,.0f} pts/sec"
            )
            plt.gca().text(0.68, 0.18, box_text, transform=plt.gca().transAxes,
                           fontsize=9.5, verticalalignment='center',
                           bbox=dict(boxstyle='round,pad=0.6', facecolor='#f5f5f5', edgecolor='#b0bec5', alpha=0.95))

        plt.title(title, fontsize=13, fontweight='bold', pad=12)
        plt.xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
        plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
        plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.92, fontsize=9.0)
        plt.ylim(y_min_plot, y_max_plot)
        if x_lim:
            plt.xlim(x_lim)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
        plt.close()

        # 2. Add to 4-panel subplot
        ax_panel.plot(x_dense, ref_lin, color='#7c4dff', linestyle='--', linewidth=1.8, label='Reference $O(n)$')
        ax_panel.plot(x_dense, ref_nlogn, color='#0097a7', linestyle='-.', linewidth=1.8, label='Reference $O(n\\log n)$')
        ax_panel.plot(x_dense, ref_quad, color='#78909c', linestyle=':', linewidth=1.8, label='Reference $O(n^2)$')
        ax_panel.errorbar(x_pts, y_pts, yerr=y_err, fmt=pcfg['marker'],
                          color=pcfg['color'], linewidth=2.0, markersize=7, capsize=3,
                          label=f'Measured ({y0:.1f}s)')

        if is_single_point and len(raw_times_list) > 1:
            for i_idx, r_t in enumerate(raw_times_list):
                ax_panel.scatter([x0], [r_t], color=pcfg['color'], alpha=0.6, edgecolors='black', s=40, zorder=5)

        ax_panel.set_title(title, fontsize=11, fontweight='bold')
        ax_panel.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.88, fontsize=8.0)
        ax_panel.set_ylabel('Execution Time (s)', fontsize=10, fontweight='bold')
        ax_panel.set_xlabel('Number of Points $N$ (Millions)', fontsize=10, fontweight='bold')
        ax_panel.set_ylim(y_min_plot, y_max_plot)
        if x_lim:
            ax_panel.set_xlim(x_lim)

    fig_4panel.suptitle('Dataset Size vs. Execution Time with Theoretical Complexity References',
                        fontsize=14, fontweight='bold', y=0.99)
    fig_4panel.tight_layout()
    fig_4panel.subplots_adjust(top=0.93)
    fig_4panel.savefig(os.path.join(out_dir, 'timing_all_individual_4panel.png'), dpi=300, bbox_inches='tight')
    plt.close(fig_4panel)

def generate_comparison_plots(df, out_dir):
    """
    Generates comparative plots:
      - 05_compare_algo_original.png
      - 06_compare_algo_sorted.png
      - 07_compare_all_combined.png
      - 08_compare_order_deterministic.png
      - 09_compare_order_randomized.png
    """
    is_single_point = (len(df['Num_Points'].unique()) == 1)

    # 05. Algorithm Comparison (Original Order)
    orig_sub = df[df['Input_Order'] == 'Original'].copy()
    if not orig_sub.empty:
        plt.figure(figsize=(8.5, 5.6), dpi=300)
        if is_single_point:
            # High-precision side-by-side bar & iteration plot
            algos = orig_sub['Algorithm'].tolist()
            means = orig_sub['Mean_Time_s'].tolist()
            errs = orig_sub['StdDev_Time_s'].tolist()
            colors = [PALETTE[(a, 'Original')]['color'] for a in algos]

            x_pos = np.arange(len(algos))
            bars = plt.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.82, width=0.45,
                           edgecolor='black', linewidth=1.2)
            
            # Overlay raw iterations
            for i, algo in enumerate(algos):
                row = orig_sub[orig_sub['Algorithm'] == algo].iloc[0]
                raw_s = row['Raw_Times_s']
                if len(raw_s) > 0:
                    plt.scatter([x_pos[i]] * len(raw_s), raw_s, color='white', edgecolors='black',
                                s=65, zorder=5, label='Raw Iterations' if i == 0 else "")
                    for r_idx, val in enumerate(raw_s):
                        plt.annotate(f"{val:.1f}s", (x_pos[i] + 0.08, val), fontsize=8.5, va='center')

            # Bar height labels
            for bar in bars:
                h = bar.get_height()
                plt.text(bar.get_x() + bar.get_width()/2.0, h * 0.5, f"{h:.2f} s\n({h/60.0:.2f} min)",
                         ha='center', va='center', color='white', fontweight='bold', fontsize=11)

            # Speedup Annotation Bracket
            if len(means) == 2:
                t_det = orig_sub[orig_sub['Algorithm'] == 'Deterministic Grid']['Mean_Time_s'].iloc[0]
                t_rand = orig_sub[orig_sub['Algorithm'] == 'Randomized Grid']['Mean_Time_s'].iloc[0]
                diff_s = t_det - t_rand
                sp_ratio = t_det / t_rand
                pct_faster = ((t_det - t_rand) / t_det) * 100.0
                
                bracket_y = max(means) * 1.08
                plt.plot([0, 0, 1, 1], [max(means)*1.03, bracket_y, bracket_y, max(means)*1.03],
                         color='#d32f2f', linewidth=1.5)
                plt.text(0.5, bracket_y * 1.02,
                         f"Randomized Grid is {sp_ratio:.3f}x Faster ({diff_s:.2f}s saved, +{pct_faster:.1f}%)",
                         ha='center', va='bottom', fontsize=10.5, fontweight='bold', color='#c62828')
                plt.ylim(0, bracket_y * 1.22)

            plt.xticks(x_pos, [f"{a}\n(Original Order)" for a in algos], fontsize=11, fontweight='bold')
            plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            plt.title(f'Algorithm Comparison (Original Order) at N = {orig_sub["Num_Points"].iloc[0]:,} Points',
                      fontsize=12, fontweight='bold', pad=14)
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, '05_compare_algo_original.png'), dpi=300, bbox_inches='tight')
            plt.close()
        else:
            for algo in ['Deterministic Grid', 'Randomized Grid']:
                sub = orig_sub[orig_sub['Algorithm'] == algo].sort_values('Num_Points')
                if sub.empty:
                    continue
                pcfg = PALETTE[(algo, 'Original')]
                plt.plot(sub['Num_Points_M'], sub['Mean_Time_s'],
                         marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                         linewidth=2.4, markersize=7.5, label=f"{algo} (Original)")
            plt.title('Algorithm Comparison (Original Input Order): Deterministic vs. Randomized', fontsize=12, fontweight='bold', pad=12)
            plt.xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
            plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, '05_compare_algo_original.png'), dpi=300, bbox_inches='tight')
            plt.close()

    # 06. Algorithm Comparison (Sorted_Time Order)
    sort_sub = df[df['Input_Order'] == 'Sorted_Time'].copy()
    fig_06, ax_06 = plt.subplots(figsize=(8.0, 5.5), dpi=300)
    if sort_sub.empty:
        draw_placeholder_card(ax_06, 'Algorithm Comparison (Sorted_Time Order)',
                              'Sorted_Time benchmark was not executed at this scale.\n'
                              'Pre-sorting 100M+ points introduces substantial CPU & memory overhead\n'
                              'which is bypassed by using the randomized grid.')
    else:
        if is_single_point:
            algos = sort_sub['Algorithm'].tolist()
            means = sort_sub['Mean_Time_s'].tolist()
            errs = sort_sub['StdDev_Time_s'].tolist()
            colors = [PALETTE[(a, 'Sorted_Time')]['color'] for a in algos]
            x_pos = np.arange(len(algos))
            bars = ax_06.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.82, width=0.45,
                             edgecolor='black', linewidth=1.2)
            for i, algo in enumerate(algos):
                row = sort_sub[sort_sub['Algorithm'] == algo].iloc[0]
                raw_s = row['Raw_Times_s']
                if len(raw_s) > 0:
                    ax_06.scatter([x_pos[i]] * len(raw_s), raw_s, color='white', edgecolors='black',
                                  s=65, zorder=5)
            for bar in bars:
                h = bar.get_height()
                ax_06.text(bar.get_x() + bar.get_width()/2.0, h * 0.5,
                           f"{h:.2f} s\n({h/60.0:.2f} min)" if h >= 60 else f"{h:.2f} s",
                           ha='center', va='center', color='white', fontweight='bold', fontsize=11)
            ax_06.set_xticks(x_pos, [f"{a}\n(Sorted_Time)" for a in algos], fontsize=11, fontweight='bold')
            ax_06.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_06.set_title(f'Algorithm Comparison (Sorted_Time Order) at N = {sort_sub["Num_Points"].iloc[0]:,} Points',
                            fontsize=12, fontweight='bold', pad=14)
            ax_06.set_ylim(0, max(means) * 1.25)
        else:
            for algo in ['Deterministic Grid', 'Randomized Grid']:
                sub = sort_sub[sort_sub['Algorithm'] == algo].sort_values('Num_Points')
                if sub.empty:
                    continue
                pcfg = PALETTE[(algo, 'Sorted_Time')]
                ax_06.plot(sub['Num_Points_M'], sub['Mean_Time_s'],
                           marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                           linewidth=2.4, markersize=7.5, label=f"{algo} (Sorted_Time)")
            ax_06.set_title('Algorithm Comparison (Sorted_Time Input Order)', fontsize=12, fontweight='bold', pad=12)
            ax_06.set_xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
            ax_06.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_06.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
    fig_06.tight_layout()
    fig_06.savefig(os.path.join(out_dir, '06_compare_algo_sorted.png'), dpi=300, bbox_inches='tight')
    plt.close(fig_06)

    # 07. Combined Performance Comparison
    plt.figure(figsize=(8.5, 5.8), dpi=300)
    if is_single_point:
        configs_present = df[['Algorithm', 'Input_Order']].drop_duplicates().values
        labels = [f"{a}\n({o})" for a, o in configs_present]
        means = []
        errs = []
        colors = []
        for a, o in configs_present:
            r = df[(df['Algorithm'] == a) & (df['Input_Order'] == o)].iloc[0]
            means.append(r['Mean_Time_s'])
            errs.append(r['StdDev_Time_s'])
            colors.append(PALETTE[(a, o)]['color'])
            
        x_pos = np.arange(len(labels))
        bars = plt.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.85, width=0.4, edgecolor='black')
        for bar in bars:
            h = bar.get_height()
            plt.text(bar.get_x() + bar.get_width()/2.0, h * 0.5, f"{h:.2f} s",
                     ha='center', va='center', color='white', fontweight='bold', fontsize=11)
        plt.xticks(x_pos, labels, fontsize=10.5, fontweight='bold')
        plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
        plt.title(f'Performance Comparison across Evaluated Configurations (N = {df["Num_Points"].iloc[0]:,})',
                  fontsize=12, fontweight='bold', pad=12)
        plt.ylim(0, max(means) * 1.25)
    else:
        for (algo, order), pcfg in PALETTE.items():
            sub = df[(df['Algorithm'] == algo) & (df['Input_Order'] == order)].sort_values('Num_Points')
            if sub.empty:
                continue
            plt.plot(sub['Num_Points_M'], sub['Mean_Time_s'],
                     marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                     linewidth=2.2, markersize=7, label=f"{algo} ({order})")
        plt.title('Combined Performance Comparison: All Algorithms and Input Orders', fontsize=12.5, fontweight='bold', pad=12)
        plt.xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
        plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
        plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, '07_compare_all_combined.png'), dpi=300, bbox_inches='tight')
    plt.close()

    # 08. Input Order Comparison (Deterministic Grid)
    fig_08, ax_08 = plt.subplots(figsize=(8.0, 5.5), dpi=300)
    det_sub = df[df['Algorithm'] == 'Deterministic Grid']
    orders_present = det_sub['Input_Order'].unique()
    if len(orders_present) > 1:
        if is_single_point:
            orders = list(orders_present)
            means = [det_sub[det_sub['Input_Order'] == o]['Mean_Time_s'].iloc[0] for o in orders]
            errs = [det_sub[det_sub['Input_Order'] == o]['StdDev_Time_s'].iloc[0] for o in orders]
            colors = [PALETTE[('Deterministic Grid', o)]['color'] for o in orders]
            x_pos = np.arange(len(orders))
            bars = ax_08.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.85, width=0.45, edgecolor='black')
            for b_idx, bar in enumerate(bars):
                h = bar.get_height()
                ax_08.text(bar.get_x() + bar.get_width()/2.0, h * 0.5,
                           f"{h:.2f} s\n({h/60.0:.2f} min)" if h >= 60 else f"{h:.2f} s",
                           ha='center', va='center', color='white', fontweight='bold', fontsize=10.5)
            ax_08.set_xticks(x_pos, [f"Deterministic Grid\n({o})" for o in orders], fontsize=10.5, fontweight='bold')
            ax_08.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_08.set_title(f'Input Order Comparison: Deterministic Grid (N = {det_sub["Num_Points"].iloc[0]:,})',
                            fontsize=12, fontweight='bold', pad=12)
            ax_08.set_ylim(0, max(means) * 1.25)
        else:
            for order in ['Original', 'Sorted_Time']:
                sub = det_sub[det_sub['Input_Order'] == order].sort_values('Num_Points')
                if sub.empty:
                    continue
                pcfg = PALETTE[('Deterministic Grid', order)]
                ax_08.plot(sub['Num_Points_M'], sub['Mean_Time_s'],
                           marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                           linewidth=2.4, markersize=7.5, label=f"Deterministic Grid ({order})")
            ax_08.set_title('Input Order Comparison: Deterministic Grid', fontsize=12, fontweight='bold', pad=12)
            ax_08.set_xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
            ax_08.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_08.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
    else:
        row_det = det_sub.iloc[0]
        raw_t = row_det['Raw_Times_s']
        raw_r = row_det['Raw_Rebuilds_Parsed']
        if len(raw_t) > 0:
            iters = [f"Iter {i+1}" for i in range(len(raw_t))]
            bars = ax_08.bar(iters, raw_t, color='#1f77b4', alpha=0.85, width=0.45, edgecolor='black')
            ax_08.axhline(row_det['Mean_Time_s'], color='#0d47a1', linestyle='--', linewidth=1.5,
                          label=f"Mean: {row_det['Mean_Time_s']:.2f}s (±{row_det['StdDev_Time_s']:.2f}s)")
            for b_idx, bar in enumerate(bars):
                h = bar.get_height()
                r_cnt = raw_r[b_idx] if b_idx < len(raw_r) else 0
                ax_08.text(bar.get_x() + bar.get_width()/2.0, h * 0.5,
                           f"{h:.1f} s\n({r_cnt} rebuilds)",
                           ha='center', va='center', color='white', fontweight='bold', fontsize=10)
            ax_08.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_08.set_title(f'Deterministic Grid Stability Across Iterations (N = {row_det["Num_Points"]:,})',
                            fontsize=12, fontweight='bold', pad=12)
            ax_08.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)
            ax_08.set_ylim(0, max(raw_t) * 1.25)
        else:
            draw_placeholder_card(ax_08, 'Input Order Comparison: Deterministic Grid',
                                  'Only Original order was evaluated for this dataset.')
    fig_08.tight_layout()
    fig_08.savefig(os.path.join(out_dir, '08_compare_order_deterministic.png'), dpi=300, bbox_inches='tight')
    plt.close(fig_08)

    # 09. Input Order Comparison (Randomized Grid)
    fig_09, ax_09 = plt.subplots(figsize=(8.0, 5.5), dpi=300)
    rand_sub = df[df['Algorithm'] == 'Randomized Grid']
    orders_present_rand = rand_sub['Input_Order'].unique()
    if len(orders_present_rand) > 1:
        if is_single_point:
            orders = list(orders_present_rand)
            means = [rand_sub[rand_sub['Input_Order'] == o]['Mean_Time_s'].iloc[0] for o in orders]
            errs = [rand_sub[rand_sub['Input_Order'] == o]['StdDev_Time_s'].iloc[0] for o in orders]
            colors = [PALETTE[('Randomized Grid', o)]['color'] for o in orders]
            x_pos = np.arange(len(orders))
            bars = ax_09.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.85, width=0.45, edgecolor='black')
            for b_idx, bar in enumerate(bars):
                h = bar.get_height()
                ax_09.text(bar.get_x() + bar.get_width()/2.0, h * 0.5,
                           f"{h:.2f} s\n({h/60.0:.2f} min)" if h >= 60 else f"{h:.2f} s",
                           ha='center', va='center', color='white', fontweight='bold', fontsize=10.5)
            ax_09.set_xticks(x_pos, [f"Randomized Grid\n({o})" for o in orders], fontsize=10.5, fontweight='bold')
            ax_09.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_09.set_title(f'Input Order Comparison: Randomized Grid (N = {rand_sub["Num_Points"].iloc[0]:,})',
                            fontsize=12, fontweight='bold', pad=12)
            ax_09.set_ylim(0, max(means) * 1.25)
        else:
            for order in ['Original', 'Sorted_Time']:
                sub = rand_sub[rand_sub['Input_Order'] == order].sort_values('Num_Points')
                if sub.empty:
                    continue
                pcfg = PALETTE[('Randomized Grid', order)]
                ax_09.plot(sub['Num_Points_M'], sub['Mean_Time_s'],
                           marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                           linewidth=2.4, markersize=7.5, label=f"Randomized Grid ({order})")
            ax_09.set_title('Input Order Comparison: Randomized Grid', fontsize=12, fontweight='bold', pad=12)
            ax_09.set_xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
            ax_09.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_09.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
    else:
        row_rand = rand_sub.iloc[0]
        raw_t = row_rand['Raw_Times_s']
        raw_r = row_rand['Raw_Rebuilds_Parsed']
        if len(raw_t) > 0:
            iters = [f"Iter {i+1}" for i in range(len(raw_t))]
            bars = ax_09.bar(iters, raw_t, color='#d62728', alpha=0.85, width=0.45, edgecolor='black')
            ax_09.axhline(row_rand['Mean_Time_s'], color='#b71c1c', linestyle='--', linewidth=1.5,
                          label=f"Mean: {row_rand['Mean_Time_s']:.2f}s (±{row_rand['StdDev_Time_s']:.2f}s)")
            for b_idx, bar in enumerate(bars):
                h = bar.get_height()
                r_cnt = raw_r[b_idx] if b_idx < len(raw_r) else 0
                ax_09.text(bar.get_x() + bar.get_width()/2.0, h * 0.5,
                           f"{h:.1f} s\n({r_cnt} rebuilds)",
                           ha='center', va='center', color='white', fontweight='bold', fontsize=10)
            ax_09.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_09.set_title(f'Randomized Grid Dynamics Across Iterations (N = {row_rand["Num_Points"]:,})',
                            fontsize=12, fontweight='bold', pad=12)
            ax_09.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)
            ax_09.set_ylim(0, max(raw_t) * 1.25)
        else:
            draw_placeholder_card(ax_09, 'Input Order Comparison: Randomized Grid',
                                  'Only Original order was evaluated for this dataset.')
    fig_09.tight_layout()
    fig_09.savefig(os.path.join(out_dir, '09_compare_order_randomized.png'), dpi=300, bbox_inches='tight')
    plt.close(fig_09)

def generate_speedup_artifacts(df, out_dir):
    """
    Computes speedup ratios (T_det / T_rand) robustly and generates:
      - 10_speedup_plot.png
      - 11_speedup_heatmap.png
      - 12_speedup_heatmap_binned.png
      - summary_speedup.csv
    """
    is_single_point = (len(df['Num_Points'].unique()) == 1)
    orders_available = list(df['Input_Order'].unique())

    # Calculate speedup per order
    speedup_records = []
    
    for order in orders_available:
        sub_det = df[(df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == order)]
        sub_rand = df[(df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == order)]
        if sub_det.empty or sub_rand.empty:
            continue

        det_mean = sub_det['Mean_Time_ms'].values
        rand_mean = sub_rand['Mean_Time_ms'].values
        pts = sub_det['Num_Points'].values
        pts_m = pts / 1e6
        sp_arr = det_mean / rand_mean

        for i in range(len(pts)):
            speedup_records.append({
                'Num_Points': pts[i],
                'Num_Points_M': pts_m[i],
                'Input_Order': order,
                'Speedup': sp_arr[i]
            })

    if not speedup_records:
        print("[Warning] No matching Deterministic & Randomized pairs found for speedup calculation.")
        return

    sp_df = pd.DataFrame(speedup_records)

    # 1. summary_speedup.csv
    summary_rows = []
    for order in ['Original', 'Sorted_Time']:
        sub_o = sp_df[sp_df['Input_Order'] == order]
        if sub_o.empty:
            continue
        
        # If single point with raw iterations, compute iteration-level min/max speedup
        if is_single_point:
            row_det = df[(df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == order)].iloc[0]
            row_rand = df[(df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == order)].iloc[0]
            raw_det = row_det['Raw_Times_s']
            raw_rand = row_rand['Raw_Times_s']
            if len(raw_det) > 0 and len(raw_det) == len(raw_rand):
                iter_sps = [raw_det[k] / raw_rand[k] for k in range(len(raw_det))]
                mean_sp = row_det['Mean_Time_s'] / row_rand['Mean_Time_s']
                min_sp = min(iter_sps)
                max_sp = max(iter_sps)
                pct_faster = (sum(s > 1.0 for s in iter_sps) / len(iter_sps)) * 100.0
            else:
                mean_sp = sub_o['Speedup'].mean()
                min_sp = sub_o['Speedup'].min()
                max_sp = sub_o['Speedup'].max()
                pct_faster = 100.0 if mean_sp > 1.0 else 0.0
        else:
            mean_sp = sub_o['Speedup'].mean()
            min_sp = sub_o['Speedup'].min()
            max_sp = sub_o['Speedup'].max()
            pct_faster = (sub_o['Speedup'] > 1.0).mean() * 100.0

        summary_rows.append({
            'Input_Order': order,
            'Mean_Speedup': mean_sp,
            'Min_Speedup': min_sp,
            'Max_Speedup': max_sp,
            'Pct_Randomized_Faster': pct_faster
        })
        
    summary_sp_df = pd.DataFrame(summary_rows)
    summary_sp_df.to_csv(os.path.join(out_dir, 'summary_speedup.csv'), index=False)

    # 2. 10_speedup_plot.png
    plt.figure(figsize=(8.5, 5.4), dpi=300)
    plt.axhline(1.0, color='black', linestyle='--', linewidth=1.5, label='Parity Baseline (1.0x)')
    plt.axhspan(1.0, 1.25, color='#ffebee', alpha=0.45, label='Randomized Grid Faster (Speedup > 1.0)')
    plt.axhspan(0.85, 1.0, color='#e3f2fd', alpha=0.45, label='Deterministic Grid Faster (Speedup < 1.0)')

    if is_single_point:
        # High resolution iteration-by-iteration speedup chart
        orders_present = [o for o in ['Original', 'Sorted_Time'] if o in df['Input_Order'].values]
        primary_order = orders_present[0] if orders_present else df['Input_Order'].iloc[0]
        sub_det = df[(df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == primary_order)]
        sub_rand = df[(df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == primary_order)]

        if not sub_det.empty and not sub_rand.empty:
            row_det = sub_det.iloc[0]
            row_rand = sub_rand.iloc[0]
            raw_det = row_det['Raw_Times_s']
            raw_rand = row_rand['Raw_Times_s']

            if len(raw_det) > 1 and len(raw_det) == len(raw_rand):
                iter_labels = [f"Iteration {k+1}" for k in range(len(raw_det))] + ["Overall Mean"]
                iter_sps = [raw_det[k] / raw_rand[k] for k in range(len(raw_det))]
                mean_sp = row_det['Mean_Time_s'] / row_rand['Mean_Time_s']
                all_sps = iter_sps + [mean_sp]
            else:
                iter_labels = [f"{primary_order} Order"]
                mean_sp = row_det['Mean_Time_s'] / row_rand['Mean_Time_s']
                all_sps = [mean_sp]

            bar_colors = ['#ef5350' if s >= 1.0 else '#42a5f5' for s in all_sps]
            if len(all_sps) > 1:
                bar_colors[-1] = '#c62828'

            x_pos = np.arange(len(iter_labels))
            bars = plt.bar(x_pos, all_sps, color=bar_colors, width=0.45, edgecolor='black', linewidth=1.2)

            for b_idx, bar in enumerate(bars):
                h = bar.get_height()
                pct_val = (h - 1.0) * 100.0
                sign_str = "+" if pct_val >= 0 else ""
                plt.text(bar.get_x() + bar.get_width()/2.0, h + 0.015,
                         f"{h:.3f}x\n({sign_str}{pct_val:.1f}%)",
                         ha='center', va='bottom', fontsize=9.5, fontweight='bold',
                         color='#b71c1c' if h >= 1.0 else '#0d47a1')

            plt.xticks(x_pos, iter_labels, fontsize=10.5, fontweight='bold')
            plt.ylabel('Speedup Ratio ($T_{det} / T_{rand}$)', fontsize=11, fontweight='bold')
            plt.title(f'Speedup Ratio Breakdown ($T_{{det}} / T_{{rand}}$) at N = {row_det["Num_Points"]:,}',
                      fontsize=12, fontweight='bold', pad=12)
            plt.ylim(0.88, max(all_sps) * 1.18)
    else:
        for order in ['Original', 'Sorted_Time']:
            sub_o = sp_df[sp_df['Input_Order'] == order].sort_values('Num_Points')
            if sub_o.empty:
                continue
            color = '#d62728' if order == 'Original' else '#e6a100'
            marker = 'o' if order == 'Original' else 's'
            mean_val = sub_o['Speedup'].mean()
            plt.plot(sub_o['Num_Points_M'], sub_o['Speedup'],
                     color=color, marker=marker, linewidth=2.2, markersize=7,
                     label=f"{order} Order (Mean Speedup = {mean_val:.3f}x)")

        plt.title('Speedup Ratio: Time(Deterministic) / Time(Randomized) vs. Dataset Size $N$', fontsize=12, fontweight='bold', pad=12)
        plt.xlabel('Number of Points $N$ (Millions)', fontsize=11, fontweight='bold')
        plt.ylabel('Speedup Ratio ($T_{det} / T_{rand}$)', fontsize=11, fontweight='bold')
        plt.ylim(0.90, 1.20)

    plt.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.92, fontsize=9.5)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, '10_speedup_plot.png'), dpi=300, bbox_inches='tight')
    plt.close()

    # 3. 11_speedup_heatmap.png
    if is_single_point:
        # Detailed iteration matrix heatmap
        plt.figure(figsize=(7.5, 4.8), dpi=300)
        orders_present = [o for o in ['Original', 'Sorted_Time'] if o in df['Input_Order'].values]
        primary_order = orders_present[0] if orders_present else df['Input_Order'].iloc[0]
        sub_det = df[(df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == primary_order)]
        sub_rand = df[(df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == primary_order)]

        if not sub_det.empty and not sub_rand.empty:
            row_det = sub_det.iloc[0]
            row_rand = sub_rand.iloc[0]
            raw_det = row_det['Raw_Times_s']
            raw_rand = row_rand['Raw_Times_s']

            hm_rows = []
            if len(raw_det) > 1 and len(raw_det) == len(raw_rand):
                for k in range(len(raw_det)):
                    t_d = raw_det[k]
                    t_r = raw_rand[k]
                    sp = t_d / t_r
                    hm_rows.append({
                        'Deterministic (s)': t_d,
                        'Randomized (s)': t_r,
                        'Diff (s)': t_d - t_r,
                        'Speedup (x)': sp
                    })
                hm_index = [f"Iteration {k+1}" for k in range(len(raw_det))] + ["Overall Mean"]
            else:
                hm_index = ["Overall Mean"]

            mean_d = row_det['Mean_Time_s']
            mean_r = row_rand['Mean_Time_s']
            hm_rows.append({
                'Deterministic (s)': mean_d,
                'Randomized (s)': mean_r,
                'Diff (s)': mean_d - mean_r,
                'Speedup (x)': mean_d / mean_r
            })

            hm_df = pd.DataFrame(hm_rows, index=hm_index)
            sns.heatmap(hm_df[['Speedup (x)']], annot=True, fmt='.3f', cmap='coolwarm',
                        vmin=0.95, vmax=1.08, linewidths=1.0, linecolor='white',
                        cbar_kws={'label': 'Speedup Ratio ($T_{det} / T_{rand}$)'})
            plt.title(f'Iteration Speedup Matrix ({primary_order} Order, N = {row_det["Num_Points"]:,})', fontsize=12, fontweight='bold', pad=12)
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, '11_speedup_heatmap.png'), dpi=300, bbox_inches='tight')
            plt.close()
    else:
        plt.figure(figsize=(6.5, 9.2), dpi=300)
        piv_sp = sp_df.pivot(index='Num_Points_M', columns='Input_Order', values='Speedup')
        piv_sp.index = [f"{x:.2f}M" for x in piv_sp.index]
        norm = mcolors.TwoSlopeNorm(vmin=0.92, vcenter=1.0, vmax=1.16)
        sns.heatmap(piv_sp, annot=True, fmt='.3f', cmap='coolwarm', norm=norm,
                    cbar_kws={'label': 'Speedup Ratio ($T_{det}/T_{rand}$)\n[Red: Randomized Faster | Blue: Deterministic Faster]'},
                    linewidths=0.5, linecolor='white')
        plt.title('Speedup Heatmap: $T_{det}/T_{rand}$\n(Red indicates Randomized is faster)', fontsize=12, fontweight='bold', pad=12)
        plt.xlabel('Input Order', fontsize=11, fontweight='bold')
        plt.ylabel('Dataset Size $N$ (Points)', fontsize=11, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '11_speedup_heatmap.png'), dpi=300, bbox_inches='tight')
        plt.close()

    # 4. 12_speedup_heatmap_binned.png
    plt.figure(figsize=(7.5, 5.0), dpi=300)
    if is_single_point:
        scorecard = []
        indices = []
        for (algo, order), r_grp in df.groupby(['Algorithm', 'Input_Order'], sort=False):
            r = r_grp.iloc[0]
            pts = int(r['Num_Points'])
            t_s = r['Mean_Time_s']
            reb = r['Mean_Rebuilds'] if 'Mean_Rebuilds' in r else 0.0
            md = r['Min_Distance_m'] if 'Min_Distance_m' in r else 0.0
            scorecard.append({
                'Mean Time (s)': round(t_s, 2),
                'Time (min)': round(t_s / 60.0, 2),
                'Throughput (kpts/s)': round((pts / t_s) / 1000.0, 2),
                'Mean Rebuilds': round(reb, 1),
                'Min Dist (m)': round(md, 4)
            })
            indices.append(f"{algo}\n({order})")
        sc_df = pd.DataFrame(scorecard, index=indices)
        sns.heatmap(sc_df, annot=True, fmt='g', cmap='Blues', linewidths=1.2, linecolor='white', cbar=False)
        plt.title(f'Benchmark Executive Scorecard (N = {int(df["Num_Points"].iloc[0]):,} Points)',
                  fontsize=11.5, fontweight='bold', pad=12)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '12_speedup_heatmap_binned.png'), dpi=300, bbox_inches='tight')
        plt.close()
    else:
        num_bins = min(6, len(sp_df['Num_Points'].unique()) // 2) if len(sp_df['Num_Points'].unique()) >= 6 else len(sp_df['Num_Points'].unique())
        if num_bins > 1:
            sp_df['Size_Bin'] = pd.qcut(sp_df['Num_Points_M'], q=num_bins)
            binned = sp_df.groupby(['Size_Bin', 'Input_Order'], observed=True)['Speedup'].mean().unstack()
            binned.index = [f"({b.left:.2f}, {b.right:.2f}]" for b in binned.index]

            norm_b = mcolors.TwoSlopeNorm(vmin=0.95, vcenter=1.0, vmax=1.10)
            sns.heatmap(binned, annot=True, fmt='.3f', cmap='coolwarm', norm=norm_b,
                        cbar_kws={'label': 'Mean Speedup Ratio ($T_{det}/T_{rand}$)\n[Red: Randomized Faster]'},
                        linewidths=1.0, linecolor='white')
            plt.title('Compact Speedup Heatmap by Size Quantiles\n(Red indicates Randomized is faster)', fontsize=12, fontweight='bold', pad=12)
            plt.xlabel('Input Order', fontsize=11, fontweight='bold')
            plt.ylabel('Dataset Size Range (Millions)', fontsize=11, fontweight='bold')
        else:
            piv_simple = sp_df.pivot_table(index='Num_Points_M', columns='Input_Order', values='Speedup')
            sns.heatmap(piv_simple, annot=True, fmt='.3f', cmap='coolwarm', vmin=0.95, vmax=1.10)
            plt.title('Speedup Matrix by Input Order', fontsize=12, fontweight='bold', pad=12)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '12_speedup_heatmap_binned.png'), dpi=300, bbox_inches='tight')
        plt.close()

def generate_summary_metrics_csv(df, out_dir):
    """
    Computes overall summary metrics across scenarios:
      Algorithm, Input_Order, Mean_Time, StdDev_Time, Min_Time, Max_Time, Mean_Rebuilds
    """
    rows = []
    for (algo, order), g in df.groupby(['Algorithm', 'Input_Order']):
        t_arr = g['Mean_Time_s']
        reb_arr = g['Mean_Rebuilds'] if 'Mean_Rebuilds' in g.columns else pd.Series([0.0])
        rows.append({
            'Algorithm': algo,
            'Input_Order': order,
            'Mean_Time': t_arr.mean(),
            'StdDev_Time': t_arr.std() if len(t_arr) > 1 else (g['StdDev_Time_s'].iloc[0] if 'StdDev_Time_s' in g.columns else 0.0),
            'Min_Time': t_arr.min(),
            'Max_Time': t_arr.max(),
            'Mean_Rebuilds': reb_arr.mean()
        })
    metrics_df = pd.DataFrame(rows)
    metrics_df.sort_values(['Algorithm', 'Input_Order'], inplace=True)
    metrics_df.to_csv(os.path.join(out_dir, 'summary_metrics.csv'), index=False)

def generate_bonus_iteration_breakdown(df, out_dir):
    """
    For multi-iteration benchmarks, generates:
      - 16_iteration_breakdown.png (Per-iteration timings, throughput, and rebuild counts)
    """
    is_single_point = (len(df['Num_Points'].unique()) == 1)
    has_raw = any(len(x) > 1 for x in df['Raw_Times_s'])
    if not (is_single_point and has_raw):
        return

    orders_present = [o for o in ['Original', 'Sorted_Time'] if o in df['Input_Order'].values]
    if not orders_present:
        return
    primary_order = orders_present[0]

    sub_det = df[(df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == primary_order)]
    sub_rand = df[(df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == primary_order)]
    if sub_det.empty or sub_rand.empty:
        return

    row_det = sub_det.iloc[0]
    row_rand = sub_rand.iloc[0]

    raw_det_t = row_det['Raw_Times_s']
    raw_rand_t = row_rand['Raw_Times_s']
    raw_det_r = row_det['Raw_Rebuilds_Parsed']
    raw_rand_r = row_rand['Raw_Rebuilds_Parsed']

    fig, axes = plt.subplots(1, 2, figsize=(13.0, 5.2), dpi=300)

    # 1. Execution Time per Iteration
    x = np.arange(len(raw_det_t))
    width = 0.35
    ax1 = axes[0]
    ax1.bar(x - width/2, raw_det_t, width, label='Deterministic Grid', color='#1f77b4', edgecolor='black', alpha=0.85)
    ax1.bar(x + width/2, raw_rand_t, width, label='Randomized Grid', color='#d62728', edgecolor='black', alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"Iteration {i+1}" for i in range(len(raw_det_t))], fontsize=10.5, fontweight='bold')
    ax1.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
    ax1.set_title('Per-Iteration Execution Time Comparison', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax1.set_ylim(0, max(max(raw_det_t), max(raw_rand_t)) * 1.2)

    for i in range(len(raw_det_t)):
        ax1.text(i - width/2, raw_det_t[i] + 30, f"{raw_det_t[i]:.1f}s", ha='center', fontsize=9, fontweight='bold')
        ax1.text(i + width/2, raw_rand_t[i] + 30, f"{raw_rand_t[i]:.1f}s", ha='center', fontsize=9, fontweight='bold')

    # 2. Rebuild Count per Iteration
    ax2 = axes[1]
    ax2.bar(x - width/2, raw_det_r, width, label='Deterministic Rebuilds', color='#2ca02c', edgecolor='black', alpha=0.85)
    ax2.bar(x + width/2, raw_rand_r, width, label='Randomized Rebuilds', color='#ff7f0e', edgecolor='black', alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"Iteration {i+1}" for i in range(len(raw_det_r))], fontsize=10.5, fontweight='bold')
    ax2.set_ylabel('Grid Rebuild Count', fontsize=11, fontweight='bold')
    ax2.set_title('Grid Rebuild Count per Iteration (Delta Shrinkages)', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax2.set_ylim(0, max(max(raw_det_r), max(raw_rand_r)) * 1.3)

    for i in range(len(raw_det_r)):
        ax2.text(i - width/2, raw_det_r[i] + 1, f"{raw_det_r[i]}", ha='center', fontsize=9.5, fontweight='bold')
        ax2.text(i + width/2, raw_rand_r[i] + 1, f"{raw_rand_r[i]}", ha='center', fontsize=9.5, fontweight='bold')

    fig.suptitle(f'100M Benchmark Multi-Iteration Deep Dive (N = {row_det["Num_Points"]:,})', fontsize=13, fontweight='bold')
    fig.tight_layout()
    fig.subplots_adjust(top=0.88)
    fig.savefig(os.path.join(out_dir, '16_iteration_breakdown.png'), dpi=300, bbox_inches='tight')
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description="OpenSky Closest-Pair Comprehensive Benchmark Suite Visualizer")
    parser.add_argument("csv_path", type=str, help="Path to input benchmark CSV file.")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory (optional).")
    args = parser.parse_args()

    csv_path = os.path.abspath(args.csv_path)
    if not os.path.isfile(csv_path):
        print(f"[Error] Specified CSV file does not exist: {csv_path}")
        sys.exit(1)

    # Establish output directory inside analyzer/ with versioning
    analyzer_root = os.path.dirname(os.path.abspath(__file__))
    if args.output_dir:
        target_dir = os.path.abspath(args.output_dir)
        os.makedirs(target_dir, exist_ok=True)
    else:
        target_dir = resolve_versioned_output_dir(analyzer_root, os.path.basename(csv_path))

    print("=" * 80)
    print("      OPENSKY BENCHMARK MASTER ANALYZER & VISUALIZATION ENGINE         ")
    print("=" * 80)
    print(f"Input CSV File     : {csv_path}")
    print(f"Output Directory   : {target_dir}")
    print("=" * 80)

    # 1. Copy input CSV into target folder
    dest_csv = os.path.join(target_dir, os.path.basename(csv_path))
    shutil.copy2(csv_path, dest_csv)
    print(f"[1/5] Copied CSV to: {dest_csv}")

    # 2. Load and preprocess
    df = load_and_preprocess_csv(dest_csv)
    print(f"[2/5] Loaded {len(df)} experiment rows.")

    # 3. Generate individual timing and 4-panel figures (01-04 & 4-panel)
    print("[3/5] Generating individual timing and complexity reference plots (01-04 & 4-panel)...")
    generate_individual_timing_plots(df, target_dir)

    # 4. Generate comparative plots (05-09)
    print("[4/5] Generating algorithm & input order comparative plots (05-09)...")
    generate_comparison_plots(df, target_dir)

    # 5. Generate speedup plots, heatmaps, and summary tables (10-12, CSVs & breakdown)
    print("[5/5] Generating speedup ratios, heatmaps, and statistical summaries (10-12 & CSVs)...")
    generate_speedup_artifacts(df, target_dir)
    generate_summary_metrics_csv(df, target_dir)
    generate_bonus_iteration_breakdown(df, target_dir)

    print("\n" + "=" * 80)
    print(" ANALYSIS COMPLETE! All artifacts generated successfully:")
    for f in sorted(os.listdir(target_dir)):
        sz = os.path.getsize(os.path.join(target_dir, f))
        print(f"  - {f:<42} ({sz/1024:.1f} KB)")
    print("=" * 80)

if __name__ == '__main__':
    main()
