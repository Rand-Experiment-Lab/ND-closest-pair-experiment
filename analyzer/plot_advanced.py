import os
import shutil
import re
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors

def main():
    # 1. Versioning and file management
    # Fallback to local build dir if the LLM/openGP one isn't found
    primary_source = "/media/vithurshan/vithu/llm/openGP/LoadTime/build/experiment_results.csv"
    fallback_source = "/media/vithurshan/vithu/rand/build/experiment_results.csv"
    
    if os.path.exists(primary_source):
        source_csv = primary_source
    elif os.path.exists(fallback_source):
        source_csv = fallback_source
    else:
        print("Could not find the source CSV file!")
        return

    results_dir = "results"
    os.makedirs(results_dir, exist_ok=True)

    existing_files = os.listdir(results_dir)
    versions = []
    for f in existing_files:
        match = re.search(r'experiment_results_v(\d+)\.csv', f)
        if match:
            versions.append(int(match.group(1)))
    v_num = max(versions) + 1 if versions else 1

    dest_csv = os.path.join(results_dir, f"experiment_results_v{v_num}.csv")
    shutil.copy2(source_csv, dest_csv)
    print(f"Copied source CSV to {dest_csv}")

    # 2. Data loading and prep
    df = pd.read_csv(dest_csv)
    df['Algorithm'] = df['Algorithm'].str.strip()
    df['Scenario'] = df['Space_Type'].astype(str) + " / " + df['Input_Order'].astype(str)

    # N_Level grouping
    def get_n_level(s):
        rank = s.rank(method='dense')
        return rank.map({1: 'Small', 2: 'Medium', 3: 'Large'})
    
    df['N_Level'] = df.groupby('Dimensions')['Num_Points'].transform(get_n_level)
    
    scenarios = ["Normal / Original", "Normal / Sorted_X_Axis", "Adversarial / Ladder_of_Pairs"]

    # ---------------------------------------------------------
    # FIGURE 1: Time vs n by scenario
    # ---------------------------------------------------------
    fig1, axes1 = plt.subplots(1, 3, figsize=(18, 6), sharey=False)
    dims = sorted(df['Dimensions'].unique())
    norm = mcolors.Normalize(vmin=min(dims), vmax=max(dims))
    cmap = plt.get_cmap('viridis')

    handles1 = {}
    
    for ax, scen in zip(axes1, scenarios):
        scen_df = df[df['Scenario'] == scen]
        for d in dims:
            color = cmap(norm(d))
            for algo, ls, marker in [('Deterministic Grid', '-', 'o'), ('Randomized Grid', '--', 's')]:
                sub = scen_df[(scen_df['Dimensions'] == d) & (scen_df['Algorithm'] == algo)].sort_values('Num_Points')
                if not sub.empty:
                    line, = ax.plot(sub['Num_Points'], sub['Mean_Time_ms'], ls=ls, marker=marker, color=color, label=f"D={d} {algo[:3]}")
                    handles1[f"D={d} {algo}"] = line
        
        ax.set_xscale('log')
        ax.set_yscale('log')
        ax.set_title(scen)
        ax.set_xlabel('Number of points (n)')
        ax.grid(True, which="both", ls=":", alpha=0.5)

    axes1[0].set_ylabel('Mean execution time (ms)')
    
    # Legend outside
    fig1.legend(handles1.values(), handles1.keys(), loc='center right', bbox_to_anchor=(1.12, 0.5))
    fig1.tight_layout()
    # Adjust layout to make room for legend
    fig1.subplots_adjust(right=0.9)
    f1_path = os.path.join(results_dir, f'fig1_time_vs_n_v{v_num}.png')
    fig1.savefig(f1_path, dpi=160, bbox_inches='tight')
    print(f"Saved {f1_path}")

    # ---------------------------------------------------------
    # FIGURE 2: Speedup heatmap
    # ---------------------------------------------------------
    speedup_df = df.pivot_table(index=['Scenario', 'Dimensions', 'N_Level'], columns='Algorithm', values='Mean_Time_ms').reset_index()
    speedup_df['Speedup'] = speedup_df['Deterministic Grid'] / speedup_df['Randomized Grid']
    print("\n--- Speedup Table ---")
    print(speedup_df.to_string())

    fig2, axes2 = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    n_order = ['Small', 'Medium', 'Large']
    
    norm2 = mcolors.TwoSlopeNorm(vmin=-1, vcenter=0, vmax=4)
    cmap2 = plt.get_cmap('RdBu_r')
    
    im = None
    for ax, scen in zip(axes2, scenarios):
        sub = speedup_df[speedup_df['Scenario'] == scen]
        if sub.empty:
            continue
        piv = sub.pivot(index='Dimensions', columns='N_Level', values='Speedup').reindex(columns=n_order)
        # Drop missing dimensions if any
        piv = piv.dropna(how='all')
        if piv.empty:
            continue

        log_spd = np.log10(piv.values)
        
        im = ax.imshow(log_spd, cmap=cmap2, norm=norm2, aspect='auto')
        ax.set_title(scen)
        ax.set_xticks(range(len(n_order)))
        ax.set_xticklabels(n_order)
        ax.set_yticks(range(len(piv.index)))
        ax.set_yticklabels(piv.index)
        
        if ax == axes2[0]:
            ax.set_ylabel('Dimensions')
            
        # Annotations
        for i in range(len(piv.index)):
            for j in range(len(n_order)):
                val = piv.values[i, j]
                if np.isnan(val):
                    continue
                lval = log_spd[i, j]
                txt = f"{int(val)}×" if val >= 100 else f"{val:.2f}×"
                color = "white" if (lval < -0.5 or lval > 1.5) else "black"
                ax.text(j, i, txt, ha="center", va="center", color=color)

    if im:
        cbar = fig2.colorbar(im, ax=axes2.ravel().tolist(), fraction=0.02, pad=0.04)
        cbar.set_label("log10(speedup)  [0 = no difference, red = randomized faster]")
    
    f2_path = os.path.join(results_dir, f'fig2_speedup_heatmap_v{v_num}.png')
    fig2.savefig(f2_path, dpi=160, bbox_inches='tight')
    print(f"Saved {f2_path}")

    # ---------------------------------------------------------
    # FIGURE 3: Empirical scaling exponent vs dimension
    # ---------------------------------------------------------
    exp_records = []
    for (scen, dim, algo), grp in df.groupby(['Scenario', 'Dimensions', 'Algorithm']):
        if len(grp) >= 2:
            slope, _ = np.polyfit(np.log10(grp['Num_Points']), np.log10(grp['Mean_Time_ms']), 1)
            exp_records.append({'Scenario': scen, 'Dimensions': dim, 'Algorithm': algo, 'Exponent': slope})
            
    exp_df = pd.DataFrame(exp_records)
    print("\n--- Empirical Scaling Exponent Table ---")
    if not exp_df.empty:
        print(exp_df.to_string())
    else:
        print("No valid exponent records found (need at least 2 points per group).")

    fig3, axes3 = plt.subplots(1, 3, figsize=(18, 5), sharey=True)
    for ax, scen in zip(axes3, scenarios):
        sub = exp_df[exp_df['Scenario'] == scen] if not exp_df.empty else pd.DataFrame()
        if sub.empty:
            ax.set_title(scen)
            continue
        
        for algo, color, marker in [('Deterministic Grid', 'blue', 'o'), ('Randomized Grid', 'orange', 's')]:
            asub = sub[sub['Algorithm'] == algo].sort_values('Dimensions')
            if not asub.empty:
                ax.plot(asub['Dimensions'], asub['Exponent'], marker=marker, color=color, label=algo, linestyle='-')
                
        ax.axhline(1.0, color='gray', linestyle=':', label='O(n) reference')
        ax.set_title(scen)
        ax.set_xticks(dims)
        ax.set_xlabel('Dimension (D)')
        
    axes3[0].set_ylabel('Empirical exponent (slope of log time vs log n)')
    
    handles, labels = axes3[0].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    fig3.legend(by_label.values(), by_label.keys(), loc='center right', bbox_to_anchor=(1.12, 0.5))
    fig3.tight_layout()
    fig3.subplots_adjust(right=0.92)
    
    f3_path = os.path.join(results_dir, f'fig3_scaling_exponent_v{v_num}.png')
    fig3.savefig(f3_path, dpi=160, bbox_inches='tight')
    print(f"Saved {f3_path}")


if __name__ == "__main__":
    main()
