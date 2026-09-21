# MBON readout and compartment-matched plasticity options

**Status: design analysis of existing v783 data; no new simulations were run.**

This document separates two decisions. A *readout* turns the firing rates of
mushroom-body output neurons (MBONs) into a decision score. *Plasticity* is the
as-yet-unimplemented rule that changes a Kenyon-cell (KC) to MBON connection.
Neither is part of the Shiu et al. model.

The KC-direct 1000-ms/5-trial result has 33 responding MBON instances (20
FlyWire labels). The eight consistent discriminators are MBON03, MBON02,
MBON07 (two cells), MBON04, MBON26, MBON11, and MBON23. Counts below are
instances, not unique cell-type names.

## Mapping of the responding data to the valence table

The saved result already carries the pinned FlyWire `cell_type` label for every
responding root ID. Mapping those labels to `mbon-valence.md` gives 5 confident
individual-label instances, 9 group-only instances, 2 conflicted instances, 12
no-significant-effect instances, and 5 types not in the 22-entry table. For
this requested five-way classification, MBON06 is placed in “no significant
effect” because its predominantly MBON06 driver was not significant; the
table's more precise wording remains “unverified individually.”

| Classification | Responding FlyWire cell types (instance count) |
|---|---|
| Confident individual label | MBON05×1 (avoidance), MBON11×2 (approach), MBON12×2 (approach) |
| Group-only label | MBON03×1 (avoidance), MBON04×1 (avoidance), MBON09×4 (approach), MBON16×1, MBON17×1, MBON18×1 (approach) |
| Conflicted | MBON02×2 |
| No significant effect | MBON06×1 (individual result unverified), MBON07×2, MBON10×6, MBON13×1, MBON14×2 |
| Not in table | MBON24×1, MBON27×1, MBON32×1, MBON33×1, MBON35×1 |

Of the eight consistent discriminators: MBON11 is the one confident individual
label; MBON03 and MBON04 are group-only; MBON02 is conflicted; both MBON07
instances had no significant effect; and MBON26 plus MBON23 are not in the
table.

## Readout options

| Option | MBONs assigned a nonzero readout weight | Responding instances used | Of 8 discriminators used | Risk |
|---|---|---:|---:|---|
| **CIRCUIT (primary; 80% dominant-family rule)** | Sum annotated direct PAM and PPL1 synapses onto an MBON. Give it an avoidance-like sign if PAM supplies ≥80%; an approach-like sign if PPL1 supplies ≥80%; otherwise give zero weight. This is a declared mushroom-body-circuit modelling assumption, not a behavioural measurement. | 28/33 | 6/8 (MBON02, MBON03, MBON04, MBON07×2, MBON11) | Its signs come from circuit logic and an inferred, unverified compartment map, and can disagree with activation-valence experiments. |
| **STRICT** | Individual, confidently labelled types only: MBON05 and MBON21 for avoidance; MBON11 and MBON12 for approach. | 5/33 (MBON05×1, MBON11×2, MBON12×2) | 1/8 (MBON11) | It is conservative about the literature, but discards almost all of the strongest cue difference. MBON21 did not respond in this result. |
| **GROUP** | STRICT plus an explicit modelling assumption: glutamatergic MBON01/03/04 are avoidance; MBON08/09 and MBON15–19 are approach. All other labels, including labels absent from the valence table, have zero weight. | 14/33 (STRICT's 5, plus MBON03×1, MBON04×1, MBON09×4, MBON16×1, MBON17×1, MBON18×1) | 3/8 (MBON03, MBON04, MBON11) | Uses more of the measured signal, but treats effects established only for co-activated groups as type-level signs. That is a declared modelling assumption, not an individual-cell experimental result. |

CIRCUIT at 80% is the primary readout. X = 70% and X = 90% are preregistered
CIRCUIT sensitivity checks, and so is CIRCUIT-80 with MBON08 and MBON09 set to
zero weight (the γ3 variant, below); STRICT and GROUP are preregistered robustness
checks. Any result that appears only under CIRCUIT must be reported as such.
MBON02 is excluded from STRICT and GROUP because the table calls its
activation valence conflicted. MBON07, MBON26, and MBON23 are also excluded
from those checks: MBON07 had no significant effect in the table; MBON26 and
MBON23 are not in that table.

### CIRCUIT assignment at the adopted 80% threshold

| Circuit assignment | Responding types (instance count) |
|---|---|
| Avoidance-like (PAM ≥80%) | MBON02×2, MBON03×1, MBON04×1, MBON05×1, MBON06×1, MBON07×2, MBON09×4, MBON10×6 |
| Approach-like (PPL1 ≥80%) | MBON11×2, MBON12×2, MBON13×1, MBON14×2, MBON16×1, MBON17×1, MBON18×1 |
| Zero: below 80% or no direct annotated input | none among responding types |
| Zero: no clear mapped compartment | MBON24×1, MBON27×1, MBON32×1, MBON33×1, MBON35×1 |

### Validation against the activation-valence table at 80%

“Agree” means CIRCUIT produces the same approach/avoidance sign as the stated
behavioural label. A zero weight is a disagreement for this comparison, rather
than silently omitted.

| Type | Behavioural label | CIRCUIT sign | Agreement? |
|---|---|---|---|
| MBON05 | avoidance | avoidance-like (PAM γ4) | yes |
| MBON21 | avoidance | avoidance-like (PAM γ4 and γ5) | yes |
| MBON11 | approach | approach-like (PPL1 γ1/pedc) | yes |
| MBON12 | approach | approach-like (PPL1 γ2/α′1) | yes |
| MBON01 | avoidance, group-only | avoidance-like (PAM γ5 and anterior β′2a) | yes |
| MBON03 | avoidance, group-only | avoidance-like (99.9% PAM) | yes |
| MBON04 | avoidance, group-only | avoidance-like (88.7% PAM) | yes |
| MBON08 | approach, group-only | zero (no direct annotated dopamine input) | **no** |
| MBON09 | approach, group-only | avoidance-like (PAM γ3/β′1) | **no** |
| MBON15 | approach, group-only | approach-like (PPL1 α′1) | yes |
| MBON16 | approach, group-only | approach-like (PPL1 α′3) | yes |
| MBON17 | approach, group-only | approach-like (PPL1 α′3) | yes |
| MBON18 | approach, group-only | approach-like (PPL1 α2) | yes |
| MBON19 | approach, group-only | approach-like (PPL1 posterior α2/α3) | yes |

The explicit 80% disagreements are MBON08 and MBON09. γ3 is therefore a
genuine exception: MBON08 is zero under the direct-connectivity rule, while
MBON09 is PAM/avoidance-like, although both have a group-level approach label.
This exception is reported, not corrected.

### γ3 sensitivity variant: CIRCUIT-80 with MBON08 and MBON09 at zero weight

**Preregistered 2026-09-21, before any learning run,** as an additional
sensitivity variant (sign table `circuit_80_no_gamma3`; data file
`src/flyshi_research/learning/data/mbon_sign_tables.json`, `circuit_variants`).
It is the primary CIRCUIT-80 table with the two γ3 types set to zero readout weight.

Rationale:

- **MBON09 is the largest contributor to the intensity bias.** In the graded-rate
  test the CIRCUIT score fell as drive rose, and MBON09 was the largest single
  avoidance-like contributor (63.7 Hz at 150 Hz;
  [`graded-encoding.md`](graded-encoding.md)).
- **It is the type where the circuit rule contradicts behavioural data.** CIRCUIT
  calls MBON09 avoidance-like (99.6% of its direct dopamine input is PAM), while its
  behavioural label is approach (group-level; table above).
- MBON08 is already zero under the direct-connectivity rule, so under CIRCUIT-80
  the variant changes only MBON09. MBON08 is listed so the variant covers γ3 as a
  whole, whatever the threshold or future dopamine data.

The variant changes the **readout only**; the plasticity compartment map is
unchanged (MBON09's inputs remain PAM-plastic). It is reported next to the primary
result and never replaces it. A result that holds under CIRCUIT-80 but not under this
variant is reported as depending on MBON09. Its use in the first learning test is
preregistered in [`first-learning-test.md`](first-learning-test.md), Section 5b.
Tested in `tests/learning/test_readout.py`
(`test_gamma3_sensitivity_variant_zeroes_only_mbon08_and_mbon09`).

### Multi-compartment types and family assignment

| Type | Dendritic compartment(s) | Family assignment from the map | CIRCUIT result |
|---|---|---|---|
| MBON01 | γ5; anterior β′2a | PAM; PAM | avoidance-like |
| MBON02 | β2; anterior β′2a | PAM (PAM04); PAM (PAM01/02) | avoidance-like |
| MBON05 | γ4 | PAM | avoidance-like |
| MBON08 | γ3 | no direct annotated PAM/PPL1→MBON08 input | zero |
| MBON09 | γ3; β′1 | PAM; PAM | avoidance-like |
| MBON11 | γ1; distal pedunculus core | PPL1; PPL1 | approach-like |
| MBON12 | γ2; α′1 | PPL1; PPL1 | approach-like |
| MBON19 | posterior α2; posterior α3 | PPL1; PPL1 | approach-like |
| MBON21 | γ4; γ5 | PAM; PAM | avoidance-like |
| MBON03/MBON04 | β′2mp | PAM-dominant despite PPL107 input (99.9% / 88.7% PAM) | avoidance-like at 80%; historical any-connection rule was zero |

All family assignments in this section remain unverified at compartment level,
for the reasons stated below.

### Dominant-family threshold: adopted at 80%

The dominant-family rule is adopted at **X = 80%** before any learning results
exist. X = 70% and X = 90% are preregistered sensitivity checks. The original
CIRCUIT “any mapped connection from both families means zero weight” rule and
its results are retained below as history. The current rule assigns a sign only
when one family supplies at least X% of an MBON's annotated dopamine input; a
type with no direct annotated dopamine input remains zero. The threshold was
chosen on connectivity grounds: clean compartments show near-total dominance
(for example, MBON03 is 99.9% PAM and MBON09 is 99.6% PAM), and 80% separates
stray-synapse contamination from genuinely mixed input. It was **not** chosen
by maximizing agreement with behavioural labels.

The counts aggregate all v783 `Connectivity` entries from annotated PAM or
PPL1 root IDs onto each MBON type. They are direct dopamine→MBON synapses, not
a direct measurement of compartment identity. “PAM types (synapses)” and
“PPL1 types (synapses)” list every dopamine type with a nonzero total.

| MBON | PAM types (synapses) | PPL1 types (synapses) | PAM / PPL1 total | PAM / PPL1 share |
|---|---|---|---:|---|
| MBON01 | PAM01 306; PAM02 64; PAM03 1; PAM04 1; PAM06 3; PAM08 10; PAM12 2; PAM13 2; PAM15 8 | — | 397 / 0 | 100.0% / 0.0% |
| MBON02 | PAM02 11; PAM03 9; PAM04 399; PAM06 2; PAM09 6; PAM10 4 | — | 431 / 0 | 100.0% / 0.0% |
| MBON03 | PAM01 1; PAM02 70; PAM03 11; PAM05 333; PAM06 1,376; PAM08 16; PAM12 1; PAM13 1; PAM14 3; PAM15 6 | PPL107 2 | 1,818 / 2 | 99.9% / 0.1% |
| MBON04 | PAM03 3; PAM05 417; PAM06 380; PAM07 2; PAM08 182; PAM12 2; PAM15 3 | PPL101 2; PPL104 2; PPL107 122 | 989 / 126 | 88.7% / 11.3% |
| MBON05 | PAM01 11; PAM05 25; PAM07 428; PAM08 910; PAM12 73; PAM13 20; PAM14 1; PAM15 2 | PPL101 12; PPL102 1; PPL103 1; PPL108 1 | 1,470 / 15 | 99.0% / 1.0% |
| MBON06 | PAM04 10; PAM05 2; PAM06 3; PAM08 1; PAM09 132; PAM10 1,108; PAM11 63; PAM14 10 | PPL105 2; PPL106 17 | 1,329 / 19 | 98.6% / 1.4% |
| MBON07 | PAM09 26; PAM10 28; PAM11 1,498; PAM14 4 | PPL101 1; PPL105 4 | 1,556 / 5 | 99.7% / 0.3% |
| MBON08 | — | — | 0 / 0 | no direct annotated input |
| MBON09 | PAM02 2; PAM05 5; PAM07 2; PAM08 27; PAM12 486; PAM13 155; PAM14 210; PAM15 2 | PPL101 2; PPL103 2 | 889 / 4 | 99.6% / 0.4% |
| MBON10 | PAM02 1; PAM04 1; PAM05 35; PAM06 2; PAM13 60; PAM14 17 | PPL101 1; PPL102 2; PPL103 1; PPL107 16 | 116 / 20 | 85.3% / 14.7% |
| MBON11 | PAM04 7; PAM06 2; PAM07 8; PAM08 2; PAM09 3; PAM10 16; PAM11 22; PAM12 1 | PPL101 894; PPL102 51; PPL103 5; PPL105 1; PPL106 3 | 61 / 954 | 6.0% / 94.0% |
| MBON12 | PAM02 2; PAM05 2; PAM07 3; PAM13 1; PAM14 3 | PPL101 8; PPL103 449; PPL105 11; PPL107 3 | 11 / 471 | 2.3% / 97.7% |
| MBON13 | — | PPL103 5; PPL104 1; PPL105 286; PPL107 2 | 0 / 294 | 0.0% / 100.0% |
| MBON14 | PAM11 1 | PPL101 2; PPL104 1; PPL105 1; PPL106 465; PPL107 2 | 1 / 471 | 0.2% / 99.8% |
| MBON15 | PAM06 1; PAM08 1; PAM12 2; PAM13 2 | PPL103 31; PPL104 1; PPL105 3; PPL107 4 | 6 / 39 | 13.3% / 86.7% |
| MBON16 | — | PPL104 141 | 0 / 141 | 0.0% / 100.0% |
| MBON17 | — | PPL104 49 | 0 / 49 | 0.0% / 100.0% |
| MBON18 | — | PPL104 2; PPL105 133; PPL106 2 | 0 / 137 | 0.0% / 100.0% |
| MBON19 | — | PPL104 1; PPL105 26 | 0 / 27 | 0.0% / 100.0% |
| MBON21 | PAM01 35; PAM02 4; PAM05 6; PAM07 112; PAM08 183; PAM12 2; PAM15 8 | PPL102 2; PPL108 1 | 350 / 3 | 99.1% / 0.9% |

MBON03 and MBON04 are the β′2mp cases: the historical any-connection rule set
both to zero because PPL107 has direct input there. At 80%, both are
PAM/avoidance-like. MBON08 has no annotated direct PAM/PPL1→MBON edge in this
extraction and is therefore zero under the direct-connectivity rule. Its earlier
avoidance-like γ3 assignment arose by carrying MBON09's inferred γ3 PAM mapping
over to MBON08; that was inconsistent with the direct-connectivity rule and is
corrected here. MBON09 itself is 99.6% PAM by direct totals.

| X | Status / change relative to historical any-connection CIRCUIT rule | Coverage in the 33 responding instances | Four confident behavioural labels (MBON05, MBON21, MBON11, MBON12) |
|---:|---|---|---|
| 70% | Sensitivity check: MBON03 and MBON04 leave zero and become PAM/avoidance-like. No type reverses sign. | 28/33; 6/8 discriminators | All four still agree. |
| 80% | **Adopted primary:** same sign changes as 70%. | 28/33; 6/8 discriminators | All four still agree. |
| 90% | Sensitivity check: MBON03 leaves zero and becomes PAM/avoidance-like. MBON04 remains zero (88.7% PAM). MBON10 leaves PAM/avoidance-like and becomes zero (85.3% PAM). Outside the responding set, MBON15 likewise changes from PPL1/approach-like to zero (86.7% PPL1). | 21/33; 5/8 discriminators | All four still agree. |

The historical any-connection rule used 26/33 responding instances and 4/8
discriminators. It remains recorded as history, not the primary analysis.

## Compartment-matched plasticity

The intended constraint is: a dopamine-neuron type may change only KC→MBON
weights belonging to the mushroom-body compartment(s) it innervates. In
particular, a dopamine signal is not a licence to alter all KC→MBON weights.

The v783 annotation table identifies root IDs and cell types (for example,
PAM06 or PPL101), but contains no compartment column. The map below was
therefore inferred from direct dopamine-neuron→MBON synapses in
`Connectivity_783.parquet`, aggregating synapse counts by annotated dopamine
and MBON type, then assigning the MBON's dendritic compartment from
`mbon-valence.md` where that label is available. This is a useful wiring-based
proxy, **not a direct compartment annotation; every compartment assignment in
this table is unverified.** Rows marked “ambiguous” have no single dominant
table-covered compartment. “Not in table” means that the MBON label has no
entry in the supplied 22-type valence table, not that it is absent from v783.

PAM is shown as the conventional reward family and PPL1 as the conventional
punishment family. That family-level shorthand should not be treated as a
proof of the reinforcement sign of every subtype in every assay (**unverified
at subtype level**).

| Dopamine type | Family | Inferred compartment(s), from its strongest direct MBON partners | MBONs in those compartment(s) and table valence |
|---|---|---|---|
| PAM01 | reward | γ5/anterior β′2a | MBON01 — avoidance, group-only |
| PAM02 | reward | β′2mp; γ5/anterior β′2a | MBON03 — avoidance, group-only; MBON01 — avoidance, group-only |
| PAM03 | reward | ambiguous | MBON03 — avoidance, group-only; MBON02 — conflicted; MBON24 — not in table |
| PAM04 | reward | β2/anterior β′2a | MBON02 — conflicted; MBON24 — not in table |
| PAM05 | reward | β′2mp | MBON03/MBON04 — avoidance, group-only; MBON26 — not in table |
| PAM06 | reward | β′2mp | MBON03/MBON04 — avoidance, group-only |
| PAM07 | reward | γ4 (also γ5 through MBON21) | MBON05 — avoidance; MBON21 — avoidance |
| PAM08 | reward | γ4 (also γ5 through MBON21) | MBON05 — avoidance; MBON21 — avoidance; weaker MBON04 link makes β′2mp an unverified secondary assignment |
| PAM09 | reward | β1 | MBON06 — unverified individually; weaker MBON07/MBON24 links are ambiguous |
| PAM10 | reward | β1 | MBON06 — unverified individually |
| PAM11 | reward | α1 | MBON07 — no significant effect |
| PAM12 | reward | γ3/β′1 | MBON09 — approach, group-only |
| PAM13 | reward | γ3/β′1 and β′1 | MBON09 — approach, group-only; MBON10 — no significant effect |
| PAM14 | reward | γ3/β′1 | MBON09 — approach, group-only |
| PAM15 | reward | ambiguous | MBON26, MBON01, MBON21, MBON03/04 have similarly small totals; no compartment assignment is reliable |
| PPL101 | punishment | γ1/distal pedunculus core | MBON11 — approach |
| PPL102 | punishment | γ1/distal pedunculus core (weak/ambiguous) | MBON11 — approach; other leading partners are not in the table |
| PPL103 | punishment | γ2/α′1 | MBON12 — approach; several co-leading partners are not in table |
| PPL104 | punishment | α′3 | MBON16/MBON17 — approach, group-only |
| PPL105 | punishment | α′2; α2; posterior α2/α3 | MBON13 — no significant effect; MBON18/MBON19 — approach, group-only; MBON23 — not in table |
| PPL106 | punishment | α3 | MBON14 — no significant effect in tested lines; individual result not fully isolated |
| PPL107 | punishment | β′2mp | MBON04 — avoidance, group-only; secondary partners do not establish a clean assignment |
| PPL108 | punishment | ambiguous | MBON35 — not in table |

For implementation, the safe operational form is a sparse mask keyed by
(dopamine type, MBON type), created from this table, with all unlisted pairs
fixed at zero plasticity. The ambiguous rows should remain disabled or require
an explicit modelling choice; the map must not silently turn them into
whole-network updates.

## Reproducibility notes

The annotation source is
`third_party/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv`
(v3.1.0 in this repository). The connectivity source is
`third_party/Drosophila_brain_model/Connectivity_783.parquet`. The direct-edge
aggregation found 15,219 synapses across 1,990 annotated PAM/PPL1→MBON edges.
It was used only to rank partners; it does not by itself prove co-compartment
innervation. The valence wording is copied from `mbon-valence.md`; its three
specified key claims still require the stated original-paper spot checks.
