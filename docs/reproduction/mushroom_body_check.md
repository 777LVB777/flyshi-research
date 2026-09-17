# Mushroom-body responsiveness check (prepared, not run)

## Purpose and scope

This is a prepared responsiveness check for the Shiu et al. model using FlyWire
v783 connectivity and v783 annotations. It tests whether two annotated
olfactory-PN inputs drive sparse, distinct Kenyon-cell (KC) populations and at
least some mushroom-body output-neuron (MBON) activity. It is not a behavioral,
reward, plasticity, market, or agent experiment.

## Annotation and connectivity sources

- Official annotations: [`flyconnectome/flywire_annotations`](https://github.com/flyconnectome/flywire_annotations), release `v3.1.0`, commit `8587524c1748ce5ef2080822a2fc890fc03bf597`, using `Supplemental_file1_neuron_annotations.tsv`.
- The repository README directly identifies this table as covering FlyWire
  materialization 783. The annotation license is **unverified**: no `LICENSE`
  file exists in the official repository at the recorded commit.
- Connectivity: upstream `third_party/Drosophila_brain_model/Connectivity_783.parquet`
  and `Completeness_783.csv`. The official FlyWire connectivity record is
  [Zenodo 10.5281/zenodo.10676866](https://zenodo.org/records/10676866), version
  783.0. Its displayed license field is blank, so the connectivity-data license
  is **unverified**.

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

## Planned conditions and criteria

The prepared command runs three serial (`n_proc=1`) v783 conditions using
upstream neural/synaptic defaults: baseline (no stimulation), left DA1 PN
stimulation, and left DL2d PN stimulation. Defaults are 150 Hz, 1,000 ms, five
trials, and seed `20260316`; trial count, rate, duration, and seed are command
line options. Raw spike data is temporary; only a CSV and JSON summary will be
saved under `repro/mushroom_body/results/`.

Pass criteria for a future run:

- KC active fraction above 0 Hz is roughly 1–20% for odor conditions.
- The DA1/DL2d active-KC Jaccard overlap is clearly below 1.
- At least one MBON has a nonzero odor-condition rate.

These are coarse responsiveness checks, not validated biological benchmarks.

## Run command

```bash
uv run --python .venv-shiu/bin/python --no-project -- .venv-shiu/bin/python repro/mushroom_body/check_mb_response.py --trials 5 --rate-hz 150 --seed 20260316
```

Use a normal terminal for this long model run. The script prints the same command
at the top of its `--help` text.
