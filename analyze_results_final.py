#!/usr/bin/env python3
"""
analyze_results_final.py

Generates publication-quality benchmark plots for experiment_results_final.csv.
Outputs are stored in results_final/ organized by category:
  1. Single Curves with O(n), O(n log n), O(n^2) complexity reference lines
  2. Dimension Scaling for each algorithm and order
  3. Algorithm Comparison (Deterministic vs. Randomized) for each dimension and order
  4. Input Order Comparison for each dimension and algorithm
  5. Summary Visualizations (Speedup heatmap & empirical exponent plots)
  6. HTML Gallery for easy interactive visual browsing

Handles varying point limits (e.g. 9D normal capped at 500k) dynamically.
"""

import os
import sys
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import seaborn as sns

# Global styling configuration for clean, modern aesthetic
plt.rcParams.update({
    'font.size': 11,
    'axes.labelsize': 12,
    'axes.titlesize': 13,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.titlesize': 14,
    'lines.linewidth': 2.0,
    'lines.markersize': 7,
    'grid.alpha': 0.4,
    'grid.linestyle': '--'
})

ALGO_COLORS = {
    'Deterministic Grid': '#1f77b4',  # Deep blue
    'Randomized Grid': '#ff7f0e'     # Vivid orange
}

DIM_COLORS = {
    2: '#2ca02c',  # Green
    3: '#1f77b4',  # Blue
    5: '#9467bd',  # Purple
    7: '#d62728',  # Red
    9: '#e377c2'   # Pink/Magenta
}

ORDER_COLORS = {
    'original': '#1f77b4',
    'sorted': '#2ca02c',
    'adversarial': '#d62728'
}


def load_dataset(csv_path):
    """
    Efficiently load only required columns from the benchmark CSV,
    ignoring raw timing/rebuild/memory array strings.
    Deduplicates re-runs by keeping the latest record.
    """
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"Source file not found: {csv_path}")

    use_cols = [
        'Timestamp', 'Space_Type', 'Dimensions', 'Num_Points', 'Input_Order',
        'Algorithm', 'Mean_Time_ms', 'Median_Time_ms', 'StdDev_Time_ms',
        'Mean_Peak_Memory_MB', 'Median_Peak_Memory_MB', 'StdDev_Peak_Memory_MB'
    ]

    print(f"Loading data from {csv_path}...")
    df = pd.read_csv(csv_path, usecols=use_cols)

    # Clean whitespace in strings
    df['Space_Type'] = df['Space_Type'].astype(str).str.strip()
    df['Input_Order'] = df['Input_Order'].astype(str).str.strip()
    df['Algorithm'] = df['Algorithm'].astype(str).str.strip()

    # Standardize order names
    def map_order_key(row):
        space = row['Space_Type'].lower()
        order = row['Input_Order'].lower()
        if 'adversarial' in space or 'ladder' in order:
            return 'adversarial'
        if 'sorted' in order:
            return 'sorted'
        return 'original'

    df['Order_Key'] = df.apply(map_order_key, axis=1)

    def map_algo_key(algo_name):
        return 'deterministic' if 'det' in algo_name.lower() else 'randomized'

    df['Algo_Key'] = df['Algorithm'].apply(map_algo_key)

    # Deduplicate repeated runs, keeping the latest timestamp
    initial_len = len(df)
    df['Timestamp'] = pd.to_datetime(df['Timestamp'], errors='coerce')
    df = df.sort_values('Timestamp').drop_duplicates(
        subset=['Dimensions', 'Space_Type', 'Input_Order', 'Num_Points', 'Algorithm'],
        keep='last'
    ).sort_values(['Dimensions', 'Order_Key', 'Algorithm', 'Num_Points']).reset_index(drop=True)

    print(f"Loaded {len(df)} records (deduplicated from {initial_len}).")
    return df


def fit_power_law(x_vals, y_vals):
    """Fit y = a * x^alpha in log-log space."""
    x = np.array(x_vals, dtype=float)
    y = np.array(y_vals, dtype=float)
    valid = (x > 0) & (y > 0)
    if np.sum(valid) >= 2:
        try:
            poly = np.polyfit(np.log(x[valid]), np.log(y[valid]), 1)
            alpha = poly[0]
            prefactor = np.exp(poly[1])
            return alpha, prefactor
        except Exception:
            return None, None
    return None, None


# =====================================================================
# CATEGORY 1: Single Curves with Complexity Reference Lines
# =====================================================================
def generate_category1_single_curves(df, base_dir):
    """
    Plots Time vs N and Memory vs N for each (Dim, Order, Algorithm) tuple.
    Includes theoretical reference lines:
      - For Time: O(n), O(n log n), O(n^2) anchored at initial measurement
      - For Memory: O(n) anchored at initial measurement
    """
    time_dir = os.path.join(base_dir, "1_single_curves", "time")
    mem_dir = os.path.join(base_dir, "1_single_curves", "memory")
    os.makedirs(time_dir, exist_ok=True)
    os.makedirs(mem_dir, exist_ok=True)

    combinations = df[['Dimensions', 'Order_Key', 'Algo_Key', 'Algorithm', 'Input_Order', 'Space_Type']].drop_duplicates()
    saved_time = []
    saved_mem = []

    for _, row in combinations.iterrows():
        dim = int(row['Dimensions'])
        order_key = row['Order_Key']
        algo_key = row['Algo_Key']
        algo_name = row['Algorithm']
        order_name = row['Input_Order']
        space_name = row['Space_Type']

        sub = df[(df['Dimensions'] == dim) & 
                 (df['Order_Key'] == order_key) & 
                 (df['Algo_Key'] == algo_key)].sort_values('Num_Points')

        if len(sub) == 0:
            continue

        n_pts = sub['Num_Points'].to_numpy(dtype=float)
        mean_time = sub['Mean_Time_ms'].to_numpy(dtype=float)
        std_time = sub['StdDev_Time_ms'].to_numpy(dtype=float)
        mean_mem = sub['Mean_Peak_Memory_MB'].to_numpy(dtype=float)
        std_mem = sub['StdDev_Peak_Memory_MB'].to_numpy(dtype=float)

        prefix = f"{dim}D_{order_key}_{algo_key}"
        color = ALGO_COLORS.get(algo_name, '#1f77b4')

        # -------------------------------------------------------------
        # 1. TIME PLOT
        # -------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(8.5, 6), dpi=180)
        
        # Empirical Power law fit
        alpha, prefactor = fit_power_law(n_pts, mean_time)
        fit_label = f"Empirical Fit: O(n^{alpha:.2f})" if alpha is not None else "Empirical Fit"

        # Reference curves anchored at first data point (n0, y0)
        n0 = n_pts[0]
        y0 = mean_time[0]
        ref_n = np.linspace(n_pts[0], n_pts[-1], 200)
        ref_on = y0 * (ref_n / n0)
        ref_onlogn = y0 * (ref_n * np.log2(ref_n)) / (n0 * np.log2(n0))
        ref_on2 = y0 * (ref_n / n0) ** 2

        # Plot theoretical lines
        ax.plot(ref_n, ref_on, ':', color='#2ca02c', alpha=0.85, linewidth=1.8, label="O(n) Reference")
        ax.plot(ref_n, ref_onlogn, '-.', color='#8c564b', alpha=0.85, linewidth=1.8, label="O(n log n) Reference")
        ax.plot(ref_n, ref_on2, '--', color='#d62728', alpha=0.75, linewidth=1.6, label="O(n²) Reference")

        # Plot empirical fit line if available
        if alpha is not None and prefactor is not None:
            ax.plot(ref_n, prefactor * (ref_n ** alpha), '-', color='#17becf', alpha=0.9, linewidth=1.8, label=fit_label)

        # Plot observed data
        ax.errorbar(n_pts, mean_time, yerr=std_time, fmt='o-', color=color,
                     ecolor=color, elinewidth=1.5, capsize=4, capthick=1.5,
                     markersize=7, label=f"Observed: {algo_name}", zorder=5)

        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel("Number of Points (n)", fontweight='bold')
        ax.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax.set_title(f"Time vs. n: {dim}D | {order_name} ({space_name}) | {algo_name}", fontweight='bold')
        ax.grid(True, which="both", ls=":", alpha=0.5)
        ax.legend(loc="best", frameon=True, framealpha=0.9)

        # Formatter for log ticks
        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))
        fig.tight_layout()

        time_filepath = os.path.join(time_dir, f"{prefix}.png")
        fig.savefig(time_filepath)
        plt.close(fig)
        saved_time.append(time_filepath)

        # -------------------------------------------------------------
        # 2. MEMORY PLOT
        # -------------------------------------------------------------
        fig, ax = plt.subplots(figsize=(8.5, 6), dpi=180)

        # Fit memory scaling exponent
        beta, mem_prefactor = fit_power_law(n_pts, mean_mem)
        mem_fit_label = f"Empirical Fit: O(n^{beta:.2f})" if beta is not None else "Empirical Fit"

        # Linear memory reference anchored at n0
        mem_n0 = n_pts[0]
        mem_y0 = mean_mem[0]
        ref_mem_on = mem_y0 * (ref_n / mem_n0)

        ax.plot(ref_n, ref_mem_on, ':', color='#2ca02c', linewidth=2.0, label="O(n) Linear Memory Reference")
        if beta is not None and mem_prefactor is not None:
            ax.plot(ref_n, mem_prefactor * (ref_n ** beta), '-', color='#17becf', linewidth=1.8, label=mem_fit_label)

        ax.errorbar(n_pts, mean_mem, yerr=std_mem, fmt='s-', color=color,
                     ecolor=color, elinewidth=1.5, capsize=4, capthick=1.5,
                     markersize=7, label=f"Observed: {algo_name}", zorder=5)

        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_xlabel("Number of Points (n)", fontweight='bold')
        ax.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax.set_title(f"Peak Memory vs. n: {dim}D | {order_name} ({space_name}) | {algo_name}", fontweight='bold')
        ax.grid(True, which="both", ls=":", alpha=0.5)
        ax.legend(loc="best", frameon=True, framealpha=0.9)

        ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))
        fig.tight_layout()

        mem_filepath = os.path.join(mem_dir, f"{prefix}.png")
        fig.savefig(mem_filepath)
        plt.close(fig)
        saved_mem.append(mem_filepath)

    print(f"Generated {len(saved_time)} Category 1 time plots and {len(saved_mem)} memory plots.")
    return saved_time, saved_mem


# =====================================================================
# CATEGORY 2: Dimension Scaling for each Algorithm and Order
# =====================================================================
def generate_category2_dimension_scaling(df, base_dir):
    """
    For each (algo, order), compares how the algorithm scales with dimensions (2D..9D).
    Creates 2-panel plots:
      Left Panel: Metric vs. n across dimensions (curves for D=2, 3, 5, 7, 9)
      Right Panel: Metric vs. Dimension for fixed point counts (D on x-axis)
    """
    time_dir = os.path.join(base_dir, "2_dimension_scaling", "time")
    mem_dir = os.path.join(base_dir, "2_dimension_scaling", "memory")
    os.makedirs(time_dir, exist_ok=True)
    os.makedirs(mem_dir, exist_ok=True)

    combos = df[['Algo_Key', 'Order_Key', 'Algorithm', 'Input_Order', 'Space_Type']].drop_duplicates()
    saved_time = []
    saved_mem = []

    for _, row in combos.iterrows():
        algo_key = row['Algo_Key']
        order_key = row['Order_Key']
        algo_name = row['Algorithm']
        order_name = row['Input_Order']
        space_name = row['Space_Type']

        sub = df[(df['Algo_Key'] == algo_key) & (df['Order_Key'] == order_key)]
        if sub.empty:
            continue

        prefix = f"{algo_key}_{order_key}_dim_scaling"
        dims = sorted(sub['Dimensions'].unique())

        # Determine points available for cross-dimension comparison
        # (For normal space, 9D is capped at 500k, so compare up to 500k to include all dims)
        common_n_pts = sorted(sub[sub['Dimensions'] == max(dims)]['Num_Points'].unique())
        # Pick representative point sizes
        if len(common_n_pts) >= 4:
            eval_n = [common_n_pts[0], common_n_pts[len(common_n_pts)//2], common_n_pts[-1]]
        else:
            eval_n = common_n_pts

        # -------------------------------------------------------------
        # 1. TIME vs DIMENSION SCALING (2 Panels)
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), dpi=180)

        # Panel 1: Time vs n for each dimension
        for d in dims:
            d_sub = sub[sub['Dimensions'] == d].sort_values('Num_Points')
            color = DIM_COLORS.get(d, '#333333')
            ax1.plot(d_sub['Num_Points'], d_sub['Mean_Time_ms'], marker='o',
                     color=color, linewidth=2.0, label=f"D = {d}")

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel("Number of Points (n)", fontweight='bold')
        ax1.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax1.set_title(f"Time vs. n Across Dimensions\n[{algo_name} | {order_name}]", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(title="Dimensions", loc="best")
        ax1.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        # Panel 2: Time vs Dimension for fixed n
        n_palette = sns.color_palette("rocket", len(eval_n))
        for idx, n_val in enumerate(eval_n):
            n_sub = sub[sub['Num_Points'] == n_val].sort_values('Dimensions')
            if not n_sub.empty:
                ax2.plot(n_sub['Dimensions'], n_sub['Mean_Time_ms'], marker='s',
                         color=n_palette[idx], linewidth=2.2, label=f"n = {int(n_val):,d}")

        ax2.set_yscale('log')
        ax2.set_xlabel("Dimension (D)", fontweight='bold')
        ax2.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax2.set_xticks(dims)
        ax2.set_title(f"Time vs. Dimension D (Fixed n)\n[{algo_name} | {order_name}]", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(title="Point Size (n)", loc="best")

        fig.suptitle(f"Dimension Scaling Analysis: {algo_name} ({order_name} / {space_name})", fontweight='bold', fontsize=14)
        fig.tight_layout()

        time_filepath = os.path.join(time_dir, f"{prefix}.png")
        fig.savefig(time_filepath)
        plt.close(fig)
        saved_time.append(time_filepath)

        # -------------------------------------------------------------
        # 2. MEMORY vs DIMENSION SCALING (2 Panels)
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), dpi=180)

        # Panel 1: Memory vs n for each dimension
        for d in dims:
            d_sub = sub[sub['Dimensions'] == d].sort_values('Num_Points')
            color = DIM_COLORS.get(d, '#333333')
            ax1.plot(d_sub['Num_Points'], d_sub['Mean_Peak_Memory_MB'], marker='o',
                     color=color, linewidth=2.0, label=f"D = {d}")

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel("Number of Points (n)", fontweight='bold')
        ax1.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax1.set_title(f"Memory vs. n Across Dimensions\n[{algo_name} | {order_name}]", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(title="Dimensions", loc="best")
        ax1.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        # Panel 2: Memory vs Dimension for fixed n
        for idx, n_val in enumerate(eval_n):
            n_sub = sub[sub['Num_Points'] == n_val].sort_values('Dimensions')
            if not n_sub.empty:
                ax2.plot(n_sub['Dimensions'], n_sub['Mean_Peak_Memory_MB'], marker='s',
                         color=n_palette[idx], linewidth=2.2, label=f"n = {int(n_val):,d}")

        ax2.set_xlabel("Dimension (D)", fontweight='bold')
        ax2.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax2.set_xticks(dims)
        ax2.set_title(f"Memory vs. Dimension D (Fixed n)\n[{algo_name} | {order_name}]", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(title="Point Size (n)", loc="best")

        fig.suptitle(f"Dimension Scaling Analysis (Memory): {algo_name} ({order_name} / {space_name})", fontweight='bold', fontsize=14)
        fig.tight_layout()

        mem_filepath = os.path.join(mem_dir, f"{prefix}.png")
        fig.savefig(mem_filepath)
        plt.close(fig)
        saved_mem.append(mem_filepath)

    print(f"Generated {len(saved_time)} Category 2 dimension scaling plots for time and {len(saved_mem)} for memory.")
    return saved_time, saved_mem


# =====================================================================
# CATEGORY 3: Algorithm Comparison per Dimension & Order
# =====================================================================
def generate_category3_algorithm_comparison(df, base_dir):
    """
    For each (Dimension, Order) pair, compares Deterministic vs. Randomized.
    Produces dual-panel plots:
      Top panel: Direct metric curves with error bars
      Bottom panel: Speedup ratio (T_det / T_rand) or Memory ratio
    """
    time_dir = os.path.join(base_dir, "3_algorithm_comparison", "time")
    mem_dir = os.path.join(base_dir, "3_algorithm_comparison", "memory")
    os.makedirs(time_dir, exist_ok=True)
    os.makedirs(mem_dir, exist_ok=True)

    dim_orders = df[['Dimensions', 'Order_Key', 'Input_Order', 'Space_Type']].drop_duplicates()
    saved_time = []
    saved_mem = []

    for _, row in dim_orders.iterrows():
        dim = int(row['Dimensions'])
        order_key = row['Order_Key']
        order_name = row['Input_Order']
        space_name = row['Space_Type']

        sub = df[(df['Dimensions'] == dim) & (df['Order_Key'] == order_key)]
        if sub.empty:
            continue

        det_sub = sub[sub['Algo_Key'] == 'deterministic'].sort_values('Num_Points')
        rand_sub = sub[sub['Algo_Key'] == 'randomized'].sort_values('Num_Points')

        if det_sub.empty or rand_sub.empty:
            continue

        # Merge for direct ratio comparison
        merged = pd.merge(det_sub, rand_sub, on='Num_Points', suffixes=('_det', '_rand'))
        if merged.empty:
            continue

        prefix = f"{dim}D_{order_key}"

        # -------------------------------------------------------------
        # 1. TIME COMPARISON PLOT (Dual Panel: Execution & Speedup)
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 8.5), dpi=180,
                                       gridspec_kw={'height_ratios': [2, 1]}, sharex=True)

        # Upper: Absolute execution times
        ax1.errorbar(det_sub['Num_Points'], det_sub['Mean_Time_ms'], yerr=det_sub['StdDev_Time_ms'],
                     fmt='o-', color=ALGO_COLORS['Deterministic Grid'], label='Deterministic Grid',
                     linewidth=2.2, markersize=7, capsize=4)
        ax1.errorbar(rand_sub['Num_Points'], rand_sub['Mean_Time_ms'], yerr=rand_sub['StdDev_Time_ms'],
                     fmt='s--', color=ALGO_COLORS['Randomized Grid'], label='Randomized Grid',
                     linewidth=2.2, markersize=7, capsize=4)

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax1.set_title(f"Algorithm Runtime Comparison: {dim}D | {order_name} ({space_name})", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(loc="best", frameon=True)

        # Lower: Speedup ratio (T_det / T_rand)
        speedup = merged['Mean_Time_ms_det'] / merged['Mean_Time_ms_rand']
        ax2.plot(merged['Num_Points'], speedup, 'd-', color='#2ca02c', linewidth=2.2, markersize=8)
        ax2.axhline(1.0, color='gray', linestyle='--', linewidth=1.5, label='Equal Runtime (1.0×)')
        
        # Shade regions
        ax2.fill_between(merged['Num_Points'], 1.0, speedup, where=(speedup >= 1.0),
                         color='#2ca02c', alpha=0.2, label='Randomized Faster')
        ax2.fill_between(merged['Num_Points'], 1.0, speedup, where=(speedup < 1.0),
                         color='#d62728', alpha=0.2, label='Deterministic Faster')

        ax2.set_xscale('log')
        ax2.set_xlabel("Number of Points (n)", fontweight='bold')
        ax2.set_ylabel("Speedup (T_det / T_rand)", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(loc="best", frameon=True)
        ax2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        fig.tight_layout()
        time_filepath = os.path.join(time_dir, f"{prefix}.png")
        fig.savefig(time_filepath)
        plt.close(fig)
        saved_time.append(time_filepath)

        # -------------------------------------------------------------
        # 2. MEMORY COMPARISON PLOT
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(9.5, 8.5), dpi=180,
                                       gridspec_kw={'height_ratios': [2, 1]}, sharex=True)

        ax1.errorbar(det_sub['Num_Points'], det_sub['Mean_Peak_Memory_MB'], yerr=det_sub['StdDev_Peak_Memory_MB'],
                     fmt='o-', color=ALGO_COLORS['Deterministic Grid'], label='Deterministic Grid',
                     linewidth=2.2, markersize=7, capsize=4)
        ax1.errorbar(rand_sub['Num_Points'], rand_sub['Mean_Peak_Memory_MB'], yerr=rand_sub['StdDev_Peak_Memory_MB'],
                     fmt='s--', color=ALGO_COLORS['Randomized Grid'], label='Randomized Grid',
                     linewidth=2.2, markersize=7, capsize=4)

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax1.set_title(f"Algorithm Memory Comparison: {dim}D | {order_name} ({space_name})", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(loc="best", frameon=True)

        # Lower: Memory overhead ratio (M_rand / M_det)
        mem_ratio = merged['Mean_Peak_Memory_MB_rand'] / merged['Mean_Peak_Memory_MB_det']
        ax2.plot(merged['Num_Points'], mem_ratio, 's-', color='#9467bd', linewidth=2.0, markersize=7)
        ax2.axhline(1.0, color='gray', linestyle='--', linewidth=1.5, label='Equal Memory (1.0×)')

        ax2.set_xscale('log')
        ax2.set_xlabel("Number of Points (n)", fontweight='bold')
        ax2.set_ylabel("Ratio (M_rand / M_det)", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(loc="best", frameon=True)
        ax2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        fig.tight_layout()
        mem_filepath = os.path.join(mem_dir, f"{prefix}.png")
        fig.savefig(mem_filepath)
        plt.close(fig)
        saved_mem.append(mem_filepath)

    print(f"Generated {len(saved_time)} Category 3 algorithm comparison plots for time and {len(saved_mem)} for memory.")
    return saved_time, saved_mem


# =====================================================================
# CATEGORY 4: Input Order Comparison per Dimension & Algorithm
# =====================================================================
def generate_category4_order_comparison(df, base_dir):
    """
    For each (Dimension, Algorithm) pair, compares the impact of input orders:
      Original vs. Sorted_X_Axis vs. Adversarial (Ladder of Pairs).
    Uses a 2-panel figure:
      Left Panel: Normal Space (Original vs. Sorted, sharing the 100k..1M scale)
      Right Panel: Full comparison in log-log space including Adversarial (10k..50k scale)
    """
    time_dir = os.path.join(base_dir, "4_order_comparison", "time")
    mem_dir = os.path.join(base_dir, "4_order_comparison", "memory")
    os.makedirs(time_dir, exist_ok=True)
    os.makedirs(mem_dir, exist_ok=True)

    dim_algos = df[['Dimensions', 'Algo_Key', 'Algorithm']].drop_duplicates()
    saved_time = []
    saved_mem = []

    for _, row in dim_algos.iterrows():
        dim = int(row['Dimensions'])
        algo_key = row['Algo_Key']
        algo_name = row['Algorithm']

        sub = df[(df['Dimensions'] == dim) & (df['Algo_Key'] == algo_key)]
        if sub.empty:
            continue

        prefix = f"{dim}D_{algo_key}"

        # -------------------------------------------------------------
        # 1. TIME ORDER COMPARISON (2 Panels)
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), dpi=180)

        # Panel 1: Normal Space (Original vs Sorted)
        normal_sub = sub[sub['Space_Type'] == 'Normal']
        for ord_key in ['original', 'sorted']:
            ord_df = normal_sub[normal_sub['Order_Key'] == ord_key].sort_values('Num_Points')
            if not ord_df.empty:
                label_name = "Sorted (X-Axis)" if ord_key == 'sorted' else "Original Order"
                ax1.plot(ord_df['Num_Points'], ord_df['Mean_Time_ms'], marker='o',
                         linewidth=2.2, label=label_name, color=ORDER_COLORS[ord_key])

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel("Number of Points (n)", fontweight='bold')
        ax1.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax1.set_title(f"Normal Space: Original vs. Sorted\n[{dim}D | {algo_name}]", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(loc="best", frameon=True)
        ax1.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        # Panel 2: All Orders (including Adversarial)
        for ord_key, ord_label, mkr in [('original', 'Normal: Original', 'o'),
                                         ('sorted', 'Normal: Sorted', 's'),
                                         ('adversarial', 'Adversarial: Ladder', '^')]:
            ord_df = sub[sub['Order_Key'] == ord_key].sort_values('Num_Points')
            if not ord_df.empty:
                ax2.plot(ord_df['Num_Points'], ord_df['Mean_Time_ms'], marker=mkr,
                         linewidth=2.2, label=ord_label, color=ORDER_COLORS[ord_key])

        ax2.set_xscale('log')
        ax2.set_yscale('log')
        ax2.set_xlabel("Number of Points (n)", fontweight='bold')
        ax2.set_ylabel("Execution Time (ms)", fontweight='bold')
        ax2.set_title(f"All Orders (Normal & Adversarial)\n[{dim}D | {algo_name}]", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(loc="best", frameon=True)
        ax2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        fig.suptitle(f"Impact of Input Order on Execution Time: {dim}D | {algo_name}", fontweight='bold', fontsize=14)
        fig.tight_layout()

        time_filepath = os.path.join(time_dir, f"{prefix}.png")
        fig.savefig(time_filepath)
        plt.close(fig)
        saved_time.append(time_filepath)

        # -------------------------------------------------------------
        # 2. MEMORY ORDER COMPARISON (2 Panels)
        # -------------------------------------------------------------
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6.5), dpi=180)

        # Panel 1: Normal Space
        for ord_key in ['original', 'sorted']:
            ord_df = normal_sub[normal_sub['Order_Key'] == ord_key].sort_values('Num_Points')
            if not ord_df.empty:
                label_name = "Sorted (X-Axis)" if ord_key == 'sorted' else "Original Order"
                ax1.plot(ord_df['Num_Points'], ord_df['Mean_Peak_Memory_MB'], marker='o',
                         linewidth=2.2, label=label_name, color=ORDER_COLORS[ord_key])

        ax1.set_xscale('log')
        ax1.set_yscale('log')
        ax1.set_xlabel("Number of Points (n)", fontweight='bold')
        ax1.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax1.set_title(f"Normal Space Memory: Original vs. Sorted\n[{dim}D | {algo_name}]", fontweight='bold')
        ax1.grid(True, which="both", ls=":", alpha=0.5)
        ax1.legend(loc="best", frameon=True)
        ax1.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        # Panel 2: All Orders
        for ord_key, ord_label, mkr in [('original', 'Normal: Original', 'o'),
                                         ('sorted', 'Normal: Sorted', 's'),
                                         ('adversarial', 'Adversarial: Ladder', '^')]:
            ord_df = sub[sub['Order_Key'] == ord_key].sort_values('Num_Points')
            if not ord_df.empty:
                ax2.plot(ord_df['Num_Points'], ord_df['Mean_Peak_Memory_MB'], marker=mkr,
                         linewidth=2.2, label=ord_label, color=ORDER_COLORS[ord_key])

        ax2.set_xscale('log')
        ax2.set_yscale('log')
        ax2.set_xlabel("Number of Points (n)", fontweight='bold')
        ax2.set_ylabel("Peak Memory (MB)", fontweight='bold')
        ax2.set_title(f"All Orders Memory (Normal & Adversarial)\n[{dim}D | {algo_name}]", fontweight='bold')
        ax2.grid(True, which="both", ls=":", alpha=0.5)
        ax2.legend(loc="best", frameon=True)
        ax2.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, p: f"{int(x/1000):,d}k" if x >= 1000 else f"{int(x)}"))

        fig.suptitle(f"Impact of Input Order on Memory: {dim}D | {algo_name}", fontweight='bold', fontsize=14)
        fig.tight_layout()

        mem_filepath = os.path.join(mem_dir, f"{prefix}.png")
        fig.savefig(mem_filepath)
        plt.close(fig)
        saved_mem.append(mem_filepath)

    print(f"Generated {len(saved_time)} Category 4 order comparison plots for time and {len(saved_mem)} for memory.")
    return saved_time, saved_mem


# =====================================================================
# SUMMARY VISUALIZATIONS & HEATMAPS
# =====================================================================
def generate_summary_plots(df, base_dir):
    """
    Generates high-level executive summaries:
      1. Speedup Heatmap (Dimensions vs Scenarios)
      2. Empirical Scaling Exponent Table & Plot
    """
    summary_dir = os.path.join(base_dir, "summary")
    os.makedirs(summary_dir, exist_ok=True)

    # 1. Empirical Exponent calculation
    exp_records = []
    for (scen, dim, algo), grp in df.groupby(['Order_Key', 'Dimensions', 'Algorithm']):
        alpha, _ = fit_power_law(grp['Num_Points'], grp['Mean_Time_ms'])
        beta, _ = fit_power_law(grp['Num_Points'], grp['Mean_Peak_Memory_MB'])
        if alpha is not None:
            exp_records.append({
                'Order_Key': scen,
                'Dimensions': dim,
                'Algorithm': algo,
                'Time_Exponent': alpha,
                'Memory_Exponent': beta if beta is not None else 1.0
            })
    exp_df = pd.DataFrame(exp_records)

    # Plot empirical exponent
    if not exp_df.empty:
        fig, axes = plt.subplots(1, 3, figsize=(18, 5.5), dpi=180, sharey=True)
        scenarios = ['original', 'sorted', 'adversarial']
        scen_titles = {'original': 'Normal / Original', 'sorted': 'Normal / Sorted_X', 'adversarial': 'Adversarial / Ladder'}

        for ax, sc in zip(axes, scenarios):
            sc_data = exp_df[exp_df['Order_Key'] == sc]
            if sc_data.empty:
                continue

            for algo, mkr in [('Deterministic Grid', 'o'), ('Randomized Grid', 's')]:
                algo_data = sc_data[sc_data['Algorithm'] == algo].sort_values('Dimensions')
                if not algo_data.empty:
                    ax.plot(algo_data['Dimensions'], algo_data['Time_Exponent'],
                            marker=mkr, color=ALGO_COLORS[algo], linewidth=2.2, label=algo)

            ax.axhline(1.0, color='#2ca02c', linestyle=':', linewidth=1.8, label="O(n) Linear")
            ax.axhline(2.0, color='#d62728', linestyle='--', linewidth=1.5, label="O(n²) Quadratic")
            ax.set_title(scen_titles.get(sc, sc), fontweight='bold')
            ax.set_xlabel("Dimension (D)", fontweight='bold')
            ax.set_xticks(sorted(df['Dimensions'].unique()))
            ax.grid(True, ls=":", alpha=0.5)

        axes[0].set_ylabel("Empirical Scaling Exponent α (T ∝ n^α)", fontweight='bold')
        axes[0].legend(loc="best", frameon=True)
        fig.suptitle("Empirical Runtime Scaling Exponents Across Dimensions", fontweight='bold', fontsize=14)
        fig.tight_layout()

        exp_filepath = os.path.join(summary_dir, "empirical_scaling_exponents.png")
        fig.savefig(exp_filepath)
        plt.close(fig)

    # 2. Speedup Heatmap (Deterministic vs. Randomized)
    piv = df.pivot_table(index=['Dimensions', 'Order_Key'], columns='Algo_Key', values='Mean_Time_ms')
    if 'deterministic' in piv.columns and 'randomized' in piv.columns:
        piv['Speedup'] = piv['deterministic'] / piv['randomized']
        speedup_matrix = piv['Speedup'].unstack(level='Order_Key')

        fig, ax = plt.subplots(figsize=(8.5, 6), dpi=180)
        sns.heatmap(speedup_matrix, annot=True, fmt=".2f", cmap="vlag", center=1.0,
                    cbar_kws={'label': 'Speedup (T_det / T_rand)'}, ax=ax, linewidths=0.5)
        ax.set_title("Overall Mean Speedup of Randomized over Deterministic", fontweight='bold')
        ax.set_ylabel("Dimension (D)", fontweight='bold')
        ax.set_xlabel("Scenario / Input Order", fontweight='bold')
        fig.tight_layout()

        heatmap_filepath = os.path.join(summary_dir, "speedup_heatmap.png")
        fig.savefig(heatmap_filepath)
        plt.close(fig)

    print("Generated summary visualizations.")


# =====================================================================
# HTML GALLERY GENERATOR
# =====================================================================
def generate_html_gallery(base_dir):
    """
    Creates an interactive HTML dashboard in results_final/index.html
    to browse all categories, plots, and charts with high fidelity.
    """
    html_path = os.path.join(base_dir, "index.html")
    
    categories = [
        ("Summary Overviews", "summary", "High-level speedup heatmaps and empirical complexity fits across all dimensions."),
        ("1. Single Curves with Complexity References (Time)", "1_single_curves/time", "Observed time vs. n with O(n), O(n log n), and O(n²) theoretical references."),
        ("1. Single Curves with Complexity References (Memory)", "1_single_curves/memory", "Observed memory vs. n with O(n) theoretical reference."),
        ("2. Dimension Scaling (Time)", "2_dimension_scaling/time", "Scaling curves across dimensions 2D to 9D for fixed algorithm and order."),
        ("2. Dimension Scaling (Memory)", "2_dimension_scaling/memory", "Peak memory scaling across dimensions 2D to 9D."),
        ("3. Algorithm Comparison (Time)", "3_algorithm_comparison/time", "Deterministic Grid vs. Randomized Grid runtime and speedup."),
        ("3. Algorithm Comparison (Memory)", "3_algorithm_comparison/memory", "Deterministic vs. Randomized peak memory usage."),
        ("4. Input Order Comparison (Time)", "4_order_comparison/time", "Impact of Original vs. Sorted vs. Adversarial on runtime."),
        ("4. Input Order Comparison (Memory)", "4_order_comparison/memory", "Impact of input ordering on peak memory usage.")
    ]

    html = ["""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ND Closest Pair Experiment Benchmark Gallery</title>
    <style>
        :root {
            --bg: #0f172a;
            --surface: #1e293b;
            --surface-card: #334155;
            --accent: #38bdf8;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
            --border: #475569;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            margin: 0;
            padding: 24px;
        }
        header {
            max-width: 1400px;
            margin: 0 auto 32px auto;
            border-bottom: 1px solid var(--border);
            padding-bottom: 20px;
        }
        h1 { margin: 0 0 8px 0; color: var(--accent); }
        p.subtitle { color: var(--text-muted); margin: 0; }
        .section-box {
            max-width: 1400px;
            margin: 0 auto 40px auto;
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 24px;
        }
        .section-header h2 {
            margin: 0 0 4px 0;
            color: var(--accent);
            font-size: 1.35rem;
        }
        .section-header p {
            margin: 0 0 20px 0;
            color: var(--text-muted);
            font-size: 0.95rem;
        }
        .gallery-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(360px, 1fr));
            gap: 20px;
        }
        .plot-card {
            background-color: var(--surface-card);
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border);
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .plot-card:hover {
            transform: translateY(-4px);
            box-shadow: 0 10px 20px rgba(0,0,0,0.3);
        }
        .plot-card img {
            width: 100%;
            height: auto;
            display: block;
            background-color: #ffffff;
            cursor: pointer;
        }
        .plot-card .caption {
            padding: 10px 14px;
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-main);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
        }
        /* Modal for full size view */
        .modal {
            display: none;
            position: fixed;
            z-index: 1000;
            top: 0; left: 0;
            width: 100%; height: 100%;
            background-color: rgba(0,0,0,0.85);
            align-items: center;
            justify-content: center;
        }
        .modal img {
            max-width: 95%;
            max-height: 95%;
            border-radius: 8px;
            box-shadow: 0 0 25px rgba(0,0,0,0.8);
        }
    </style>
</head>
<body>
<header>
    <h1>ND Closest Pair Benchmark Gallery</h1>
    <p class="subtitle">Comprehensive performance, complexity scaling, and memory evaluation across Dimensions (2D to 9D), Algorithms, and Orders.</p>
</header>
"""]

    for title, rel_dir, desc in categories:
        abs_dir = os.path.join(base_dir, rel_dir)
        if not os.path.exists(abs_dir):
            continue
        files = sorted([f for f in os.listdir(abs_dir) if f.endswith(".png")])
        if not files:
            continue

        html.append(f"""
<div class="section-box">
    <div class="section-header">
        <h2>{title} ({len(files)} plots)</h2>
        <p>{desc}</p>
    </div>
    <div class="gallery-grid">
""")
        for fn in files:
            rel_file_path = os.path.join(rel_dir, fn)
            html.append(f"""
        <div class="plot-card">
            <img src="{rel_file_path}" alt="{fn}" onclick="openModal(this.src)">
            <div class="caption">{fn.replace('.png', '')}</div>
        </div>
""")
        html.append("""
    </div>
</div>
""")

    html.append("""
<div id="imageModal" class="modal" onclick="this.style.display='none'">
    <img id="modalImg" src="" alt="Full View">
</div>

<script>
function openModal(src) {
    const modal = document.getElementById('imageModal');
    const modalImg = document.getElementById('modalImg');
    modalImg.src = src;
    modal.style.display = 'flex';
}
</script>
</body>
</html>
""")

    with open(html_path, "w", encoding="utf-8") as f:
        f.write("".join(html))

    print(f"Generated visual HTML gallery at: {html_path}")


# =====================================================================
# MAIN RUNNER
# =====================================================================
def main():
    default_csv = "/home/pratheep/Desktop/projects/rand/experiment_results_final.csv"
    csv_path = sys.argv[1] if len(sys.argv) > 1 else default_csv
    base_dir = "/home/pratheep/Desktop/projects/rand/results_final"
    os.makedirs(base_dir, exist_ok=True)

    print("=========================================================")
    print("ND Closest Pair Experiment Benchmark Plot Generation")
    print("=========================================================")
    print(f"Input CSV       : {csv_path}")
    print(f"Output Directory: {base_dir}")

    df = load_dataset(csv_path)

    print("\n--- Generating Category 1: Single Curves with Complexity Lines ---")
    generate_category1_single_curves(df, base_dir)

    print("\n--- Generating Category 2: Dimension Scaling Comparison ---")
    generate_category2_dimension_scaling(df, base_dir)

    print("\n--- Generating Category 3: Algorithm Comparison (Det vs. Rand) ---")
    generate_category3_algorithm_comparison(df, base_dir)

    print("\n--- Generating Category 4: Input Order Comparison ---")
    generate_category4_order_comparison(df, base_dir)

    print("\n--- Generating High-Level Summaries & Heatmaps ---")
    generate_summary_plots(df, base_dir)

    print("\n--- Building Interactive HTML Gallery ---")
    generate_html_gallery(base_dir)

    print("\n=========================================================")
    print("All plots and summaries generated successfully!")
    print(f"Outputs located in: {base_dir}")
    print("=========================================================")


if __name__ == "__main__":
    main()
