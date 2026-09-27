# Left-only pools at encoder-realistic drive: containment and noise diagnostic

**Status: PRE-STATED; NOT RUN. The runner does not exist yet.** Written
2026-09-27, before any simulation and before the code that would produce one.
Fixed here: the stimuli, the pools, the seeds, what is recorded, how a run is
labelled, and what the comparison may and may not conclude. If this needs to
change, write a new dated pre-statement rather than editing this one.

**DIAGNOSTIC, NOT A VALIDATION** (`is_a_validation: false`,
`has_pass_criterion: false` in the output). **No pass criterion**, no verdict
field. PASS/FAIL and ACCEPTED / USABLE RANGE / FAIL belong to validations and
must not be applied to anything here.

## 1. Question

The left-only population-scaling ladder
([`left-only-population-scaling-diagnostic.md`](left-only-population-scaling-diagnostic.md))
tested left-hemisphere-only pools at one uniform rate, 90 Hz, up to 45,000 Hz
total drive, and stayed contained except for one weak event
([`bilateral-pool-draw-finding.md`](bilateral-pool-draw-finding.md) §5). The two
graded encoding runs — balanced and unbalanced Option-B
([`balanced-encoding-failure.md`](balanced-encoding-failure.md),
[`unbalanced-single-framing-diagnostic.md`](unbalanced-single-framing-diagnostic.md))
— drive five pools at **unequal** rates, 39,600–60,000 Hz total, and were run
with **bilateral** pools by a since-fixed bug (`bilateral-pool-draw-finding.md`
§1). Left-only pools have never been tested at this drive shape or level.

This diagnostic runs the encoder's own YES-framed stimuli, drawn from
left-hemisphere KCs only, at the same values the two graded diagnostics used, and
asks two questions:

1. **Containment.** Do these stimuli ignite, the way the bilateral runs at this
   drive level did, or stay contained, the way the left-only 90 Hz ladder did?
2. **Same-stimulus noise.** What is the run-to-run MBON noise at this drive level
   with left-only pools? This is the number that decides whether a left-only
   graded re-validation (a new pre-stated test with its own pass rule) is worth
   the roughly 60 simulations it would cost.

## 2. Encoder, pools and stimuli (fixed)

- **Encoder:** `KCEncoder(left_kc_ids())`, default `EncoderParams`, pool seed
  **20260401** — the same construction as `left_ladder_500` and the (now-fixed)
  graded runners. Its five 100-KC feature pools (`price`, `recent_change`,
  `time_to_resolution`, `liquidity`, `signal`) are therefore **identical to those
  used by `left_ladder_500`**, not an independent draw. Its 300-KC balance pool
  is a **left-hemisphere set not used by any earlier diagnostic** (the ladder
  never presented a balance pool).
- **Guard:** before simulating, assert every KC in every feature pool and the
  balance pool is annotated left, aborting otherwise — the same check
  (`_assert_pools_left_only`) added to the two graded runners
  (`bilateral-pool-draw-finding.md` §1), reused rather than re-derived so the
  guard cannot drift between runners.
- **Framing:** **YES only**, for every stimulus. The NO framing, the contrast
  `S(v) = g(v) - g(1-v)`, and any monotonicity or endpoint-separation statistic
  are **not computed here** — see §4 for why.
- **Background (fixed, all seven stimuli):** `recent_change = 0.0`,
  `time_to_resolution = 182.5`, `liquidity = 0.5`, `signal = 0.5` — the same
  four values used by both graded pre-statements, each mapping to 90 Hz.

**The seven stimuli:**

| id | source | variant | price value `v` | price rate | balance pool | total drive |
|---|---|---|---:|---:|---|---:|
| `unbalanced_v0p05` | unbalanced diagnostic §3 | unbalanced | 0.05 | 36.0 Hz | none | 39,600 Hz |
| `unbalanced_v0p22` | unbalanced diagnostic §3 | unbalanced | 0.22 | 56.4 Hz | none | 41,640 Hz |
| `unbalanced_v0p41` | unbalanced diagnostic §3 | unbalanced | 0.41 | 79.2 Hz | none | 43,920 Hz |
| `unbalanced_v0p63` | unbalanced diagnostic §3 | unbalanced | 0.63 | 105.6 Hz | none | 46,560 Hz |
| `unbalanced_v0p88` | unbalanced diagnostic §3 | unbalanced | 0.88 | 135.6 Hz | none | 49,560 Hz |
| `balanced_v0p00` | balanced spec, `v=0.00` | balanced | 0.00 | 30.0 Hz | 70 Hz × 300 | 60,000 Hz |
| `balanced_v0p25` | balanced spec, `v=0.25` | balanced | 0.25 | 60.0 Hz | 50 Hz × 300 | 57,000 Hz |

The unbalanced five reuse `OPTION_B_UNBALANCED`
(`run_unbalanced_g_diagnostic.py`'s variant) and drive **500 KCs** (5 pools ×
100) per stimulus. The balanced two reuse the default (balanced) variant and
drive **800 KCs** (5 pools × 100 + 300 balance) per stimulus. Every stimulus
drives the same five feature pools; the two balanced stimuli additionally drive
the balance pool.

- **Seeds:** **20260316, 20260317, 20260318, 20260319, 20260320, 20260321** —
  unchanged from every earlier diagnostic in this family.
- **Presentation:** 1000 ms × 5 trials.

**7 stimuli × 6 seeds = 42 simulations.**

## 3. What is recorded (fixed)

Per (stimulus, seed):

- The full per-neuron mean-over-trials rate vector for **MBONs, Kenyon cells,
  APL, PAM and PPL1** — recorded the same way as every earlier runner in this
  family — plus the stimulated KC IDs by pool, the pool assignments, and the
  side composition.
- **Per-trial rates for Kenyon cells, MBONs and APL**, in addition to the
  mean-over-trials vectors above. `run_cue_rates` already returns a spikes table
  carrying a `trial` column
  (`repro/mushroom_body/fast_runner.py:185`); the existing `present()` path
  discards it by binning across all trials before returning. The runner for this
  diagnostic must bin per trial instead —
  `rate[trial, neuron] = count(neuron, trial) / (duration_ms / 1000)` — and save
  the resulting `(5 trials × n_neurons)` arrays for these three populations. This
  is new: no earlier runner in this family saved per-trial resolution. It exists
  to answer a gap the left-only ladder could not close
  (`bilateral-pool-draw-finding.md` §5): whether a recruitment event, if one
  occurs, appears in one trial or all five, and how it evolves within the 1000 ms
  presentation.

Reported per stimulus, mirroring the ladder's format:

- **ignition count out of 6** and the per-seed label (non-stimulated KC active
  fraction over **1%**, from the mean-over-trials rate — the existing label,
  unchanged, computed the same way as every earlier diagnostic in this family);
- **per-seed non-stimulated KC active fraction, overall and split by
  hemisphere**;
- **the rate-weighted recruitment measure**
  ([`recruitment-intensity-measure.md`](recruitment-intensity-measure.md)):
  `recruited_kc_mean_rate_hz` and `recruited_kc_median_rate_hz`, both from the
  mean-over-trials rate (null when nothing is recruited) — included from the
  start here, not bolted on afterward, because task 2's retrospective pass
  showed the binary label alone cannot distinguish a weak event from a
  saturating one. **The binary label is kept, not replaced**, exactly as in
  that document;
- **the same measure computed per trial**, where the per-trial KC rates make it
  possible: `recruited_kc_mean_rate_hz` for each of the 5 trials separately, so
  a brief event is visible instead of averaged away;
- **active MBONs** (> 0.5 Hz) and **APL rate**, per seed and mean, both from the
  mean-over-trials vectors, plus per-trial APL rate;
- **CIRCUIT-80 per-type-mean score `g(v) = CIRCUIT(m_yes)`**: mean, SD, and all
  six values — the same statistic and table the unbalanced diagnostic used,
  computed here from the mean-over-trials MBON vector;
- **same-stimulus noise**: the mean pairwise MBON-vector distance across the 6
  seeds (`mbon_vector_distance_hz`, the same statistic already reported for
  every bilateral and left-only ladder condition, equal to the unbalanced
  diagnostic's `d_same(v)` under a different name) — the number this diagnostic
  exists to measure;
- **stimulated-KC rate, measured against imposed, per pool**: for each of the
  five (or six, for the balanced stimuli) driven pools separately, since pools
  no longer share one imposed rate — the imposed rate, the measured mean per
  seed and across seeds, and the ratio.

**No bilateral reference block.** Unlike the population-scaling ladder, no
bilateral run exists at any of these exact seven stimuli (unequal per-pool
rates, YES-only), so there is nothing matched to compare against directly. The
two recorded graded FAILs remain the closest bilateral analogues, at the caveats
already stated in `bilateral-pool-draw-finding.md` §3.1: their ignition is
inferred, not measured, because they saved MBON rates only.

**Run labelling, for reporting only:** unchanged from the ladder — a run is
*ignited* when its non-stimulated KC active fraction exceeds 1%, *contained*
otherwise. Not a pass criterion; no verdict is derived from it.

## 4. What this can and cannot conclude

**Can:**

- **Locate containment or ignition** for left-only pools at the encoder's own
  multi-pool, unequal-rate drive, from 39,600 to 60,000 Hz — a drive shape and
  level the 90 Hz ladder never tested.
- **Measure the same-stimulus noise** at this drive level with left-only pools,
  directly comparable to the unbalanced diagnostic's recorded 70.42–136.86 Hz and
  the balanced diagnostic's 24.90–183.50 Hz (both bilateral). This is the number
  that decides whether a left-only graded re-validation is worth running: if
  noise here is of the same order as the left-only ladder's (score SD 0.5–5.1
  Hz), a re-validation is plausible; if it is of the same order as the bilateral
  runs', it is not.
- **If anything ignites**, locate it in time (which trial or trials) and
  quantify its intensity with the recruitment measure, rather than only
  reporting a binary label — closing the specific gap left by the left-only
  ladder's single 300-KC event.

**Cannot:**

- **Address the mirroring antisymmetry.** This is the balanced encoder's
  structural defect (`balanced-encoding-failure.md` §2a): `NO(v) ≡ YES(1-v)`
  identically, so `c(1-v) = -c(v)` and `c(0.50) = 0` exactly, for any pool draw,
  bilateral or left-only. **This diagnostic presents YES only and never
  constructs the NO framing, the contrast `c(v)`, or the score difference
  `S(v)`** — it cannot exercise, let alone fix or rule out, the antisymmetry,
  because the quantity the antisymmetry is a property of is never computed here.
  The antisymmetry is **independent of hemisphere**: it follows from mirroring
  interacting with the sweep, not from which cells carry the drive, and nothing
  in this document bears on it either way.
- **Authorise either encoder for any experiment.** This is a diagnostic. Only a
  new, separately pre-stated graded test with its own pass rule could do that,
  and this document's containment result would only inform whether running one
  is worthwhile — it is not a substitute for one.
- **Separate hemisphere from pool draw.** One left draw is tested, at pool seed
  20260401, the same draw as every other diagnostic in this family. Whether a
  different left draw, or a right-only draw, behaves the same way is untested.
- **Test a matched bilateral condition.** No bilateral run exists at these exact
  seven stimuli. Comparisons to the two recorded graded FAILs are against a
  different (bilateral) pool draw, not a controlled pair.
- **Say anything about other pool seeds, other feature values, or the NO
  framing.**
- **Resolve whether either encoder carries an above-noise value signal.** That
  is a graded question, needing its own monotonicity or endpoint-separation
  statistic and its own pre-stated pass rule (as in the unbalanced diagnostic's
  §5) — deliberately out of scope here, which is why no such statistic is listed
  in §3.
- **Give a precise ignition probability.** Six seeds per stimulus give a count,
  with the same roughly ±0.2–0.3 uncertainty documented in
  `bilateral-pool-draw-finding.md` §5.

## 5. Outputs and stopping rule

One JSON per (stimulus, seed): the mean-over-trials rate vectors for all five
populations (as in every earlier runner in this family), the per-trial rate
arrays for Kenyon cells, MBONs and APL, the per-pool stimulated KC IDs and
imposed rates, and the stimulus's variant and total drive. Then one summary
JSON, `left_only_realistic_drive_summary.json`, with the per-stimulus statistics
of §3. **No verdict field.** Each per-seed file may exceed the 1 MB ceiling used
by earlier runners in this family, because of the per-trial arrays (5 trials ×
(5,177 KC + 96 MBON + 2 APL) ≈ 26,400 floats ≈ 210 KB as JSON, on top of the
existing mean-rate vectors) — still small, but the ceiling is relaxed here to
**5 MB per file** rather than raised without acknowledging the change.

Restartable: a (stimulus, seed) whose file exists is skipped. **No summary is
produced unless all 42 files exist.** Do not add stimuli, seeds or statistics
after inspecting results; any further analysis is exploratory and must be
labelled as such, as in `bilateral-pool-draw-finding.md` §5.

## 6. Cost

42 simulations at 1000 ms × 5 trials. At the 50.5 s per simulation measured on
the author's machine, plus one ~4 s build, this is **about 35.4 minutes**. The
per-simulation figure is UNVERIFIED on other machines and was measured on
smaller stimuli (uniform 90 Hz, up to 45,000 Hz); the balanced stimuli here reach
60,000 Hz across 800 KCs, and if either ignites, both the simulation and the
per-trial binning may run slower than this figure reflects. The estimate is not
used by anything this document concludes.

## 7. Exact command

**The runner does not exist yet.** This specification is written first, on
purpose. Once
`repro/mushroom_body/run_left_only_realistic_drive_diagnostic.py` is implemented
to this document, the run is:

```bash
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/run_left_only_realistic_drive_diagnostic.py
```

and, once the 42 result files exist, the analysis-only re-run (loads no
connectome):

```bash
.venv-shiu/bin/python repro/mushroom_body/run_left_only_realistic_drive_diagnostic.py --analyze-only
```

The runner must load the connectome only on a real run: `--analyze-only` and
importing the module must neither construct the model nor open
`Connectivity_783.parquet`, matching every existing runner in this family.
