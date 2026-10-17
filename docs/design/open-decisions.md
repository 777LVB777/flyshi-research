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

**Update 2026-09-30:** two further decisions are recorded as items 5
(the remaining learning-rule and reward placeholders are locked) and 6 (the
Phase 2 market data source). Items 1–4 are unchanged.

**Update 2026-10-11:** item 6 is revised. Kalshi is blocked pending written
permission, and the Phase 2 venue is under review. See the dated revision at the
end of item 6.

**Update 2026-10-12:** item 6 is revised again. Polymarket is planned as the
primary venue under stated conditions, with Manifold as backup. This rests on a
human support reply that is not definitive. The verbatim support transcript and
an open Gamma-versus-CLOB conflict are recorded in the second dated revision at
the end of item 6. Later the same day, the owner resolved the conflict by
allowing CLOB `/prices-history` alongside Gamma (amendment at the end of
item 6).

**Update 2026-10-14:** Polymarket support answered the follow-up. Publication of
aggregate results and sharing market IDs with reviewers and editors are cleared.
CLOB `/prices-history` was not covered and a question about it is pending. See
the 2026-10-14 revision at the end of item 6.

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
is still a placeholder; changing it would break the match. *(2026-09-30:
`profit_scale = 1.0` is now decided, item 5, so the match is kept.)*

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
results. `drift_rate = 0.01` itself remains a placeholder. *(2026-09-30:
`drift_rate = 0.01` is now decided, item 5.)*

*Where the drift-off check runs (decided 2026-09-22):* as its own training
condition, `profit_drift_off`, in the synthetic-market experiment — drift acts
inside the learning loop, so it cannot be recomputed from a run that had drift on.
That raises the selected synthetic plan from 15,000 runs in 75 jobs to **20,000
runs in 100 jobs**. It is deliberately **not** added to the first learning test,
whose 260-run plan is unchanged.

## 5. Locking the learning-rule and reward placeholders

**DECIDED 2026-09-30 (project owner).** The following are fixed at the values
under which the first learning test returned **LEARNING DEMONSTRATED** (tag
`layer3-learning-demonstrated`, commit `1e1a9f7`). The values match that run's
saved configuration,
`repro/mushroom_body/results/first_learning_6fea97ac91/config.json`.

| parameter | value | was |
|---|---:|---|
| `profit_scale` | 1.0 | placeholder |
| `learning_rate` | 0.1 | placeholder |
| `floor_fraction` | 0.1 | placeholder |
| `drift_rate` | 0.01 | placeholder |

They are marked `decided` in `learning/params.py`. A test checks them against
that saved configuration.

*Rationale:*

- **No value is chosen after seeing market results.** Every value carries
  forward unchanged from the configuration where learning was shown, and no
  market experiment has been run.
- **The matched reward sizes are kept.** `profit_scale = 1.0` preserves the
  match behind `brier_scale = 0.04` (item 3): a two-point edge gives an accuracy
  reward of 0.39, against an example profit reward of 0.38.

*Kept on record:*

- **Drift disabled remains a preregistered sensitivity check.** `drift_rate = 0`
  is still run as the `profit_drift_off` condition of the synthetic-market
  experiment (item 4).
- **How far the first test constrains `profit_scale`.** That test delivered a
  profit of exactly ±1 stake (`reward_strength = 1.0`), so the normalised reward
  was ±1. Any `profit_scale` ≤ 1 would have given the same teaching signal. The
  test shows learning *at* 1.0; it does not discriminate among values at or
  below it.
- **Not tuned.** Learning was demonstrated at these values. They were not
  selected from alternatives, and no other values were run.
- **Still placeholders:** `kc_active_threshold_hz`, `kc_rate_ref_hz`,
  `dopamine_max_rate_hz`, `margin_threshold`, `pool_seed`, `pool_size` and the
  encoder rate bounds and feature ranges. None of them is decided here.

## 6. Phase 2 market data source

**DECIDED 2026-09-30 (project owner).**

- **Primary source:** **Kalshi**, via its official public REST API
  **historical endpoints**.
- **Planned second-venue replication:** **Polymarket**.

*Rationale:*

- **Regulation:** Kalshi is a U.S.-regulated exchange.
- **Ground truth:** its public history is free and includes settlement
  outcomes.
- **Prices:** prices are quoted in cents, which map directly to implied
  probability.
- **Independence:** using it requires no research partnership with a company,
  which avoids a conflict of interest.

*Known pitfall (must be handled by the loader):*

- **Where the data live.** The live endpoints hold only recent months of
  markets. Older markets are in the `/historical/` namespace.
- **What the loader must do.** It must read from the historical endpoints and
  check the archive cutoff explicitly.
- **What goes wrong otherwise.** A backtest would silently drop older markets.
  That would bias the market sample, with no error to show it.

*Open before any bulk download:*

- **Terms of use.** Kalshi's terms of use **have not yet been reviewed**. They
  must be reviewed before any bulk download.
- **API facts unverified.** The API details above (the endpoint split, the
  `/historical/` namespace, cent pricing) are recorded as stated by the project
  owner. They were not re-checked against Kalshi's API documentation when this
  was written.
- **Backtest details still open.** Date range, market-selection criteria, fee
  schedule and the Polymarket replication protocol are not yet specified.

> **REVISION 2026-10-11 (project owner): Kalshi blocked pending permission; venue
> under review.** The decision above is kept unchanged as the record. It no longer
> holds. **No Kalshi data may be downloaded, stored or used.** No Kalshi data was
> ever downloaded, and the Kalshi API was never called.
>
> *Finding.* The terms review that item 6 required before any bulk download was
> done on 2026-10-11. Kalshi's terms forbid what Phase 2 needs unless Kalshi
> gives written permission. That covers storing historical data, analysing it,
> using it with a learning model, publishing results and sharing data with
> reviewers.
>
> *Documents reviewed, retrieved 2026-10-11:*
>
> | document | source | version shown | SHA-256 of the file retrieved |
> |---|---|---|---|
> | Kalshi Developer Agreement | `https://assets.kalshi.com/Kalshi-Developer-Agreement.pdf`, linked from `kalshi.com/developer-agreement` | "v1.1", no date | `9d3e33685c0f0a88d23895685107975b0745283aac96f8bf7d202f5ae4dc1fa6` |
> | Kalshi Data Terms of Use | `https://kalshi-public-docs.s3.amazonaws.com/kalshi-data-terms-of-service.pdf`, linked from `kalshi.com/terms` | no date | `d19a0f94ffd65aa51eccb80cc8c9a06fb842478c5bf4cbd5a31ec51dd0a3966f` |
>
> Kalshi's API documentation says that using the API binds the user to the
> Developer Agreement. The two documents were not copied into the repository. The
> checksums identify the exact versions read. Clause summaries follow, with one
> short verbatim quote; the wording governs.
>
> *Developer Agreement:*
>
> - **§3 (preamble).** API use is limited to facilitating the member's own trading
>   on the exchange. Every other use is disallowed and can lead to suspension.
>   **This blocks the project:** a historical replay is not trading.
> - **§3.1.** Collecting, caching, aggregating or storing API data is prohibited
>   except to facilitate one's own trading. Sharing it with third parties in any
>   manner needs Kalshi's prior written authorization. **This blocks building the
>   dataset and blocks giving data to reviewers.**
> - **§4.1.1.** API users must be Kalshi Members, which means an exchange account
>   with identity checks. **Unclear** whether the project owner qualifies.
> - **§6.4.** Public statements, releases and disclosures relating to Kalshi or
>   its API need Kalshi's prior written approval. **This limits publication.**
>   How broadly Kalshi reads this clause is **unclear**.
>
> *Data Terms of Use* (all Kalshi Data: prices, volume, settlement prices, market
> descriptions):
>
> - **§I.** Access is for personal, non-commercial use only, and only in the form
>   presented on the website. Without prior written consent, non-commercial use
>   excludes developing software, including "training a machine learning or
>   artificial intelligence system", and excludes giving archived or cached data
>   sets to anyone else.
> - **§II.** Without prior written authorization this section prohibits:
>   - downloading, collecting and copying;
>   - compiling databases and systematic retrieval;
>   - text and data mining;
>   - publishing, distributing and creating derivative works;
>   - analysing the data;
>   - using scripts or bots.
>
>   A closing paragraph in bold prohibits any use of Kalshi Data in any manner for
>   machine learning or AI. **This blocks the project.** Whether a spiking circuit
>   with plasticity counts as machine learning is arguable. The design does not
>   rely on arguing that it does not.
> - **§III.** Kalshi claims all rights to the data. **This blocks redistributing
>   a dataset with the paper.**
>
> *Not settled:*
>
> - **Kalshi Research.** Kalshi Research (`kalshi.com/research`), reported as
>   launched in December 2025, says it collaborates with academics. No public data
>   access route or research licence was found.
> - **Third-party resellers.** Resellers of Kalshi data were not checked. Buying
>   from them does not obviously avoid the Data Terms.
> - **Member Agreement and Rulebook.** Not reviewed.
>
> *Decision (project owner, 2026-10-11):*
>
> - **Primary source:** *Kalshi blocked pending permission; venue under review.*
> - **Permission request.** A request to Kalshi Research is drafted as a document
>   only, in [`kalshi-permission-request-DRAFT.md`](kalshi-permission-request-DRAFT.md).
>   Nothing has been sent.
> - **Alternative venues.** Their terms, reviewed the same day, are in
>   [`phase2-design.md`](phase2-design.md), Section 1.
> - **Phase 2 design.** The design is now venue-neutral and DRAFT, in
>   [`phase2-design.md`](phase2-design.md).
> - **Budget.** The Phase 2 compute budget remains about $100. It is set in the
>   [`synthetic-market-experiment.md`](synthetic-market-experiment.md) Section 7
>   revision of 2026-10-11.

> **REVISION 2026-10-12 (project owner): Polymarket planned as primary, under
> conditions; Manifold backup.** The 2026-10-11 revision above is kept unchanged
> as the record. Kalshi remains blocked pending permission.
>
> *Polymarket support conversation.* The project owner asked Polymarket support,
> through the polymarket.com support chat, whether the planned research use is
> allowed. The conversation began at about 21:55 ET on 2026-10-11. The final
> substantive reply came at about 22:55 ET the same day. Both times are
> approximate.
>
> - The messages signed "Polybot (AI Agent)" or "Polybot" are from Polymarket's
>   AI support agent. Polybot gave no answer on the substance. It said it lacked
>   the relevant terms and handed the request to a human.
> - The final substantive reply is from "Roni", a human member of Polymarket
>   support, who joined after the handoff. Roni is a support agent, not
>   Polymarket's legal team. The reply reports what Polymarket's documentation
>   says. It does not grant a licence or permission.
>
> *What the human reply supports:*
>
> - the Gamma API is public, needs no authentication, and is intended for public,
>   read-only use, including non-profit research projects;
> - Roni found no stated restriction on bulk retrieval within rate limits, on
>   private storage for research, or on use with learning models. That holds as
>   long as access is read-only and unauthenticated, with no direct interaction
>   with the Polymarket platform or contracts.
>
> *What it does not settle:*
>
> - The reply says itself that it is **not a definitive written confirmation**
>   of compliance with Polymarket's terms of use for academic research.
> - It does not address attribution, publication of aggregate results, or
>   confidential sharing with peer reviewers. It says only that the
>   documentation specifies no requirements on them. According to the project
>   owner, a follow-up on these points has been sent. No answer has been recorded.
> - It speaks only about the **Gamma API**. It does not mention the CLOB API or
>   the Data API, and it does not address the Terms of Use §4 ban on
>   scrapers and data harvesting.
>
> *Transcript, verbatim* as supplied by the project owner (the typo
> "scrapyour" is in the original):
>
> ```text
> Hey, Welcome to Polymarket Support! 👋
> What brings you here today?
> — Polybot (AI Agent)
>
> Luca: Hi, I'm an undergraduate at the University of Pennsylvania doing a non-commercial computational neuroscience research project. I'd like written confirmation that a planned use of Polymarket's historical data is allowed under your terms.
> I would retrieve historical, already-resolved binary markets (metadata, price history, volume, outcomes) through your official public API, within rate limits, and replay them to a simulated fruit-fly brain model that includes a learning rule. No trading, no account, no money involved.
> Could you confirm whether: (1) bulk retrieval through the official API is permitted, as opposed to the scrapyour terms prohibit; (2) I may store the data privately for the research; (3) I may use it with a model that learns from it; (4) I may publish aggregate results crediting Polymarket; and (5) I may share market IDs or data confidentially with peer reviewers if a journal asks?
> If this needs to go to a different team, I'd be grateful if you could forward it. Thank you!
>
> Polybot (AI Agent): Thank you for sharing the details of your research! Let me look into the guidelines around data use for you.
>
> Polybot: To make sure I get you the right information, are you using the Polymarket website or the US app?
>
> Luca: The Polymarket website (polymarket.com) and its public data API, not the US app. I don't have an account on either and won't be trading. My question is only about using historical, already-resolved market data for academic research.
>
> Polybot (AI Agent): I don't have the specific terms for academic data usage and publication in my documentation. I can connect you with the team that handles these requests to get you a definitive answer.
> The team is handling a high volume right now so a human reply may take quite a while, and you can usually sort this out faster right here. Would you like me to pass this along to them?
>
> Luca: Yes, please pass it along.
>
> Polybot (AI Agent): Thanks for laying out your research use case so clearly. I'm going to hand this over to a human member of the support team so they can review and provide the written confirmation you're asking for.
>
> Polybot: Sure thing! Polymarket will reply as soon as they can.
>
> [Roni joined the conversation]
>
> Roni: Hi there! This is Roni. Thank you for bringing this to our attention. I acknowledge the inquiry regarding API.
> Please allow me a moment to look into this for you. Thanks!
>
> Luca: Sounds good
>
> Roni: Thank you for your patience while I investigate a solution for the API.
>
> The Gamma API is fully public, does not require authentication, and is intended for public, read-only use, including for non-profit research projects. There is no mention of restrictions on bulk retrieval within rate limits, private storage for research, or use with learning models, as long as the API is accessed in a read-only, unauthenticated manner and there is no direct interaction with the Polymarket platform or contracts.
>
> Our documentation does not specify requirements regarding attribution, publication of aggregate results, or confidential sharing with peer reviewers.
>
> However, the sources do not explicitly address the terms of use or licensing restrictions for academic research, nor do they provide definitive written confirmation for your specific use case.
>
> Therefore, while your described use case appears to align with the intended public, read-only use of the API, the provided documentation does not fully address all aspects of your query or provide a definitive written confirmation regarding compliance with Polymarket's terms of use for academic research.
> ```
>
> *Decision (project owner, 2026-10-12):*
>
> - **Primary source:** *Polymarket (Gamma API only, read-only, unauthenticated,
>   within rate limits, no platform or contract interaction, no public
>   redistribution of raw data) planned as primary; human support reply
>   2026-10-11 supports this use but is not definitive; publication and reviewer
>   sharing not addressed (follow-up sent); Manifold backup.*
> - **Kalshi.** Still blocked pending permission. The request draft remains
>   unsent.
> - **Conditions in the design.** The conditions are carried into
>   [`phase2-design.md`](phase2-design.md), Section 1.
> - **Downloads.** No Polymarket data has been downloaded.
>
> **Open conflict, needs the owner's decision before any download.** Polymarket's
> own API specifications, read on 2026-10-12, put the data the design needs
> on different APIs:
>
> - **Gamma** (`gamma-api.polymarket.com`) serves market and event metadata,
>   resolution status, and *current* snapshot fields. Those fields include
>   `outcomePrices`, `lastTradePrice`, `bestBid`/`bestAsk`, `volume` and
>   `liquidity`.
> - **The historical price time series** is served only by the **CLOB API**,
>   `GET clob.polymarket.com/prices-history`. That endpoint is marked
>   `security: []`, so it needs no authentication.
>
> Under "Gamma API only", `price` and `recent_change` at the decision time
> `t_d` therefore cannot be built. Liquidity at `t_d` cannot be built either,
> because Gamma's `liquidity` and `volume` are snapshots. The owner must choose
> one:
>
> - extend the condition to include read-only, unauthenticated CLOB
>   `/prices-history`, and ideally ask support to confirm that the reply also
>   covers it;
> - or restrict the design to data Gamma can supply.
>
> The specs read were `gamma-openapi.yaml`, SHA-256
> `0630db87b3fd91e908c16de674561f1466a3049867d56322bd2069132eb1a9dd`, and
> `clob-openapi.yaml`, SHA-256
> `d993169c2fd17cbc75304c9cd7bc3b6a351fa21f98cbd12dcd4c5dbbca2fedb8`. Both come
> from `docs.polymarket.com/api-spec/`. They are API documentation, not market
> data.
>
> **AMENDMENT 2026-10-12 (project owner): conflict resolved by option (i).** The
> decision and conflict above are kept unchanged as the record. They are
> superseded by this:
>
> - **Primary source:** *Polymarket (Gamma API plus CLOB `GET /prices-history`
>   only; read-only, unauthenticated, at a pre-set rate under the published
>   limit, with a request log; no platform or contract interaction; no public
>   redistribution of raw data) planned as primary. The CLOB endpoint is allowed
>   pending Polymarket's confirmation that the 2026-10-11 human support reply
>   also covers it. That reply supports the use but is not definitive.
>   Publication and reviewer sharing are not addressed. A follow-up was sent
>   2026-10-12 asking about the CLOB endpoint, publication and reviewer sharing.
>   Manifold backup.*
> - **If Polymarket says no to the CLOB endpoint,** it is dropped and option (ii)
>   applies: Polymarket cannot support the design, and Manifold becomes primary.
> - **Not allowed:** any other CLOB endpoint, including the POST
>   `/batch-prices-history`, and the Data API.
> - **Still open:** liquidity at `t_d` cannot be built from allowed data.
>   `/prices-history` gives prices only, and Gamma gives snapshots. See
>   [`phase2-design.md`](phase2-design.md), Section 1 and open decision 4.
> - **Downloads.** No Polymarket data has been downloaded.


> **DECISIONS 2026-10-12, later the same day (project owner): Phase 2 design
> choices.** Everything above is kept as the record. The details are in
> [`phase2-design.md`](phase2-design.md), Section 10, which is still DRAFT.
>
> 1. **Signal: none.** The signal pool is held at 0.5 so total drive stays in the
>    validated range. The question is whether the circuit can beat the market
>    using only market-internal features (price, recent_change and
>    time_to_resolution). Cross-venue signal is deferred to a follow-up.
> 2. **Comparator: the market price, calibrated on training markets only.** The
>    method is **proposed, not final**, and awaits the owner's confirmation:
>    - isotonic regression on the probability scale;
>    - shrinkage toward the block's mean price, with pseudo-count 20;
>    - a training-only cross-validation guard that falls back to the raw price if
>      calibration does not beat it.
>
>    It is chosen to avoid the Platt-on-logit artifact seen at extreme prices.
> 3. **Liquidity: input held at 0.5.** Final volume is used **only** as a
>    market-selection criterion, never as an input. The threshold, ≥ $10,000
>    USDC, is **proposed**.
> 4. **Size: Design A.** Arms `profit`, `learning_off` and the shuffled-outcome
>    null control: about **$75** at the measured CCX33 rate, leaving about
>    **$25 buffer** within the $200 total.
>
> - **Also proposed:**
>   - the decision time: a seeded uniform draw over the scheduled life, minus
>     24 h at each end;
>   - a 7-day train/test gap.
> - **Loader.** A Polymarket loader is drafted and tested on recorded fake
>   responses only. No network request has been made and no data has been
>   downloaded. Network is refused unless both `--allow-network` and a recorded
>   permission file covering the endpoint are given. No permission file exists.

> **REVISION 2026-10-14 (project owner): Polymarket follow-up answered;
> publication and reviewer sharing cleared; `/prices-history` still pending.**
> Everything above is kept unchanged as the record.
>
> *The follow-up exchange.* It continues the same support ticket as the
> 2026-10-11 transcript recorded in the 2026-10-12 revision above. The replies
> of 2026-10-13 and 2026-10-14 are from "Roni", the same human support agent who
> gave the 2026-10-11 reply. As before, Roni is a support agent, not Polymarket's
> legal team.
>
> *What it settles:*
>
> - **Publication of aggregate results** in an academic or research paper is
>   cleared: "We have no objection". Crediting Polymarket as the data source is
>   encouraged.
> - **Sharing market IDs and other reproducibility metadata** with journal peer
>   reviewers **and editors** is cleared: "completely fine".
> - **Stated limit:** no re-distributing or reselling of the raw API bulk dataset
>   as one's own commercial product.
>
> *What it does not settle:*
>
> - **CLOB `/prices-history`.** The follow-up did not ask about it. The
>   2026-10-12 amendment above says the 2026-10-12 follow-up asked about the CLOB
>   endpoint; the verbatim message below shows that it asked only about
>   publication and reviewer sharing. A one-line question about
>   `GET clob.polymarket.com/prices-history` was sent on 2026-10-14 in reply to
>   Roni's check-in. **PENDING:** no answer has been recorded.
>   `/prices-history` remains unpermitted, and no permission file for it exists.
> - **Public release** of market IDs or derived per-market features was not
>   asked about. The reply covers reviewers and editors only.
>
> *Transcript, verbatim* as supplied by the project owner (the spelling
> "re-distributing" is in the original).
>
> **Corrected 2026-10-16 (project owner).** This transcript first read
> "unauthenticat" in Luca's 2026-10-14 message, and that was noted as the
> original spelling. The owner confirmed that the original reads
> "unauthenticated". "unauthenticat" was a copy error, not the original, so it
> is corrected below.
>
> In Roni's 2026-10-13 reply, "always" is the original. The "ways" in a later
> copy was also a copy error.
>
> ```text
> Luca (2026-10-12): Thank you, Roni, that's very helpful. One follow-up: since the documentation doesn't address it, could you confirm whether Polymarket has any objection to (1) publishing aggregate results in a paper that credits Polymarket as the data source, and (2) sharing the list of market IDs used with journal peer reviewers? I wouldn't redistribute the raw data publicly.
>
> Luca (2026-10-13): Hey, I just wanted to follow up on this
>
> Roni (2026-10-13): Thanks for following up.
>
> To answer your questions directly:
>
> 1. Publishing Aggregate Results & Citation: We have no objection to you publishing aggregate analytical results in an academic or research paper. Crediting Polymarket as the data source is encouraged.
> 2. Sharing Market IDs with Peer Reviewers: Sharing the list of market IDs (or other metadata used for reproducibility) with journal peer reviewers and editors is completely fine.
>
> Because Polymarket's market data is publicly accessible and stored transparently on-chain, using aggregated metrics and sharing research methodology/IDs for peer review and academic reproducibility aligns with our open data ecosystem.
> As long as you are not re-distributing or reselling the raw API bulk dataset as your own commercial product, you are good to go!
> Let us know if you need anything else or if you'd like to share a copy of your paper with us once it's published—we always love seeing how researchers use Polymarket data.
>
> Roni (2026-10-14): Hi there, just checking in one more time to see if you need any additional assistance. If there's anything else we can help with, please don't hesitate to let us know before we close the ticket.
>
> Luca (2026-10-14): Thank you, Roni! One last quick check before you close the ticket: does the same apply to the public prices-history endpoint (clob.polymarket.com/prices-history), accessed read-only and unauthenticated within rate limits, for the same research? That's everything; I'll gladly share the paper once it's out.
> ```
>
> *Effect on the design* ([`phase2-design.md`](phase2-design.md), Section 1):
>
> - Condition 7 (publication and reviewer sharing on hold) is **cleared**.
> - Condition 6 (no public redistribution of raw data) **stands**.
> - CLOB `/prices-history` remains **unpermitted** pending Roni's answer. No
>   permission file for it is to be written until then.
>
> *Applied 2026-10-16 (project owner; the repository is public).*
>
> - The 2026-10-13 reply above is the record for publication and reviewer
>   sharing.
>   - Publication of aggregate results crediting Polymarket: **cleared**.
>   - Sharing market IDs and metadata with peer reviewers and editors:
>     **cleared**.
> - **Public** release of the market-ID list was not asked about. The frozen
>   list and any fill plan therefore stay **private**. Only their SHA-256
>   hashes are committed, and the lists are available to reviewers and editors
>   on request.
> - CLOB `/prices-history` remains **unpermitted** pending Roni's answer to the
>   2026-10-14 question.
> - Details: [`phase2-design.md`](phase2-design.md), Section 1, conditions 6
>   and 7, and Section 10.12.

> **REVISION 2026-10-16 (project owner): `/prices-history` answered (2026-10-15);
> ticket closed 2026-10-16.** Everything above is kept unchanged as the record.
>
> *The exchange.* This is the last part of the same support ticket. Luca's
> 2026-10-14 question, already shown in the 2026-10-14 transcript above, is
> repeated here with the reply it received. Roni is the same human support
> agent, not Polymarket's legal team. **The ticket was closed on 2026-10-16.**
>
> *What it settles.* For non-commercial academic research, the reply confirms
> the following for `GET https://clob.polymarket.com/prices-history`:
>
> - unauthenticated, read-only access within rate limits ("no fees or licensing
>   requirements … for non-commercial purposes, including academic research, as
>   long as you comply with rate limits and do not scrape the site");
> - storing the data privately for research;
> - using it with a learning model;
> - publishing aggregate results that credit Polymarket as the data source.
>
> **Peer-reviewer sharing** is acceptable, provided the raw data is not
> redistributed publicly.
>
> *Its own caveat.* The reply says the documentation "does not provide formal
> written confirmation or address every aspect of academic publishing". It is
> based on "the intended public, read-only use of the API". So, like the
> 2026-10-11 reply, it **is not a formal written confirmation**.
>
> *Transcript, verbatim* as supplied by the project owner on 2026-10-16.
>
> **Spelling, resolved 2026-10-16.** The owner confirmed that the originals read
> "unauthenticated" (Luca, 2026-10-14) and "always" (Roni, 2026-10-13). The
> variants "unauthenticat" and "ways" were copy errors, not originals. Both
> transcripts now agree.
>
> ```text
> Luca (2026-10-14): Thank you, Roni! One last quick check before you close the ticket: does the same apply to the public prices-history endpoint (clob.polymarket.com/prices-history), accessed read-only and unauthenticated within rate limits, for the same research? That's everything; I'll gladly share the paper once it's out.
>
> Roni (2026-10-15): Thanks for the response.
>
> The public prices-history endpoint (https://clob.polymarket.com/prices-history) is intended for retrieving historical price data for traded tokens and is accessible via unauthenticated, read-only requests within rate limits. There are no fees or licensing requirements for accessing or using this data for non-commercial purposes, including academic research, as long as you comply with rate limits and do not scrape the site.
>
> In addition, storing the data privately for research, using it with a learning model, and publishing aggregate results that credit Polymarket as the data source are all consistent with the intended use of the public API. The documentation does not specify restrictions on sharing market IDs or data with peer reviewers, provided you do not redistribute the raw data publicly.
>
> And there are no explicit objections or prohibitions in the documentation regarding your described use case. However, the documentation does not provide formal written confirmation or address every aspect of academic publishing, so this answer is based on the intended public, read-only use of the API as described in the sources.
>
> For more details, you can review the documentation at docs.polymarket.com and the prices-history endpoint.
> ```
>
> *Effect on the design* ([`phase2-design.md`](phase2-design.md), Section 1):
>
> - CLOB `GET /prices-history` is **PERMITTED** under every existing condition:
>   - read-only and unauthenticated;
>   - a pre-set rate under the published limit;
>   - a request log;
>   - no platform or contract interaction;
>   - no public redistribution of raw data;
>   - the terms re-checked before download;
>   - **no scraping of the website**.
> - It is recorded in a permission file covering that endpoint only, under
>   `repro/polymarket/permissions/`.
> - Condition 6 stands: the market-ID list stays private.

## 7. Synthetic-market mitigation and the remaining encoder/eligibility placeholders

**DECIDED 2026-10-09 (project owner).** Item 5's list of remaining placeholders is
superseded by this item for the entries below. Item 5 itself is unchanged.

- **Mitigation: none.** The synthetic-market sweep uses the encoder exactly as
  ACCEPTED, with the raw CIRCUIT-80 per-type-mean score. The innate policy is
  reported, not removed. The rationale and scope are recorded as the dated
  revision of [`synthetic-market-experiment.md`](synthetic-market-experiment.md),
  Sections 4 and 7.
- **Now decided:**

  | parameter | value | basis |
  |---|---:|---|
  | `min_rate_hz` / `max_rate_hz` | 30 / 150 | the ACCEPTED left-only mirrored validation (`c084908`) |
  | `pool_size` | 100 | the ACCEPTED validation |
  | `pool_seed` | 20260401 | the ACCEPTED validation; its pools are the validated pools |
  | `kc_active_threshold_hz` | 1.0 | in force in the first learning test (LEARNING DEMONSTRATED) |
  | `kc_rate_ref_hz` | 150 | in force in the first learning test; equals `max_rate_hz` |
  | `score_scale` (synthetic sweep) | 20 Hz | cannot affect the gate (Platt on `S/20` is exact unless the score exceeds about 690 Hz) |

- **Still placeholders:**
  - the encoder **feature ranges**, except `recent_change`. Its range was set to
    ±1 later on 2026-10-09 (Proposal A, in the generator and in `FeatureSpec`).
    The caveat recorded in the synthetic-market spec, Section 1 revision, applies:
    in independent synthetic markets the feature is largely a noisy copy of
    price. A within-market change is deferred to Phase 2;
  - `dopamine_max_rate_hz` and `ReadoutParams.margin_threshold`. The synthetic
    sweep uses neither: the first is never given to the network, and the sweep
    has its own `decision_margin = 0`, fixed by its pre-statement.

## 8. Synthetic sweep: comparator, null control and power design

**DECIDED 2026-10-09 by the project owner, before any synthetic-market run.** The
dated revisions are in [`synthetic-market-experiment.md`](synthetic-market-experiment.md),
Sections 1, 2, 3, 6 and 7.

- **Market comparator:** the exact price-only Bayes posterior, replacing the
  Platt-calibrated price. With the old comparator the gate could pass at
  strength 0 without signal.
- **Strength 0 is the null control.** A pass there is a pipeline or generator
  problem, not a finding.
- **Strengths 0, 0.4, 0.8, 1.0.**
  - 1.0 is the positive control.
  - 0.4 is pre-stated as underpowered: a non-pass there is undetermined.
  - 0.1 and 0.2 are dropped.
- **Design (b′):** seeds 20261001–20261020, 250 markets per seed (70 train /
  180 test), all four arms. That is 160,000 runs in 320 jobs with 500-run chains,
  about $121 on CCX43, with about $50 held as contingency.
- **Reporting:**
  - the profit arm against learning-off is labelled "learning effect, any
    source";
  - profit is reported by price region next to a price-only Bayes trader;
  - the strength-s versus strength-0 comparison is a non-gating secondary
    report.
- **Considered, not adopted:** making that comparison part of the gate, and
  changing the generator.
