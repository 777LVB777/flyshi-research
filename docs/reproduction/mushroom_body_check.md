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
| 150 Hz, `--dan-kc-off` | Odor A | 66.01% / 57.64% | 33.10 / 21.70 | 0.9863 |
| 150 Hz, `--dan-kc-off` | Odor B | 65.47% / 57.64% | 33.12 / 21.48 | 0.9863 |

¹ The original run predates the per-KC-rate CSV; only active/inactive IDs were
retained, not individual rates, so per-side mean rate cannot be recovered.
Baseline is 0.00% / 0.00 Hz on both sides in every run.

`--kc-kc-off` (KC→KC weights zeroed) reduces overall active fraction from
65.7% to 56.0% and Jaccard from 0.991 to 0.976 — a real but modest effect,
consistent with the KC-input audit below showing KC→KC is a large (40%) but
not majority source of excitatory drive onto KCs.

`--dan-kc-off` (60,657 synapses from 331 annotated DANs onto KCs zeroed; run
2026-09-16, logged in `repro/mushroom_body/run_log_dan_kc_off.txt`) gives
overall active 61.81%/61.54% and Jaccard 0.986 — an even smaller effect than
`--kc-kc-off`. Combined with the KC-input audit's finding that true DAN input
is only 7.48% of excitatory KC drive, this is consistent, not surprising.

### Ruled out as the sole/main cause of non-sparse, non-selective KC activity

Three independent single-factor manipulations each produced only a modest
reduction from the ~65% baseline non-sparse state, none approaching the
5–20% target:

- **DAN→KC excitation** (`--dan-kc-off`): 65.7% → 61.8%/61.5%, Jaccard 0.991 → 0.986.
- **KC→KC recurrence** (`--kc-kc-off`): 65.7% → 56.0%, Jaccard 0.991 → 0.976.
- **Input drive strength** (`--pn-rate 50` vs. 150): overall active fraction essentially unchanged (65.6%/65.2% vs. 65.7%/65.4%), even though odor B's mean rate dropped by more than half — the *fraction of KCs crossing spike threshold* is nearly rate-invariant even though *how hard* they fire is not.

Any odor, at either 50 Hz or 150 Hz, with or without DAN→KC or KC→KC
connectivity, converges on the same ~60–65% KC active state with >0.97
odor A/B overlap. This points toward either (a) a combination/interaction of
these factors rather than any single one, or (b) a distinct pathway not yet
tested (e.g. broad PN→KC connectivity itself, or activity that is already
saturated after the first few excitatory relays regardless of how it's driven
downstream — see the target-vs-non-target analysis below).

## Are non-target KCs driven through direct PN input, or through spread?

Using the existing per-KC-rate CSVs (`--kc-kc-off`, `--pn-rate 50`, and
`--dan-kc-off` runs — the only three with per-KC rates saved) split against
the anatomical direct-target KC sets (374 KCs downstream of left DA1 PNs, 174
downstream of left DL2d PNs, computed straight from `Connectivity_783.parquet`,
no simulation needed):

| Run | Odor | Direct targets: active% / mean Hz | Non-targets: active% / mean Hz |
| --- | --- | --- | --- |
| `--kc-kc-off` | A (DA1, n=374 targets / 4,803 non) | 81.28% / 37.40 Hz | 54.01% / 20.36 Hz |
| `--kc-kc-off` | B (DL2d, n=174 targets / 5,003 non) | 81.61% / 40.19 Hz | 54.57% / 20.45 Hz |
| `--pn-rate 50` | A | 84.76% / 46.82 Hz | 64.11% / 29.56 Hz |
| `--pn-rate 50` | B | 83.33% / 20.46 Hz | 64.56% / 12.30 Hz |
| `--dan-kc-off` | A | 85.29% / 45.80 Hz | 59.98% / 26.43 Hz |
| `--dan-kc-off` | B | 82.76% / 48.65 Hz | 60.80% / 26.54 Hz |

**Finding: non-target KCs are not merely noisy — they fire at 54–65% active
and roughly half-to-two-thirds the mean rate of direct targets, in every run
tested.** Direct anatomical PN→KC input explains why targets fire *somewhat*
more than non-targets, but it clearly does not explain why 54–65% of the
4,800+ KCs that receive **no direct synapse from the stimulated PNs** are
active at all, often at tens of Hz. This is consistent with the "spread, not
direct-input selectivity" picture the DAN/KC-KC/rate manipulations already
pointed toward — the mechanism recruiting non-target KCs was not identified by
any single-factor removal tried so far, and is the leading open question for
the next round of diagnostics (the new timing/brain-wide probes below are
aimed at localizing where that spread originates).

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
- `--dan-kc-off` — zeroes synapses from all annotated dopaminergic
  neurons (`cell_class=='DAN'`: PAM, PPL1, and 4 other PPL2ab-type neurons)
  onto KCs. From the connectivity table alone (no simulation needed to count
  this): **60,657 synapses (47,404 pre/post pairs)**. Rationale: dopamine is a
  slow neuromodulator of KC plasticity in vivo, not a fast driver of KC
  spiking; this model currently gives it the same fast-excitatory sign as
  acetylcholine (see sign-rule section above). **Run 2026-09-16**: KC active
  61.81%/61.54%, Jaccard 0.986 — ruled out as the sole/main cause (see above).
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

## Diagnostics added this round (localizing the spread)

Since DAN→KC, KC→KC, and input-rate manipulations each ruled out only a modest
share of the ~65% non-sparse KC state, and non-target KCs turn out to fire
almost as much as direct targets (see above), every future run of
`check_mb_response.py` now also saves four small (each well under 1 MB), self-
documenting CSVs, computed with no new CLI flags — they run automatically:

- **`mb_pn_rates_<suffix>.csv`** — rate for all 277 uniglomerular PNs, tagged
  with `glomerulus` and `side` (from the same grouping used to pick odor A/B).
  Lets us check whether PNs *outside* the two stimulated glomeruli fire at all
  — if they do, activity is leaking upstream of the MB, not just spreading
  within it.
- **`mb_brain_wide_<suffix>.csv`** — per condition, the count and fraction of
  *all* ~138,639 v783 neurons with nonzero rate (not just MB-related groups).
- **`mb_top_active_types_<suffix>.csv`** — per condition, the top 20
  `cell_type`s ranked by mean rate (computed over the type's full membership,
  0 for non-spiking members), each with `cell_class`, `n_total`, `n_active`,
  `fraction_active`. Shows whether the spread stays inside olfactory/MB
  circuitry or reaches unrelated brain regions.
- **`mb_latency_<suffix>.csv`** — first-spike latency in trial 0 only (raw
  spikes are read before the temporary run directory is cleaned up), in ms:
  - `kc_target_median_ms` / `kc_nontarget_median_ms` — median first-spike time
    among direct-target vs. non-target KCs that spiked at all, plus `_n_spiked`.
  - `apl_first_ms` / `apl_first_id` — earliest of the 2 APL neurons' first spikes.
  - `first_nonstim_pn_ms` / `first_nonstim_pn_id` — earliest first-spike among
    the ~268–277 PNs *not* in the stimulated glomerulus, i.e. how fast a signal
    could in principle leak back into other PN channels.
  - `first_right_kc_ms` / `first_right_kc_id` — earliest first-spike among all
    right-hemisphere KCs, i.e. how fast activity crosses the midline.
  - If `kc_nontarget_median_ms` is close to (not much later than)
    `kc_target_median_ms`, that would argue against a multi-synapse relay
    picture and for something closer to simultaneous broad recruitment.

Direct-target KC sets (used for `kc_target`/`kc_nontarget` above) are computed
once per run straight from `Connectivity_783.parquet` (no simulation), exactly
as in the target-vs-non-target analysis above. `--duration-ms` (default 1000)
already existed before this round and is unchanged; it can be set to 200 for
short exploratory runs, e.g. to see whether the latency ordering already holds
well before 1 s.

All four writer functions (`write_pn_rates_csv`, `write_brain_wide_csv`,
`write_top_active_types_csv`, `write_latency_csv`) and their underlying
analysis functions (`pn_rate_rows`, `direct_kc_targets`, `brain_wide_summary`,
`first_spike_latencies_ms`) were unit-tested against synthetic data (no Brian2,
no simulation) before being added; `--help` was confirmed working after the
change (exit code 0).

### Results (run 2026-09-16, unmodified model, 150 Hz, 5 trials, 1000 ms, seed 20260316)

**Non-stimulated PNs fire heavily, on both sides, in every glomerulus.**
Stimulating only the 9 left-DA1 PNs (odor A) or 7 left-DL2d PNs (odor B) drives:

| Group | n | Active | Mean rate (active only) |
| --- | ---: | ---: | ---: |
| Odor A: stimulated left-DA1 PNs | 9 | 100% | 265.8 Hz |
| Odor A: same-glomerulus right-DA1 PNs (not stimulated) | 8 | 100% | 129.8 Hz |
| Odor A: all other-glomerulus PNs, both sides | 260 | 97.3% | 127.0 Hz (123.6 Hz incl. silent) |
| Odor B: stimulated left-DL2d PNs | 7 | 100% | 231.2 Hz |
| Odor B: same-glomerulus right-DL2d PNs (not stimulated) | 7 | 100% | 106.6 Hz |
| Odor B: all other-glomerulus PNs, both sides | 263 | 97.0% | 127.2 Hz (123.4 Hz incl. silent) |

Non-stim activation is essentially bilaterally symmetric (odor A: 127 active
left / 126 active right among the 260 non-stim PNs; odor B: 128 / 127). This
is measured directly from `mb_pn_rates_*.csv`; no simulation was run to
produce this number, only post-hoc analysis of the existing file.

**Brain-wide:** 0% of ~138,639 v783 neurons active at baseline; 6.22% (8,619
neurons) for odor A; 6.20% (8,592 neurons) for odor B (`mb_brain_wide_*.csv`).
So the spread, while already well beyond the MB and AL, has not saturated the
whole brain.

**Top 10 active cell types** (by mean rate, from `mb_top_active_types_*.csv`;
nearly identical top-10 for both odors):

| Rank | Cell type | Cell class | Mean rate (odor A / odor B) |
| ---: | --- | --- | --- |
| 1 | APL | MBIN | 336.3 / 331.8 Hz |
| 2 | v2LN30 | ALLN | 295.4 / 290.6 Hz |
| 3 | il3LN6 | ALLN | 287.9 / 284.0 Hz |
| 4 | lLN1_bc | ALLN | 285.9 / 281.8 Hz |
| 5 | lLN2X03 | ALLN | 285.1 / 281.7 Hz |
| 6 | DPM (odor A) / lLN1_a (odor B) | MBIN / ALLN | 284.0 / 278.9 Hz |
| 7 | lLN1_a (odor A) / DPM (odor B) | ALLN / MBIN | 282.5 / 278.8 Hz |
| 8 | lLN2F_b | ALLN | 282.1 / 278.3 Hz |
| 9 | lLN2T_c | ALLN | 281.4 / 278.0 Hz |
| 10 | lLN2X04 | ALLN | 280.1 / 276.9 Hz |

All 10 are at or near saturating rates (the refractory period `t_rfc=2.2ms`
caps the theoretical max near ~455 Hz). Ranks 14–20 are dominated by
`_adPN` cell types (e.g. `DP1m_adPN`, `VP2_adPN`, `DC1_adPN`) — uniglomerular
PNs from glomeruli that are neither DA1 nor DL2d, confirming the PN-level
finding above at the cell-type-ranking level. `cell_class=ALLN` (antennal-lobe
local neuron) dominates the top 10 for both odors; KCs and DANs do not appear
in the top 10 at all.

**Latency (trial 0), from `mb_latency_*.csv`:**

| Metric | Odor A | Odor B |
| --- | ---: | ---: |
| First non-stim PN (`first_nonstim_pn_ms`, neuron `...628467611`, VL2p-left, same for both odors) | 13.8 ms | 27.8 ms |
| APL first spike (`apl_first_ms`, same 2-neuron pair both odors) | 18.5 ms | 27.1 ms |
| KC direct-target median first spike (`kc_target_median_ms`, n=322/145) | 33.9 ms | 45.1 ms |
| Right-hemisphere KC earliest first spike (`first_right_kc_ms`) | 35.6 ms | 46.7 ms |
| KC non-target median first spike (`kc_nontarget_median_ms`, n=3073/3216) | 45.0 ms | 55.5 ms |

Ordering (earliest to latest) is the same for both odors: **non-stim PN ≈ APL
< KC direct-target median < right-hemisphere-KC earliest < KC non-target
median.** The non-stimulated PN and APL both fire before the *median*
direct-target KC. **Caveat:** the non-stim-PN/APL/right-KC values are each a
single earliest-spike time across a group, while the KC target/non-target
values are medians across all spiking members of a (much larger) group — these
are not the same kind of statistic, so "X ms before Y" here means "before the
midpoint of Y's response," not "before every member of Y." The true earliest
KC-target spike (not reported by this metric) could well be earlier than 18.5
or 13.8 ms; this was not measured and is **unverified**.

## Top-k KC selectivity analysis

For k ∈ {2%, 5%, 10%} of the 5,177 KCs, took each odor's top-k most active KCs
by mean rate (ties broken deterministically: rate descending, then FlyWire
root ID ascending), across all four runs with a per-KC-rate CSV. Reports the
odor A/B Jaccard overlap of the two top-k sets, and what fraction of each
odor's top-k set are direct anatomical targets of that odor's own PNs (374 KCs
for DA1, 174 for DL2d, from `Connectivity_783.parquet`, no simulation).

| Run | k | n | A/B Jaccard | A-set is DA1-target | B-set is DL2d-target |
| --- | ---: | ---: | ---: | ---: | ---: |
| unmodified 150 Hz | 2% | 104 | 0.748 | 21.15% | 17.31% |
| unmodified 150 Hz | 5% | 259 | 0.799 | 22.01% | 14.29% |
| unmodified 150 Hz | 10% | 518 | 0.860 | 20.85% | 12.36% |
| `--kc-kc-off` | 2% | 104 | 0.719 | 26.92% | 14.42% |
| `--kc-kc-off` | 5% | 259 | 0.818 | 20.46% | 13.90% |
| `--kc-kc-off` | 10% | 518 | 0.857 | 19.31% | 10.42% |
| `--dan-kc-off` | 2% | 104 | 0.691 | 25.00% | 17.31% |
| `--dan-kc-off` | 5% | 259 | 0.830 | 21.62% | 13.13% |
| `--dan-kc-off` | 10% | 518 | 0.857 | 20.66% | 12.16% |
| `--pn-rate 50` | 2% | 104 | 0.857 | 14.42% | 12.50% |
| `--pn-rate 50` | 5% | 259 | 0.884 | 17.37% | 10.04% |
| `--pn-rate 50` | 10% | 518 | 0.901 | 17.76% | 10.42% |

**Findings:**

- Restricting to only the top 2% most active KCs does not recover
  selectivity: Jaccard stays 0.69–0.86 across all four runs, versus the
  full-active-set Jaccard of 0.976–0.991 reported earlier — some improvement,
  but nowhere near "well below 0.5."
- **Only 10–27% of each odor's top-k KCs are direct anatomical targets of that
  odor's own PNs**, in every run and at every k. So even the *most* active
  KCs for a given odor are, 73–90% of the time, KCs the odor's PNs never
  directly synapse onto. Whatever is putting a KC at the top of the activity
  ranking, it is usually not that KC receiving direct odor-specific PN input.
- `--dan-kc-off` and `--kc-kc-off` produce essentially no improvement in top-k
  Jaccard over the unmodified model (differences are within the noise of a
  single 5-trial seed). `--pn-rate 50` actually has *higher* top-k Jaccard
  (0.86–0.90) than the unmodified 150 Hz run (0.75–0.86), despite the two
  odors' full-active-set Jaccard being nearly identical (0.990 vs. 0.991) —
  weakening the input drive did not make the top responders more
  odor-specific.

## Diagnosis: where does the spread originate?

**Shown by data (this session, no simulation needed for the analysis itself):**

- Stimulating one glomerulus's ~7–9 left-hemisphere PNs drives 97%+ of *all*
  277 uniglomerular PNs — every glomerulus, both hemispheres — to fire, at
  rates comparable to the stimulated PNs themselves. This happens in the
  antennal-lobe PN population itself, upstream of the mushroom body.
- The cell types firing hardest (250–336 Hz, near the refractory-period
  ceiling) are APL, DPM, and a large set of `cell_class=ALLN`/`lLN*`
  antennal-lobe local neurons — not KCs, not DANs, not even the stimulated
  glomerulus's own PNs particularly more than other glomeruli's PNs.
- A non-stimulated PN and APL both reach their first spike (13.8–27.8 ms)
  before the *median* direct-target KC responds (33.9–45.1 ms).
- Even the top 2–10% most active KCs by rate are 73–90% NOT direct anatomical
  targets of the stimulating odor's PNs, and their odor A/B overlap (0.69–0.86)
  is only modestly better than the full active-set overlap (0.976–0.991).
- Three independent single-factor removals — DAN→KC, KC→KC, and halving PN
  input rate — each left the ~65% non-sparse KC state and top-k
  non-selectivity essentially intact.

**Hypothesis, not yet verified:**

- The most likely primary locus of the pathological non-selectivity is
  **upstream of the mushroom body, in the antennal-lobe local-interneuron
  network** (the ALLN/lLN population), not in KC recurrence or DAN input as
  originally hypothesized. The evidence above is consistent with this: the
  spread is already essentially complete at the PN layer, before signal ever
  reaches KCs, and the hardest-firing cell types are AL local neurons, not MB
  neurons.
- A plausible mechanism (**unverified — not checked this session**): real
  antennal-lobe local neurons are predominantly GABAergic and provide lateral
  inhibition/contrast enhancement between glomeruli; if this connectome-derived
  model's ALLN/lLN population is instead net excitatory (or has the same
  broad fast-excitatory sign issue documented for DA/5-HT/OA), stimulating one
  glomerulus could excite the local-neuron network into broadcasting activity
  to every other glomerulus instead of suppressing them. **This has not been
  checked** — the sign/neurotransmitter breakdown for `cell_class=ALLN` (or
  whatever local-neuron classes exist) was not audited this session and is the
  natural next diagnostic.
- It is also plausible (**unverified**) that this reflects a calibration issue
  — `w_syn`/`f_poi` too strong for this connectome density — rather than a
  transmitter-sign issue specifically. This was not tested this session (would
  require sweeping `w_syn`/`f_poi`, not requested) and should not be assumed
  correct or ruled out.
- The MB-internal manipulations tried so far (`--dan-kc-off`, `--kc-kc-off`,
  `--pn-rate`) were, in retrospect, looking downstream of where the data now
  points; that does not mean they are wrong to have tried, but future
  diagnostics should prioritize the antennal lobe over further MB-internal
  probes.

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
# Repeat the observed configuration with per-KC/hemisphere reporting (unmodified
# baseline for comparison). Now also produces mb_pn_rates_*, mb_brain_wide_*,
# mb_top_active_types_*, and mb_latency_* CSVs (new diagnostics, no flags needed).
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316

# Optional: short 200 ms trials to check whether the latency ordering (target vs.
# non-target KC, APL, non-stim PN, right-hemisphere KC) already holds before 1 s.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --duration-ms 200 --seed 20260316

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
