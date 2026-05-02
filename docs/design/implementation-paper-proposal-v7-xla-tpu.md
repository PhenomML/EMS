---
title: "Paper Proposal: Implementation Landscape for AMP-Family Vector CS Algorithms (v7-xla-tpu)"
type: synthesis
wikis: [algorithms, theory, applications]
sources: [../raw/amp-matrix-recovery-codebase.md, ../raw/dey-donoho-2025-steinsense.md, ../raw/marlowe-stanford-specs.md, ../raw/yadav-2026-cutile-evaluation.md, ../raw/mukunoki-2025-ozaki-fp8.md, ../raw/uchino-2026-ozaki-ii-fp8.md, ../raw/schwarz-2025-ozaki-adp.md, ../raw/mojo-linalg-gpu-2026.md]
related: [../algorithms/concepts/steinsense.md, ../algorithms/methods/steinsense-implementation.md, ../algorithms/methods/onsager_closed_form.py, ../algorithms/projects/amp-matrix-recovery.md, ../syntheses/steinsense-in-context.md, ../syntheses/onsager-jacobian-lemma-v2.md, ../syntheses/onsager-jacobian-gemini-critique.md, ../syntheses/warp-assessment.md, ../syntheses/mojo-assessment.md]
created: 2026-05-01
updated: 2026-05-02
---


> **Version:** v7-xla-tpu | **Audience:** Internal | **Date:** 2026-05-02
> **Base:** [v6-lemma-corrected](implementation-paper-proposal-v6-lemma-corrected.md)
> **Differs from v6:** (1) Compilation strategy paragraph in §Motivation: added sentence on XLA kernel fusion for the closed-form Onsager (element-wise ops + GEMM now the measurable fusion target, not AD). (2) RQ3 expanded: explicit question on whether XLA fuses the closed-form Onsager pattern better through `lax.scan` than TorchInductor does through `torch.compile`. (3) Extension B expanded: TPU Pod scaling added as empirical test of the AMP large-$N$ assumption; `torch_xla` path noted as second framework on the same hardware; "What this adds" updated to cover three distinct findings.
> **Redaction guide (before sending to NVIDIA):** Remove (1) the cuTile availability table note "Confirmed by NVIDIA Python team" in §Hardware matrix; (2) the "personal relationship with NVIDIA's Python team" clause in Open question §3; (3) the "Access path" paragraph in Extension C. Additionally review Extension E §GB10 comparison language and §Tools considered before sharing externally.

---

# Paper Proposal: Implementation Landscape for AMP-Family Vector CS Algorithms

**Status:** Internal draft — for discussion before raising with collaborators.

---

## Working title

*SteinSense Across the Stack: CPU Through Petascale GPU Implementation Strategies for AMP-Based Vector Compressed Sensing*

---

## One-sentence summary

We implement SteinSense — the recently proven optimal vector CS algorithm — in seven computational backends spanning both dominant ML frameworks (JAX and PyTorch) and GPU kernel layers (Triton, cuTile), across four hardware tiers covering three GPU generations (Ampere, Hopper, Blackwell), and show that all implementations reproduce the same theoretically predicted phase transition while measuring the value of explicit loop fusion (`lax.scan`) versus automatic compilation (`torch.compile`) for iterative numerical algorithms.

---

## Motivation

SteinSense (Dey & Donoho, arXiv:2505.00326) is a short algorithm with a clean mathematical structure: a fixed-point iteration whose inner step is a James–Stein denoiser, an Onsager correction computed as a Jacobian average, and two matrix-vector products. Its per-iteration operations are a small, well-defined set of primitives (GEMM, eigendecomposition of a small matrix, a vmapped shrinkage denoiser, a Jacobian sum). This simplicity makes it an unusually tractable vehicle for a systematic, multi-dimensional implementation study.

The study is organized around three independently varying axes.

**Abstraction tier.** Python-accessible GPU stacks now span a wide range: from interpreted NumPy and explicit CUDA arrays (cuPy/cuBLAS), through JIT-compiled frameworks (JAX with `lax.scan`, PyTorch with `torch.compile`) that promise high-level expressibility without sacrificing performance, to hand-written tile kernels (Triton, cuTile) where the programmer controls memory layout explicitly. SteinSense is short enough that implementing it at each tier is a realistic project rather than an engineering heroics exercise — the code is never more than a few hundred lines — making it an ideal vehicle for measuring what each tier actually costs in performance and developer effort.

**Hardware generation.** Available hardware spans three GPU generations — Ampere (8× A100, Sherlock), Hopper (248× H100, Marlowe SuperPOD, 11.1 PFlops), and Blackwell (2× GB10, DGX Spark) — without requiring code changes between them. The hardware axis measures generation-to-generation improvement independently of implementation choices. Marlowe's scale ($N \sim 10^6$, 400 Gb/s InfiniBand fabric) enables experiments inaccessible on local hardware.

**Compilation strategy.** Two philosophies for fusing an iterative loop are now directly comparable: JAX's `lax.scan`, where the programmer explicitly declares the loop structure and XLA compiles all iterations into a single kernel, versus PyTorch's `torch.compile`, which attempts automatic fusion of a plain Python loop via TorchInductor. This comparison — explicit declaration versus automatic compilation — is the central question that PyTorch's promotion to the core matrix adds to the study. The closed-form Onsager correction (Contribution C2) sharpens this comparison: by replacing $NB$ AD passes with element-wise weight computation ($q_i$, $w_i$) fused into a single GEMM $H^\top D H$, the remaining fusion target is exactly the pattern — scalar broadcasts followed by a matrix product — where XLA's algebraic simplification is designed to excel. The question of whether XLA fuses this pattern better through a statically declared `lax.scan` than TorchInductor does through automatic compilation is now directly measurable.

Separating these three axes within a single controlled sweep, rather than conflating them as prior benchmarks do, is the core methodological contribution. The mathematical validation angle — SteinSense has a theoretically predicted phase transition boundary, and all implementations must reproduce it — grounds the performance comparison in a correctness requirement and makes the study relevant to the statistics and signal processing community, not only to systems researchers.

---

## Research questions

1. **Performance vs. problem scale**: How does wall time scale with $(N, B, \delta)$ across implementations, and which implementation wins at which scale?
2. **Abstraction cost**: What performance is sacrificed at each abstraction tier — high-level frameworks (JAX, PyTorch), mid-level CUDA (cuPy/cuBLAS), and low-level tile kernels (Triton, cuTile) — and is the cost at each tier justified by implementation simplicity?
3. **Compiler fusion strategies**: Does JAX's explicit `lax.scan` primitive produce better loop fusion than PyTorch's automatic `torch.compile` for an iterative AMP algorithm? At what $(N, B)$ does each approach's compilation overhead amortize, and where does TorchDynamo fail to fuse (graph breaks at `linalg.eigh` or loop control flow)? With the closed-form Onsager in place, the dominant remaining fusion target is the element-wise weight computation ($q_i$, $w_i$, masking) fused into the GEMM $H^\top D H$ — the exact pattern where XLA's algebraic simplification specializes. Does XLA fuse this more completely through the statically declared `lax.scan` loop than TorchInductor achieves through `torch.compile`?
4. **Jacobian optimization**: How much does replacing automatic differentiation (`vmap(jacfwd(...))`) with the closed-form Jacobian sum affect performance across backends?
5. **Mathematical fidelity**: Do GPU numerical paths (float32 accumulation order, `lax.cond` both-branches evaluation) produce phase transition curves consistent with the CPU baseline and the theoretical prediction?
6. **Hardware generation**: How does performance scale across three GPU generations (A100 → H100 → GB10) for each implementation, and how much of the improvement is captured by code that runs unchanged?
7. **Multi-GPU parallelism strategies**: Does *replicate parallelism* (multiple independent recoveries in parallel across GPUs) and *single-instance parallelism* (one large recovery sharded across GPUs) produce different scaling profiles, and at what $N$ does single-instance parallelism become advantageous? Marlowe's 248-GPU InfiniBand fabric enables this at scales not available locally.
8. **Numerical precision**: Does SteinSense's inherent noise tolerance mean that native FP32 (TF32 tensor cores) produces phase transition curves indistinguishable from the FP64 baseline, or does precision matter? If FP64 accuracy is required, does the Ozaki scheme (FP64-accurate DGEMM via FP8/INT8 tensor cores) recover it at useful speedup across Ampere, Hopper, and Blackwell?

---

## Expected contributions

1. **Empirical**: First systematic performance comparison of NumPy, cuPy/cuBLAS, JAX, PyTorch, Triton, and cuTile for an AMP-family iterative algorithm, across three GPU generations (Ampere, Hopper, Blackwell) and two multi-GPU parallelism modes, covering six orders of magnitude in problem scale ($N=100$ to $N=10^6$).
2. **Algorithmic**: A novel closed-form expression for the Onsager Jacobian sum in SteinSense, presented as a proved lemma, reducing the per-iteration cost from $N$ calls to an AD-differentiated denoiser to a scalar sum and one weighted Gram matrix product. Dey & Donoho (2025) explicitly identify the $NB^2$ Jacobian computation as "a major computational bottleneck that needs to be overcome using advanced software"; this lemma is the analytical answer to that open problem. Empirical validation characterizes the speedup across all backends.

   > **Lemma (Closed-form Onsager Jacobian for SteinSense).** *Let $H \in \mathbb{R}^{N \times B}$ with rows $h_i^\top$, let $\Sigma \in \mathbb{R}^{B \times B}$ be symmetric positive definite, and let $q_i = h_i^\top \Sigma^{-1} h_i$. Under the standard AMP assumption that the noise covariance is treated as fixed at each iteration, the per-row contribution to the Onsager correction matrix of the James–Stein denoiser $\eta_{\mathrm{JS}}(y;\Sigma) = \bigl(1 - \tfrac{B-2}{q}\bigr)_{\!+} y$ (nonsingular branch, $q_i > B-2$) is*
   >
   > $$J_i^\top = \Bigl(1 - \tfrac{B-2}{q_i}\Bigr) I_B + \tfrac{2(B-2)}{q_i^2}\, \bigl(\Sigma^{-1} h_i\bigr)\, h_i^\top$$
   >
   > *Singular rows ($q_i \leq B-2$) contribute $J_i^\top = 0$. The Onsager correction matrix (Dey & Donoho 2025, Algorithm 2: $J_{\mathrm{ColorJS}} = \frac{1}{N}\sum_i \mathrm{Jac}(\eta)_i^\top$) therefore admits the closed form*
   >
   > $$\sum_{i=1}^{N} J_i^\top \;=\; \alpha\, I_B \;+\; 2(B-2)\, \Sigma^{-1} H^\top D H$$
   >
   > *where $\alpha = \sum_{i:\, q_i > B-2} \!\bigl(1 - \tfrac{B-2}{q_i}\bigr)$ is a scalar and $D = \mathrm{diag}(1/q_i^2)$ restricted to nonsingular rows. Applied in the residual update as $R^t \cdot \frac{1}{N}\sum_i J_i^\top$. Verified against `vmap(jacfwd).sum(0).T` at machine epsilon by `tests/verify_onsager_jacobian_v3.py`; validated by Gemini (2026-05-02). Full derivation and version history: [`syntheses/onsager-jacobian-lemma-v2.md`](onsager-jacobian-lemma-v2.md).*

3. **Mathematical**: Demonstration that all GPU implementations reproduce the theoretically predicted SteinSense phase transition at both the aggregate level (recovery probability curves) and the instance level (per-seed comparison across implementations); the controlled RNG design enables attribution of numerical differences to specific implementation choices — precision regime, compilation strategy, or hardware generation.
4. **Framework comparison**: First head-to-head measurement of JAX `lax.scan` vs. PyTorch `torch.compile` fusion for an iterative sparse recovery algorithm; identification of graph break sources in TorchDynamo for scientific computing workloads; characterization of the conditions under which automatic compilation matches explicit scan declaration.
5. **Precision analysis**: Empirical determination of whether SteinSense's inherent noise tolerance makes native FP32 sufficient for phase-transition fidelity, or whether FP64 emulation (Ozaki scheme) is required — with speedup characterization for the Ozaki path if needed.
6. **Prescriptive**: A practical guide for the signal processing and statistics community on implementation and hardware strategy for AMP-family algorithms — which backend, precision mode, and hardware tier is appropriate at which problem scale, and which multi-GPU parallelism mode to prefer.
7. **Infrastructure**: An open, EMS-based benchmark suite that can be re-run on new hardware generations without modification to the algorithm implementations.

---

## Implementation matrix

The code is short enough that all cells are feasible. Each implementation is self-contained: the same AMP loop expressed in a different backend.

| Implementation | Backend | Notes |
|---|---|---|
| **NumPy** | CPU | Dey's original reference; serial |
| **JAX-CPU** | JAX on CPU | `lax.scan` fusion, `vmap(jacfwd(...))` Onsager |
| **JAX-GPU** | JAX on GPU | Remove `JAX_PLATFORMS="cpu"`; otherwise identical to JAX-CPU |
| **PyTorch-GPU** | PyTorch on GPU | `torch.linalg.eigh`; `torch.func.vmap` + `torch.func.jacfwd`; `torch.compile(mode="max-autotune")` wrapping the AMP loop |
| **cuPy/cuBLAS** | GPU, NumPy-compatible | Explicit CUDA arrays; cuBLAS dispatch via cuPy; no compiler fusion |
| **Triton** | GPU, custom kernels | Fused denoiser + Jacobian + residual kernel; Python-level tile control |
| **cuTile** | GPU, tile-native | NVIDIA CUDA Tile (CUDA 13.1+); runs on Ampere (software DMA, no TMA) and Blackwell (full TMA); **not supported on Hopper (H100)** |

Each implementation is tested in two Jacobian variants:
- **AD variant**: Onsager correction via automatic differentiation (`jacfwd` / `torch.func.jacfwd` or equivalent)
- **Closed-form variant**: Onsager correction via the analytical Jacobian sum (see [algorithms/methods/steinsense-implementation.md](../algorithms/methods/steinsense-implementation.md))

This yields a 7 × 2 = 14-cell performance matrix.

### Precision axis

Primary question: does FP32 produce phase transition curves within Monte Carlo noise of the FP64 baseline? If yes, FP64 accuracy is unnecessary and the Ozaki comparison becomes an optional contribution. If no, the precision section becomes a required part of the paper. This experiment is inexpensive (same code, different dtype) and should be run first.

Each JAX-GPU and cuPy cell is also tested across a precision axis:

| Precision mode | Notes |
|---|---|
| **FP64** | NumPy baseline; JAX with `x64` enabled |
| **FP32 (TF32)** | JAX-GPU default; Blackwell tensor cores |
| **FP16** | Explicit downcast; tests tolerance to lower precision |
| **FP64-emulated (Ozaki)** | FP64-accurate GEMM via FP8/INT8 tensor cores; NVIDIA ADP framework (Schwarz et al. arXiv:2511.13778); tests whether emulation cost is justified |

Four additional rows isolate compiler fusion value and enable the JAX vs. PyTorch comparison directly:
- **JAX-GPU, no scan**: iteration loop in Python; GPU dispatch per step
- **JAX-GPU, scan**: `lax.scan` fused; all iterations in a single compiled kernel
- **PyTorch-GPU, no compile**: Python loop with eager dispatch; no `torch.compile`
- **PyTorch-GPU, compiled**: `torch.compile(mode="max-autotune")`; TorchInductor attempts automatic loop fusion

The JAX pair and PyTorch pair form a 2×2 comparison: {explicit declaration, automatic compilation} × {fused, unfused}. This is the direct measurement of RQ3.

---

## Hardware matrix

Four hardware tiers spanning three GPU generations.

| Tier | Hardware | Count | Memory | Architecture | Location | Role |
|---|---|---|---|---|---|---|
| CPU | Sherlock / local | — | — | — | Sherlock / local | NumPy baseline |
| Ampere | A100 SXM 80GB | 1 | 80 GB HBM2e | cc 8.0 | Sherlock | Single-GPU Ampere baseline |
| Ampere | A100 SXM 80GB | 8 | 640 GB total | cc 8.0 | Sherlock | Multi-GPU (replicate-parallel) |
| Ampere | A100 SXM 80GB | 8 | 640 GB total | cc 8.0 | Sherlock | Multi-GPU (single-instance, large $N$) |
| Hopper | H100 SXM 80GB | 1 | 80 GB HBM3 | cc 9.0 | Marlowe | Single-GPU Hopper (generation step) |
| Hopper | H100 SXM 80GB | up to 248 | up to 19.8 TB | cc 9.0 | Marlowe | Large-scale multi-GPU (InfiniBand fabric) |
| Blackwell | GB10 | 1 | 128 GB LPDDR5X | cc 10.0 | DGX Spark | Single-GPU Blackwell |
| Blackwell | GB10 | 2 | 256 GB total | cc 10.0 | DGX Spark | Multi-GPU Blackwell |

**H100 performance context (vs. A100):** ~3× TF32 tensor core throughput (989 vs. 312 TFLOPS), ~1.7× memory bandwidth (3.35 vs. 2.0 TB/s), NVLink 4.0 (900 vs. 600 GB/s). The A100→H100 step is larger than H100→GB10 in raw compute.

**GB10 memory subsystem caveat.** The DGX Spark's GB10 uses LPDDR5X unified memory (~273 GB/s) rather than the HBM found on server-class GPUs — a known limitation. For comparison: A100 delivers ~2,000 GB/s (HBM2e), H100 ~3,350 GB/s (HBM3), and even an M4 Pro MacBook Pro matches GB10 bandwidth (273 GB/s) while an M4 Max doubles it (546 GB/s). SteinSense's dominant operations are GEMM-bound and memory-bandwidth-bound at large $N$; the GB10 is therefore expected to underperform its Blackwell tensor-core throughput rating, with the gap widening as $N$ increases. This is a reportable finding: the GB10 isolates the effect of the LPDDR5X memory bottleneck independently of the compute generation, and the contrast with server-class Blackwell (Extension C, HBM3e) will quantify the memory subsystem's contribution to wall time.

**cuTile availability across tiers:**

| Hardware | cuTile support | Notes |
|---|---|---|
| A100 (Ampere, cc 8.0) | Yes | Confirmed by NVIDIA Python team; tile loads use software DMA (no TMA hardware on Ampere) |
| H100 (Hopper, cc 9.0) | **No** | Deliberately skipped; CUDA 13.2 supports cc 8.x and 10.x/12.x but not 9.x; future support planned |
| GB10 (Blackwell, cc 10.0) | Yes | Full TMA hardware acceleration |

Consequence: **Marlowe cuTile is currently unsupported** in public CUDA releases. The default Marlowe implementation matrix is NumPy (baseline), JAX, cuPy/cuBLAS, and Triton. The portability gap itself (cuTile skipping Hopper) is a reportable finding. However, early/pre-release access to cuTile on Hopper is being pursued via the NVIDIA Python team relationship — if obtained, Marlowe recovers the full implementation matrix and the paper gains a complete three-generation cuTile comparison.

An independent evaluation (Yadav et al., arXiv:2604.23466, April 2026) confirms: cuTile does not run on H100; Triton achieves 62–101% of cuBLAS across *all* tested platforms without architecture-specific tuning, demonstrating substantially better portability than cuTile.

### Multi-GPU parallelism modes (distinct experiments)

These are qualitatively different and should be measured and reported separately:

**Replicate parallelism** — dispatch independent MC replicates across GPUs. Embarrassingly parallel; trivially orchestrated by EMS/Dask. Scales throughput without changing single-instance problem size. Relevant at all $N$.

**Single-instance parallelism** — shard one large recovery (very large $N$) across multiple GPUs, with the measurement matrix $A$ partitioned row-wise across devices and residuals exchanged over NVLink. Relevant only at $N$ large enough that single-GPU HBM is a constraint or that inter-GPU bandwidth is amortized. Likely requires $N \geq 10^4$–$10^5$ to show meaningful benefit.

---

## Experimental design

### Parameter sweep

| Axis | Values |
|---|---|
| $N$ (signal rows) | 100, 500, 1000, 2000, 5000, 20000, 100000$^\dagger$, 1000000$^\ddagger$ |
| $B$ (signal columns) | 1, 5, 10, 20, 50 |
| $\delta = n/N$ (undersampling ratio) | 0.1, 0.2, 0.3, 0.5 |
| Signal distribution | Normal, Poisson, Binary |
| MC replicates per cell | $\geq 20$ |

$^\dagger$ Large $N$ (20000, 100000): probes multi-GPU single-instance scaling on Sherlock A100 and Marlowe H100; restricted to a subset of $(B, \delta)$ values.
$^\ddagger$ Very large $N$ ($10^6$): Marlowe only; tests the InfiniBand multi-node fabric and the limit of JAX/Triton scalability; minimal $(B, \delta)$ grid.

### Primary metrics

- **Wall time per recovery** (seconds): end-to-end, JIT warm-up amortized over MC replicates
- **Throughput** (recoveries/second at fixed $(N, B, \delta)$): for replicate-parallel multi-GPU
- **Convergence iterations**: iterations to relative error $< 10^{-4}$
- **Phase transition curve**: empirical recovery probability vs. $\delta$ at fixed $\epsilon = k/N$, for each implementation × hardware combination

### Validation condition

The RNG seed is a first-class parameter of the sweep: each $(N, B, \delta, \text{seed})$ tuple generates a specific problem instance $(A, x_0)$ that every implementation processes. This controlled design enables two levels of validation.

**Aggregate validation.** Recovery probability curves across the $(N, B, \delta)$ sweep must match the theoretical phase transition and the NumPy/float64 baseline within Monte Carlo noise. Any implementation that diverges at the curve level is flagged and its numerical behavior investigated (float32 accumulation order, `lax.cond` both-branch evaluation, `torch.compile` operator reordering, etc.).

**Instance-level validation.** Because the same problem instances run across all implementation × hardware combinations, outcomes can be compared at the individual run level. An instance recovered by one implementation but not another is a specific, attributable numerical event — not statistical noise — and can be traced to a particular axis: precision regime, compilation strategy, or hardware generation. This per-instance comparison is a more sensitive fidelity test than aggregate recovery probability alone.

The EMS + BigQuery infrastructure naturally supports both levels: each $(N, B, \delta, \text{seed}, \text{implementation}, \text{hardware})$ is a row in the results table, and cross-implementation joins on $(N, B, \delta, \text{seed})$ are straightforward. The data analysis plan should exploit this structure to isolate variation attributable to each axis of the study.

### Infrastructure

EMS dispatches the full parameter sweep across all implementations and hardware targets; results land in a common BigQuery table for unified analysis.

| Environment | Access | Status |
|---|---|---|
| Sherlock (A100) | SLURM, existing `donoho` queue allocation | Ready — already in Dey's codebase |
| Marlowe (H100) | SLURM; allocation proposal required | Pending — 5,000 free GPU hours available to new PIs; large-scale work requires faculty-committee review |
| DGX Spark (GB10) | Local | Ready — hardware on-site |

Marlowe uses SLURM with the same job submission model as Sherlock; EMS adaptation is straightforward. Contact: srcc-support@stanford.edu.

---

## Key related work

- **Mukunoki (2025), arXiv:2508.00441** — "DGEMM without FP64 Arithmetic – Using FP64 Emulation and FP8 Tensor Cores with Ozaki Scheme." Revisits Ozaki scheme with FP8 tensor cores on Blackwell RTX; adds FP64 arithmetic emulation via integer arithmetic (eliminating all hardware FP64 instructions) and blocking for $k > 2^{16}$. Foundational reference for the Ozaki/precision axis. — [raw/mukunoki-2025-ozaki-fp8.md](../raw/mukunoki-2025-ozaki-fp8.md)

- **Uchino, Ozaki, Imamura (2026), arXiv:2603.10634** — "Double-Precision Matrix Multiplication Emulation via Ozaki-II Scheme with FP8 Quantization." Adapts the Ozaki-II scheme (fewer GEMM calls than Ozaki-I) to FP8 MMA units; motivated by Blackwell Ultra / Rubin reducing INT8 performance. Ozaki-II (INT8) achieves 137–138 TFLOP/s on B200, 1.3–3.9× speedup over native FP64 at large matrices. Workspace: 27–55 GB. — [raw/uchino-2026-ozaki-ii-fp8.md](../raw/uchino-2026-ozaki-ii-fp8.md)

- **Schwarz et al. (NVIDIA Research, 2025), arXiv:2511.13778** — "Guaranteed DGEMM Accuracy While Using Reduced Precision Tensor Cores Through Extensions of the Ozaki Scheme." Introduces ADP (Automatic Dynamic Precision): GPU-resident, auto-selects Ozaki slice count via ESC estimator, falls back to native FP64 automatically. Up to 2.3× on Blackwell GB200, up to 13.2× on RTX Pro 6000 Blackwell (where native FP64 is very slow). Most production-ready Ozaki implementation; relevant if validation sweep reveals FP32 is insufficient. — [raw/schwarz-2025-ozaki-adp.md](../raw/schwarz-2025-ozaki-adp.md)

- **Yadav, Zhao, Kumar (2026), arXiv:2604.23466** — "Evaluating CUDA Tile for AI Workloads on Hopper and Blackwell GPUs." First independent cross-architecture evaluation of cuTile vs. cuBLAS, Triton, WMMA on H100, B200, and RTX PRO 6000. Key findings directly relevant to this proposal: (1) cuTile does not run on H100; (2) cuTile GEMM reaches only 52–79% of cuBLAS — not the right tool for standard GEMMs; (3) cuTile fused attention reaches 2.5× FlashAttention-2 on B200 but only 53% on RTX PRO 6000, exposing large cross-architecture gaps; (4) Triton achieves 62–101% of cuBLAS across all platforms without architecture-specific tuning. Our paper extends this comparison to an iterative sparse recovery algorithm with a non-standard inner kernel (the Onsager correction), and adds the Ampere generation and the CPU baseline. — [raw/yadav-2026-cutile-evaluation.md](../raw/yadav-2026-cutile-evaluation.md)

---

## Optional extensions (access pending)

The core experimental plan (Sections above) is self-contained and executable with hardware already in hand. The following extensions require non-trivial negotiation to access. They are tracked here so the proposal can be updated once access is confirmed. **None of these extensions blocks the core work.**

### Extension A — AMD GPU via Triton

**Motivation.** Triton's portability claim — that a single kernel compiles comparably on NVIDIA and AMD without architecture-specific tuning — can only be validated with AMD hardware. If the Triton SteinSense kernel achieves similar performance relative to rocBLAS on AMD as it does relative to cuBLAS on NVIDIA (Yadav et al.: 62–101%), that transforms "Triton is good on NVIDIA" into "Triton is genuinely vendor-neutral." This strengthens the portability finding considerably and distinguishes the paper from any NVIDIA-only benchmark.

**Hardware target.** AMD Instinct MI300X (CDNA3): 192 GB HBM3 unified memory, ROCm 6.x. The larger per-device memory (vs. 80 GB A100/H100, 128 GB GB10) means the large-$N$ single-device experiment that requires multi-GPU sharding on NVIDIA hardware fits on a single MI300X — a useful data point in its own right.

**What ports cleanly:**
- NumPy — CPU baseline, trivially vendor-neutral
- Triton — first-class ROCm support; the same kernel, recompiled
- **PyTorch (now core)** — first-class ROCm support; the primary supported framework for AMD Instinct GPUs; `torch.compile` + ROCm is a proven production path; substantially more mature than `jax-rocm`
- JAX — `jax-rocm` package; `lax.scan`, `vmap`, `linalg.eigh` all have ROCm implementations; functional for standard ops but less mature than PyTorch-ROCm

**What does not apply:** cuPy (CUDA arrays), cuTile (NVIDIA-only). The AMD row in the implementation table would be NumPy + Triton + PyTorch-ROCm + JAX-ROCm, with rocBLAS as the explicit BLAS baseline in place of cuBLAS. PyTorch-ROCm is the proven anchor; JAX-ROCm is best-effort.

**Status:** access under negotiation. No AMD hardware yet confirmed.

---

### Extension B — Google TPU via JAX

**Motivation.** JAX was designed at Google Brain for TPU; `lax.scan` compilation was developed specifically for TPU's on-chip execution model. The SteinSense JAX code requires a single environment change (`JAX_PLATFORMS = "tpu"`) to target TPU — there is no porting work. Two independent scientific questions motivate this extension.

*Compilation:* Does `lax.scan` provide a larger speedup on TPU (where XLA fusion eliminates inter-TPU-core transfers across the 50-step AMP loop) than on GPU (where XLA achieves similar fusion but via a different hardware path)? The closed-form Onsager makes this question sharper: the remaining fusion target — element-wise weight computation fused into $H^\top D H$ — is a pattern XLA was designed to handle, and TPU provides a second hardware context in which to measure it.

*Large-system limit:* The AMP Onsager correction is theoretically grounded in the $N \to \infty$ limit. Distributed TPU topology (TPU v5p or v6e Pod) enables experiments at $N \sim 10^6$–$10^7$ with `jax.Array` sharding across devices and near-transparent distributed `jit` — scales inaccessible on any local hardware. These experiments directly test the large-$N$ regime where the AMP asymptotic guarantees are expected to hold, providing empirical grounding for the theoretical assumption. Marlowe's 248 H100s can test $N \sim 10^6$ on NVIDIA; a TPU Pod tests the same regime on Google's interconnect architecture.

**Hardware target.** TPU v5p or v6e (Trillium) research allocation via Google. Access via a research collaboration agreement rather than Google Cloud billing.

**What ports cleanly:**
- NumPy (via `jnp` on TPU, same code)
- JAX — all ops (`lax.scan`, `vmap`, `linalg.eigh`, closed-form Jacobian) are supported on TPU via XLA
- **PyTorch (now core)** — `torch_xla` bridges PyTorch to XLA/TPU; since PyTorch is now a core implementation, `torch_xla` extends that result to TPU without additional porting work

**What does not apply:** cuPy (CUDA), cuTile (NVIDIA), Triton on TPU (Google uses "Pallas" as its TPU kernel DSL — related to Triton in spirit but a distinct language; out of scope unless Pallas support is specifically offered).

**What this adds to the paper.** Three distinct findings: (1) Cross-platform XLA fusion comparison — does `lax.scan`'s fusion advantage on NVIDIA GPU persist on TPU, where XLA was designed to run? (2) `torch_xla` vs. `lax.scan` on identical TPU hardware — the compiler-strategy comparison gains a second platform data point. (3) Large-$N$ empirical validation of the AMP large-system limit — TPU Pod scale ($N \sim 10^6$) provides the regime where the asymptotic Onsager correction assumption is expected to hold cleanly, grounding the theoretical convergence claim in measured phase transition fidelity.

**Status:** access under negotiation. No TPU allocation yet confirmed.

---

### Extension C — Larger Blackwell and Vera Rubin (NVIDIA early access)

**Motivation.** The core plan uses GB10 (Blackwell cc 10.0, 128 GB LPDDR5X) as the Blackwell representative. NVIDIA's rack-scale Blackwell systems — GB200 NVL72 (72 GPUs, 192 GB HBM3e each, NVLink 5.0 interconnect) and the standalone B200 (192 GB HBM3e) — offer substantially more memory per device and higher aggregate bandwidth, enabling single-instance experiments at $N$ that cannot fit on any single GB10. Vera Rubin (NVIDIA's post-Blackwell architecture, announced GTC 2025) introduces a further generation step with a shifted precision profile: Uchino et al. (arXiv:2603.10634) note that Blackwell Ultra and Rubin reduce INT8 throughput relative to FP8, making the FP8-based Ozaki scheme the forward path. A Rubin data point would complete the four-generation progression (Ampere → Hopper → Blackwell → Rubin) and make the hardware generation finding substantially more durable.

**Access path.** The existing NVIDIA Python team relationship — already the channel for cuTile on H100 early access — is the natural contact point. NVIDIA research partnerships have historically offered early access to pre-release systems for academic benchmarking work.

**What ports cleanly.** The full implementation matrix: NumPy, JAX, Triton, cuPy/cuBLAS, PyTorch run without modification. cuTile on GB200/B200 (cc 10.0): supported, full TMA hardware. cuTile on Rubin: support expected (cc 12.x); confirm when access is arranged.

**What this adds.** (1) Larger-memory single-device experiments: the $A$ matrix that requires NVLink sharding on GB10 fits on a single GB200, cleanly separating memory constraint from parallelism benefit. (2) The Ozaki precision story gains a Rubin data point — the generation where FP8 Ozaki becomes the dominant path over INT8. (3) Four GPU generations in one paper is a strong hardware narrative for SC/ICS.

**Status:** access under negotiation via NVIDIA relationship. No hardware confirmed.

---

### Extension D — AWS Trainium 2 and Intel Gaudi 3 (cloud research credits)

**Motivation.** Extension B (Google TPU) establishes that the JAX implementation runs on Google's custom silicon with no code changes. AWS Trainium 2 extends that finding to a second cloud-provider accelerator, completing a natural "big cloud custom silicon" comparison: Google TPU, AWS Trainium, NVIDIA GPU — all running the same JAX code. Together with Extension B, this makes the JAX portability claim substantially stronger and broadens the paper's relevance to the growing community of researchers running workloads on cloud-provider AI hardware.

**Hardware target.** AWS Trainium 2 (`trn2.48xlarge`, 16 chips per instance). AWS Neuron SDK provides a JAX plugin (`jax-neuronx`) that compiles via XLA — the same compilation path as GPU. The open question is whether `lax.scan` compiles cleanly through the `neuronx-cc` compiler; if it does, this is near-zero porting effort.

**Access path.** No personal negotiation required. AWS has a research credit program accessible to academic groups; a Stanford affiliation and Dave's involvement strengthen the application. This distinguishes Extension D from Extensions A and C, which require direct industry relationships.

**Secondary target: Intel Gaudi 3.** Intel's AI accelerator is available on the Intel Developer Cloud (free research tier) and AWS `dl2q` instances. Intel is actively positioning Gaudi 3 as an NVIDIA alternative for HPC training workloads. JAX support exists but is less mature than AWS Neuron. Worth pursuing as a lower-priority addition within the same access process, particularly given Intel's geographic proximity and active academic partnership program.

**What ports cleanly.** NumPy (CPU baseline, trivially); JAX via Neuron SDK (primary target); closed-form Jacobian (pure JAX). cuPy, cuTile, and Triton do not apply.

**Status:** access not yet applied for. AWS research credit application is the first step; no personal relationship required.

---

### Extension E — Apple MLX on Apple Silicon

**Motivation.** MLX (Apple Machine Learning Research, 2023) is a NumPy-like array framework for Apple Silicon with JAX-style composable function transforms (`mx.vmap`, `mx.grad`, `mx.compile`) and a unified memory model. It has all the primitives SteinSense requires: `mlx.core.linalg.eigh`, `mx.vmap`, `mx.grad` (functional AD), and matrix multiplication via Metal. The primary research angle is architectural: both the GB10 (LPDDR5X, ~273 GB/s) and Apple Silicon use unified CPU+GPU memory. An M4 Pro MacBook Pro (273 GB/s) is bandwidth-matched to the GB10; an M4 Max (546 GB/s) is 2× faster. At memory-bandwidth-limited problem scales this raises a pointed question: does a MacBook outperform a DGX Spark on SteinSense — and does the M4 Max's bandwidth advantage translate to proportional speedup?

**What ports cleanly.** All SteinSense operations map directly to MLX primitives:
- GEMM: `mx.matmul` dispatches to Metal Performance Shaders
- Eigendecomposition: `mlx.core.linalg.eigh`
- Per-row Jacobian: `mx.vmap(mx.jacfwd(...))` or `mx.vmap(mx.grad(...))` compositions
- Closed-form Jacobian: pure array arithmetic, trivially portable
- Loop fusion: `mlx.core.compile()` optimizes the AMP iteration loop; no `scan` primitive exists, but MLX's lazy evaluation with graph compilation achieves partial fusion

**Key limitation.** MLX has no explicit `scan` primitive. The AMP loop is a Python for-loop compiled via `mx.compile()`, which may fuse within but not guaranteed across iterations. This makes MLX's loop fusion directly comparable to PyTorch's `torch.compile` — both are compiler-based approaches vs. JAX's explicit `lax.scan` declaration. Since PyTorch is now in the core matrix, the MLX vs. PyTorch compiler comparison is grounded in a measured NVIDIA baseline rather than a hypothetical one.

**Hardware.** M4 Pro MacBook Pro (273 GB/s, bandwidth-matched to GB10) and M4 Max (546 GB/s, 2× GB10) — both already on hand. MLX is pip-installable; no access negotiation required.

**The GB10 comparison.** Both GB10 and Apple Silicon are unified memory architectures where the GPU and CPU share the same physical memory pool. The M4 Pro (273 GB/s) is bandwidth-matched to the GB10 — a fair comparison that isolates framework and Metal-backend efficiency from memory subsystem effects. The M4 Max (546 GB/s) then tests whether 2× bandwidth translates to proportional speedup for SteinSense's memory-bound operations. Both results would appear alongside the GB10 result in the memory-bandwidth analysis section.

**Note on JAX-Metal.** An alternative to a native MLX port is `jax-metal` (JAX's Apple Silicon backend), which requires no code changes beyond setting `JAX_PLATFORMS="metal"`. A `jax-metal` measurement would be faster to obtain and would isolate the JAX vs. MLX framework comparison on identical hardware. Both measurements are complementary: `jax-metal` tests JAX portability; MLX tests whether Apple's native framework has Metal-specific optimizations that JAX-Metal does not.

**Status:** ready to implement. Hardware likely already available; no access negotiation required.

---

### Impact on framing if extensions land

With AMD + TPU (Extensions A, B) and cloud-provider silicon (Extension D), the paper's central finding expands: the same JAX and PyTorch implementations run on CPU, NVIDIA GPU, AMD GPU, Google TPU, and AWS Trainium with no code changes — and the `lax.scan` vs. `torch.compile` comparison measured on NVIDIA GPU repeats on each new platform. Triton (Extension A) extends vendor-neutral coverage to AMD without tuning. With larger Blackwell + Rubin (Extension C), the NVIDIA hardware narrative spans four GPU generations and rack-scale systems. With MLX (Extension E), the `torch.compile` vs. `mx.compile()` compiler comparison gains a Metal-backed data point, and the GB10 gains two direct comparators on the same unified-memory architecture: M4 Pro (bandwidth-matched at 273 GB/s) isolates framework efficiency; M4 Max (2× at 546 GB/s) tests bandwidth scaling. The mathematical validation angle — phase transitions reproduce across all platforms — remains the distinguishing element relative to pure systems benchmarking regardless of which extensions land.

---

## Tools considered and excluded

Two Python-accessible frameworks were evaluated for the implementation matrix — both the core matrix and the optional extensions — and excluded. Brief notes here serve as paper methodology context; full analyses are in the linked assessment files.

### NVIDIA Warp

NVIDIA Warp (v1.12.1) is a Python framework that JIT-compiles decorated functions to CUDA kernels with built-in automatic differentiation via `wp.Tape`. Its tile programming layer (`wp.tile_matmul`, backed by cuBLASDx) makes differentiable custom kernels accessible from Python. For SteinSense, Warp's primary value would be the Onsager correction: `wp.Tape` would generate a single custom backward kernel over the JS denoiser rather than unrolling $B$ forward-mode AD passes.

Warp was excluded because Contribution 2 of this paper — the closed-form $O(NB)$ Jacobian sum — eliminates the need for any AD framework at the Onsager step entirely. Warp's tape-based AD solves a problem the closed-form already solves analytically. Two additional factors reinforced the decision: Warp is CUDA-only (no cross-vendor portability value), and its primary domain (physics simulation) is off-label for a CS benchmarking study. The specific question Warp can answer — does `wp.Tape` outperform JAX's `jacfwd` + `vmap` for the AD variant of the Onsager correction? — remains open and would make a focused supplementary microbenchmark if the AD mechanism comparison is of independent interest. Full analysis: [syntheses/warp-assessment.md](warp-assessment.md).

### Modular Mojo

Mojo (Modular, 2023—) is a Python superset with systems-language capabilities: `fn` declarations add strict typing, ownership semantics, and SIMD primitives. The compiler backend is MLIR — the same IR used by XLA (JAX's compiler) — giving Mojo a credible cross-vendor portability path and serious compiler pedigree. Mojo's natural role in this matrix would be the "systems language" row: implement SteinSense in explicit, compiled Mojo starting nearly verbatim from the NumPy code, isolating the value of explicit SIMD and memory layout control relative to JIT-compiled frameworks.

Mojo was excluded because **GPU eigendecomposition (`eigh`) is absent from its standard library** (confirmed May 2026: `kernels/linalg/` provides matmul, gemv, and QR; no eigendecomposition). SteinSense requires $B \times B$ `eigh` at every AMP iteration. The available workarounds — writing a custom GPU `eigh` kernel in Mojo (large effort, eliminates the porting-lift advantage) or falling back to `numpy.linalg.eigh` via Python interop (CPU-only, host/device transfer every iteration) — both undermine the rationale for inclusion. Mojo's porting-lift advantage over Julia (Python superset vs. new language) is real for the GEMM-heavy parts but does not survive the `eigh` gap. If GPU `eigh` is added in a future Mojo release, Mojo becomes a strong candidate for an additional extension — particularly for the Triton comparison: same "custom kernel" abstraction tier, different language model (systems language vs. tile DSL). Full analysis: [syntheses/mojo-assessment.md](mojo-assessment.md).

---

## Venue candidates

Audience and framing remain open; the paper could fit several communities:

| Venue type | Examples | Framing emphasis | Notes |
|---|---|---|---|
| HPC / systems | SC, ICS, PPoPP | Performance, generation-over-generation scaling, cuTile comparison | Strengthened if AMD/TPU/PyTorch extensions land |
| Numerical methods | SIAM J. Scientific Computing, NeurIPS systems track | Algorithm + implementation co-design | |
| Signal processing / statistics | IEEE Trans. Signal Processing, JMLR | Phase transition validation, prescriptive guide | Core NVIDIA plan sufficient |
| Reproducibility | ReScience, JOSS | Open implementation suite across hardware generations | |

A joint systems + mathematical validation framing would distinguish the paper from pure benchmarking and broaden its appeal. The venue decision can wait until the experimental results are in hand.

---

## Author roles (tentative)

| Role | Person |
|---|---|
| Research design, implementation suite, EMS infrastructure, experimental sweep | Andrew Donoho |
| Research design, proposal synthesis, literature survey, technical analysis | Claude (Anthropic) |
| Mathematical context, theory validation, SteinSense framing | David Donoho |
| Reference codebase, algorithm specification | Apratim Dey (participation uncertain; depends on new position) |

---

## Open questions before raising with collaborators

1. ~~**Scope boundary**~~ **Resolved**: The closed-form Jacobian sum is a genuine contribution of this paper. Dey & Donoho (2025) explicitly identifies the NB² Jacobian computation as "a major computational bottleneck that needs to be overcome using advanced software" and states that SteinSense "requires specialized software for significant speed up." The paper has no closed-form derivation — its only appendix is additional experiments. Dey's reference codebase uses `vmap(jacfwd(...))` (AD, not closed-form), confirming the bottleneck is unsolved in the original work. The O(NB) closed-form Jacobian sum directly answers the open problem they describe.
2. **Dey involvement**: If Dey does not participate, be careful about characterizing the reference implementation; attribute the original codebase explicitly.
3. ~~**cuTile on A100**~~ **Resolved**: cuTile supports A100 (confirmed by NVIDIA Python team; CUDA 13.2 cc 8.x). **cuTile on H100 (Marlowe) — open**: publicly, CUDA 13.2 skips Hopper (cc 9.x); NVIDIA states full Ampere-and-later support is coming in a future release but gives no timeline. H100 has TMA hardware, so the implementation path exists. Given the personal relationship with NVIDIA's Python team, pursue early/pre-release access to cuTile on Hopper — if obtainable, Marlowe recovers the full implementation matrix and the paper gains a complete three-generation cuTile comparison. If not obtainable before submission, the portability gap itself becomes a documented finding.
4. **Float32 vs. float64**: The reference implementation uses float64 (NumPy default). GPU implementations will likely use float32. The phase transition validation section must address this; may require a float32 NumPy baseline for a clean comparison.
5. **`CHUNK` size sensitivity**: Is the `lax.scan` chunk size (currently 50) a tunable that affects performance? A sensitivity sweep over `CHUNK` ∈ {10, 50, 100, 500} is cheap and informative — include as a secondary experiment.
6. **Single-instance multi-GPU threshold**: At what $N$ does single-instance NVLink parallelism become worthwhile on A100 vs. simply running larger $N$ on a single GB10 (which has 128 GB vs. 80 GB per A100)? The crossover point is a useful practical result.
7. **Sherlock allocation**: Confirm 8× A100 are in an NVLink configuration (DGX A100 topology) or independent nodes — this affects whether single-instance parallelism is feasible at all on Sherlock, vs. replicate parallelism only.
8. **Marlowe allocation strategy**: The 5,000 free GPU-hour starter allocation (one cycle, ~12 weeks) is sufficient for the small-to-mid $N$ experiments. Large-scale experiments ($N \geq 10^5$, full implementation matrix) will require a project allocation reviewed by a faculty committee. Dave's involvement likely strengthens that application. Contact: srcc-support@stanford.edu.
9. **Precision requirement**: Does SteinSense converge to the correct phase transition under FP32 (TF32) on GPU? The hypothesis is yes — the algorithm operates on a noisy signal, so GEMM round-off is dominated by measurement noise $\sigma$. This should be checked first (cheaply, by toggling `jax.config.update("jax_enable_x64", False)`) before designing any Ozaki-based precision path. If FP32 suffices, precision becomes a *validation finding*; if it fails, it becomes a *required paper section* with Ozaki speedup characterization.
10. **Mojo GPU `eigh`**: Mojo's standard library currently lacks GPU eigendecomposition; this is the single blocking gap for a future Mojo extension. Monitor Modular releases for `kernels/linalg/eigh` on GPU. If it lands, Mojo becomes a strong "systems language" row — particularly for a Mojo vs. Triton comparison at the same abstraction tier. The Modular relationship could be initiated via the NVIDIA Python team channel.
11. **torch.compile graph breaks (required pre-experiment)**: Does `torch.compile` fuse the AMP iteration loop without graph breaks? The `linalg.eigh` call and Python-level control flow are known graph-break sources in TorchDynamo. This must be characterized before reporting the PyTorch result — the paper must state whether the compiled result reflects full fusion or partial fusion with measured break points. If graph breaks occur, profile which operations break the graph and quantify the performance gap at each; this is itself a reportable finding about the structural limits of automatic compilation for iterative scientific algorithms.
12. **MLX CUDA backend**: The MLX API reference includes a `python/cuda.html` section, suggesting expansion beyond Apple Silicon. If CUDA support matures, MLX would become a cross-vendor framework comparable to JAX in portability. Monitor this development; it could elevate Extension E from a local-hardware comparison to a broader portability story.
