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

## Candidate diagnostic manipulations (not model changes)

`--kc-kc-off` is a reversible, in-memory diagnostic that zeroes KC→KC weights
after the upstream model builds its network. It does not edit upstream source
or connectivity data. `--pn-rate` makes the input drive explicit. These are
candidate diagnostic controls for determining where broad activity originates,
not proposed changes to the Shiu model.

Run each in a normal terminal; do not run long simulations inside Codex.

```bash
# Repeat the observed configuration with new per-KC/hemisphere reporting.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316

# Test whether recurrent KC-to-KC excitation is necessary for broad overlap.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 150 --seed 20260316 --kc-kc-off

# Test sensitivity to a weaker PN drive while retaining the upstream network.
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --pn-rate 50 --seed 20260316
```

Use a normal terminal for these long model runs. The script prints the standard
command at the top of its `--help` text.
