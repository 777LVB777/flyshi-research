# Mushroom-body responsiveness check

## Purpose and scope

This responsiveness check uses the Shiu et al. model with FlyWire v783
connectivity and v783 annotations. It tests whether two annotated olfactory-PN
inputs drive sparse, distinct Kenyon-cell (KC) populations and at least some
mushroom-body output-neuron (MBON) activity. It is not a behavioral, reward,
plasticity, market, or agent experiment.

## Annotation and connectivity sources

- Official annotations: [`flyconnectome/flywire_annotations`](https://github.com/flyconnectome/flywire_annotations), release `v3.1.0`, commit `8587524c1748ce5ef2080822a2fc890fc03bf597`, using `Supplemental_file1_neuron_annotations.tsv`.
- The repository README directly identifies this table as covering FlyWire materialization 783. The annotation license is **unverified**: no `LICENSE` file exists in the official repository at the recorded commit.
- Connectivity: upstream `third_party/Drosophila_brain_model/Connectivity_783.parquet` and `Completeness_783.csv`. The official FlyWire connectivity record is [Zenodo 10.5281/zenodo.10676866](https://zenodo.org/records/10676866), version 783.0. Its displayed license field is blank, so the connectivity-data license is **unverified**.

## Annotation-derived v783 selections

All counts are restricted to IDs in `Completeness_783.csv` (138,625 annotated
neurons in the intersection). The reproducible source, filters, records, and ID
lists are stored in `repro/mushroom_body/neuron_ids_783.json`.

| Group | Annotation columns and values | Count |
| --- | --- | ---: |
| Uniglomerular AL projection neurons | `cell_class=ALPN`, `cell_sub_class=uniglomerular` | 277 |
| Kenyon cells | `cell_class=Kenyon_Cell` | 5,177 |
| MBONs | `cell_class=MBON` | 96 |
| PAM dopamine neurons | `cell_class=DAN`, `cell_type` starts `PAM` | 307 |
| PPL1 dopamine neurons | `cell_class=DAN`, `cell_type` starts `PPL1` | 16 |
| APL neurons | `cell_type=APL` | 2 |

The APL selection is confident in the annotation table: IDs `720575940613583001`
(right) and `720575940624547622` (left) have `cell_type=APL`. PN glomerulus is
the prefix of `cell_type` before its first underscore; side is the annotation
`side` field. No cell-class assignment was inferred from names outside this
table.

## Chosen odors

The script uses two same-side, multi-PN glomeruli:

- Odor A: left `DA1`, 9 uniglomerular PNs.
- Odor B: left `DL2d`, 7 uniglomerular PNs.

These were chosen from the annotation-derived PN grouping only.

## Conditions and criteria

The command runs three serial (`n_proc=1`) v783 conditions using upstream
neural/synaptic defaults: baseline (no stimulation), left DA1 PN stimulation,
and left DL2d PN stimulation. Defaults are 150 Hz, 1,000 ms, five trials, and
seed `20260316`; trial count, PN rate, duration, and seed are command-line
options. Raw spike data is temporary. The script saves small derived summaries:
a JSON, a non-KC CSV, and a compact per-KC-rate CSV. The latter supports
hemisphere-specific analyses in future runs without retaining raw spikes.

Pass criteria:

- KC active fraction above 0 Hz is roughly 1–20% for odor conditions.
- The DA1/DL2d active-KC Jaccard overlap is clearly below 1.
- At least one MBON has a nonzero odor-condition rate.

These are coarse responsiveness checks, not validated biological benchmarks.

## Observed run (local, 2026-09-16)

The locally run default check used FlyWire v783, 5 trials of 1,000 ms per
condition, 150 Hz PN stimulation, `n_proc=1`, and the fixed seed `20260316`.
It did not meet the sparse/selective response criteria.

| Condition | KC active >0 Hz | KC active >5 Hz | Mean KC rate | Nonzero MBONs |
| --- | ---: | ---: | ---: | ---: |
| Baseline | 0.00% | 0.00% | 0.00 Hz | 0 |
| Odor A: left DA1 | 65.69% | 64.15% | 31.32 Hz | 69 |
| Odor B: left DL2d | 65.35% | 63.92% | 30.62 Hz | 69 |

The active-KC Jaccard index for odor A versus B was 0.9912. By hemisphere,
odor A activated 1,775/2,580 left KCs (68.80%) and 1,626/2,597 right KCs
(62.61%); odor B activated 1,764/2,580 left KCs (68.37%) and 1,619/2,597 right
KCs (62.34%). Per-hemisphere mean rates cannot be recovered from the existing
summary, which retained active IDs but not every KC's rate. Future runs now
write a compact per-KC-rate CSV and report both active fractions and mean rate
by side.

### APL and dopamine rates

Rates below are over the five trials. PAM and PPL1 figures report nonzero-cell
count, followed by mean and range across those nonzero annotated neurons.

| Condition | APL right / left (Hz) | PAM (Hz) | PPL1 (Hz) |
| --- | --- | --- | --- |
| Baseline | 0.0 / 0.0 | 0/307 nonzero | 0/16 nonzero |
| Odor A: left DA1 | 326.2 / 346.4 | 129/307; mean 48.30, range 0.2–112.6 | 14/16; mean 125.90, range 5.0–224.6 |
| Odor B: left DL2d | 322.0 / 341.6 | 125/307; mean 48.65, range 0.2–110.6 | 14/16; mean 122.87, range 4.6–219.4 |

The saved JSON retains the individual nonzero APL, PAM, PPL1, and MBON rates.

## Connectivity audit and diagnosis

`Connectivity_783.parquet` contains 15,091,983 directed connections. In the
upstream model, the sign-bearing `Excitatory x Connectivity` column is assigned
directly to synaptic weight (`syn.w`): positive values are excitatory and
negative values are inhibitory. The following counts use the annotation-derived
v783 ID lists above and sum the `Connectivity` column (synapses), with an edge
meaning a nonzero pre/post pair.

| Pathway | Edges | Synapses | Assigned sign |
| --- | ---: | ---: | --- |
| KC → KC | 293,762 | 379,338 | all positive (excitatory) |
| APL → KC | 5,194 | 98,654 | all negative (inhibitory) |
| KC → APL | 5,215 | 116,878 | all positive (excitatory) |

For direct PN targets, the left DA1 PNs connect to 374 distinct KCs (451
edges; 5,325 synapses), while left DL2d PNs connect to 174 distinct KCs (182
edges; 2,888 synapses). Only 11 KCs are direct targets of both; the direct
target Jaccard index is 11/537 = 0.0205. DA1 has 5,295 excitatory and 30
inhibitory synapses in this direct PN→KC subset; DL2d has 2,888 excitatory
synapses.

Thus the direct anatomy is not highly overlapping. The observed 0.9912
active-KC overlap must arise downstream of direct PN→KC targeting in this model
run. Dense, all-excitatory KC→KC connectivity is an evident candidate for
activity spread, while broad APL inhibition is also strongly engaged; this is a
connectivity-informed hypothesis, not a demonstrated causal attribution.

**Verdict: circuit connected, but non-sparse and non-selective.** The silent
baseline and abundant MBON response establish that the prepared pathway is
connected. The approximately 65% KC activity and 0.9912 odor-overlap do not
meet the stated biological target of roughly 5–10% sparse, odor-specific KC
activity.

## `--pn-rate` bug check (odor A vs. odor B)

**Conclusion: no bug in `check_mb_response.py`.** `run_condition()`
(`repro/mushroom_body/check_mb_response.py:131`) sets `params["r_poi"] =
args.pn_rate * Hz` once per condition from a fresh `default_params.copy()`,
and each condition is a separate upstream `run_exp()` call with its own
`neu_exc` list — baseline, odor A, and odor B never share a Brian2 run. In
`third_party/Drosophila_brain_model/model.py`, `poi()` (lines 58–106) applies
`params['r_poi']` uniformly to every index in `exc` (`neu_exc`), and `exc2`
(`neu_exc2`/`r_poi2`) is always empty because this script never passes
`neu_exc2` to `run_exp`. Both `--pn-rate 50` runs used
`stimulated_pn_ids` = the identical 9 DA1 / 7 DL2d IDs recorded in the JSON's
`glomeruli` block, confirming the same 50 Hz per-PN Poisson rate was applied
to both conditions.

The asymmetry that motivated the check is real but not a bug: at 50 Hz, odor A
(9 PNs) barely drops from its 150 Hz mean rate (30.81 vs. 31.32 Hz) while odor
B (7 PNs) drops sharply (12.58 vs. 30.62 Hz). This tracks the anatomy already
documented above — DA1 PNs make 5,325 direct synapses onto 374 KCs, DL2d PNs
make 2,888 synapses onto 174 KCs — so DA1's stronger direct drive plus fewer
PNs needed to cross the network's recurrent-excitation threshold lets it keep
recruiting the KC→KC/DAN feedback loop at 50 Hz, while DL2d's weaker direct
drive does not. This is an emergent property of the (currently oversensitive)
recurrent dynamics, not unequal rate application.

## Per-hemisphere KC results, all runs

| Run | Condition | Active >0 Hz (L / R) | Mean rate Hz (L / R) | Jaccard A/B |
| --- | --- | --- | --- | ---: |
| 150 Hz (original) | Odor A | 68.80% / 62.61% | not recorded¹ | 0.9912 |
| 150 Hz (original) | Odor B | 68.37% / 62.34% | not recorded¹ | 0.9912 |
| 150 Hz, `--kc-kc-off` | Odor A | 60.16% / 51.83% | 25.98 / 17.23 | 0.9760 |
| 150 Hz, `--kc-kc-off` | Odor B | 59.30% / 51.68% | 25.26 / 16.99 | 0.9760 |
| 50 Hz | Odor A | 68.68% / 62.53% | 36.84 / 24.82 | 0.9903 |
| 50 Hz | Odor B | 68.22% / 62.19% | 15.02 / 10.16 | 0.9903 |

¹ The original run predates the per-KC-rate CSV; only active/inactive IDs were
retained, not individual rates, so per-side mean rate cannot be recovered.
Baseline is 0.00% / 0.00 Hz on both sides in every run.

`--kc-kc-off` (KC→KC weights zeroed) reduces overall active fraction from
65.7% to 56.0% and Jaccard from 0.991 to 0.976 — a real but modest effect,
consistent with the KC-input audit below showing KC→KC is a large (40%) but
not majority source of excitatory drive onto KCs.

## Neurotransmitter sign rules

**Not present in `model.py` or `utils.py`.** Both files were searched
exhaustively (`grep -rn -i "dopamine\|serotonin\|octopamine\|gaba\|acetylcholine\|glutamate\|sign"`)
and contain no neurotransmitter-to-sign logic. The only sign-related line is
`model.py:183`:

```python
syn.w = df_con.loc[:,'Excitatory x Connectivity'].values * params['w_syn']
```

`Excitatory x Connectivity` is a precomputed column already baked into
`Connectivity_783.parquet` (and the v630 equivalent) before this repo's code
ever runs; the code that produced it is not part of this upstream repository
and was not found elsewhere in `third_party/`.

**Empirically recovered from data (verified, not code).** Cross-referencing
each synapse's presynaptic `top_nt` (predicted transmitter, from
`third_party/flywire_annotations/.../Supplemental_file1_neuron_annotations.tsv`)
against `Connectivity_783.parquet`'s per-synapse `Excitatory` column (±1)
gives a near-deterministic rule:

| `top_nt` | Assigned sign | Synapses matching (of total for that `top_nt`) |
| --- | --- | ---: |
| acetylcholine | excitatory (+1) | 99.11% |
| dopamine | excitatory (+1) | 99.96% |
| octopamine | excitatory (+1) | 99.98% |
| serotonin | excitatory (+1) | 99.81% |
| gaba | inhibitory (−1) | 98.68% |
| glutamate | inhibitory (−1) | 97.56% |

This confirms the session's working hypothesis: **dopamine, serotonin, and
octopamine are all assigned the same fast-excitatory sign as acetylcholine**,
with no distinct slow-modulatory treatment. The small (~1–2%) exceptions per
`top_nt` were not further investigated; a plausible explanation is
disagreement between per-synapse and per-neuron transmitter calls, but this is
**unverified**.

**Critical confound found while auditing this: the classifier mispredicts
Kenyon cells.** Of 5,177 KCs, `top_nt` says `dopamine` for 5,172 (99.9%),
while `known_nt` (immunohistochemistry/scRNA-seq literature calls) says
`acetylcholine; sNPF` for essentially all of them. KCs alone account for
984,448 of the 1,384,531 synapses (71%) that the connectome-wide `top_nt ==
'dopamine'` label covers. Because both true ACh and (mislabeled) "dopamine"
map to the same excitatory sign, this misclassification happens to leave
KC→KC sign correct by coincidence — but it means **any manipulation keyed on
`top_nt == 'dopamine'` will also hit Kenyon cells**, not just genuine
dopaminergic neurons (see `--modulatory-fast-off` caveat below).

DPM (the single unpaired mushroom-body input neuron classically described as
serotonergic/GABAergic) is a second, smaller instance of the same problem:
`cell_class=MBIN`, `cell_type=DPM`, `top_nt=dopamine` (confidence 0.68/0.59),
but `known_nt=serotonin; amnesiac; gaba` sourced from Lee et al. 2011, Waddell
et al. 2000, Haynes et al. 2015, and Aso et al. 2019. DPM's 9,280 synapses
onto KCs are therefore treated as fast-excitatory in this model, though the
literature transmitter is inhibitory/modulatory.

## KC input audit (v783, restricted to `Completeness_783.csv`)

404,453 presynaptic/postsynaptic pairs (943,190 synapses) target the 5,177
annotated Kenyon cells:

| Presynaptic class | Synapses | % of KC input | Sign | Dominant `top_nt` |
| --- | ---: | ---: | --- | --- |
| KC (KC→KC) | 379,338 | 40.2% | 100% excitatory | dopamine (mislabeled; true ACh) |
| PN (all ALPN) | 329,394 | 34.9% | 99.8% excitatory | acetylcholine |
| APL | 98,654 | 10.5% | 100% inhibitory | gaba |
| other (unclassified/CX/sensory/etc.) | 52,661 | 5.6% | 55.5% excitatory | mixed |
| PAM | 42,911 | 4.5% | 100% excitatory | dopamine |
| PPL1 | 16,366 | 1.7% | 100% excitatory | dopamine |
| MBON | 13,206 | 1.4% | 29.5% excitatory | mixed (ACh/GABA/Glu) |
| DPM | 9,280 | 1.0% | 100% excitatory | dopamine (mislabeled; true 5-HT/GABA) |
| other DAN (PPL2ab ×4, ×2 each side) | 1,380 | 0.15% | 100% excitatory | dopamine |

Of the 811,035 excitatory synapses onto KCs:

- **True dopaminergic neurons (PAM + PPL1 + other DAN, by `cell_class=='DAN'`): 60,657 synapses = 7.48%.**
- **DPM (predicted dopamine, literature serotonin/GABA): 9,280 synapses = 1.14%.**
- **Serotonergic (`top_nt=='serotonin'`, excluding KCs): 283 synapses = 0.03%**, from 23 neurons including CSD, a known bilateral serotonergic modulator of olfactory circuits.
- **Octopaminergic (`top_nt=='octopamine'`, excluding KCs): 793 synapses = 0.10%**, from 13 neurons including several OA-VPM/OA-VUMa reward-signaling octopaminergic types.
- Combined DAN + DPM + serotonergic + octopaminergic excitatory input onto KCs: 71,013 / 811,035 = **8.76%** of all excitatory KC input.

So dopaminergic/serotonergic/octopaminergic input is a real but minority
contributor to excitatory KC drive; recurrent KC→KC (40.2%) and direct PN
input (34.9%) are larger. This suggests fast-modulatory excitation alone is
unlikely to fully explain the ~65% non-sparse activity, but removing it is
still an informative diagnostic, especially combined with `--kc-kc-off`.

## Candidate diagnostic manipulations (not model changes)

All diagnostics below are reversible, in-memory-only manipulations applied
after the upstream model builds its network (`repro/mushroom_body/check_mb_response.py`,
`install_diagnostic_silencers`). None edit upstream source or connectivity
files. They isolate candidate causes of non-sparse, non-selective KC activity;
none are proposed fixes to the Shiu model. **The unmodified model must always
be reported alongside any modified/diagnostic run for comparison.**

- `--kc-kc-off` — zeroes KC→KC synapse weights. Rationale: recurrent
  excitatory KC→KC connectivity (40.2% of excitatory KC input, all treated as
  excitatory per the sign table above) is a documented candidate for runaway
  activity spread.
- `--dan-kc-off` (new) — zeroes synapses from all annotated dopaminergic
  neurons (`cell_class=='DAN'`: PAM, PPL1, and 4 other PPL2ab-type neurons)
  onto KCs. From the connectivity table alone (no simulation needed to count
  this): **60,657 synapses (47,404 pre/post pairs)**. Rationale: dopamine is a
  slow neuromodulator of KC plasticity in vivo, not a fast driver of KC
  spiking; this model currently gives it the same fast-excitatory sign as
  acetylcholine (see sign-rule section above).
- `--modulatory-fast-off` (new) — zeroes **all** outgoing synapses from any
  neuron with `top_nt` in `{dopamine, serotonin, octopamine}`, network-wide
  (not just onto KCs). From the connectivity table alone: **1,958,576
  synapses (832,432 pairs) = 3.59% of all 54,492,922 synapses in the v783
  connectome.** **Caveat, load-bearing for interpretation:** 50.2% of the
  synapses this flag removes (983,202) originate from Kenyon cells
  themselves, because of the KC `top_nt` misclassification documented above —
  those are the model's normal cholinergic KC→KC/KC→MBON/KC→APL output, not
  genuine monoamine signaling. `--modulatory-fast-off` on its own therefore
  conflates "remove true DA/5-HT/OA modulatory drive" with "remove roughly
  half of all KC recurrent/output connectivity." Results from this flag alone
  should not be read as a clean test of the neuromodulator-sign hypothesis;
  compare against `--dan-kc-off` (which is not confounded this way) and
  consider `--kc-kc-off` + `--dan-kc-off` combined as a less-confounded
  two-factor probe.

Both new flags print their synapse-removal counts (computed directly from
`Connectivity_783.parquet`, before any Brian2 run starts) and are recorded in
the output JSON's `parameters` block (`dan_kc_off`, `modulatory_fast_off`).
The masking logic (`zero_between`, `zero_from`) was unit-tested against a
stand-in synapses object (no Brian2/simulation involved) and reproduces the
same 47,404 and 832,432 pair counts obtained directly from the connectivity
table.

## Acceptance target for any fix

A candidate fix (not yet attempted) should be judged against:

- KC active fraction roughly **5–20% on the stimulated (left) side**.
- KC active fraction **clearly lower on the opposite (right) side** than on
  the stimulated side (current runs show the opposite pattern is barely
  present: left leads right by only ~6 points at 65%+ activity).
- Odor A/B active-KC Jaccard **well below 0.5** (current best is 0.976).
- Baseline **still silent** (0.00% active, 0.00 Hz) — true in every run so far.
- **Always report the unmodified (upstream-default) model alongside any
  modified/diagnostic run**, using the same seed, trial count, and duration,
  so the comparison is apples-to-apples.

## Exact commands for the next diagnostic runs

Run each in a normal terminal; do not run long simulations inside Codex.

```bash
# Repeat the observed configuration with per-KC/hemisphere reporting (unmodified baseline for comparison).
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316

# Test whether recurrent KC-to-KC excitation is necessary for broad overlap.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316 --kc-kc-off

# Test sensitivity to a weaker PN drive while retaining the upstream network.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 50 --seed 20260316

# New: test whether treating dopamine as fast-excitatory onto KCs drives broad activity.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316 --dan-kc-off

# New: broader probe, removing all DA/5-HT/OA-predicted output network-wide.
# NOTE: run --dan-kc-off first and read its result before this one — this flag
# is confounded by the KC top_nt misclassification (see caveat above).
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316 --modulatory-fast-off
```

Use a normal terminal for these long model runs. The script prints the standard
command at the top of its `--help` text.
