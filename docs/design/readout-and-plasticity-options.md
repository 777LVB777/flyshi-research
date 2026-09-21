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
| **CIRCUIT (proposed primary)** | Give an MBON an avoidance-like sign when all mapped dendritic compartments are innervated by PAM (reward-family) dopamine types, and an approach-like sign when they are all innervated by PPL1 (punishment-family) types. Give zero weight to a type spanning both families or with no clear mapped compartment. This is a declared mushroom-body-circuit modelling assumption, not a behavioural measurement. | 26/33 | 4/8 (MBON02, MBON07×2, MBON11) | Its signs come from circuit logic and an inferred, unverified compartment map, and can disagree with activation-valence experiments. |
| **STRICT** | Individual, confidently labelled types only: MBON05 and MBON21 for avoidance; MBON11 and MBON12 for approach. | 5/33 (MBON05×1, MBON11×2, MBON12×2) | 1/8 (MBON11) | It is conservative about the literature, but discards almost all of the strongest cue difference. MBON21 did not respond in this result. |
| **GROUP** | STRICT plus an explicit modelling assumption: glutamatergic MBON01/03/04 are avoidance; MBON08/09 and MBON15–19 are approach. All other labels, including labels absent from the valence table, have zero weight. | 14/33 (STRICT's 5, plus MBON03×1, MBON04×1, MBON09×4, MBON16×1, MBON17×1, MBON18×1) | 3/8 (MBON03, MBON04, MBON11) | Uses more of the measured signal, but treats effects established only for co-activated groups as type-level signs. That is a declared modelling assumption, not an individual-cell experimental result. |

CIRCUIT is the proposed primary readout. STRICT and GROUP are preregistered
robustness checks. Any result that appears only under CIRCUIT must be reported
as such. MBON02 is excluded from STRICT and GROUP because the table calls its
activation valence conflicted. MBON07, MBON26, and MBON23 are also excluded
from those checks: MBON07 had no significant effect in the table; MBON26 and
MBON23 are not in that table.

### CIRCUIT assignment for responding MBONs

| Circuit assignment | Responding types (instance count) |
|---|---|
| Avoidance-like (PAM only) | MBON02×2, MBON05×1, MBON06×1, MBON07×2, MBON09×4, MBON10×6 |
| Approach-like (PPL1 only) | MBON11×2, MBON12×2, MBON13×1, MBON14×2, MBON16×1, MBON17×1, MBON18×1 |
| Zero: both families | MBON03×1, MBON04×1 (β′2mp has PAM and PPL107 assignments) |
| Zero: no clear mapped compartment | MBON24×1, MBON27×1, MBON32×1, MBON33×1, MBON35×1 |

### Validation against the activation-valence table

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
| MBON03 | avoidance, group-only | zero (PAM and PPL1 β′2mp) | **no** |
| MBON04 | avoidance, group-only | zero (PAM and PPL1 β′2mp) | **no** |
| MBON08 | approach, group-only | avoidance-like (PAM γ3; inferred through the γ3/β′1 MBON09 map) | **no** |
| MBON09 | approach, group-only | avoidance-like (PAM γ3/β′1) | **no** |
| MBON15 | approach, group-only | approach-like (PPL1 α′1) | yes |
| MBON16 | approach, group-only | approach-like (PPL1 α′3) | yes |
| MBON17 | approach, group-only | approach-like (PPL1 α′3) | yes |
| MBON18 | approach, group-only | approach-like (PPL1 α2) | yes |
| MBON19 | approach, group-only | approach-like (PPL1 posterior α2/α3) | yes |

The explicit disagreements are MBON03, MBON04, MBON08, and MBON09. They are
retained as validation failures of the declared CIRCUIT assumption; the rule is
not adjusted to remove them.

### Multi-compartment types and family assignment

| Type | Dendritic compartment(s) | Family assignment from the map | CIRCUIT result |
|---|---|---|---|
| MBON01 | γ5; anterior β′2a | PAM; PAM | avoidance-like |
| MBON02 | β2; anterior β′2a | PAM (PAM04); PAM (PAM01/02) | avoidance-like |
| MBON05 | γ4 | PAM | avoidance-like |
| MBON08 | γ3 | PAM, inferred through MBON09 | avoidance-like |
| MBON09 | γ3; β′1 | PAM; PAM | avoidance-like |
| MBON11 | γ1; distal pedunculus core | PPL1; PPL1 | approach-like |
| MBON12 | γ2; α′1 | PPL1; PPL1 | approach-like |
| MBON19 | posterior α2; posterior α3 | PPL1; PPL1 | approach-like |
| MBON21 | γ4; γ5 | PAM; PAM | avoidance-like |
| MBON03/MBON04 | β′2mp | PAM and PPL1 (PPL107) | zero |

All family assignments in this section remain unverified at compartment level,
for the reasons stated below.

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
