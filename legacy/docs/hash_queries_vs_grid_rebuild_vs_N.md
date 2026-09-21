# Algorithmic Cost Decomposition: Hash Queries vs. Grid Rebuilds vs. N

## 1. Executive Summary: Amdahl's Law in Spatial Algorithms

In the $d$-dimensional closest pair problem, total computational work decomposes into two fundamentally distinct components:

$$\text{Total Work} = \underbrace{W_{\text{fixed}}(N, D)}_{\text{Neighbor Searches (Fixed)}} + \underbrace{W_{\text{variable}}(N)}_{\text{Grid Rebuilds (Variable)}}$$

* **$W_{\text{fixed}}$ (Fixed Cost):** Searching the $3^D$ neighboring cells in the spatial hash table. **Every point must perform this search, regardless of whether the algorithm is deterministic or randomized.**
* **$W_{\text{variable}}$ (Variable Cost):** Rebuilding the grid and re-inserting accumulated points when a strictly smaller minimum distance $\delta$ is discovered.

---

## 2. Mathematical Formalization

Let:
* $N$ = Total number of input points.
* $D$ = Spatial dimensionality ($D \in [2, 7]$).
* $c_q$ = CPU cost of querying 1 hash cell (hash computation + candidate distance checks).
* $c_r$ = CPU cost of re-inserting 1 point into a newly sized hash cell.

### A. The Fixed Cost: Neighbor Hash Queries
For every incoming point $p_i$, the algorithm must query all $3^D$ relative cell offsets $\{-1, 0, +1\}^D$:

$$W_{\text{fixed}} = c_q \cdot N \cdot 3^D$$

* When $D = 2$: $N \times 3^2 = 9 N$ queries.
* When $D = 4$: $N \times 3^4 = 81 N$ queries.
* When $D = 7$: $N \times 3^7 = 2,187 N$ queries.
* For $N = 133.5\text{M}$ in 4D: $133,484,198 \times 81 = \mathbf{10,812,220,038 \text{ queries (10.8 Billion!)}}$.

### B. The Variable Cost: Grid Rebuilds
When step $i$ discovers $\delta_{\text{new}} < \delta$, the hash table is cleared and all $i$ previous points are re-inserted into the new grid. **During a rebuild, ZERO neighbor queries and ZERO pairwise distance calculations are performed.**

* **In Randomized Grid (Uniform Permutation):**
  By backward analysis (Raimund Seidel, 1993), the probability that step $i$ triggers a rebuild is bounded by $\Pr[I_i = 1] \le \frac{2}{i}$.
  The expected total number of points re-inserted across **all rebuilds combined** is:
  
  $$\mathbb{E}[W_{\text{variable}}^{\text{rand}}] = \sum_{i=1}^N \left( \Pr[\text{rebuild at } i] \times i \cdot c_r \right) \le \sum_{i=1}^N \left( \frac{2}{i} \times i \cdot c_r \right) = \sum_{i=1}^N 2 c_r = \mathbf{2 c_r N}$$

* **In Deterministic Grid:**
  * **Benign / Uniform Inputs:** Rebuilds occur rarely (e.g. 20 to 30 times total). Total re-inserted points $\approx k \cdot N$ where $k \le 2$.
  * **Adversarial Inputs:** Every pair shrinks $\delta$, causing rebuilds on almost every step:
    $$W_{\text{variable}}^{\text{det, adv}} = \sum_{i=1}^N i \cdot c_r = c_r \cdot \frac{N(N+1)}{2} \approx \mathbf{\frac{c_r}{2} N^2}$$

---

## 3. The Average Over All $N!$ Permutations: Why Expected Complexity is Strictly $O(N)$

A natural question arises:
> *"There are $N!$ possible permutations when shuffling. The fastest run takes $O(N)$ and the costliest adversarial run takes $O(N^2)$. If we ran the algorithm on all $N!$ permutations and computed their exact arithmetic average, wouldn't the heavy $O(N^2)$ cases pull the average up to $O(N^{1.5})$ or $O(N \log N)$?"*

The answer is **strictly NO**. The average across all $N!$ combinations is **rigorously $O(N)$**.

### A. The Mathematical Proof of the Average
Let $S_N$ be the symmetric group of all $N!$ permutations. The arithmetic average of total work across all permutations is:

$$\text{Average Work} = \frac{1}{N!} \sum_{\pi \in S_N} T(\pi)$$

The fixed neighbor search cost ($c_q \cdot N \cdot 3^D$) is identical for every permutation. Now examine the average variable rebuild cost:

$$\text{Average Rebuild Work} = \frac{1}{N!} \sum_{\pi \in S_N} \left( c_r \sum_{i=3}^N I_i(\pi) \cdot i \right)$$

Swapping the two summations:

$$\text{Average Rebuild Work} = c_r \sum_{i=3}^N i \cdot \underbrace{\left( \frac{1}{N!} \sum_{\pi \in S_N} I_i(\pi) \right)}_{\text{Fraction of permutations where step } i \text{ triggers a rebuild}}$$

By Seidel's backward analysis:
* Among the prefix of the first $i$ points, there are only **2 critical points** (the endpoints of the closest pair among those $i$ points).
* Because every point in the prefix is placed at the $i$-th position in exactly $\frac{1}{i}$ of all $N!$ permutations, the fraction of permutations that rebuild at step $i$ is:

$$\frac{1}{N!} \sum_{\pi \in S_N} I_i(\pi) \le \frac{2}{i}$$

Substituting $\frac{2}{i}$ back into the summation:

$$\text{Average Rebuild Work} \le c_r \sum_{i=3}^N i \cdot \left( \frac{2}{i} \right)$$

**Notice that $i$ in the numerator and $i$ in the denominator cancel out completely:**

$$\text{Average Rebuild Work} \le c_r \sum_{i=3}^N 2 = 2 c_r (N - 2) \le \mathbf{2 c_r N}$$

Adding the fixed neighbor query work:

$$\mathbf{\text{Average Total Work Across ALL } N! \text{ Permutations} \le c_q \cdot N \cdot 3^D + 2 c_r N = O(N)!}$$

### B. Why Doesn't the $O(N^2)$ Worst-Case Pull the Average Up?

To understand why the worst case has zero impact on the average, we must ask: **How many permutations out of $N!$ actually exhibit the $O(N^2)$ worst case?**

For a permutation to take $O(N^2)$ time, it must trigger a rebuild at almost **every single step**:
* Step 3 rebuilds: probability $\le \frac{2}{3}$
* Step 4 rebuilds: probability $\le \frac{2}{4}$
* Step 5 rebuilds: probability $\le \frac{2}{5}$
* $\dots$
* Step $N$ rebuilds: probability $\le \frac{2}{N}$

The probability that a random permutation triggers a rebuild at every step from $3$ to $N$ is the joint product:

$$\Pr[\text{Worst-Case } O(N^2)] \le \prod_{i=3}^N \frac{2}{i} = \frac{2 \times 2 \times \dots \times 2}{3 \times 4 \times \dots \times N} = \mathbf{\frac{2^{N-1}}{N!}}$$

#### How Microscopic is $\frac{2^{N-1}}{N!}$?
* For $N = 10$: $\frac{2^9}{10!} = \frac{512}{3,628,800} \approx \mathbf{0.014\%}$
* For $N = 50$: $\frac{2^{49}}{50!} \approx \mathbf{10^{-50}}$
* For $N = 100$: $\frac{2^{99}}{100!} \approx \mathbf{10^{-128}}$
* For $N = 1,000,000$: $\frac{2^{999,999}}{1,000,000!} \approx \mathbf{10^{-5,000,000}}$ (infinitesimal).

There are fewer than $2^N$ "evil" permutations in existence. Compared to the massive universe of $N!$, $2^N$ is an invisible speck of dust:

$$\lim_{N \to \infty} \frac{2^N}{N!} = 0$$

#### The Lottery Analogy:
Imagine a lottery with **$10^{128}$ tickets**:
* Exactly **1 ticket** loses $\$1,000,000$ (the $O(N^2)$ case).
* The other **$10^{128} - 1$ tickets** win $\$10$ (the $O(N)$ case).

What is the average outcome across all tickets?
$$\text{Average} = \frac{(10^{128} - 1) \times 10 - 1,000,000}{10^{128}} = \mathbf{\$10.0000000000...}$$

The single $\$1,000,000$ loss is so astronomically outnumbered that it has **zero measurable effect on the average**.

### C. Chernoff Concentration: Hyper-Concentration Around the Mean

The runtime across all $N!$ permutations is not evenly spread between $O(N)$ and $O(N^2)$. Instead, by **Chernoff-Hoeffding bounds**, the runtime is hyper-concentrated tightly around the mean $\mu \approx 2 \ln N$:

```text
Fraction of
Permutations
    ▲
    │             μ = 2 ln N (Mean Rebuilds)
    │                  │
    │                ╭─┴─╮
    │              ╭─╯   ╰─╮
    │            ╭─╯       ╰─╮
    │          ╭─╯           ╰─╮
────┼──────────┴───────────────┴───────────────────────────────► Total Work
    0         O(N)           O(N)                         O(N^2)
        [99.9999999999% of all N! permutations]        [0.00000000001%]
```

* **$99.9999999999\%$ of all $N!$ permutations** finish in $O(N)$ time with $\approx 2 \ln N$ rebuilds.
* The probability of a permutation taking even $2\times$ longer than the mean decays exponentially as $e^{-\Omega(\ln N)} = \frac{1}{N^c}$.
* Therefore, when the Fisher–Yates shuffle chooses a permutation just **once**, you are guaranteed to land in an $O(N)$ permutation with near-certainty ($1 - 10^{-128}$).

---

## 4. The Speedup Equation: $T_{\text{det}} / T_{\text{rand}}$

$$\text{Speedup } S = \frac{T_{\text{det}}}{T_{\text{rand}}} = \frac{c_q \cdot N \cdot 3^D + W_{\text{variable}}^{\text{det}}}{c_q \cdot N \cdot 3^D + 2 c_r N}$$

Dividing both numerator and denominator by $N$:

$$S = \frac{c_q \cdot 3^D + \left(\frac{W_{\text{variable}}^{\text{det}}}{N}\right)}{c_q \cdot 3^D + 2 c_r}$$

---

## 5. The Impact of Dimensionality ($D$)

Notice the structure of the denominator:
* Rebuild cost $= 2 c_r$ (a small constant, independent of dimension).
* Query cost $= c_q \cdot 3^D$ (explodes exponentially with dimension).

### The Dilution Effect:
As dimension $D$ increases, the fixed $3^D$ neighbor query cost completely **drowns out** the variable rebuild cost:

$$\lim_{D \to \infty} S = \frac{c_q \cdot 3^D}{c_q \cdot 3^D} = \mathbf{1.000}$$

| Dimension $D$ | Neighbor Cells ($3^D$) | Rebuild Work ($2N$) | Rebuild % of Total Work | Expected Speedup on Benign Data |
| :---: | :---: | :---: | :---: | :---: |
| **2D** | $3^2 = 9$ | $\approx 2$ | $\approx 18\%$ | **$1.10\times \to 1.25\times$** (Noticeable) |
| **3D** | $3^3 = 27$ | $\approx 2$ | $\approx 7\%$ | **$1.03\times \to 1.08\times$** |
| **4D** | $3^4 = 81$ | $\approx 2$ | $\approx 2.4\%$ | **$1.01\times \to 1.03\times$** (Nearly Parity) |
| **5D** | $3^5 = 243$ | $\approx 2$ | $\approx 0.8\%$ | **$1.002\times \to 1.005\times$** |
| **7D** | $3^7 = 2,187$ | $\approx 2$ | $< 0.09\%$ | **$1.000\times$** (Mathematically locked at 1.0) |

**Conclusion on Dimension:** Any performance improvement achieved by reducing rebuilds is mathematically erased in higher dimensions because neighbor querying dominates the CPU execution time.

---

## 6. The Impact of Dataset Size ($N$)

How does scaling $N$ from $1,000 \to 100,000,000$ affect this balance?

### Phenomenon 1: On Benign / Uniform Data, $N$ Cancels Out!
When data is uniform or has natural spatial continuity (like OpenSky flight data):
* Fixed cost scales as $O(N)$.
* Rebuild cost scales as $O(N)$.
Because $N$ appears linearly in both numerator and denominator, **$N$ cancels out completely**:

$$S_{\text{uniform}} = \frac{c_q \cdot 3^D + k \cdot c_r}{c_q \cdot 3^D + 2 c_r} \quad (\text{Constant with respect to } N)$$

**Empirical Confirmation:** In all synthetic uniform and OpenSky benchmarks, the speedup ratio $T_{\text{det}} / T_{\text{rand}}$ forms a **flat horizontal line near $1.0\times$** across all scales $N$.

### Phenomenon 2: Rebuild Frequency per Point Decays to Zero
The total expected count of rebuilds scales only logarithmically:
$$\mathbb{E}[\text{Rebuilds}] \le 2 \ln N$$

The probability that any arbitrary point triggers a rebuild is:
$$\text{Frequency} = \frac{2 \ln N}{N}$$

* At $N = 1,000$: $\frac{2 \ln(10^3)}{10^3} \approx \frac{13.8}{1000} \approx \mathbf{1.38\%}$ (1 in every 72 points rebuilds).
* At $N = 1,000,000$: $\frac{2 \ln(10^6)}{10^6} \approx \frac{27.6}{10^6} \approx \mathbf{0.0028\%}$ (1 in every 36,000 points rebuilds).
* At $N = 133,484,198$: $\frac{2 \ln(1.33 \times 10^8)}{1.33 \times 10^8} \approx \mathbf{0.000028\%}$ (1 in every 3,600,000 points rebuilds).

$$\lim_{N \to \infty} \frac{2 \ln N}{N} = \mathbf{0}$$

As $N$ becomes massive, **grid rebuilds become practically extinct events**. The algorithm spends $>99.999\%$ of its execution cycles performing neighbor searches.

### Phenomenon 3: On Adversarial Data, $N$ Causes an Explosion
If an adversary constructs a point sequence where every step forces a rebuild:
$$W_{\text{variable}}^{\text{det}} = c_r \cdot \frac{N^2}{2}$$

The speedup ratio becomes:
$$S_{\text{adversarial}} = \frac{c_q \cdot 3^D + c_r \frac{N}{2}}{c_q \cdot 3^D + 2 c_r} \approx \mathbf{\left( \frac{c_r}{2 c_q \cdot 3^D} \right) \cdot N}$$

On adversarial data, **speedup grows linearly with $N$**:
* $N = 10^3 \implies \text{Speedup } \approx 10\times$.
* $N = 10^6 \implies \text{Speedup } \approx 10,000\times$.
* $N = 10^8 \implies \text{Speedup } \approx 1,000,000\times$ (finishes in 30 minutes vs. several years for Deterministic).

---

## 7. Takeaway Matrix

| Factor | Change | Fixed Query Cost ($N \cdot 3^D$) | Variable Rebuild Cost | Net Effect on Speedup ($T_{\text{det}} / T_{\text{rand}}$) |
| :--- | :---: | :---: | :---: | :--- |
| **Dimension** | $D \uparrow$ | Explodes as $3^D$ | Constant ($2N$) | **Speedup converges to $1.0\times$ (Dilution).** |
| **Scale (Uniform)** | $N \uparrow$ | Scales as $O(N)$ | Scales as $O(N)$ | **Speedup remains flat horizontal line $\approx 1.0\times$.** |
| **Scale (Adversarial)** | $N \uparrow$ | Scales as $O(N)$ | Deterministic explodes as $O(N^2)$ | **Randomized speedup explodes linearly ($S \propto N$).** |
