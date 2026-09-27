# Unbalanced single-framing score diagnostic

> **ADDENDUM 2026-09-27: run recorded; FAIL attributable to a since-identified
> bug.** Added after the run. The pre-statement below is kept exactly as written,
> including its "NOT RUN" status line, which described the document when it was
> written.
>
> **The recorded result (unchanged).** The run completed: 30 of 30 files, from
> `repro/mushroom_body/results/unbalanced_g_diagnostic_verdict.json` and
> `repro/mushroom_body/run_log_unbalanced_g.txt`. **VERDICT: FAIL**, on both
> conditions:
>
> - **Monotonicity:** the six-seed mean `gbar(v)` = −212.45, −84.10, −115.30,
>   −74.37, −70.33 is not strictly monotonic.
> - **Endpoint separation:** `D_end` = 321.90 Hz is below its threshold of
>   410.59 Hz (3 × `d_noise` = 3 × 136.86 Hz).
>
> Same-stimulus noise was 70.42–136.86 Hz. This verdict is not altered.
>
> **The bug.** The run did not implement §2 as pre-stated. §2 says pools are
> "drawn from left-hemisphere KCs", but the runner
> (`repro/mushroom_body/run_unbalanced_g_diagnostic.py:127`) passed all 5,177 KCs
> to `KCEncoder`. All five pools were split about 50/50 between the hemispheres
> (left/right 51/49, 52/48, 52/48, 54/46, 43/57).
>
> **Why it matters.**
>
> - **The background itself ignites.** The bilateral population-scaling rung
>   `ladder_400` is exactly this run's background: the same four pools at 90 Hz
>   with price silent. It ignited in 6/6 runs, with 67% non-stimulated KC spread.
> - **Left-only pools do not.** A left-only ladder at the same rate did not ignite,
>   apart from one weak event, up to 500 KCs, with score SD 0.5–5.1 Hz against
>   this run's 37.8–63.0 Hz.
>
> See [`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md).
>
> **How to read the result.**
>
> - **It is not evidence against the unbalanced encoder design.** It is evidence
>   about the bilateral-draw regime, and it does not support sparing option (c) on
>   the grounds in §6.
> - **What the bug does not settle.** Whether the unbalanced encoder with left-only
>   pools gives a monotone, above-noise `g` is untested. The left-only ladder used
>   uniform 90 Hz, not this run's price sweep, and ignition in this run is
>   inferred, not measured, because only MBON rates were saved.
> - **The §6 total-drive confound stands unchanged.**
>
> **Fix status (2026-09-27, postdates this run).** The runner
> (`repro/mushroom_body/run_unbalanced_g_diagnostic.py`) now draws its pools from
> `left_kc_ids()` and asserts every drawn KC, in every feature pool and the
> balance pool, is annotated left before simulating; it aborts otherwise. **This
> fix postdates the recorded FAIL above and was not applied to it**: the FAIL was
> produced by, and remains a true record of, the unfixed bilateral-draw runner.
> No rerun has been performed.

**Status: PRE-STATED; NOT RUN. The runner does not exist yet.** Written
2026-09-22, before any unbalanced market-encoder simulation and before the code
that would produce one. Everything below — value set, seeds, statistic, pass
rule — is fixed by this document and must not be revised after seeing results.
If it needs to change, write a new dated pre-statement rather than editing this
one.

**This is a diagnostic, not a validation.** A pass does not authorise the
unbalanced encoder for any experiment; only a new preregistered graded test can
do that. Its purpose is to spend 30 simulations answering one question before
spending 60 on a full re-validation of redesign option (c)
([`balanced-encoding-failure.md`](balanced-encoding-failure.md), §4c).

## 1. Question

With total-drive balancing removed, does the single-framing CIRCUIT score

```text
g(v) = CIRCUIT(m_yes(v))
```

vary monotonically with the price feature value, and by more than the
directly-measured run-to-run noise of the same stimulus in this drive regime?

Why this and not the contrast: under mirroring, `S(v) = g(v) − g(1−v)`, and if
`g` is strictly monotone then `S` is strictly monotone automatically
([`balanced-encoding-failure.md`](balanced-encoding-failure.md), §2b). `g` is
therefore the quantity that decides whether option (c) can work, and it costs
half as much to measure because only one framing is presented.

The motivating measurements, both from the failed balanced run: with the balance
pool at its 30 Hz floor, `g` moved only **16.6 Hz** across 90→150 Hz, while the
scalar score's across-seed SD in that regime was **13.2–87.5 Hz**. If the
unbalanced regime does not improve that ratio substantially, option (c) fails a
full re-validation and the 60 simulations need not be spent.

## 2. Encoder and stimulus (fixed)

- Encoder: the default `EncoderParams` with **`option_b_variant = "unbalanced"`**
  — the named historical ablation already in the code. No balancing pool is
  presented.
- Feature-pool size 100 KCs; pool seed 20260401; rate bounds 30–150 Hz; pools
  drawn from left-hemisphere KCs, as every cue-direct experiment does.
- **YES framing only.** The NO framing is not presented: under mirroring it is
  the YES framing at `1−v`, so it adds no distinct stimulus.
- Non-price features held at the midpoints of their declared ranges:
  `recent_change = 0`, `time_to_resolution = 182.5`, `liquidity = 0.5`,
  `signal = 0.5`. All four encode to 90 Hz, giving a **400-KC background at
  90 Hz** — the regime the market encoder actually runs in, and the one the
  original accepted graded test did not have.
- Total drive is *not* equalised across values; in the unbalanced encoder the
  price value is carried partly by total drive. See §6.

## 3. Value set (fixed)

```text
v = 0.05, 0.22, 0.41, 0.63, 0.88
```

giving nominal price-pool rates **36.0, 56.4, 79.2, 105.6, 135.6 Hz**.

Chosen for four reasons:

1. **No two values are reflections** (`vᵢ + vⱼ ≠ 1` for every pair: the sums are
   0.27, 0.46, 0.68, 0.93, 0.63, 0.85, 1.10, 1.04, 1.29, 1.51) and **none is
   0.50**. The same set is therefore reusable by a later contrast test without
   the redundancy or the structurally forced zero that broke the balanced run.
2. **It spans the rate range.** A one-sided set (all `v > 0.5`) would probe only
   90–150 Hz, leaving the lower half of the curve unmeasured — yet the contrast
   test needs `g` at both `r(v)` and `r(1−v)`, so the lower half is exactly what
   it would later depend on.
3. **The mirrored partners stay in range**: `r(1−v)` = 144.0, 123.6, 100.8, 74.4,
   44.4 Hz, all inside 30–150, so a later contrast test on this same set clips
   nothing.
4. **Spacing is deliberately unequal**, so the sweep does not coincide with the
   quartile grid of the failed test or with any round-number structure in the
   encoder.

## 4. Simulation (fixed)

- Model and connectome: the unchanged Shiu et al. model, v783.
- Path: the accepted reusable per-neuron-rate runner.
- Duration 1000 ms, 5 trials per stimulus — the same cell as every other
  completed measurement.
- Seeds: **20260316, 20260317, 20260318, 20260319, 20260320, 20260321** — the
  primary seed plus the five established noise seeds.
- Total: 5 values × 6 seeds × 1 framing = **30 simulations**.

## 5. Statistic and pre-stated pass rule

Let `m_s(v)` be the 96-instance MBON rate vector at value `v` and seed `s`, with
silent instances included as zero, and `g_s(v) = CIRCUIT(m_s(v))` under the
`circuit_80` table with the per-type mean.

Define

```text
gbar(v)   = mean over the 6 seeds of g_s(v)
d_same(v) = mean over s<s' of || m_s(v) - m_s'(v) ||          (same-stimulus noise)
D_end     = mean over the 6 seeds of || m_s(0.88) - m_s(0.05) ||
d_noise   = max( d_same(0.05), d_same(0.88) )
```

**PASS if and only if both hold:**

1. **Monotonicity.** `gbar(v)` is strictly monotone across the five values: all
   four successive differences share one sign. An exact tie breaks monotonicity.
2. **Endpoint separation.** `D_end ≥ 3 × d_noise`.

**Otherwise FAIL.**

Two choices in this rule are deliberate and are stated here rather than decided
later:

- **Monotonicity is judged on the seed mean, not on one seed.** The balanced run
  showed a single-seed judgement is decided by the noise realisation of one run
  ([`balanced-encoding-failure.md`](balanced-encoding-failure.md), §2b-bis). All
  six per-seed sequences are reported next to the mean. This rule governs **this
  diagnostic only**; the proposal to restructure the preregistered graded
  criterion remains a proposal, not an adopted change.
- **`d_noise` takes the larger of the two endpoint noise estimates**, because
  same-stimulus noise varied about sevenfold across stimuli in the balanced run.
  Both values are reported.

## 6. What a verdict does and does not mean

- **A PASS** means the unbalanced single-framing score carries a monotone,
  above-noise value signal in the real market drive regime. It does **not**
  validate option (c): the contrast `S(v)`, the readout margin, and the
  intensity-bias mitigation are all still unvalidated, and a preregistered graded
  test would still be required.
- **A FAIL** means option (c) would very likely fail a full re-validation, and
  the 60 simulations can be spared. It does not by itself condemn mirroring,
  because a failure could come from the 400-KC background, the price pool's
  identity, or the noise regime rather than from the mirror.
- **Confound, stated in advance.** In the unbalanced encoder the price value is
  carried partly by *total drive*: `g` may be monotone because the network is
  driven harder, not because the price pool means anything in particular. This
  diagnostic cannot separate the two. That separation is exactly what the
  intensity-bias mitigation is for, and innate-score subtraction is the candidate
  under option (c) — whose own validation gap is recorded in
  [`balanced-encoding-failure.md`](balanced-encoding-failure.md), §4c.

## 7. Outputs and stopping rule

Save one JSON per (value, seed): feature value, nominal price-pool rate, exact
per-pool rates, total drive, the full 96-instance MBON vector with its label
order, seed, duration and trial count. Then save a verdict JSON containing
`gbar(v)`, every per-seed `g_s(v)`, `d_same(v)` for all five values, `D_end`,
`d_noise`, the threshold actually used, and the verdict. Keep each file below
1 MB.

The runner must be restartable and skip any (value, seed) whose file exists. **No
verdict may be produced unless all 30 result files exist.** Stop once the verdict
is computed. Do not add values or seeds, change the statistic, or loosen the rule
after inspecting results; any later analysis is exploratory and must be labelled
as such.

## 8. Exact command

**The runner does not exist yet.** This specification is written first, on
purpose. Once `repro/mushroom_body/run_unbalanced_g_diagnostic.py` is
implemented to this document, the run is:

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_unbalanced_g_diagnostic.py
```

and the analysis-only re-run, once the 30 result files exist, is:

```bash
.venv-shiu/bin/python repro/mushroom_body/run_unbalanced_g_diagnostic.py --analyze-only
```

The runner must load the connectome only on a real run: `--analyze-only` and
importing the module must neither construct the model nor open
`Connectivity_783.parquet`, matching the existing balanced runner.
