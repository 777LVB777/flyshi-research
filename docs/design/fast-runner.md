# Fast runner: build the network once, reset between trials

**Status: the equivalence test has been run and PASSED** (git commit `6a00cdd`;
see "Results" at the end of Section 4). This documents the reusable-network fast
path (`repro/mushroom_body/fast_runner.py`), why it should be faster, how
synaptic weights are handled across resets (critical for the future learning
design), and the pre-stated equivalence criteria and commands, written **before**
the equivalence run. The per-neuron-rate variant (`run_cue_rates`, Section 6) has
still NOT been executed against the real model.

## 1. What happens per trial today, and what dominates

The existing path (`check_mb_response.run_condition` → upstream
`model.run_exp` → `run_trial`) does the following **for every trial**:

1. `create_model(path_comp, path_con, params)` —
   - `pd.read_csv(Completeness_783.csv)` (~3 MB), and
   - **`pd.read_parquet(Connectivity_783.parquet)` (~100 MB, brotli-compressed,
     ~15 million rows)**;
   - build the `NeuronGroup` (~138k neurons);
   - **`syn.connect(i=i_pre, j=i_post)` — construct ~15 million synapses**;
   - assign `syn.w` from the `Excitatory x Connectivity` column;
   - create a `SpikeMonitor`.
2. `poi(...)` — create one `PoissonInput` per stimulated neuron.
3. `silence(...)` — (no-op unless silencing).
4. `Network(...).run(t_run)` — the actual integration (e.g. 1000 ms).
5. build a dataframe of spikes and write a parquet.

Steps 1's parquet read and the 15M-synapse `connect`/weight assignment are
repeated on **every** trial even though the network never changes between trials
of the same cue. With `n_proc=1` upstream also runs trials sequentially, so there
is no parallelism hiding that cost.

**Estimated dominant cost (UNVERIFIED — to be confirmed by the instrumentation
below):** the per-trial **build** (parquet read + 15M-synapse construction), not
the integration. Reasoning: reading and decompressing a 100 MB parquet into
~15M rows and materialising 15M Brian2 synapses is heavy fixed work, whereas a
1000 ms integration of this network is comparatively short. Supporting evidence
already in hand: at 1000 ms / 5 trials a single-cue run takes ~28 s (≈5.6 s/trial
including build), while the smoke test in `shiu2024.md` — which builds the
network and runs only *10 ms* × 2 trials — still took ~7.5 s, i.e. most of that
time was **not** integration. **Cython compilation is a one-time cost** (Brian2
caches compiled objects on disk under `~/.cython/brian_extensions`), so it hits
the first run on a machine and is negligible thereafter; it is not the per-trial
driver. This ordering is marked unverified until measured.

**Instrumentation added (in our code only, never upstream):** `fast_runner.py`
times the one-time `build_network()` (the `create_model` call) separately from
each `net.run()`, and prints `build_seconds` and `sim_seconds_total` plus
per-trial sim times. That directly shows the build-vs-simulate split for the new
path. The existing path cannot be split without editing upstream `run_trial`
(which we must not touch), so its ~28 s stays a single number; the new path's
`build_seconds` (paid once) vs `sim_seconds_total` (paid every trial) is what
quantifies where the old path's repeated cost went.

## 2. What changed (new code only; existing path untouched)

New file `repro/mushroom_body/fast_runner.py`:

- **Builds the network once.** It calls upstream `create_model()` **verbatim**
  for the neurons and the 15M recurrent synapses, so the network is constructed
  byte-for-byte as in the existing path. It then wraps them in a `Network` and
  calls `net.store("init")` to snapshot the pristine state.
- **Resets between trials with `store()`/`restore()`** instead of rebuilding:
  `net.restore("init")` returns neuron state (`v`, `g`, `rfc`), the clock
  (`t → 0`), and the `SpikeMonitor` (emptied) to the snapshot. By Brian2's
  default `restore_random_state=False` (confirmed for 2.5.1), **restore does NOT
  reset the RNG**, so the random stream advances across trials — matching the
  existing path, which seeds once and lets trials advance the same stream.
- **Retargetable stimulation without rebuilding.** Instead of upstream's
  per-neuron `PoissonInput` (which cannot be re-pointed at a different neuron set
  without reconstructing network membership), the fast path adds a single
  `PoissonGroup` (one Poisson source per neuron) plus one-to-one input synapses
  `on_pre="v_post += w_in"` with `w_in = w_syn * f_poi` — the *same* target
  variable (`v`) and weight as upstream `poi()`. Between runs, the stimulated set
  and rate are changed by setting `pin.rates` and the per-neuron refractory
  `neu.rfc` (0 for stimulated neurons, `t_rfc` otherwise), with no rebuild.
- **Seeds exactly as the existing path:** `np.random.seed(seed)` and
  `brian_seed(seed)` once before the trial loop.
- Writes the same MBON-rate CSV schema as `run_single_cue.py` (via the same
  `utils.get_rate` + `annotated_rates`), to a `fast_mbon_cue_*` filename, so
  outputs are directly comparable.

The existing `check_mb_response.py` and `run_single_cue.py` are **not modified**,
so the reference results remain reproducible.

## 3. How weights are handled across resets (critical for learning)

**The learning design will change KC→MBON weights between decisions, and those
changes must persist across runs while neuron state resets.** Brian2's
`restore()` **does** restore synaptic weights to the stored snapshot — so a naive
`restore("init")` every trial would silently **wipe any learned weights**.

The fast path handles this explicitly, every trial:

```
weights_now = np.array(syn.w[:])   # capture current (possibly learned) weights (SI/volt)
net.restore("init")                # resets v/g/rfc/clock/monitor; also reverts weights to snapshot
syn.w[:] = weights_now * volt      # RE-APPLY -> weights persist across the reset
```

So state resets but weights carry forward. In the equivalence test there is no
plasticity, so `weights_now` equals the snapshot and the re-apply is a no-op —
but the mechanism is already correct for when plasticity is added later (the
plasticity itself is **not** implemented here).

This behaviour is unit-tested by `fast_runner.py --self-test`, which builds a
tiny 3-neuron network and confirms both halves of the claim, and **passes**:

```
[self-test] plain restore() reverts weights to snapshot : True
[self-test] save->restore->reapply preserves weights    : True
[self-test] PASS
```

(Note the units detail the self-test caught: `np.array(syn.w[:])` strips Brian2
units, returning volt values, so re-application must multiply by `volt`.)

## 4. Equivalence test — pre-stated criteria (before running)

Compare the new path against the existing path on the **same cue, seeds, and
settings**: cue A, 1000 ms / 5 trials, `--kc-set-seed 20260316`, `--pn-rate 150`,
seeds **20260317–20260321**. The existing-path reference outputs already exist —
they are the noise-floor CSVs `mbon_noise_floor_cue_a_duration_ms_1000_trials_5_
..._seed_S.csv` produced earlier by `run_single_cue.py`.

**Bit-identical spike output is NOT expected, for concrete reasons:**

- The fast path drives stimulation with a `PoissonGroup` + synapses, whereas the
  existing path uses `PoissonInput`. These are different Brian2 objects that draw
  from the RNG in a different order and count, so even with the same seed the
  exact Poisson event times differ.
- Build-once vs rebuild-per-trial changes how many RNG draws happen during
  construction and in what order relative to the run.
- The existing path runs trials through `joblib`/`loky` (`n_proc=1`), whose
  per-trial RNG behaviour across worker processes is not cleanly reproducible in
  the first place.

Because exact reproduction is impossible, equivalence is judged on the readout,
with a tolerance tied to the already-measured simulation noise:

**Equivalence is ACCEPTED if BOTH hold:**

1. The **mean Euclidean distance** between the old-path and new-path per-MBON
   rate vectors (averaged over the 5 seeds, union MBON support, zero-filled) is
   **≤ the measured same-cue noise floor `d_AA = 5.10 Hz`** from
   `docs/design/mbon-separability.md`. Rationale: two runs of the *same* cue
   already differ by ~5.10 Hz from RNG alone, so a new path that lands within
   that spread is indistinguishable from re-running the old path.
2. **All 8 consistent discriminating MBONs keep the same sign** of the cue-A −
   cue-B difference under the new path (new-path mean cue A vs the existing cue-B
   rates at 1000 ms / 5 trials). The 8 MBONs and their established signs are the
   ones from `mbon-separability.md` §1 (MBON03/07·90134/07·02365/04/26/23
   negative, MBON02/11 positive).

If criterion 1 fails, the new path is not equivalent. If criterion 2 fails, the
readout direction changed and the fast path must not be used for the study.

**Speedup** is also reported: `fast_runner.py` prints `build_seconds` (paid once)
and `sim_seconds_total` (per run). The relevant comparison is *amortised* cost —
existing path ≈ 28 s per single-cue run (rebuild every trial); fast path ≈
`build_seconds` once **plus** `sim_seconds_total` per run, so across many
decisions the build cost is paid a single time. Report both the first-run cost
(build + sim) and the amortised per-run cost (sim only).

The comparison itself is analysis-only: `repro/mushroom_body/compare_equivalence.py`
reads the old and new CSVs and prints both criteria and the verdict. It does not
run any simulation.

### Results (run 2026-09-21; git commit `6a00cdd`)

The full equivalence test was run: cue A, 1000 ms / 5 trials, `--kc-set-seed
20260316`, `--pn-rate 150`, seeds 20260317–20260321, fast path, compared against
the existing-path reference CSVs from the noise-floor experiment (outputs and log
in `repro/mushroom_body/run_log_fast_full.txt`).

**Verdict: ACCEPTED.**

- **Criterion 1 (mean distance ≤ 5.10 Hz):** per-seed old-vs-new distances were
  5.463, 3.231, 6.053, 3.904, and 4.382 Hz; **mean = 4.606 Hz** — PASS.
- **Criterion 2 (all 8 discriminator signs match):** **8/8** — PASS (MBON03,
  MBON02, MBON07·90134, MBON07·02365, MBON04, MBON26, MBON11, MBON23 all kept
  their established sign under the new path).
- **Speedup observed:** `build_seconds` was 4.6 s on the first run and 1.3–1.5 s
  on subsequent runs in the same process; `sim_seconds_total` was 44–48 s per
  5-trial run, against the existing path's ≈28 s per single-cue run (rebuild
  every trial) — the amortised comparison in the design above.

This satisfies the dependency that `docs/design/first-learning-test.md` and
`docs/design/synthetic-market-experiment.md` name as a prerequisite for those
experiments; those documents' own text was written before this run and is
updated separately to record it. This result does **not** cover `run_cue_rates`
(Section 6), which has not been run against the real model.

## 5. Commands to run yourself

Run in a normal terminal; each real run is a Brian2 simulation, so use
`caffeinate -i` on macOS. Preparation checks (no model) come first.

```bash
# (0) checks that do NOT run the model
uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/fast_runner.py --self-test   # weight persistence
uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/fast_runner.py --help

# (1) SMOKE TEST — one seed, fast path (prints build vs simulate timing)
caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/fast_runner.py \
  --cue a --seed 20260317 --duration-ms 1000 --trials 5 \
  --pn-rate 150 --kc-set-size 100 --kc-set-seed 20260316

# (2) FULL EQUIVALENCE TEST — cue A, 1000 ms / 5 trials, all 5 seeds, fast path
for S in 20260317 20260318 20260319 20260320 20260321; do
  caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
    .venv-shiu/bin/python repro/mushroom_body/fast_runner.py \
    --cue a --seed "$S" --duration-ms 1000 --trials 5 \
    --pn-rate 150 --kc-set-size 100 --kc-set-seed 20260316
done

# (3) COMPARE against the existing-path reference (analysis only, no simulation)
uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/compare_equivalence.py
```

The existing-path reference CSVs (`mbon_noise_floor_cue_a_...trials_5..._seed_S`)
already exist from the noise-floor experiment, so no re-run of the old path is
needed. Each fast run writes one small CSV
(`fast_mbon_cue_a_duration_ms_1000_trials_5_..._seed_S.csv`). Step (3) prints the
mean old-vs-new distance against the 5.10 Hz bound, the 8-MBON sign check, and
the ACCEPTED / NOT-ACCEPTED verdict.

## 6. Per-neuron-rate variant (added 2026-09-21; not yet run on the real model)

**Why.** `run_cue` gives every stimulated neuron the *same* rate. The learning
encoder ([`mb-learning-interface.md`](mb-learning-interface.md), 4a) drives
several feature pools at *different* rates in one run, so it needs a rate per
neuron. `fast_runner.py` now has `run_cue_rates(bundle, rates_by_flyid, n_trials,
base_seed, exp_name)`, where `rates_by_flyid` is `{FlyWire root ID: Hz}` (the
encoder's `Stimulus.rates_by_kc_id()` produces exactly this).

**The scalar path is unchanged.** `run_cue` is byte-for-byte the code it was
(checked by diffing its source against the previous version); only the module
docstring, `--self-test` help text and `main()`'s self-test call were touched.
`run_cue_rates` is added beside it and does the same things in the same order:
seed once before the trial loop, `store()`/`restore()` between trials,
save-then-reapply of synaptic weights across each restore (so learned weights
persist), the same spike collection and return values. The one intended
difference is that `pin.rates` receives a per-neuron vector instead of a scalar
broadcast. The per-trial set-up (everything up to `net.run`) lives in a small
helper, `_apply_trial_state`, used only by the new function, so it can be tested
without running a simulation. (The trial loop is therefore duplicated between the
two functions; `run_cue` was deliberately not refactored so that the path the
existing results came from stays exactly as it was.)

**Stricter input handling than `run_cue`.** `run_cue` silently skips a root ID it
cannot find. `run_cue_rates` raises on an unknown ID, on a non-integer ID key
(float64 cannot hold a 64-bit root ID exactly: neighbouring IDs collapse), and on
a negative or non-finite rate, because a silently dropped stimulus would corrupt
an experiment. Neurons at exactly 0 Hz are not treated as stimulated (their
refractory period is not cleared).

**Self-test (no model, no `net.run`).** `--self-test` now also runs
`self_test_rates()`, on tiny four-neuron networks. It checks: the rate vector and
driven indices; that 64-bit IDs stay exact; that bad input raises; that a
distinct rate lands on each neuron of a `PoissonGroup`; that the refractory
period is cleared only on driven neurons; that `restore()` resets state; that
learned weights survive it; and that a second stimulus *replaces* the first
rather than adding to it. All pass (run 2026-09-21). Each check was confirmed
able to fail by deliberately breaking the code in a scratch copy (skipping the
weight re-apply, using a scalar rate, clearing the refractory period on all
neurons). What this does **not** cover: `run_cue_rates` itself, which needs
`net.run`.

**Unverified.** With every rate equal, `run_cue_rates` performs the same
operations as `run_cue`, so for the same seed it is *expected* to give the same
spikes. That has not been checked; it needs one paired real run. **Section 4's
equivalence test, by contrast, has since been run and PASSED** (git commit
`6a00cdd`; see the Results at the end of Section 4) — but that test exercised
`run_cue` (a scalar rate), not `run_cue_rates`, so it does not by itself verify
`run_cue_rates`.

### Pre-stated check: `run_cue_rates`, uniform-rate case (prepared; NOT yet run)

**Question.** Our learning code calls `run_cue_rates`, not `run_cue`, and
`run_cue_rates` has never executed a real `net.run`. This checks the smallest
case where the two are expected to agree exactly: every stimulated neuron given
the *same* rate.

**Design (fixed).** Stimulate cue A's full 100-KC pool (`--kc-set-seed
20260316`) through `run_cue_rates`, giving **every** one of those 100 KCs the
identical **150 Hz** rate (via an explicit per-neuron rate map, not a scalar
argument) — mathematically the same stimulus `run_cue`'s scalar path already
delivers. Same seeds, duration, and trial count as the Section 4 equivalence
test: **1000 ms / 5 trials, seeds 20260317–20260321**.

**Pre-stated criteria (identical to Section 4, applied to `run_cue_rates`
instead of `run_cue`):**

1. Mean Euclidean distance between the `run_cue_rates` output and the existing
   old-path cue-A reference (`mbon_noise_floor_cue_a_..._seed_S.csv`), averaged
   over the 5 seeds, **≤ 5.10 Hz** (the same measured same-cue noise floor).
2. All 8 consistent discriminating MBONs (the same set as Section 4) keep the
   same established sign of the cue-A − cue-B difference.

A bonus, non-gating diagnostic also compares the `run_cue_rates` output
directly against the already-ACCEPTED `run_cue` output at the same seeds and
rate (expected distance ≈ 0 Hz if `run_cue_rates` truly reduces to `run_cue`
when every rate is equal); it cannot by itself change the verdict.

**Implementation, not yet run:** `repro/mushroom_body/run_rates_uniform_check.py`
(the simulation; writes `fast_rates_mbon_cue_a_..._seed_S.csv`) and
`repro/mushroom_body/compare_rates_equivalence.py` (analysis only, no
simulation; reads the CSVs and prints both criteria, the verdict, and the bonus
diagnostic).

```bash
# (1) SIMULATION — one seed at a time, all 5 needed; on macOS use caffeinate -i
for S in 20260317 20260318 20260319 20260320 20260321; do
  caffeinate -i uv run --python .venv-shiu/bin/python --no-project -- \
    .venv-shiu/bin/python repro/mushroom_body/run_rates_uniform_check.py --seed "$S"
done

# (2) COMPARE against the existing-path reference (analysis only, no simulation)
uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/compare_rates_equivalence.py
```

Neither script has been executed as part of preparing this section.

```bash
# no-model checks (the original weight-persistence check plus the new one)
uv run --python .venv-shiu/bin/python --no-project -- \
  .venv-shiu/bin/python repro/mushroom_body/fast_runner.py --self-test
```
