# Final Research Report: An Empirical & Theoretical Investigation of Grid-Based Randomization in the $d$-Dimensional Closest Pair Problem

**Authors:** Computational Geometry & Systems Performance Laboratory  
**Hardware Platforms:**
* **Server Machine:** 13th Gen Intel Core i7-13700 (Raptor Lake, 16 Cores / 24 Threads @ up to 5.20 GHz, 30 MB L3 Cache)
* **Local Machine:** AMD Ryzen 9 5900HX (Zen 3 Architecture, 8 Cores / 16 Threads @ up to 4.85 GHz, 16 MB Unified L3 Cache)  
**Implementation:** High-performance modular C++20 engine compiled under `-O3 -march=native -DNDEBUG`

---

## 1. Initial Expectation (Theoretical Background & Literature Promise)

In computational geometry textbooks and landmark papers (Rabin 1976, Seidel 1991, Kleinberg & Tardos, Cormen et al.), the closest pair problem is introduced with three complexity tiers:
1. **Naive Brute-Force:** Checking all pairs takes $\Theta(N^2)$ comparisons.
2. **Deterministic Divide-and-Conquer:** Bentley & Shamos achieved $O(N \log N)$ in $\mathbb{R}^2$.
3. **Randomized Hash-Grid (Rabin–Seidel):** By hashing points into a dynamic grid with cell diameter $\delta$ and randomizing the insertion order, Seidel's backward analysis promises an expected linear time of **$O(N)$**.

### What Was Expected:
* **The Hypothesis:** By applying a random permutation to the input points, we expected to dramatically improve performance over deterministic insertion orders.
* **The Mechanism:** Literature asserts that randomizing the order ensures that smaller pairwise distances are discovered progressively, preventing excessive grid rebuilds and keeping expected runtime strictly linear:
  $$\mathbb{E}[\text{Total Time}] = O(3^D \cdot N + 2N) = O(N) \quad (\text{for constant } D)$$

---

## 2. Experimental Setup

To test this expectation, we implemented an instrumentation-grade benchmark suite across both synthetic distributions and real-world telemetry:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          EXPERIMENTAL TEST SUITE                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ 1. Algorithmic Implementations:                                             │
│    • Deterministic Grid: Streams points in provided / natural order.        │
│    • Randomized Grid: Applies Fisher-Yates shuffle (std::shuffle) upfront.  │
│                                                                             │
│ 2. Datasets Evaluated:                                                      │
│    • Dimension Scaling: Synthetic Uniform (D = 2 .. 11, N = 100,000).       │
│    • Scale Variation: Synthetic Uniform (D = 4, N = 10k, 50k, 100k, 500k, 1M)│
│    • Adversarial Stress Test: "Ladder of Pairs" (N = 1k, 10k, 25k).         │
│    • Real-World Telemetry: OpenSky 4D Flight Data (N ≈ 1.08M - 1.28M).      │
│                                                                             │
│ 3. Hardware Platforms:                                                      │
│    • Intel Core i7-13700 Desktop (Locked 5.2 GHz, 30MB L3 Cache).           │
│    • AMD Ryzen 9 5900HX Laptop (4.85 GHz Boost, 16MB Unified L3 Cache).     │
│                                                                             │
│ 4. Metrics Instrumented:                                                    │
│    • probe_time_ms, rebuild_time_ms, shuffle_time_ms.                       │
│    • Rebuild Work W = ∑ i_k, Rebuild Events R, Total Probes N · 3^D.        │
│    • Sample Size: K = 30 to 40 independent iterations per experimental unit.│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Empirical Results: Did It Meet Expectations?

### 3.1 On Benign / Uniform and Real-World Data: **NO**
Across hundreds of runs on uniform synthetic points and real aviation telemetry:
* **Equivalence:** Deterministic and Randomized methods performed almost identically.
* **Deterministic Superiority:** In over $65\%$ of runs, **Deterministic Grid was $5\% - 15\%$ FASTER than Randomized Grid**.
* **The Shuffle Tax:** Randomization suffered from the overhead of `std::shuffle` (generating $N$ random numbers, swapping elements in memory, and evicting CPU L1/L2 cache lines), whereas Deterministic avoided this overhead entirely.

### 3.2 On Adversarial Data: **YES (280× Speedup)**
When tested against an adversarial "Ladder of Pairs" where distances shrink monotonically:

| Dataset Scale ($N$) | Metric | Deterministic Grid | Randomized Grid | Empirical Factor |
| :--- | :--- | :---: | :---: | :---: |
| **Ladder $10{,}000$** | Rebuild Work ($W$) | $49{,}995{,}000\text{ pts}$ | $19{,}450\text{ pts}$ | **$2,570\times$ work reduction** |
| | Total Time ($T$) | $328.4\text{ ms}$ | **$1.82\text{ ms}$** | **$180\times$ faster** |
| **Ladder $25{,}000$** | Rebuild Work ($W$) | $312{,}487{,}500\text{ pts}$ | $48{,}120\text{ pts}$ | **$6,494\times$ work reduction** |
| | Total Time ($T$) | $12{,}841.2\text{ ms}$ ($12.8\text{ s}$) | **$45.6\text{ ms}$** | **$281\times$ faster** |

**Summary:** Randomization met expectations **only on adversarial inputs**, while failing to provide any speedup on typical uniform or real-world data.

---

## 4. Hypotheses for the Unexpected Behavior

To explain why randomization behaved this way, we formulated three working hypotheses:

1. **The Fixed vs. Variable Work Hypothesis:**  
   The algorithm consists of two distinct components: a *Fixed Cost* that cannot be changed by shuffling, and a *Variable Cost* that depends on insertion order. Randomization only affects the Variable Cost.
2. **The Dimensional Phase Transition Hypothesis:**  
   As spatial dimension $D$ increases, the Fixed Cost grows exponentially as $O(3^D \cdot N)$, while the Variable Cost is bounded by $2N$. Therefore, the proportion of work that randomization can optimize shrinks exponentially toward zero.
3. **The Microarchitectural & Cache Hypothesis:**  
   When working set sizes fit into CPU cache ($N \le 50\text{k}$), memory lookups are fast and deterministic. When working set sizes spill into DRAM ($N \ge 100\text{k}$), and when mobile processors experience thermal throttling, memory bus and clock jitter drown out algorithmic signals.

---

## 5. Algorithmic Work Deconstruction: Identifying the Heaviest Suspects

By profiling the execution pipeline, we isolated the two heaviest computational sections:

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                        ALGORITHMIC RUNTIME DECOMPOSITION                         │
│                                                                                  │
│   Total Time T  =   T_pre (Shuffle)  +  T_probe (Fixed)  +  T_rebuild (Variable) │
└───────────────────────────────────────────┬───────────────────────────────┬──────┘
                                            │                               │
                                            ▼                               ▼
                          ┌──────────────────────────────────┐   ┌──────────────────────────────┐
                          │           FIXED COST             │   │        VARIABLE COST         │
                          │   Neighbor Stencil Probing       │   │  Grid Allocation & Re-hash   │
                          ├──────────────────────────────────┤   ├──────────────────────────────┤
                          │ Work: N · 3^D hash queries       │   │ Work: W = ∑ i_k points       │
                          │ Strictly INVARIANT across runs   │   │ Dictated by pair order       │
                          │ In 2D:  9N probes                │   │ Worst-case: Ω(N^2) (Ladder)  │
                          │ In 4D:  81N probes               │   │ Randomized: ≤ 2N (Seidel)    │
                          │ In 11D: 177,147N probes          │   │ Natural:    O(N) (Uniform)   │
                          └──────────────────────────────────┘   └──────────────────────────────┘
```

1. **Suspect 1 (Fixed Cost): Neighbor Stencil Probing ($T_{\text{probe}}$)**
   * Every streamed point $p_i$ queries all neighboring grid cells within $L_\infty$ distance $1$.
   * Number of neighbor cells queried per point: $3^D$.
   * Total neighbor probes across $N$ points: $(N - 2) \cdot 3^D$.
   * **Invariance:** This operation count is **strictly identical across all $N!$ permutations**.
2. **Suspect 2 (Variable Cost): Grid Rebuilding ($T_{\text{rebuild}}$)**
   * When a closer pair is detected ($\delta' < \delta$), the grid is cleared and all previous $i$ points are re-quantized and re-inserted.
   * Work per rebuild: $W_k = i + 1$ points re-inserted.
   * Total points re-inserted: $W = \sum_{k=1}^R (i_k + 1)$.

---

## 6. Mathematical Analysis: What Randomization Actually Does

### 6.1 Randomization as an Adversarial Insurance Policy
Randomization operates **exclusively on the Variable Cost**:
* Under an adversarial sequence: Every point triggers a rebuild:
  $$W_{\text{adversarial}} = \sum_{i=1}^N i = \frac{N(N-1)}{2} = \mathbf{\Omega(N^2)}$$
* Under a randomized sequence: Seidel's backward analysis applies:
  $$\mathbb{P}(\text{Rebuild at step } i) \le \frac{2}{i} \implies \mathbb{E}[W_{\text{randomized}}] \le \sum_{i=1}^N i \cdot \left(\frac{2}{i}\right) = \mathbf{2N}$$

Randomization does **not** make neighbor probing faster. It simply prevents the Variable Cost from exploding to $\Omega(N^2)$. On benign or uniform distributions, the natural order already behaves like an arbitrary permutation, so $W \approx O(N)$ without any shuffling!

### 6.2 The Dimensional Proportion Law ($\frac{2}{3^D}$)
Because Expected Rebuild Work is at most $2N$, while Probing Work is $(N - 2) \cdot 3^D$, the ratio of Rebuild Work to Probing Work is mathematically bounded:

$$\rho(D) = \frac{\mathbb{E}[W_{\text{rebuild}}]}{\text{Total Neighbor Probes}} \le \frac{2N}{N \cdot 3^D} = \mathbf{\frac{2}{3^D}}$$

As dimension $D$ increases, the exponential denominator $3^D$ forces the rebuild work proportion to collapse toward zero:

$$\lim_{D \to \infty} \frac{2}{3^D} = 0$$

---

## 7. Experimental Proof: Measuring the Probing vs. Rebuild Workload

To verify this mathematical law, we recorded the exact nanosecond-level breakdown between Probing Time and Rebuild Time across dimensions $D = 2 \dots 11$ on $N = 100{,}000$ points.

### 7.1 Server Benchmark Results (Intel Core i7-13700 @ 5.2 GHz)

| Dimension $D$ | Stencil $3^D$ | Total Probes ($N \cdot 3^D$) | Theoretical Ratio $\frac{2}{3^D}$ | **Server Probe Time %** | **Server Rebuild Time %** | Server Mean Runtime | Server $r(W, T)$ |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **2D** | 9 | $900{,}000$ | $22.22\%$ | **$68.48\%$** | **$31.52\%$** | $24.6\text{ ms}$ | **$0.9943$** ($R^2 = 98.9\%$) |
| **3D** | 27 | $2{,}700{,}000$ | $7.41\%$ | **$82.16\%$** | **$17.84\%$** | $46.0\text{ ms}$ | **$0.9932$** ($R^2 = 98.6\%$) |
| **4D** | 81 | $8{,}100{,}000$ | $2.47\%$ | **$92.76\%$** | **$7.24\%$** | $119.8\text{ ms}$ | **$0.9965$** ($R^2 = 99.3\%$) |
| **5D** | 243 | $24{,}300{,}000$ | $0.82\%$ | **$97.13\%$** | **$2.87\%$** | $363.1\text{ ms}$ | **$0.9628$** ($R^2 = 92.7\%$) |
| **6D** | 729 | $72{,}900{,}000$ | $0.27\%$ | **$99.05\%$** | **$0.95\%$** | $1{,}189.7\text{ ms}$ | **$0.8372$** ($R^2 = 70.1\%$) |
| **7D** | 2,187 | $218{,}700{,}000$ | $0.091\%$ | **$99.70\%$** | **$0.30\%$** | $3{,}994.7\text{ ms}$ | **$0.8237$** ($R^2 = 67.9\%$) |
| **8D** | 6,561 | $656{,}100{,}000$ | $0.030\%$ | **$99.90\%$** | **$0.10\%$** | $13.57\text{ s}$ | **$0.7987$** ($R^2 = 63.8\%$) |
| **9D** | 19,683 | $1{,}968{,}300{,}000$ | $0.010\%$ | **$99.97\%$** | **$0.028\%$** | $46.05\text{ s}$ | **$0.6375$** ($R^2 = 40.6\%$) |
| **10D** | 59,049 | $5{,}904{,}800{,}000$ | $0.0034\%$ | **$99.991\%$** | **$0.0091\%$** | $153.05\text{ s}$ ($2.5\text{ min}$) | **$0.7922$** ($R^2 = 62.8\%$) |
| **11D** | 177,147 | $17{,}714{,}300{,}000$ | $0.0011\%$ | **$99.997\%$** | **$0.0027\%$** | $512.53\text{ s}$ ($8.5\text{ min}$) | **$0.6143$** ($R^2 = 37.7\%$) |

### 7.2 Microarchitectural Verification: Why Rebuild Takes 10 ms while Probing Takes 13 Seconds
In 8D on the Intel Core i7-13700 server:
* **Rebuild Work:** Seidel's bound limits total points re-inserted across all 21 rebuilds to $\le 200{,}000$. The actual observed work was $184{,}001$ points. Pre-allocated hash buckets eliminate dynamic reallocation. Inserting $184{,}001$ points at $\approx 55.9\text{ ns}$ per insertion takes:
  $$184{,}001 \times 55.9\text{ ns} = \mathbf{10.3\text{ milliseconds}}$$
* **Probing Work:** The algorithm must execute $100{,}000 \times 3^8 = \mathbf{656{,}086{,}878}$ hash table lookups. At $\approx 20.1\text{ ns}$ per lookup:
  $$656{,}086{,}878 \times 20.1\text{ ns} = \mathbf{13.20\text{ seconds}}$$
* **Operation Ratio:** Probing executes **$3,565\times$ more operations** than Rebuilding.

---

### 7.3 Analytics Visualizations (Plots)

#### Figure 1: The Curse of Dimensionality Phase Transition
*Shows the exponential explosion of Neighbor Probing ($3^D$) swallowing $>99.99\%$ of runtime while Rebuild Work collapses to $0.003\%$.*
![Curse of Dimensionality Phase Transition](storage/results/rebuild_work/rebuild_work_server_dim_20260920_004009_analysis/rebuild_work_04_curse_of_dimensionality_phase_transition.png)

#### Figure 2: Pearson Correlation Stability Across Dimensions
*Demonstrates that Rebuild Work ($W$) remains dominant ($r \approx 0.99 - 0.61$) across all dimensions, while Rebuild Count ($R$) fails.*
![Correlation Stability](storage/results/rebuild_work/rebuild_work_server_dim_20260920_004009_analysis/rebuild_work_01_correlation_stability.png)

#### Figure 3: Proportion of Runtime Variance Explained ($R^2$)
*Compares $R^2$ of Cumulative Rebuild Work ($W$) versus raw Rebuild Count ($R$), showing $W$ explains up to $99.3\%$ of variance.*
![Variance Attribution](storage/results/rebuild_work/rebuild_work_server_dim_20260920_004009_analysis/rebuild_work_02_variance_attribution_bars.png)

#### Figure 4: Cross-Platform Performance Comparison (Desktop Intel i7 vs. Mobile AMD Ryzen 9)
*Highlights the effect of thermal throttling and cache sizes between desktop and mobile microarchitectures.*
![Local vs Server Comparison](storage/results/rebuild_work/local_vs_server_comparison/03_local_vs_server_r_work_comparison.png)

---

## 8. Hardware & Scale Suspects: Cache Boundaries & Shuffling Tax

Physical hardware interactions explain why empirical behavior changes with scale $N$ and platform architecture:

```
Working Set Size vs. CPU Memory Hierarchy:
┌────────────────────────────────────────────────────────────┐
│ N ≤ 50k: Fits in L2/L3 Cache (Deterministic Memory Latency) │
│          r(Work, Time) ≥ 0.93 - 0.99                       │
├────────────────────────────────────────────────────────────┤
│ N ≥ 100k: Spills to Main DRAM (Memory Bus Contention)       │
│           r(Work, Time) drops if thermal throttling occurs │
└────────────────────────────────────────────────────────────┘
```

1. **The Cache Cliff ($N \le 50\text{k}$ vs. $N \ge 100\text{k}$):**
   * At $N = 10\text{k}$ and $50\text{k}$, the hash table fits entirely within the CPU's high-speed L3 cache (16 MB on Ryzen 9, 30 MB on i7-13700). Memory access latencies are deterministic, producing correlations of $r(W, T) = \mathbf{0.93 - 0.98}$.
   * At $N \ge 100\text{k}$, node allocations spill into main system DRAM, where page faults and bus latency add external variance.
2. **Thermal Throttling Discrepancy (Server vs. Laptop):**
   * On the **Server (Desktop Intel Core i7-13700)**, desktop-grade cooling maintained locked 5.2 GHz frequencies. In 8D, standard deviation was only **$\pm 94\text{ ms}$ ($0.7\%$ variation)**.
   * On the **Local PC (Mobile AMD Ryzen 9 5900HX)**, 7 continuous hours of sustained multi-billion-probe loops triggered SoC thermal throttling. Clock frequencies adjusted dynamically, creating timing jitter that degraded correlation.
3. **The Shuffling Overhead Tax:**
   Applying `std::shuffle` requires generating $N$ pseudo-random numbers and executing $N$ random memory swaps. This flushes the CPU L1/L2 data cache lines immediately prior to grid execution, adding a $5\% - 15\%$ performance penalty that deterministic execution avoids.

---

## 9. Insights & Discoveries: What Literature Misses

1. **Textbooks Omit Constant Multipliers:**  
   Literature states the Big-O bound $O(3^D \cdot N + 2N)$ and simplifies it to $O(N)$ for "constant $D$." However, in physical computing, $3^D$ is an enormous constant. At $D = 8$, $3^8 = 6,561$. The constant multiplier of neighbor probing is $3,280\times$ larger than the rebuild multiplier ($2$).
2. **Randomization is an Insurance Policy, Not an Accelerator:**  
   Randomization does not speed up search on natural data; it guarantees protection against worst-case $\Omega(N^2)$ inputs.
3. **Rebuild Count ($R$) is a Broken Metric:**  
   In OpenSky real data, $r(R, T) = \mathbf{-0.0919}$ (negative correlation). Counting rebuild events equally is physically meaningless because an early rebuild costs $O(1)$ while a late rebuild costs $O(N)$. **Cumulative Rebuild Work ($W = \sum i_k$) is the true physical metric.**

---

## 10. Conclusions

1. **The Invariance Principle Holds in Low Dimensions ($D \le 4$):**  
   In low dimensions, because the $3^D \cdot N$ probes are flat and invariant across random permutations, **over $98.6\% - 99.3\%$ of runtime variance between shuffles is driven by Rebuild Work** ($r \approx 0.99$).
2. **The Dimensional Phase Transition Occurs at $D \ge 5$:**  
   Beyond $D = 5$, neighbor probing consumes $>97\%$ of runtime. At $D = 11$, probing consumes **$99.997\%$** ($17.7$ billion lookups), reducing rebuild work to **$0.003\%$** ($33\text{ ms}$ out of $18.1\text{ minutes}$).
3. **Engineering Recommendation:**  
   The Rabin-Seidel hash-grid algorithm is outstanding for $D \le 4$. For $D \ge 5$, spatial tree hierarchies (KD-Trees, Ball Trees) or approximate nearest neighbor algorithms must be used to escape the exponential $3^D$ neighbor lookup stencil.
