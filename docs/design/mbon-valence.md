# Drosophila MBON activation-valence table

**Compilation note.** This table was compiled with an AI research assistant. Before any use, spot-check these three key claims against the original papers: MBON11 approach (Aso et al. 2014b, eLife 3:e04580, Fig. 2C); MBON21 avoidance (Rubin & Aso 2023, eLife RP90523, Fig. 3H–I); MBON02 attraction (Mohammad et al. 2024, PLOS Biology).

## Scope and interpretation

Aso et al. described 21 MBON types innervating the mushroom-body lobes, plus MBON-calyx, yielding the 22 entries below. The part of an Aso name before ">" denotes dendritic compartments; the part after ">" denotes axonal targets.

"Valence" here means the acute behral response to experimentally activating an MBON in otherwise untrained flies. It does not mean:
- The valence of memories formed in that compartment.
- Whether the neuron is necessary for learned behavior.
- A universal effect across every assay, internal state, or stimulation intensity.

"No significant effect" means that Aso et al. did not detect a statistically significant preference in their quadrant assay. It should not be interpreted as proof that the neuron is behaviorally neutral.

Aso's numbered names use hyphens, such as MBON-11. Hemibrain and FlyWire annotations normally omit the hyphen, giving MBON11. These are cell-type mappings, not FlyWire root IDs; root IDs and annotations should be pinned to a specific release before analysis. Aso's Table 1 (https://elifesciences.org/articles/04580/figures) establishes the numbering, while Li et al. 2020 (https://elifesciences.org/articles/62576) and the FlyWire annotation repository (https://github.com/flyconnectome/flywire_annotations) document the modern label convention.

### Source abbreviations
- A14a: Aso et al. 2014 anatomy paper, especially Table 1 and Figure 3.
- A14b: Aso et al. 2014 valence paper: Table 1 for names/transmitters, Table 2 for driver expression, and Figure 2C for activation valence.
- O15: Owald et al. 2015, especially Figure 5E.
- L20: Li et al. 2020, especially Figures 7, 8 and 17.
- R23: Rubin and Aso 2023, especially Figure 3H–I.
- M24: Mohammad et al. 2024, especially Figure 7 and Supplementary Figure 8.

## Table

| Aso MBON type | FlyWire label | Dendritic compartment(s) | Neurotransmitter | Activation valence | Cell-type resolution and later findings | Sources |
|---|---|---|---|---|---|---|
| MBON-γ5β′2a | MBON01 | γ5 and anterior β′2 | Glutamate | Avoidance, group-only | Aso's significant MB011B line also contained MBON03 and MBON04. Smaller subsets had weaker or nonsignificant effects. Owald's M4/6 activation also caused avoidance but did not isolate MBON01 from all other M4/6 types. Individual activation valenfied. | A14a Table 1; A14b Fig. 2C, Table 2; O15 Fig. 5E |
| MBON-β2β′2a | MBON02 | β2 and anterior β′2 | Glutamate | Conflicted | Aso's selective MB399B line produced no significant effect. Owald activated MBON01+02+03 together and found avoidance. Mohammad et al. later reported attraction with MB399C/MBON02, ΔPI approximately +0.25. Thus this type should not receive a stable avoidance label. | A14b Fig. 2C, Table 2; O15 Fig. 5E; M24 Suppl. Fig. 8 and accompanying text |
| MBON-β′2mp | MBON03 | Middle/posterior layers of β′2 | Glutamate | Avoidance, group-only | Significant in Aso's MB011B combination with MBON01 and MBON04. Owald's avoiding lines contained MBON03 with MBON01, or with MBON01+02. Individual activation valence: unverified. | A14b Fig. 2C, Table 2; O15 Fig. 5E |
| MBON-β′2mp_bilateral | MBON04 | Middle/posterior β′2, bilateral arborization | Glutamate | Avoidance, group-only | Present in the significant MB011B three-type combination. Drivers containing smaller subsets didividual effect. Individual activation valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-γ4>γ1γ2 | MBON05 | Dendrites in γ4; axons terminate in γ1/γ2 | Glutamate | Avoidance | MB298B isolated this type sufficiently for Aso to assign a significant repulsive effect. The MBON05+06 combination also caused avoidance. | A14b Fig. 2C, Table 2 |
| MBON-β1>α | MBON06 | Dendrites in β1; axons innervate α lobe | Glutamate | Unverified individually | MB434B, activating MBON05+06, caused avoidance. MB433B, predominantly labeling MBON06 with weak MBON05 expression, was not significant. Therefore avoidance cannot be assigned confidently to MBON06 alone. | A14b Fig. 2C, Table 2 |
| MBON-α1 | MBON07 | α1 | Glutamate | No significant effect | Tested with the single-type MB310C line; no significant preference was detected in Aso's assay. | A14b Fig. 2C, Table 2 |
| MBON-γ3 | MBON08 | γ3 | GABA | Approach, group-only | MBON08 and MBON09 were always co-labeled by the tested split-GAL4 lines; both MB083C and MB1pproach. Individual contributions are unverified. MBON08 was absent from the hemibrain volume examined by Li et al., so its identity should be checked carefully in the selected FlyWire release. | A14b Fig. 2C, Table 2; L20 Fig. 7 |
| MBON-γ3β′1 | MBON09 | γ3 and β′1 | GABA | Approach, group-only | Co-activated with MBON08 in two significant approach-producing lines. Individual contribution: unverified. | A14b Fig. 2C, Table 2 |
| MBON-β′1 | MBON10 | β′1, plus substantial dendrites outside the lobes | GABA | No significant effect | The MB057B line did not produce significant approach or avoidance. Li et al. subsequently classified MBON10 as an "atypical MBON" because much of its dendritic arbor lies outside the lobes. | A14b Fig. 2C, Table 2; L20 Fig. 8 |
| MBON-γ1pedc>α/β | MBON11 | γ1 and distal pedunculus core; axons innervate α/β lobes | GABA | Approach | Aso's MB112C single-type driver produced significant attraction. Later work supports its characterization as an approach-promoting ontradiction identified. | A14b Figs. 2C and 6, Table 2 |
| MBON-γ2α′1 | MBON12 | γ2 and α′1 | Acetylcholine | Approach | Significant attraction was produced by MB077B, which labels MBON12 alone. Mixed MBON12/13 lines gave weaker or variable effects. | A14b Fig. 2C, Table 2 |
| MBON-α′2 | MBON13 | α′2 | Acetylcholine | No significant effect | The MB018B single-type driver did not produce significant approach or avoidance. | A14b Fig. 2C, Table 2 |
| MBON-α3 | MBON14 | α3 | Acetylcholine | No significant effect in tested lines; individual result not fully isolated | MB082C and MB093C contained MBON14 plus MBON13 expression and were not significant in the activation screen. Because the tested lines were not completely selective, a clean single-type activation result remains unverified. | A14b Fig. 2C, Table 2 |
| MBON-α′1 | MBON15 | α′1 | Acetylcholine | Approach only in a multi-type combination | The five-type MB052B V2-cluster line produced strong approach; smaller combinations containnificant or much weaker. Individual valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-α′3ap | MBON16 | Anterior/posterior layers of α′3 | Acetylcholine | Approach only in a multi-type combination | Included strongly in MB052B. Smaller combinations such as MB027B and MB549C were not significant. Individual valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-α′3m | MBON17 | Middle layer of α′3 | Acetylcholine | Approach only in a multi-type combination | Weak/stochastic expression in the significant MB052B combination; smaller subsets were not significant. Individual valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-α2sc | MBON18 | Surface/core layers of α2 | Acetylcholine | Approach only in a multi-type combination | Included strongly in MB052B, but MB050B and MB549C subsets were not significant. Individual valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-α2p3p | MBON19 | Posterior α2 and posterior α3 | Acetylcholine | Approach only in a multi-type combination | Weak/stochastihe significant MB052B combination. MB542B, containing MBON19 with a smaller subset, was not significant. Individual valence: unverified. | A14b Fig. 2C, Table 2 |
| MBON-γ1γ2 | MBON20 | γ1 and γ2, plus dendrites outside the lobes | Predicted GABA; Aso reported N.D. | Not tested individually | Excluded from Aso's Figure 2 screen. Mohammad et al. found avoidance when MBON20 and MBON21 were co-activated with VT999036, but MBON21 alone is sufficient for avoidance. Therefore MBON20's individual valence remains unverified. Li et al. reclassified it as an atypical MBON. | A14b Table 1/Fig. 2; L20 Figs. 8 and 17; M24 Fig. 7 |
| MBON-γ4γ5 | MBON21 | γ4 and γ5 | Acetylcholine | Avoidance | Not tested in Aso's original screen. Rubin and Aso later used two independent MBON21 lines and found avoidance of illuminated quadrants during CsChrimson activation. This is an important exception to the "cholinergic MBONs are attractive" pattern. | A14b Table 1/Fig. 2; R23 Fig. 3H–I |
| MBON-calyx | MBON22 | Main calyx | acetylcholine; Aso reported N.D. | No significant effect | MB242A labels MBON-calyx alone and produced no significant acute preference in Aso's assay. The acetylcholine assignment is a later connectomic prediction, not the experimentally determined transmitter reported in 2014. | A14b Fig. 2C, Tables 1–2; L20 Figs. 7 and 17 |

## Types that cannot presently be labeled confidently

The following should not be given a single-cell valence sign in the Flyshi readout without an explicit modeling assumption:
- MBON01, MBON03 and MBON04: avoidance was demonstrated only for overlapping multi-type combinations.
- MBON02: results are assay-dependent and conflicting — no significant effect in Aso 2014, avoidance in a broader M4/6 group in Owald 2015, and attraction with an MBON02 driver in Mohammad 2024.
- MBON06: MBON05+06 activation was aversive, but the predominantly MBON06 driver was not significant.
- MBON08 and MBON09: always co-labeled in Aso's activation experiments.
- MBON14: α3-containing drivers were gnificant, but clean single-type activation was not demonstrated in the primary screen.
- MBON15–MBON19: strong approach occurred only when the V2-cluster types were activated together.
- MBON20: MBON20+21 activation caused avoidance, but MBON21 alone is already aversive.
- MBON20 and MBON22 neurotransmitters: later connectomic assignments are predictions; Aso 2014 listed these as not determined.

For a conservative computational readout, these types should either be excluded, assigned zero weight, or represented by interval/uncertainty parameters rather than being forced into positive and negative categories.

## Neurotransmitter pattern and exceptions

Aso et al. found a strong association in their original significant results:
- Glutamatergic activation was associated with avoidance.
- GABAergic or cholinergic activation was associated with approach.

This was an empirical pattern, not a biological law. Important qualifications include:
- Several glutamatergic types produced no significant effect.
- Seral cholinergic or GABAergic types produced no significant effect or were only effective in combinations.
- Cholinergic MBON21 drives avoidance in later single-type experiments.
- The later MBON02 attraction result is inconsistent with a simple "glutamate equals avoidance" rule.
- Glutamate can be excitatory or inhibitory depending on the receptors expressed by downstream cells.

Consequently, transmitter identity should not itself determine the sign of an MBON's decision-readout weight.

## Why MBON-γ1pedc>α/β can be approach-promoting in an aversive-learning compartment

There is no contradiction between these two observations:
1. Directly activating MBON11 causes approach.
2. The γ1/pedc compartment receives punishment-related dopamine and is required in aversive learning.

The dopaminergic neuron PPL1-γ1pedc supplies an aversive teaching signal. During conditioning, dopamine paired with odor-responsive Kenyon-cell activity is proposed to depress the odor-specific KC→MBON11 connection. This subseqreduces activity in an approach-promoting MBON when the punished odor is encountered. Avoidance therefore results from the learned loss of an approach signal — and from the changed balance among multiple MBON outputs — not because MBON11 activation is intrinsically aversive. Aso et al. demonstrate MBON11's attractive activation effect in Figure 2C and the punishment role of PPL1-γ1pedc in Figure 6G–H.

## Full references

1. Aso Y, Hattori D, Yu Y, et al. The neuronal architecture of the mushroom body provides a logic for associative learning. eLife. 2014;3:e04577. https://doi.org/10.7554/eLife.04577
2. Aso Y, Sitaraman D, Ichinose T, et al. Mushroom body output neurons encode valence and guide memory-based action selection in Drosophila. eLife. 2014;3:e04580. https://doi.org/10.7554/eLife.04580
3. Owald D, Felsenberg J, Talbot CB, Das G, Perisse E, Huetteroth W, Waddell S. Activity of defined mushroom body output neurons underlies learned olfactory behavior in Drosophila. Neuron. 2015;86(2):417–42//doi.org/10.1016/j.neuron.2015.03.025
4. Li F, Lindsey JW, Marin EC, et al. The connectome of the adult Drosophila mushroom body provides insights into function. eLife. 2020;9:e62576. https://doi.org/10.7554/eLife.62576
5. Rubin GM, Aso Y. New genetic tools for mushroom body output neurons in Drosophila. eLife. 2023;13:RP90523. https://doi.org/10.7554/eLife.90523
6. Mohammad F, Mai Y, Ho J, et al. Dopamine neurons that inform Drosophila olfactory memory have distinct, acute functions driving attraction and aversion. PLOS Biology. 2024;22(11):e3002843. https://doi.org/10.1371/journal.pbio.3002843
7. Schlegel P, Yin Y, Bates AS, et al. Whole-brain annotation and multi-connectome cell typing of Drosophila. Nature. 2024;634:139–152. https://doi.org/10.1038/s41586-024-07686-5
