# Open decisions requiring project-owner sign-off

**Status:** decision brief, written 2026-09-22. **All four items were RESOLVED
by the project owner on 2026-09-22**; each section ends with the recorded
decision and rationale. The analysis above each decision is kept unchanged as
the record of what was weighed. The brief originally consolidated four
unresolved items from
[`docs/preregistration.md`](../preregistration.md), Sections 11–12, against the
current code. Resource estimates and biological interpretations explicitly
marked **unverified** have not been checked by a real connectome generation or
simulation.

## 1. Degree-preserving shuffle scope

The implemented shuffle exchanges the targets of two directed edges while
leaving their sources, signs, and synapse counts on their original rows. It
preserves every neuron's row-count in-degree and out-degree exactly, but destroys
specific partners, motifs, paths, target-specific weighted input, and signed
input balance inside the selected scope. The two available scopes answer
different questions.

### Option A — mushroom-body-only

Only rows whose **two endpoints** belong to a frozen mushroom-body neuron list
are eligible. Boundary edges between an MB neuron and a neuron outside that list,
and all other central-brain edges, remain unchanged.

What it isolates:

- whether the particular internal mushroom-body wiring—especially the local
  organization connecting KCs, MBONs, dopamine neurons, and other declared MB
  neurons—is needed for learning and readout;
- while retaining the native surrounding network, boundary connections, and
  broad dynamical operating point.

What it does not isolate:

- it is a weaker null for the claim that the *whole fly connectome* matters;
- any useful structure carried by unchanged MB boundary edges or the rest of the
  brain remains available;
- the result depends on the membership definition. At minimum that definition
  must explicitly address KCs, MBONs, PAM neurons, PPL1 neurons, and APL. It must
  be frozen as a root-ID file before generation, rather than adjusted after a
  result.

Resource cost in the current implementation:

- The entire connectivity parquet is still loaded, copied, validated, indexed,
  and written. The Python set used to reject duplicate edges also contains the
  whole network. Peak memory and output-file size are therefore approximately
  the same as for the whole-network scope: **8.9 GiB estimated peak and 17.9 GiB
  recommended RAM**, both **unverified** planning figures for 15 million rows.
- The swap loop requests ten accepted swaps per **eligible MB-internal edge**, so
  it should take less CPU time than the whole-network shuffle in proportion to
  the smaller eligible edge set. The eligible count and runtime are **unverified**
  until the frozen membership and real table are inspected on the server.
- Subsequent Brian2 simulations still instantiate the full network, so their
  memory and runtime are not reduced by choosing this scope.

### Option B — whole-network

Every connectivity row is eligible.

What it isolates:

- the broadest null: whether performance requires the fly's particular global
  partner structure, rather than merely the same neurons, row-degree sequence,
  and source-attached weight/sign material.

What makes it less diagnostic:

- it can destroy generic propagation, recurrent dynamics, sensory pathways, and
  downstream structure before the mushroom-body computation is evaluated;
- therefore, poor performance would not specifically show that KC→MBON or other
  mushroom-body organization matters. It could simply show that the globally
  shuffled network no longer occupies a usable dynamical regime.

Resource cost in the current implementation:

- The same **8.9 GiB estimated peak / 17.9 GiB recommended RAM** applies, and the
  full shuffled parquet has the same scale as the input. These figures remain
  **unverified**.
- Ten accepted swaps are requested for each of the roughly 15 million planning
  rows: approximately 150 million accepted swaps, plus rejected attempts, in a
  Python loop. Runtime is **unverified** and may be substantial. This is expected
  to be much slower than an MB-only swap, although both pay the same full-table
  read, memory, validation, and write costs.
- Subsequent simulation size and nominal per-run cost are again unchanged.

### Recommendation

Use **mushroom-body-only as the primary structural control**, with a membership
file frozen before generation, because the intervention then targets the circuit
whose learning rule and readout are under study while preserving a functioning
surrounding network. This gives a more interpretable causal comparison: a loss
of learning is more plausibly attributable to destroyed MB organization.

If server time permits, use the whole-network shuffle as a secondary stress-test,
not as the sole structural control. It answers a broader question, but a negative
result is too easily explained by global network disruption. For the MB list, the
recommended starting definition is all annotated KCs, MBONs, PAM/PPL1 dopamine
neurons, and APL, plus any additional class included by a written annotation rule;
the exact membership still requires approval.

**RESOLVED 2026-09-22 (project owner): `mushroom-body` is the PRIMARY shuffle
scope.** The proposed membership is approved: all annotated **KCs + MBONs + PAM +
PPL1 + APL**, with any additional class admitted only by the written annotation
rule, which must be frozen (together with the resulting root-ID file) before the
shuffled connectome is generated and never adjusted after a result.
**Whole-network shuffle is optional and exploratory, not preregistered**; if run,
it is reported as exploratory and cannot change a preregistered verdict.

*Rationale:* market input enters directly at the Kenyon cells, bypassing the
antennal lobe, so the question the control must answer is whether the mushroom
body's specific wiring matters, not whether the whole brain's does.

*Done 2026-09-22:* the rule is frozen as code
(`src/flyshi_research/controls/mb_membership.py`) and the membership file was
generated from the pinned annotation release:
`repro/connectome/mb_membership_783.json`, sha256
`b05b5c23ef19e0be6dbb1b574d774f01f07b3a9fd8b7b3b31f0a473cc820446f`. Counts match
the counts already observed for v783 — 5,177 KCs, 96 MBONs, 307 PAM, 16 PPL1,
2 APL, 5,598 root IDs in total, no overlap between classes. The generator keeps
`--scope` as a required argument with no default, so every run states its scope
explicitly. The shuffle itself has not been generated.

## 2. MBON instances included in the per-type mean

The ambiguity is in [`mb-learning-interface.md`](mb-learning-interface.md),
Section 4b and its open-items list, and is repeated in the preregistration. The
readout code itself does not select a hemisphere:
`learning/readout.py::circuit_score` averages exactly the labels and rates the
caller supplies. The real backend currently supplies **all 96 annotated MBON
instances from both hemispheres**, without filtering. The historical graded
test and first-learning-test specification also use all instances in both
hemispheres, including silent instances as zero. Thus bilateral inclusion is the
effective current behavior, but it has not been recorded as the final study
decision.

The concrete primary options are:

1. **Both hemispheres, all instances (current effective behavior).** For each
   MBON type, average every annotated left and right instance, including silent
   instances, then give the type one signed vote. This measures the output of the
   complete modeled circuit and retains cross-hemisphere propagation. It is also
   continuous with every circuit diagnostic completed so far. Its cost is that a
   strong ipsilateral response can be diluted by silent contralateral instances,
   and types with unequal left/right instance counts implicitly weight the side
   with more instances more heavily inside the type mean.
2. **Stimulated hemisphere only (left).** Average only left-side instances,
   because the encoder stimulates left KCs. This makes the readout more local to
   the injected circuit and avoids dilution by contralateral neurons. It discards
   real right-side activity produced by the full network, changes the score scale
   and decision-margin calibration, and breaks direct continuity with the
   completed diagnostics unless those analyses are recomputed.

A useful sensitivity analysis is to keep bilateral inclusion as primary and
recompute scores from left-only MBONs. This is analysis-only once full per-MBON
outputs are saved, but the left-only decision margin must be calibrated
separately on training data because its units differ. The current real backend
exposes MBON IDs and type labels but not a parallel side mask through the shared
simulator interface, so the frozen annotation-derived left/right mask and its
metadata would need to be added before that sensitivity analysis is run.

### Recommendation

Use **all instances in both hemispheres as the primary readout**, with silent
instances included, and pre-state **left-only as a sensitivity analysis**. The
model is a connected bilateral network, right MBONs demonstrably respond to left
KC input, and the existing diagnostics already use all 96 instances. Excluding
the right side would remove a modeled circuit response after it has propagated,
rather than isolate the input. The left-only sensitivity check will show whether
the conclusion depends on that choice.

*(Naming note added 2026-09-22 with the decision, so the pre-decision text above
is not misread: "left-only" is a **post-hoc rescoring**, never an arm or a
condition. It is exact in the first learning test, whose teaching signal comes
from the condition and not the readout; in the closed-loop synthetic market it
rescores the runs as they actually happened and cannot show what a left-only
system would have done. See the RESOLVED block below.)*

**RESOLVED 2026-09-22 (project owner): all 96 MBON instances, both hemispheres,
silent instances included at 0 Hz, is the PRIMARY instance set.
Left-hemisphere-only is a preregistered POST-HOC RESCORING** — never an arm, a
condition or a separate experiment (reported, never gating; its decision margin
would have to be calibrated separately on training data because its units differ).
What it can show differs by experiment: in the **first learning test it is exact**
— the teaching signal comes from the condition, not the readout, so a left-only
system would have run identical simulations and the rescoring coincides with what
it would have done; in the **synthetic market it is not**, because that loop is
closed (score → action → teaching), so it rescores the runs as they actually
happened, does not replay the decision loop, and cannot show what a left-only
system would have done.

*Rationale:* right-side MBONs respond to left-side KC input (e.g. a right
MBON03 instance fired at ~80 Hz in an existing set-A run), so excluding them
would discard real circuit output after it has propagated.

*Done 2026-09-22:* the side labels are frozen in
`src/flyshi_research/learning/data/mbon_sides_783.json` (96 instances, 48 left and
48 right, from the pinned annotation release), and both runners save per-MBON
rates with the MBON root IDs, so the left-only score is rescored after a run with
no extra simulation — exact in the first learning test, not exact in the
closed-loop synthetic market. No left-only training arm exists or is planned.

## 3. Reward normalization and accuracy-arm `brier_scale`

The implemented accuracy reward is

```text
raw improvement = Brier(market price, outcome) - Brier(circuit forecast, outcome)
normalised reward = clip(raw improvement / brier_scale, -1, 1).
```

The current `brier_scale = 0.25` is explicitly a placeholder. With the documented
example—market price 0.60, circuit forecast 0.62, outcome YES—the raw improvement
is 0.0156, so the current normalized reward is only 0.0624.

For comparison, in the synthetic configuration a winning YES position bought at
0.60 has gross profit 0.40 and net profit 0.38 after the placeholder 0.01 fee and
0.01 half-spread. With `profit_scale = 1.0`, its profit reward is 0.38. Calling
either example “typical” is **unverified**; the actual training-market
distribution must be reported.

Concrete alternatives:

| `brier_scale` | Reward for improvement 0.0156 | Rationale and tradeoff |
|---:|---:|---|
| **0.10** | **0.156** | Conservative amplification. It strengthens small accuracy edges by 2.5× relative to the placeholder while leaving more headroom before clipping. It will usually make accuracy teaching weaker than the example profit reward. |
| **0.04** | **0.390** | Direct example-matching choice: the documented two-point edge produces nearly the same magnitude as the example net profit reward (0.38). It makes the two reward arms comparable in this concrete case, but that case is not yet known to represent the training distribution. |
| **0.025** | **0.624** | Aggressive accuracy teaching. It gives small edges strong influence but clips whenever `|Brier improvement| ≥ 0.025`, potentially erasing distinctions among moderately large gains and losses. |

Whichever value is selected, it must be frozen before the preregistered run and
not selected from held-out outcomes. A defensible training-only check is to report
the distribution of absolute Brier improvements and the resulting clipping rate
under each already-proposed value; that describes the consequence of the choice
without changing the success criterion. The current symmetric clipping to
`[-1,1]` and `dead_zone = 0` should also be explicitly confirmed or changed at
the same sign-off.

**RESOLVED 2026-09-22 (project owner): `brier_scale = 0.04`, symmetric clipping
to `[-1, 1]`, `dead_zone = 0`.** These are now the defaults in
`learning/params.py` and are frozen for the preregistered runs.

*Rationale:* with 0.04 the documented two-point edge (improvement 0.0156) gives a
normalized accuracy reward of 0.39, matching the example net profit reward (0.38)
under `profit_scale = 1.0`. The profit-vs-accuracy comparison therefore tests the
*type* of teaching signal rather than a difference in reward size.

*Caveats kept:* that the example is typical of the training distribution remains
**unverified**; the training-only report of absolute Brier improvements and the
resulting clipping rate at 0.04 is still to be produced and is descriptive only,
it cannot change the value. The size match assumes `profit_scale = 1.0`, which
is still a placeholder; changing it would break the match.

## 4. Drift-pace unit

The code in `learning/plasticity.py` applies drift as

```text
W_after = W0 + (1 - drift_rate)^n_steps × (W_before - W0).
```

With the current placeholders, `drift_rate = 0.01` and
`drift_steps_per_resolution = 1`. After an acted-on market resolves, the code
first applies any dopamine-gated weakening and then closes **1% of every
weight's remaining gap back to its original connectome value**. An acted-on
resolution with no teaching signal still advances drift. An abstained market's
resolution applies neither learning nor drift. `advance(n_steps)` exists for
explicit time passage, but the current experiment runners do not use it as a
calendar clock.

Physically, one current “step” therefore means **one acted-on market resolution**,
not one hour, day, simulation second, or unit of biological time. Ten markets
resolving together cause ten successive drift steps; one market resolving after
a month causes one. With no further learning, the remaining deviation is
`0.99^N` after `N` acted resolutions—about one half after 69 resolutions and 37%
after 100. The pace also depends on abstention rate, because abstained resolutions
do not advance it.

This event-count clock is well-defined for the controlled first-learning and
synthetic-market experiments, where presentations/resolutions are the intended
experimental unit. It is not automatically comparable across historical or
prospective datasets with different market frequency, overlap, or time to
resolution. Before a real-market experiment it needs an explicit interpretation:

1. **Keep the current event clock:** one step per acted resolution. This treats
   forgetting as experience-dependent and requires no timestamp handling, but
   makes drift depend on market density and abstention.
2. **Use elapsed calendar time:** call `advance` according to a fixed unit such
   as one day and define/freeze the corresponding `drift_rate` or half-life.
   This gives comparable forgetting across datasets but requires reliable event
   timestamps and a newly justified time constant.
3. **Disable drift in the primary real-market analysis:** set `drift_rate = 0`
   and retain drift as a sensitivity condition. This removes an unanchored
   timescale but also removes the safeguard intended to restore weights and
   prevent long-run saturation.

### Recommendation

Keep **one step per acted resolution for the already-defined controlled
experiments**, where it is a clear exposure unit. Before the real historical or
prospective experiment, anchor drift to **elapsed calendar time** (preferably a
reported half-life, implemented through `advance`) or explicitly disable it;
do not silently carry the event-count rate across datasets with different event
density. The calendar unit and half-life must be fixed from biological rationale
or training-period behavior, never from held-out performance.

**RESOLVED 2026-09-22 (project owner): one drift step per acted-on resolution
for BOTH the controlled experiments and the real-market experiments**
(`drift_steps_per_resolution = 1`; `advance` is not used as a calendar clock).
**Drift disabled (`drift_rate = 0`) is a preregistered sensitivity check.**
The recommendation above to switch to a calendar-time clock for the real-market
phase was **not adopted**.

*Rationale:* one clock across phases lets parameters set in the synthetic phase
carry over unchanged. A calendar-time clock would introduce a half-life parameter
with no calibration.

*Consequence kept on record:* the effective forgetting rate still depends on
market density and abstention rate, so it is not comparable across datasets with
different event density. Both numbers must be reported alongside real-market
results. `drift_rate = 0.01` itself remains a placeholder.

*Where the drift-off check runs (decided 2026-09-22):* as its own training
condition, `profit_drift_off`, in the synthetic-market experiment — drift acts
inside the learning loop, so it cannot be recomputed from a run that had drift on.
That raises the selected synthetic plan from 15,000 runs in 75 jobs to **20,000
runs in 100 jobs**. It is deliberately **not** added to the first learning test,
whose 260-run plan is unchanged.
