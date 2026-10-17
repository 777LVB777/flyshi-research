# Phase 2 preregistration: the circuit on real Polymarket markets (Design A)

**Written 2026-10-16, before any price data exists.** No price history has been
requested, no market file has been built and no Phase 2 simulation has run. Only
metadata has been downloaded, and the market list is frozen.

Everything below is fixed now. A change after this date is recorded here as a
**dated deviation**, with its reason, before any affected result is read.

**Sources.**

- [`phase2-design.md`](phase2-design.md), Sections 5–7 and 10. Section 10
  governs.
- The synthetic sweep, [`synthetic-market-experiment.md`](synthetic-market-experiment.md),
  whose circuit and gate this reuses.
- The code is in `src/flyshi_research/learning/real_market.py`,
  `src/flyshi_research/evaluation/isotonic_comparator.py`,
  `repro/mushroom_body/run_real_market_experiment.py` and
  `repro/mushroom_body/launch_real_market_parallel.py`. Their tests,
  `tests/learning/test_real_market.py`, use fake data only.

## 1. Question

Can a connectome-constrained mushroom-body circuit with dopamine plasticity,
taught only by the profit of its own trades, beat the market's own price on
held-out real binary markets? It sees only market-internal features: price,
recent change and time to resolution.

This is option (a) of Section 4 of the design: there is no outside signal. A pass
would be an edge from price-history features. It would say nothing about
integrating outside evidence.

## 2. Data (frozen)

| item | value |
|---|---|
| venue, endpoints | Polymarket. Gamma `/markets/keyset` (metadata); CLOB `/prices-history` (prices). Both permitted under Section 1. |
| metadata snapshot | SHA-256 `2b226bd69ed57736413b2688ebc78949ec581729db36af850b8c2a67ca679245` |
| frozen market list | SHA-256 `f3d41123e20ef10b0651b24531e909cb41691e94e1c83df7b0f83a3f2d5975f8`. 40,893 markets: resolved binary, final volume ≥ $10,000, one per event. |
| decision time `t_d` | seeded uniform draw over the scheduled life, minus 24 h at each end (10.5) |
| features at `t_d` | price (last point strictly before `t_d`, at most 24 h old), recent change over 24 h, days to the **scheduled** end; signal = 0.5 and liquidity = 0.5 (90 Hz in both framings) |
| split | training: resolved before 2026-03-01 00:00 UTC. Test: `t_d` in [2026-03-08, 2026-09-01). |
| pools | training 16,992 markets, test 17,944 markets |
| sample order | sha256(`flyshi-phase2-sample-20261016`|market ID) within each pool |
| fill | fetch in that order until 3,220 training and 8,280 test markets are usable (need + 15%) |

**Per-series caps: not applied (decided 2026-10-16, project owner, before any
price download).** One market per event is the only clustering rule.

- **Limitation.** Markets in the same series may be correlated. The bootstrap
  resamples markets, so its intervals may be somewhat narrow. A pass is
  therefore a little easier to reach than the stated 95% level suggests, and a
  borderline pass should be read with that in mind.
- It is reported with the verdict as a limitation, not corrected for.

## 3. Design A

- **Chains.** 40 disjoint chains, each **70 training markets, then 180 test
  markets**: the synthetic sweep's chain shape (`int(250 × 0.28) = 70`).
  - Chain c takes ranks [70c, 70c + 70) of the training pool's usable, built
    markets, in the sample order, and ranks [180c, 180c + 180) of the test
    pool's.
  - The other built markets are the reserve.
  - Within a chain, training markets are shown in resolution order and test
    markets in decision-time order (ties by market ID).
  - Assembly reads IDs, the sample order and dates only (`assemble_chains`).
- **Arms.** Each arm runs every chain: 120 jobs of 500 runs, 60,000 runs.

  | arm | role |
  |---|---|
  | `profit` | primary: plasticity on for the 70 training markets, frozen for the 180 test markets |
  | `learning_off` | the same circuit at baseline weights ("learning effect, any source") |
  | `null_permuted` | the profit arm taught with the chain's training outcomes **permuted** |

- **The circuit is the synthetic sweep's, unchanged.**
  - The locked configuration is `SyntheticConfig()`, config hash `a325e6b206`.
  - The encoder is unbalanced Option B, with left-hemisphere pools only
    (guarded) and a mirrored NO framing, at 30–150 Hz.
  - The readout is the raw CIRCUIT-80 per-type-mean score.
  - Plasticity, the profit reward, fee and spread in the teaching signal, the
    decision margin, training-only seeded exploration and per-trial ignition
    tracking are all unchanged.
  - The per-market loop *is* the sweep's code (`synthetic_market.decision_loop`).
    Extracting it changed no synthetic output: all 24 test outputs are
    byte-identical.
- **Seeds.**
  - Presentation: `20280000 + 1000·chain + index`, identical in every arm.
  - Exploration: keyed by the chain number.
  - Null permutation: `numpy.random.default_rng([20261016, chain]).permutation(70)`.
    Training position i is taught with the outcome of position perm[i].
- **The null arm sees only permuted outcomes.** That covers its teaching signal
  and its own Platt calibrator. Its test markets are scored against the **true**
  outcomes.
- **Each arm's forecast.** As in the synthetic sweep, it is the sigmoid of the
  score difference, Platt-calibrated on that chain's 70 training markets.

## 4. Comparator (frozen before any test market is scored)

- **Method.** The FINAL method of 10.2 (`isotonic_comparator`):
  - isotonic regression of the outcome on the raw price, with tied prices
    pooled;
  - each block shrunk toward its own mean price with pseudo-count 20;
  - **pool-adjacent-violators applied again to the shrunk values** (decided
    2026-10-16, see below), weighted by n + 20, so the map is monotone
    non-decreasing;
  - linear interpolation between block mean prices, and the nearest end value
    beyond them.
- **Guard.** A 5-fold cross-validation on training markets, with folds by
  sha256(`flyshi-phase2-comparator-folds-20261016`|market ID) mod 5.
  - The comparator is the raw price or the calibrated price, whichever has the
    lower cross-validated Brier score. A tie keeps the raw price.
- **Fitted on every training market of the market file**, about 3,220
  including the reserve. Never on a test market: the function has no test
  argument, and the verdict refuses if any test ID is among the training IDs.
- **Frozen.** `--prepare` writes the chains, the comparator and a manifest of
  SHA-256s before any job runs. Every job and the verdict refuse if a hash no
  longer matches.
- **Re-pooling after shrinkage (decided 2026-10-16, project owner, before
  `--prepare` and before any price download).**
  - Shrinking each block toward *its own* mean price can put two adjacent
    shrunk values out of order, when a small block follows a large one. A test
    reproduces this.
  - Pool-adjacent-violators is therefore applied again to the shrunk values,
    weighted by n + 20. A pooled run of blocks takes one value and keeps its
    blocks' centres, so the interpolated map is monotone non-decreasing, as
    10.2 says it should be.
  - The values before re-pooling are saved (`shrunk_values`), and the report
    says whether re-pooling acted (`repooled_after_shrinkage`).
  - The same function is used inside the 5-fold guard.

## 5. Pass rule (gate)

On the 7,200 held-out test markets of all 40 chains, with paired per-market
Brier differences:

- `vs_comparator` = (comparator − y)² − (profit − y)²
- `vs_learning_off` = (learning_off − y)² − (profit − y)²

**PASS** if and only if the **95% percentile bootstrap lower bounds of both
mean differences are strictly above zero.**

- 2,000 resamples, by market, which is by event since there is one market per
  event.
- Seeds: 20261016 for `vs_comparator`, 20261116 for `vs_learning_off`.

This is the synthetic gate (Section 6 of its spec) with the frozen comparator in
place of the price-only posterior.

## 6. Null control

- `null_vs_comparator` = (comparator − y)² − (null_permuted − y)², with the same
  bootstrap and seed 20261216.
- **If its lower bound is above zero, the verdict is NULL CONTROL FAILED.** That
  means a pipeline problem, not a finding, and no edge is reported even if the
  gate passes.
- `success` = gate passes **and** the null does not.

## 7. Reported only, never gating

- **Realised σ_d and MDE** for both comparisons, together with the Brier score
  of every arm, the comparator and the raw price.
- **The ≥ $100,000 subset.** The same two comparisons restricted to test markets
  with final volume ≥ $100,000. Seeds 20261316 and 20261416.
- **Ignition.**
  - Decisions with an ignited framing, per arm, for training and test.
  - The gate re-evaluated without every test market in which either framing
    ignited in `profit` or `learning_off` (seeds 20261516 and 20261616).
  - The excluded markets are not random, and learning from ignited training
    presentations stays in the weights.
- **Gross P&L** (added 2026-10-16, before any price download). Per test market,
  one contract at the decision-time price with **no fee and no spread**: YES
  earns outcome − price, NO earns price − outcome, ABSTAIN earns 0. Reported for
  each arm as the total, the per-market mean (with a 95% bootstrap interval,
  seeds 20261716 to 20261718), the number of trades and abstentions.
  - Label, always printed with it: **"gross, before fees and spread, not
    achievable as stated"**.
  - It is not net P&L: CLOB `/prices-history` gives prices only, not the spread
    at `t_d`, so P&L after fees and spread is not computed.

## 8. Reading rules (pre-stated wording, `real_market.readings`)

- **Pass:** "on held-out real markets the circuit's Brier score beats both the
  frozen training-calibrated price and its own learning-off control (both 95%
  lower bounds above zero)".
  - The comparator comparison is "edge over the market price, calibrated on
    training markets only".
  - The learning-off comparison is "learning effect, any source".
- **Non-pass:** "no detectable edge larger than the minimum detectable effect at
  the realised σ_d. This is not evidence of no edge." The realised MDEs are
  printed with it.
- **Null control failed:** a pipeline problem, not a finding.
- **Reported-only analyses cannot change the verdict.** None of the ≥ $100k
  subset, the gross P&L, the ignition exposure or the ignited-market sensitivity analysis can
  turn a non-pass into a pass, or overturn a pass.

## 9. Minimum detectable effect at the actual sizes

MDE = 2.80 · σ_d / √n: 80% power at two-sided α = 0.05, the method of Section 7
of the design. σ_d is the per-market standard deviation of the paired Brier
difference, ≈ 0.9 × RMS(forecast − comparator). It is unknown until the run and
is reported with the verdict.

| test markets | σ_d = 0.02 | 0.034 | 0.06 | 0.09 |
|---|---:|---:|---:|---:|
| **7,200 (Design A, the gate)** | 0.0007 | 0.0011 | 0.0020 | 0.0030 |
| about 980 (the ≥ $100k subset, reported only) | 0.0018 | 0.0030 | 0.0054 | 0.0081 |

- **The subset's size.** 2,497 of the 17,944 test-pool markets (13.9%) have
  final volume ≥ $100,000. 978 of them are among the first 7,200 in the sample
  order, before attrition.
  - The subset's MDE is therefore about **2.7×** Design A's.
  - This corrects the 10.11 estimate (about 2,230 markets, 1.8×), which had
    assumed, unverified, that the ≥ $100k markets follow the overall time
    profile. They are concentrated in the training period.
- **Reading.**
  - A circuit that moves about 0.04 from the comparator (σ_d ≈ 0.034) is
    detectable at a Brier edge of about 0.0011.
  - One that moves about 0.10 (σ_d ≈ 0.09) needs about 0.0030.
  - Real-market edges over the price are probably smaller (unverified).
- **Accepted 2026-10-16 (project owner):** the corrected subset size (about 980
  markets) and its MDE (about 2.7× the gate's).

## 10. Before any run

1. `load_polymarket.py history` (fill), then `build`.
2. `run_real_market_experiment.py --prepare --market-file … --fill-plan …` writes
   the chains, the frozen comparator and the manifest.
3. **Total-drive check:** `run_real_market_experiment.py --drive-check --market-file …`.
   - Arithmetic only, no simulation. It reads features only, never an outcome.
   - It reports the per-framing drive, the YES−NO difference, clipping and the
     drive bands for training and test.
   - It compares them with the **decided synthetic sweep, design (b′)**: 19.3–70.7
     kHz, with 3.06% of presentations above 60 kHz and 3.06% below 30 kHz.
     The code reproduces those figures in a test.
   - Section 3 of the design quoted 22.8–67.5 kHz and 2.12%. Those are the
     **pre-revision** design's figures, which the code also reproduces.
   - **Accepted 2026-10-16 (project owner):** the reference is the as-run
     sweep, 19.3–70.7 kHz with 3.06% above 60 kHz, not the pre-revision figures.
   - **The owner signs off on the drive check before any job runs.**
4. `launch_real_market_parallel.py --run-dir …`, then the verdict (`--finish`).
   The verdict is computed only once all 120 job files exist.

## 11. Verdict script

`run_real_market_experiment.py --finish --run-dir …` (`real_market.evaluate`)
was written and tested on fake files only, before any price data exists. The
tests show:

- the gate passes only when profit beats both the comparator and learning_off;
- a passing null arm makes the verdict NULL CONTROL FAILED;
- the reported-only analyses never change the verdict;
- the script refuses on a missing job, misaligned arms, or a test market in the
  comparator's training set.

## 12. Phase 2 and the Phase 1 verdict (dated deviation, 2026-10-17)

**Decided 2026-10-17 (project owner), before any Phase 1 verdict exists.** Sections
1–11 did not say whether Phase 2 depends on the synthetic sweep's Phase 1 verdict.
Phase 2 runs regardless of the Phase 1 verdict; the two phases answer different
questions (synthetic vs. real markets), and this was fixed on 2026-10-17 before any
verdict was computed. The line below is read by the server autopilot
([`../cloud/autopilot.md`](../cloud/autopilot.md)).

<!-- autopilot-phase2-rule: run-regardless -->
