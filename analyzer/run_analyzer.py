#!/usr/bin/env python3
"""
Benchmark Master Analyzer & Visualizer
======================================
Universal analyzer for Closest-Pair benchmarks across real-world (OpenSky)
and synthetic datasets (Normal Uniform & Adversarial).

Supports:
  - Single-dimensional benchmarks (e.g. 4D OpenSky multi-slice scaling or 100M benchmarks)
  - Multi-dimensional benchmarks (e.g. Synthetic 2D, 3D, 5D, 7D)
  - Arbitrary input orders (Original, Sorted_Time, Sorted_X_Axis, Ladder_of_Pairs, etc.)
  - Adaptive scale formatting (Thousands vs Millions, Linear vs Logarithmic scaling)

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
 Plus (for multi-iteration single-scale benchmarks):
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

DIM_PALETTE = {
    2: {'color': '#1f77b4', 'marker': 'o', 'linestyle': '-'},
    3: {'color': '#2ca02c', 'marker': 's', 'linestyle': '--'},
    5: {'color': '#ff7f0e', 'marker': '^', 'linestyle': '-.'},
    7: {'color': '#9467bd', 'marker': 'D', 'linestyle': ':'}
}

ALGO_COLORS = {
    'Deterministic Grid': '#1f77b4',
    'Randomized Grid': '#d62728'
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
    for col in ['Algorithm', 'Input_Order', 'Space_Type', 'Hour_Tag']:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            
    if 'Input_Order' in df.columns:
        df['Input_Order'] = df['Input_Order'].replace({'Sorted_Time_Axis': 'Sorted_Time'})
            
    is_operations = df['Space_Type'].str.contains('Operations', case=False, na=False).any() if 'Space_Type' in df.columns else False
    if is_operations:
        df['Mean_Time_s'] = df['Mean_Time_ms']
        df['Median_Time_s'] = df['Median_Time_ms'] if 'Median_Time_ms' in df.columns else df['Mean_Time_ms']
        df['StdDev_Time_s'] = df['StdDev_Time_ms'] if 'StdDev_Time_ms' in df.columns else 0.0
        df['Metric_Label'] = 'Algorithmic Work Units'
        df['Metric_Short'] = 'Work Units'
        df['Is_Operations'] = True
    else:
        if 'Mean_Time_ms' in df.columns:
            df['Mean_Time_s'] = df['Mean_Time_ms'] / 1000.0
        if 'Median_Time_ms' in df.columns:
            df['Median_Time_s'] = df['Median_Time_ms'] / 1000.0
        if 'StdDev_Time_ms' in df.columns:
            df['StdDev_Time_s'] = df['StdDev_Time_ms'] / 1000.0
        else:
            df['StdDev_Time_s'] = 0.0
        df['Metric_Label'] = 'Execution Time (s)'
        df['Metric_Short'] = 'Time (s)'
        df['Is_Operations'] = False

    if 'Min_Distance' in df.columns and 'Min_Distance_m' not in df.columns:
        df['Min_Distance_m'] = df['Min_Distance']

    if 'Dimensions' not in df.columns:
        df['Dimensions'] = 4

    # Determine scaling unit
    max_pts = df['Num_Points'].max()
    if max_pts >= 1e6:
        df['Num_Points_Scaled'] = df['Num_Points'] / 1e6
        df['Scale_Unit'] = 'M'
        df['Scale_Label'] = 'Number of Points $N$ (Millions)'
    else:
        df['Num_Points_Scaled'] = df['Num_Points'] / 1e3
        df['Scale_Unit'] = 'k'
        df['Scale_Label'] = 'Number of Points $N$ (Thousands)'

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

def get_palette_for_dataset(df):
    orders = list(dict.fromkeys(df['Input_Order'].dropna()))
    order1 = orders[0] if len(orders) > 0 else 'Original'
    order2 = orders[1] if len(orders) > 1 else 'Sorted'

    palette = {
        ('Deterministic Grid', order1): {
            'color': '#1f77b4', 'marker': 'o', 'linestyle': '-',
            'label': f'Deterministic Grid ({order1})'
        },
        ('Randomized Grid', order1): {
            'color': '#d62728', 'marker': '^', 'linestyle': '-.',
            'label': f'Randomized Grid ({order1})'
        }
    }
    if len(orders) > 1:
        palette[('Deterministic Grid', order2)] = {
            'color': '#2ca02c', 'marker': 's', 'linestyle': '--',
            'label': f'Deterministic Grid ({order2})'
        }
        palette[('Randomized Grid', order2)] = {
            'color': '#e6a100', 'marker': 'd', 'linestyle': ':',
            'label': f'Randomized Grid ({order2})'
        }
    return palette, order1, order2

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
    Generates Figures 01 through 04 and the combined 4-panel figure:
      01_timing_deterministic_original.png
      02_timing_deterministic_sorted.png
      03_timing_randomized_original.png
      04_timing_randomized_sorted.png
      timing_all_individual_4panel.png
    Supports both single-dimension datasets with reference curves and
    multi-dimension datasets with per-dimension curves.
    """
    palette, order1, order2 = get_palette_for_dataset(df)
    is_multi_dim = df['Dimensions'].nunique() > 1
    dims = sorted(df['Dimensions'].unique())
    scale_label = df['Scale_Label'].iloc[0]

    metric_lbl = df['Metric_Label'].iloc[0]
    metric_short = df['Metric_Short'].iloc[0]

    configs = [
        ('Deterministic Grid', order1, '01_timing_deterministic_original.png', f'Deterministic Grid ({order1} Order)'),
        ('Deterministic Grid', order2, '02_timing_deterministic_sorted.png', f'Deterministic Grid ({order2} Order)'),
        ('Randomized Grid', order1, '03_timing_randomized_original.png', f'Randomized Grid ({order1} Order)'),
        ('Randomized Grid', order2, '04_timing_randomized_sorted.png', f'Randomized Grid ({order2} Order)'),
    ]

    fig_4panel, axes_4panel = plt.subplots(2, 2, figsize=(14, 11), dpi=300)
    axes_flat = axes_4panel.flatten()

    for idx, (algo, order, fname, title) in enumerate(configs):
        sub = df[(df['Algorithm'] == algo) & (df['Input_Order'] == order)].copy()
        ax_panel = axes_flat[idx]

        if sub.empty:
            fig_ph, ax_ph = plt.subplots(figsize=(8.0, 5.8), dpi=300)
            reason_text = (
                f"Configuration: {algo} ({order})\n"
                "Not Evaluated in this benchmark dataset."
            )
            draw_placeholder_card(ax_ph, title, reason_text)
            fig_ph.tight_layout()
            fig_ph.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig_ph)

            draw_placeholder_card(ax_panel, title, "Not Evaluated in this Benchmark")
            continue

        fig_ind, ax_ind = plt.subplots(figsize=(8.0, 5.8), dpi=300)

        if is_multi_dim:
            # Multi-dimension plot: Plot a curve for each dimension
            has_extreme_spread = False
            y_vals_all = sub['Mean_Time_s'].to_numpy()
            if len(y_vals_all) > 0 and (np.nanmax(y_vals_all) / max(1e-4, np.nanmin(y_vals_all)) > 50):
                has_extreme_spread = True

            for d in dims:
                d_sub = sub[sub['Dimensions'] == d].sort_values('Num_Points')
                if d_sub.empty:
                    continue
                d_cfg = DIM_PALETTE.get(d, {'color': '#333333', 'marker': 'o', 'linestyle': '-'})
                
                # Standalone figure
                ax_ind.errorbar(
                    d_sub['Num_Points_Scaled'], d_sub['Mean_Time_s'], yerr=d_sub['StdDev_Time_s'],
                    fmt=d_cfg['marker'], color=d_cfg['color'], linestyle=d_cfg['linestyle'],
                    linewidth=2.2, markersize=7.5, capsize=4, capthick=1.5,
                    label=f'{d}D Space (Mean: {d_sub["Mean_Time_s"].mean():.1f} {metric_short})'
                )
                # 4-panel subplot
                ax_panel.errorbar(
                    d_sub['Num_Points_Scaled'], d_sub['Mean_Time_s'], yerr=d_sub['StdDev_Time_s'],
                    fmt=d_cfg['marker'], color=d_cfg['color'], linestyle=d_cfg['linestyle'],
                    linewidth=1.8, markersize=6.5, capsize=3, capthick=1.2,
                    label=f'{d}D'
                )

            if has_extreme_spread:
                ax_ind.set_yscale('log')
                ax_panel.set_yscale('log')
                ax_ind.set_ylabel(f'{metric_lbl} [Log Scale]', fontsize=11, fontweight='bold')
                ax_panel.set_ylabel(f'{metric_lbl} [Log Scale]', fontsize=10, fontweight='bold')
            else:
                ax_ind.set_ylabel(metric_lbl, fontsize=11, fontweight='bold')
                ax_panel.set_ylabel(metric_lbl, fontsize=10, fontweight='bold')

            ax_ind.set_title(title, fontsize=12.5, fontweight='bold', pad=12)
            ax_ind.set_xlabel(scale_label, fontsize=11, fontweight='bold')
            ax_ind.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.92, fontsize=9.5)

            ax_panel.set_title(title, fontsize=11, fontweight='bold')
            ax_panel.set_xlabel(scale_label, fontsize=10, fontweight='bold')
            ax_panel.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=8.5)

        else:
            # Single dimension dataset (OpenSky style): Plot points with theoretical reference curves
            sub.sort_values('Num_Points', inplace=True)
            x_pts = sub['Num_Points_Scaled'].to_numpy()
            y_pts = sub['Mean_Time_s'].to_numpy()
            y_err = sub['StdDev_Time_s'].to_numpy()
            x0, y0 = x_pts[0], y_pts[0]
            pcfg = palette.get((algo, order), {'color': '#1f77b4', 'marker': 'o', 'linestyle': '-'})

            is_single_pt = (len(np.unique(x_pts)) == 1)
            if is_single_pt:
                x_dense = np.linspace(max(0.1, x0 * 0.5), x0 * 1.3, 200)
            else:
                x_dense = np.linspace(x_pts.min(), x_pts.max(), 200)

            c1 = y0 / x0
            ref_lin = c1 * x_dense
            c2 = y0 / (x0 * np.log2(max(2.0, x0 * 1e3)))
            ref_nlogn = c2 * (x_dense * np.log2(np.maximum(2.0, x_dense * 1e3)))
            c3 = y0 / (x0 ** 2)
            ref_quad = c3 * (x_dense ** 2)

            for target_ax in [ax_ind, ax_panel]:
                target_ax.plot(x_dense, ref_lin, color='#7c4dff', linestyle='--', linewidth=1.8, label='Reference $O(n)$')
                target_ax.plot(x_dense, ref_nlogn, color='#0097a7', linestyle='-.', linewidth=1.8, label='Reference $O(n\\log n)$')
                target_ax.plot(x_dense, ref_quad, color='#78909c', linestyle=':', linewidth=1.8, label='Reference $O(n^2)$')
                target_ax.errorbar(x_pts, y_pts, yerr=y_err, fmt=pcfg['marker'],
                                   color=pcfg['color'], linewidth=2.0, markersize=7.5, capsize=4,
                                   label=f'Measured Time')

            ax_ind.set_title(title, fontsize=12.5, fontweight='bold', pad=12)
            ax_ind.set_xlabel(scale_label, fontsize=11, fontweight='bold')
            ax_ind.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            ax_ind.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.92, fontsize=9.0)

            ax_panel.set_title(title, fontsize=11, fontweight='bold')
            ax_panel.set_xlabel(scale_label, fontsize=10, fontweight='bold')
            ax_panel.set_ylabel('Execution Time (s)', fontsize=10, fontweight='bold')
            ax_panel.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.88, fontsize=8.0)

        fig_ind.tight_layout()
        fig_ind.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
        plt.close(fig_ind)

    fig_4panel.suptitle('Benchmark Dataset Size vs. Execution Time Analysis', fontsize=14, fontweight='bold', y=0.99)
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
    palette, order1, order2 = get_palette_for_dataset(df)
    is_multi_dim = df['Dimensions'].nunique() > 1
    dims = sorted(df['Dimensions'].unique())
    scale_label = df['Scale_Label'].iloc[0]

    # Helper for 05 & 06: Algorithm Comparison for a given order
    def plot_algo_comparison_for_order(order, fname, figure_title):
        sub = df[df['Input_Order'] == order].copy()
        if sub.empty:
            fig, ax = plt.subplots(figsize=(8.0, 5.5), dpi=300)
            draw_placeholder_card(ax, figure_title, f"Order '{order}' was not evaluated in this benchmark.")
            fig.tight_layout()
            fig.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig)
            return

        if is_multi_dim:
            # 2x2 multi-dimension faceted comparison
            fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.5), dpi=300)
            axes_flat = axes.flatten()

            for i, d in enumerate(dims):
                if i >= 4:
                    break
                ax = axes_flat[i]
                d_sub = sub[sub['Dimensions'] == d]
                
                det_sub = d_sub[d_sub['Algorithm'] == 'Deterministic Grid'].sort_values('Num_Points')
                rand_sub = d_sub[d_sub['Algorithm'] == 'Randomized Grid'].sort_values('Num_Points')

                has_extreme = False
                all_times = list(det_sub['Mean_Time_s']) + list(rand_sub['Mean_Time_s'])
                if len(all_times) > 0 and (max(all_times) / max(1e-4, min(all_times)) > 50):
                    has_extreme = True

                if not det_sub.empty:
                    ax.plot(det_sub['Num_Points_Scaled'], det_sub['Mean_Time_s'],
                            color=ALGO_COLORS['Deterministic Grid'], marker='o', linestyle='-',
                            linewidth=2.2, markersize=7, label='Deterministic Grid')
                if not rand_sub.empty:
                    ax.plot(rand_sub['Num_Points_Scaled'], rand_sub['Mean_Time_s'],
                            color=ALGO_COLORS['Randomized Grid'], marker='^', linestyle='--',
                            linewidth=2.2, markersize=7, label='Randomized Grid')

                if has_extreme:
                    ax.set_yscale('log')
                    ax.set_ylabel('Execution Time (s) [Log]', fontsize=10, fontweight='bold')
                else:
                    ax.set_ylabel('Execution Time (s)', fontsize=10, fontweight='bold')

                # Speedup annotation at max N
                common_pts = set(det_sub['Num_Points']).intersection(set(rand_sub['Num_Points']))
                if common_pts:
                    max_pt = max(common_pts)
                    t_det = det_sub[det_sub['Num_Points'] == max_pt]['Mean_Time_s'].iloc[0]
                    t_rand = rand_sub[rand_sub['Num_Points'] == max_pt]['Mean_Time_s'].iloc[0]
                    sp = t_det / t_rand if t_rand > 0 else 1.0
                    ax.text(0.05, 0.88, f"Max $N$ Speedup: {sp:.2f}x\n(Rand vs Det)",
                            transform=ax.transAxes, fontsize=9.5, fontweight='bold',
                            bbox=dict(boxstyle='round,pad=0.4', facecolor='#e8f5e9' if sp >= 1.0 else '#e3f2fd',
                                      edgecolor='#81c784' if sp >= 1.0 else '#90caf9', alpha=0.9))

                ax.set_title(f'Dimension: {d}D Space', fontsize=11.5, fontweight='bold')
                ax.set_xlabel(scale_label, fontsize=10, fontweight='bold')
                ax.legend(loc='lower right', frameon=True, facecolor='white', framealpha=0.9, fontsize=9)

            fig.suptitle(figure_title, fontsize=13.5, fontweight='bold', y=0.99)
            fig.tight_layout()
            fig.subplots_adjust(top=0.93)
            fig.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig)

        else:
            # Single-dimension comparison
            is_single_pt = (len(sub['Num_Points'].unique()) == 1)
            plt.figure(figsize=(8.5, 5.6), dpi=300)
            if is_single_pt:
                algos = sub['Algorithm'].tolist()
                means = sub['Mean_Time_s'].tolist()
                errs = sub['StdDev_Time_s'].tolist()
                colors = [ALGO_COLORS.get(a, '#1f77b4') for a in algos]
                x_pos = np.arange(len(algos))
                bars = plt.bar(x_pos, means, yerr=errs, capsize=6, color=colors, alpha=0.85, width=0.45, edgecolor='black')
                for bar in bars:
                    h = bar.get_height()
                    plt.text(bar.get_x() + bar.get_width()/2.0, h * 0.5, f"{h:.2f} s",
                             ha='center', va='center', color='white', fontweight='bold', fontsize=11)
                plt.xticks(x_pos, algos, fontsize=11, fontweight='bold')
                plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
                plt.title(f'{figure_title} (N = {sub["Num_Points"].iloc[0]:,})', fontsize=12, fontweight='bold', pad=14)
            else:
                for algo in ['Deterministic Grid', 'Randomized Grid']:
                    a_sub = sub[sub['Algorithm'] == algo].sort_values('Num_Points')
                    if a_sub.empty:
                        continue
                    pcfg = palette.get((algo, order), {'color': ALGO_COLORS.get(algo, '#333'), 'marker': 'o', 'linestyle': '-'})
                    plt.plot(a_sub['Num_Points_Scaled'], a_sub['Mean_Time_s'],
                             marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                             linewidth=2.4, markersize=7.5, label=f"{algo}")
                plt.title(figure_title, fontsize=12, fontweight='bold', pad=12)
                plt.xlabel(scale_label, fontsize=11, fontweight='bold')
                plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
                plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close()

    # 05. Algorithm Comparison (Order 1)
    plot_algo_comparison_for_order(order1, '05_compare_algo_original.png',
                                   f'Algorithm Comparison ({order1} Order): Deterministic vs. Randomized')

    # 06. Algorithm Comparison (Order 2)
    plot_algo_comparison_for_order(order2, '06_compare_algo_sorted.png',
                                   f'Algorithm Comparison ({order2} Order): Deterministic vs. Randomized')

    # 07. Combined Performance Comparison
    if is_multi_dim:
        fig_07, axes_07 = plt.subplots(2, 2, figsize=(14, 11), dpi=300)
        axes_07_flat = axes_07.flatten()
        for i, d in enumerate(dims):
            if i >= 4:
                break
            ax = axes_07_flat[i]
            d_df = df[df['Dimensions'] == d]
            
            all_times = d_df['Mean_Time_s'].dropna().tolist()
            has_extreme = len(all_times) > 0 and (max(all_times) / max(1e-4, min(all_times)) > 50)

            for (algo, o), pcfg in palette.items():
                sub_ao = d_df[(d_df['Algorithm'] == algo) & (d_df['Input_Order'] == o)].sort_values('Num_Points')
                if sub_ao.empty:
                    continue
                ax.plot(sub_ao['Num_Points_Scaled'], sub_ao['Mean_Time_s'],
                        marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                        linewidth=2.0, markersize=6.5, label=f"{algo} ({o})")

            if has_extreme:
                ax.set_yscale('log')
                ax.set_ylabel('Execution Time (s) [Log]', fontsize=10, fontweight='bold')
            else:
                ax.set_ylabel('Execution Time (s)', fontsize=10, fontweight='bold')

            ax.set_title(f'Dimension: {d}D Space', fontsize=11.5, fontweight='bold')
            ax.set_xlabel(scale_label, fontsize=10, fontweight='bold')
            ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.88, fontsize=8.5)

        fig_07.suptitle('Combined Performance Comparison: All Algorithms & Input Orders', fontsize=14, fontweight='bold', y=0.99)
        fig_07.tight_layout()
        fig_07.subplots_adjust(top=0.93)
        fig_07.savefig(os.path.join(out_dir, '07_compare_all_combined.png'), dpi=300, bbox_inches='tight')
        plt.close(fig_07)
    else:
        plt.figure(figsize=(8.5, 5.8), dpi=300)
        for (algo, order), pcfg in palette.items():
            sub = df[(df['Algorithm'] == algo) & (df['Input_Order'] == order)].sort_values('Num_Points')
            if sub.empty:
                continue
            plt.plot(sub['Num_Points_Scaled'], sub['Mean_Time_s'],
                     marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                     linewidth=2.2, markersize=7, label=f"{algo} ({order})")
        plt.title('Combined Performance Comparison: All Algorithms and Input Orders', fontsize=12.5, fontweight='bold', pad=12)
        plt.xlabel(scale_label, fontsize=11, fontweight='bold')
        plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
        plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '07_compare_all_combined.png'), dpi=300, bbox_inches='tight')
        plt.close()

    # Helper for 08 & 09: Input Order Comparison for a given algorithm
    def plot_order_comparison_for_algo(algo, fname, figure_title):
        sub = df[df['Algorithm'] == algo].copy()
        orders_present = list(dict.fromkeys(sub['Input_Order'].dropna()))
        
        if len(orders_present) < 2:
            fig, ax = plt.subplots(figsize=(8.0, 5.5), dpi=300)
            draw_placeholder_card(ax, figure_title, f"Only 1 input order was evaluated for {algo}.")
            fig.tight_layout()
            fig.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig)
            return

        if is_multi_dim:
            fig, axes = plt.subplots(2, 2, figsize=(13.5, 10.5), dpi=300)
            axes_flat = axes.flatten()
            for i, d in enumerate(dims):
                if i >= 4:
                    break
                ax = axes_flat[i]
                d_sub = sub[sub['Dimensions'] == d]
                
                all_times = d_sub['Mean_Time_s'].dropna().tolist()
                has_extreme = len(all_times) > 0 and (max(all_times) / max(1e-4, min(all_times)) > 50)

                for o in orders_present:
                    o_sub = d_sub[d_sub['Input_Order'] == o].sort_values('Num_Points')
                    if o_sub.empty:
                        continue
                    pcfg = palette.get((algo, o), {'color': '#333', 'marker': 'o', 'linestyle': '-'})
                    ax.plot(o_sub['Num_Points_Scaled'], o_sub['Mean_Time_s'],
                            color=pcfg['color'], marker=pcfg['marker'], linestyle=pcfg['linestyle'],
                            linewidth=2.2, markersize=7, label=f"{o} Order")

                if has_extreme:
                    ax.set_yscale('log')
                    ax.set_ylabel('Execution Time (s) [Log]', fontsize=10, fontweight='bold')
                else:
                    ax.set_ylabel('Execution Time (s)', fontsize=10, fontweight='bold')

                ax.set_title(f'Dimension: {d}D Space', fontsize=11.5, fontweight='bold')
                ax.set_xlabel(scale_label, fontsize=10, fontweight='bold')
                ax.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=9)

            fig.suptitle(figure_title, fontsize=13.5, fontweight='bold', y=0.99)
            fig.tight_layout()
            fig.subplots_adjust(top=0.93)
            fig.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close(fig)
        else:
            plt.figure(figsize=(8.0, 5.5), dpi=300)
            for o in orders_present:
                o_sub = sub[sub['Input_Order'] == o].sort_values('Num_Points')
                pcfg = palette.get((algo, o), {'color': '#333', 'marker': 'o', 'linestyle': '-'})
                plt.plot(o_sub['Num_Points_Scaled'], o_sub['Mean_Time_s'],
                         marker=pcfg['marker'], linestyle=pcfg['linestyle'], color=pcfg['color'],
                         linewidth=2.4, markersize=7.5, label=f"{algo} ({o})")
            plt.title(figure_title, fontsize=12, fontweight='bold', pad=12)
            plt.xlabel(scale_label, fontsize=11, fontweight='bold')
            plt.ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
            plt.legend(loc='upper left', frameon=True, facecolor='white', framealpha=0.9, fontsize=10)
            plt.tight_layout()
            plt.savefig(os.path.join(out_dir, fname), dpi=300, bbox_inches='tight')
            plt.close()

    # 08. Input Order Comparison (Deterministic Grid)
    plot_order_comparison_for_algo('Deterministic Grid', '08_compare_order_deterministic.png',
                                   f'Input Order Comparison: Deterministic Grid ({order1} vs. {order2})')

    # 09. Input Order Comparison (Randomized Grid)
    plot_order_comparison_for_algo('Randomized Grid', '09_compare_order_randomized.png',
                                   f'Input Order Comparison: Randomized Grid ({order1} vs. {order2})')

def generate_speedup_artifacts(df, out_dir):
    """
    Computes speedup ratios (T_det / T_rand) robustly and generates:
      - 10_speedup_plot.png
      - 11_speedup_heatmap.png
      - 12_speedup_heatmap_binned.png
      - summary_speedup.csv
    """
    palette, order1, order2 = get_palette_for_dataset(df)
    is_multi_dim = df['Dimensions'].nunique() > 1
    dims = sorted(df['Dimensions'].unique())
    orders_available = list(dict.fromkeys(df['Input_Order'].dropna()))
    scale_label = df['Scale_Label'].iloc[0]
    scale_unit = df['Scale_Unit'].iloc[0]

    # Calculate speedup per (Dimensions, Input_Order, Num_Points)
    speedup_records = []
    merge_keys = ['Num_Points']
    if 'Hour_Tag' in df.columns:
        merge_keys.append('Hour_Tag')
    elif 'Dataset' in df.columns:
        merge_keys.append('Dataset')
    
    for dim in dims:
        for order in orders_available:
            sub_det = df[(df['Dimensions'] == dim) & (df['Algorithm'] == 'Deterministic Grid') & (df['Input_Order'] == order)]
            sub_rand = df[(df['Dimensions'] == dim) & (df['Algorithm'] == 'Randomized Grid') & (df['Input_Order'] == order)]
            if sub_det.empty or sub_rand.empty:
                continue

            # Merge on Num_Points (and Hour_Tag / Dataset if available)
            det_cols = merge_keys + ['Num_Points_Scaled', 'Mean_Time_ms', 'Mean_Rebuilds']
            rand_cols = merge_keys + ['Mean_Time_ms', 'Mean_Rebuilds']
            det_cols = [c for c in det_cols if c in sub_det.columns]
            rand_cols = [c for c in rand_cols if c in sub_rand.columns]

            merged = pd.merge(sub_det[det_cols],
                              sub_rand[rand_cols],
                              on=merge_keys, suffixes=('_det', '_rand'))

            for _, row in merged.iterrows():
                t_det = row['Mean_Time_ms_det']
                t_rand = row['Mean_Time_ms_rand']
                sp = t_det / t_rand if t_rand > 0 else 1.0
                rec = {
                    'Dimensions': dim,
                    'Input_Order': order,
                    'Num_Points': int(row['Num_Points']),
                    'Num_Points_Scaled': row['Num_Points_Scaled'],
                    'Num_Points_M': row['Num_Points'] / 1e6,
                    'Det_Time_ms': t_det,
                    'Rand_Time_ms': t_rand,
                    'Det_Rebuilds': row.get('Mean_Rebuilds_det', 0.0),
                    'Rand_Rebuilds': row.get('Mean_Rebuilds_rand', 0.0),
                    'Speedup': sp
                }
                if 'Hour_Tag' in row:
                    rec['Hour_Tag'] = row['Hour_Tag']
                if 'Dataset' in row:
                    rec['Dataset'] = row['Dataset']
                speedup_records.append(rec)

    if not speedup_records:
        print("[Warning] No matching Deterministic & Randomized pairs found for speedup calculation.")
        return

    sp_df = pd.DataFrame(speedup_records)

    # 1. summary_speedup.csv
    summary_rows = []
    for order in orders_available:
        sub_o = sp_df[sp_df['Input_Order'] == order]
        if sub_o.empty:
            continue
        summary_rows.append({
            'Input_Order': order,
            'Mean_Speedup': sub_o['Speedup'].mean(),
            'Min_Speedup': sub_o['Speedup'].min(),
            'Max_Speedup': sub_o['Speedup'].max(),
            'Pct_Randomized_Faster': (sub_o['Speedup'] > 1.0).mean() * 100.0
        })
    summary_sp_df = pd.DataFrame(summary_rows)
    summary_sp_df.to_csv(os.path.join(out_dir, 'summary_speedup.csv'), index=False)

    # 2. 10_speedup_plot.png
    max_sp = sp_df['Speedup'].max()
    min_sp = sp_df['Speedup'].min()
    has_large_speedup = max_sp > 5.0

    if is_multi_dim:
        num_orders = len(orders_available)
        fig_10, axes_10 = plt.subplots(1, num_orders, figsize=(7.2 * num_orders, 5.5), dpi=300, squeeze=False)
        axes_10_flat = axes_10[0]

        for o_idx, order in enumerate(orders_available):
            ax = axes_10_flat[o_idx]
            sub_o = sp_df[sp_df['Input_Order'] == order]
            
            ax.axhline(1.0, color='black', linestyle='--', linewidth=1.5, label='Parity Baseline (1.0x)', zorder=2)
            
            for d in dims:
                sub_d = sub_o[sub_o['Dimensions'] == d].sort_values('Num_Points')
                if sub_d.empty:
                    continue
                dcfg = DIM_PALETTE.get(d, {'color': '#333', 'marker': 'o', 'linestyle': '-'})
                ax.plot(sub_d['Num_Points_Scaled'], sub_d['Speedup'],
                        color=dcfg['color'], marker=dcfg['marker'], linestyle=dcfg['linestyle'],
                        linewidth=2.2, markersize=7.5, label=f'{d}D Space (Mean: {sub_d["Speedup"].mean():.2f}x)', zorder=3)

            if has_large_speedup:
                ax.set_yscale('log')
                ax.set_ylabel('Speedup Ratio ($T_{det} / T_{rand}$) [Log Scale]', fontsize=11, fontweight='bold')
            else:
                ax.set_ylabel('Speedup Ratio ($T_{det} / T_{rand}$)', fontsize=11, fontweight='bold')
                ax.axhspan(1.0, max(1.2, max_sp * 1.05), color='#ffebee', alpha=0.35)
                ax.axhspan(min(0.8, min_sp * 0.95), 1.0, color='#e3f2fd', alpha=0.35)

            ax.set_title(f'Speedup Ratio vs. Dataset Size ({order} Order)', fontsize=12, fontweight='bold', pad=12)
            ax.set_xlabel(scale_label, fontsize=11, fontweight='bold')
            ax.legend(loc='best', frameon=True, facecolor='white', framealpha=0.9, fontsize=9.5)

        fig_10.suptitle('Speedup Ratio: Time(Deterministic) / Time(Randomized) vs. Dataset Scale', fontsize=13.5, fontweight='bold', y=0.99)
        fig_10.tight_layout()
        fig_10.subplots_adjust(top=0.90)
        fig_10.savefig(os.path.join(out_dir, '10_speedup_plot.png'), dpi=300, bbox_inches='tight')
        plt.close(fig_10)

    else:
        plt.figure(figsize=(8.5, 5.4), dpi=300)
        plt.axhline(1.0, color='black', linestyle='--', linewidth=1.5, label='Parity Baseline (1.0x)')
        for order in orders_available:
            sub_o = sp_df[sp_df['Input_Order'] == order].sort_values('Num_Points')
            if sub_o.empty:
                continue
            color = '#d62728' if order == order1 else '#e6a100'
            marker = 'o' if order == order1 else 's'
            mean_val = sub_o['Speedup'].mean()
            plt.plot(sub_o['Num_Points_Scaled'], sub_o['Speedup'],
                     color=color, marker=marker, linewidth=2.2, markersize=7,
                     label=f"{order} Order (Mean Speedup = {mean_val:.3f}x)")
        plt.title('Speedup Ratio: Time(Deterministic) / Time(Randomized) vs. Dataset Size $N$', fontsize=12, fontweight='bold', pad=12)
        plt.xlabel(scale_label, fontsize=11, fontweight='bold')
        plt.ylabel('Speedup Ratio ($T_{det} / T_{rand}$)', fontsize=11, fontweight='bold')
        plt.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.92, fontsize=9.5)
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '10_speedup_plot.png'), dpi=300, bbox_inches='tight')
        plt.close()

    # 3. 11_speedup_heatmap.png
    if is_multi_dim:
        num_orders = len(orders_available)
        fig_11, axes_11 = plt.subplots(1, num_orders, figsize=(7.0 * num_orders, 5.2), dpi=300, squeeze=False)
        axes_11_flat = axes_11[0]

        for o_idx, order in enumerate(orders_available):
            ax = axes_11_flat[o_idx]
            sub_o = sp_df[sp_df['Input_Order'] == order]
            if sub_o.empty:
                continue

            # Pivot: Dimensions (rows) vs Num_Points (cols)
            piv = sub_o.pivot_table(index='Dimensions', columns='Num_Points', values='Speedup', aggfunc='mean')
            # Sort dimensions descending for intuitive heatmap display
            piv = piv.reindex(sorted(piv.index, reverse=True))
            
            # Format column labels
            col_labels = [f"{int(c/1e3)}k" if c < 1e6 else f"{c/1e6:.1f}M" for c in piv.columns]
            piv.columns = col_labels
            piv.index = [f"{d}D" for d in piv.index]

            if has_large_speedup:
                norm = mcolors.LogNorm(vmin=max(0.8, min_sp), vmax=max_sp)
                cmap = 'YlOrRd'
            else:
                norm = mcolors.TwoSlopeNorm(vmin=max(0.5, min(0.9, min_sp)), vcenter=1.0, vmax=max(1.1, max_sp))
                cmap = 'coolwarm'

            sns.heatmap(piv, annot=True, fmt='.2f' if has_large_speedup else '.3f',
                        cmap=cmap, norm=norm, ax=ax, linewidths=1.0, linecolor='white',
                        cbar_kws={'label': 'Speedup Ratio ($T_{det}/T_{rand}$)'})
            ax.set_title(f'Speedup Matrix ({order} Order)', fontsize=12, fontweight='bold', pad=12)
            ax.set_xlabel('Dataset Size $N$', fontsize=11, fontweight='bold')
            ax.set_ylabel('Dimensions', fontsize=11, fontweight='bold')

        fig_11.suptitle('Speedup Heatmap: Randomized Speedup Over Deterministic Grid', fontsize=13.5, fontweight='bold', y=0.99)
        fig_11.tight_layout()
        fig_11.subplots_adjust(top=0.88)
        fig_11.savefig(os.path.join(out_dir, '11_speedup_heatmap.png'), dpi=300, bbox_inches='tight')
        plt.close(fig_11)

    else:
        has_hours = 'Hour_Tag' in sp_df.columns
        has_dataset = 'Dataset' in sp_df.columns

        if has_hours:
            def format_tag(row):
                tag = str(row['Hour_Tag']).replace('states_', '').replace('_4d', '')
                pts = row['Num_Points']
                pts_str = f"{pts/1e6:.2f}M" if pts >= 1e6 else f"{int(pts/1e3)}k"
                return f"{tag} ({pts_str})"
            sp_df['Row_Label'] = sp_df.apply(format_tag, axis=1)
            y_col = 'Row_Label'
            y_label = 'Surveillance Hour (UTC) & Scale'
            fig_height = max(7.0, min(24.0, len(sp_df['Row_Label'].unique()) * 0.30 + 2.0))
        elif has_dataset:
            sp_df['Row_Label'] = sp_df['Dataset'].astype(str)
            y_col = 'Row_Label'
            y_label = 'Dataset'
            fig_height = max(6.0, min(24.0, len(sp_df['Row_Label'].unique()) * 0.35 + 2.0))
        else:
            sp_df['Row_Label'] = [f"{x:.2f}M" if scale_unit == 'M' else f"{x:.0f}k" for x in sp_df['Num_Points_Scaled']]
            y_col = 'Row_Label'
            y_label = f'Dataset Size $N$ ({scale_unit})'
            fig_height = max(6.0, len(sp_df['Row_Label'].unique()) * 0.35 + 2.0)

        plt.figure(figsize=(7.5, fig_height), dpi=300)
        piv_sp = sp_df.pivot_table(index=y_col, columns='Input_Order', values='Speedup', aggfunc='mean')
        
        v_min = min(0.9, sp_df['Speedup'].min())
        v_max = max(1.1, sp_df['Speedup'].max())
        if v_min < 1.0 and v_max > 1.0:
            norm = mcolors.TwoSlopeNorm(vmin=v_min, vcenter=1.0, vmax=v_max)
        else:
            norm = None

        sns.heatmap(piv_sp, annot=True, fmt='.3f', cmap='coolwarm', norm=norm,
                    cbar_kws={'label': 'Speedup Ratio ($T_{det}/T_{rand}$)\n[Red: Randomized Faster | Blue: Deterministic Faster]'},
                    linewidths=0.5, linecolor='white')
        plt.title('Speedup Heatmap: $T_{det}/T_{rand}$\n(Red indicates Randomized is faster)', fontsize=12, fontweight='bold', pad=12)
        plt.xlabel('Input Order', fontsize=11, fontweight='bold')
        plt.ylabel(y_label, fontsize=11, fontweight='bold')
        plt.tight_layout()
        plt.savefig(os.path.join(out_dir, '11_speedup_heatmap.png'), dpi=300, bbox_inches='tight')
        plt.close()

    # 4. 12_speedup_heatmap_binned.png (Executive Scorecard)
    plt.figure(figsize=(10.0, max(5.5, len(df.groupby(['Dimensions', 'Input_Order', 'Algorithm'])) * 0.32)), dpi=300)
    scorecard = []
    indices = []
    
    group_cols = ['Dimensions', 'Input_Order', 'Algorithm'] if is_multi_dim else ['Input_Order', 'Algorithm']
    for grp_keys, r_grp in df.groupby(group_cols, sort=False):
        mean_t = r_grp['Mean_Time_s'].mean()
        pts_mean = r_grp['Num_Points'].mean()
        reb_mean = r_grp['Mean_Rebuilds'].mean() if 'Mean_Rebuilds' in r_grp.columns else 0.0
        
        if is_multi_dim:
            d_val, ord_val, alg_val = grp_keys
            # Find matching speedup
            sp_sub = sp_df[(sp_df['Dimensions'] == d_val) & (sp_df['Input_Order'] == ord_val)]
            sp_val = sp_sub['Speedup'].mean() if not sp_sub.empty else 1.0
            indices.append(f"{d_val}D | {alg_val[:5]}. | {ord_val[:10]}")
        else:
            ord_val, alg_val = grp_keys
            sp_sub = sp_df[sp_df['Input_Order'] == ord_val]
            sp_val = sp_sub['Speedup'].mean() if not sp_sub.empty else 1.0
            indices.append(f"{alg_val} ({ord_val})")

        scorecard.append({
            'Mean Time (s)': round(mean_t, 3),
            'Throughput (kpts/s)': round((pts_mean / max(1e-4, mean_t)) / 1000.0, 1),
            'Mean Rebuilds': round(reb_mean, 1),
            'Speedup vs Det (x)': round(sp_val, 2) if 'Randomized' in alg_val else 1.0
        })

    sc_df = pd.DataFrame(scorecard, index=indices)
    sns.heatmap(sc_df, annot=True, fmt='g', cmap='Blues', linewidths=1.0, linecolor='white', cbar=False)
    plt.title('Benchmark Executive Scorecard: Performance & Complexity Summary', fontsize=12, fontweight='bold', pad=12)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, '12_speedup_heatmap_binned.png'), dpi=300, bbox_inches='tight')
    plt.close()

def generate_summary_metrics_csv(df, out_dir):
    """
    Computes overall summary metrics across scenarios:
      Algorithm, Input_Order, Mean_Time, StdDev_Time, Min_Time, Max_Time, Mean_Rebuilds
    """
    rows = []
    is_multi_dim = df['Dimensions'].nunique() > 1
    group_cols = ['Dimensions', 'Algorithm', 'Input_Order'] if is_multi_dim else ['Algorithm', 'Input_Order']

    for grp_keys, g in df.groupby(group_cols):
        t_arr = g['Mean_Time_s']
        reb_arr = g['Mean_Rebuilds'] if 'Mean_Rebuilds' in g.columns else pd.Series([0.0])
        
        row_dict = {}
        if is_multi_dim:
            row_dict['Dimensions'] = grp_keys[0]
            row_dict['Algorithm'] = grp_keys[1]
            row_dict['Input_Order'] = grp_keys[2]
        else:
            row_dict['Algorithm'] = grp_keys[0]
            row_dict['Input_Order'] = grp_keys[1]

        row_dict.update({
            'Mean_Time': t_arr.mean(),
            'StdDev_Time': t_arr.std() if len(t_arr) > 1 else (g['StdDev_Time_s'].iloc[0] if 'StdDev_Time_s' in g.columns else 0.0),
            'Min_Time': t_arr.min(),
            'Max_Time': t_arr.max(),
            'Mean_Rebuilds': reb_arr.mean()
        })
        rows.append(row_dict)

    metrics_df = pd.DataFrame(rows)
    metrics_df.to_csv(os.path.join(out_dir, 'summary_metrics.csv'), index=False)

def generate_bonus_iteration_breakdown(df, out_dir):
    """
    For multi-iteration benchmarks at a single scale, generates:
      - 16_iteration_breakdown.png (Per-iteration timings and rebuild counts)
    """
    is_single_point = (len(df['Num_Points'].unique()) == 1) and (df['Dimensions'].nunique() == 1)
    has_raw = any(len(x) > 1 for x in df['Raw_Times_s'])
    if not (is_single_point and has_raw):
        return

    orders_present = list(dict.fromkeys(df['Input_Order'].dropna()))
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
    x = np.arange(len(raw_det_t))
    width = 0.35

    ax1 = axes[0]
    ax1.bar(x - width/2, raw_det_t, width, label='Deterministic Grid', color='#1f77b4', edgecolor='black', alpha=0.85)
    ax1.bar(x + width/2, raw_rand_t, width, label='Randomized Grid', color='#d62728', edgecolor='black', alpha=0.85)
    ax1.set_xticks(x)
    ax1.set_xticklabels([f"Iter {i+1}" for i in range(len(raw_det_t))], fontsize=10.5, fontweight='bold')
    ax1.set_ylabel('Execution Time (s)', fontsize=11, fontweight='bold')
    ax1.set_title('Per-Iteration Execution Time Comparison', fontsize=12, fontweight='bold')
    ax1.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax1.set_ylim(0, max(max(raw_det_t), max(raw_rand_t)) * 1.2)

    ax2 = axes[1]
    ax2.bar(x - width/2, raw_det_r, width, label='Deterministic Rebuilds', color='#2ca02c', edgecolor='black', alpha=0.85)
    ax2.bar(x + width/2, raw_rand_r, width, label='Randomized Rebuilds', color='#ff7f0e', edgecolor='black', alpha=0.85)
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"Iter {i+1}" for i in range(len(raw_det_r))], fontsize=10.5, fontweight='bold')
    ax2.set_ylabel('Grid Rebuild Count', fontsize=11, fontweight='bold')
    ax2.set_title('Grid Rebuild Count per Iteration', fontsize=12, fontweight='bold')
    ax2.legend(loc='upper right', frameon=True, facecolor='white', framealpha=0.9)
    ax2.set_ylim(0, max(max(raw_det_r), max(raw_rand_r)) * 1.3)

    fig.suptitle(f'Iteration Deep Dive (N = {row_det["Num_Points"]:,})', fontsize=13, fontweight='bold')
    fig.tight_layout()
    fig.subplots_adjust(top=0.88)
    fig.savefig(os.path.join(out_dir, '16_iteration_breakdown.png'), dpi=300, bbox_inches='tight')
    plt.close(fig)

def main():
    parser = argparse.ArgumentParser(description="Closest-Pair Benchmark Suite Master Analyzer & Visualizer")
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
    print("         BENCHMARK MASTER ANALYZER & VISUALIZATION ENGINE              ")
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
    print(f"[2/5] Loaded {len(df)} experiment rows. Dimensions: {sorted(df['Dimensions'].unique())}, Orders: {list(df['Input_Order'].unique())}")

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
