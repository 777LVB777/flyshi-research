# Degree-preserving shuffled-connectome control

**Status:** implementation and synthetic-graph tests complete 2026-09-21. The
real v783 connectivity file has not been read or shuffled. All resource figures
and real-connectome behavior below are **unverified**.

This is the structural null control named in Section 6 of
`mb-learning-interface.md`. It asks whether Flyshi needs the fly's particular
wiring or merely a directed network with the same neurons, edge degrees, and
synaptic-strength distribution. This document fixes the method and checks
before any real shuffle is generated.

## Method

For two directed edge rows `a -> b` and `c -> d`, propose

```
a -> d
c -> b
```

and keep the proposal only when it satisfies the chosen self-loop and parallel
edge policy. Sources stay in their original rows and targets are exchanged.
Pairs with the same source or target are rejected because they make no
structural change. A seeded NumPy random generator chooses edge pairs. The
default is ten accepted swaps per eligible edge; failure to achieve every
requested swap within the attempt limit is an error, not a partial success.

This is a directed double-edge-swap procedure. We have not independently
verified a primary source for this precise implementation, so it is documented
here without a literature citation. A finite swap chain is not claimed to be a
perfectly uniform sample of all directed graphs with the same degree sequence.

## What stays fixed

- The neuron set and number of edge rows.
- Every neuron's unweighted out-degree and in-degree, exactly. Here “degree” is
  the number of connectivity rows, not the sum of anatomical synapse counts.
- The global joint distribution of `(synapse count, sign)`, exactly.
- Each presynaptic neuron's multiset of outgoing synapse counts and signs,
  because those attributes remain on their edge rows and sources never move.
- Rows outside the chosen scope, exactly.
- No self-loop or parallel edge is introduced if the input contains none. If
  the input already contains one, that feature is permitted by default; the
  command can instead reject such an input explicitly.

The sign travels with the edge row. Because its presynaptic endpoint also stays
fixed, this preserves each source neuron's outgoing sign profile. This matters:
shuffling signs independently could turn a consistently excitatory or
inhibitory neuron into a biologically incoherent mixture. The target receiving
that signed, weighted row changes, which is the structural intervention of
interest.

## What is destroyed

- Specific pre/post partners, motifs, paths, compartments, and cell-type
  preferences within the selected scope.
- Each target's weighted in-degree and balance of excitatory/inhibitory input.
- Correlations between target identity and synapse count or sign.
- If parallel rows are present and allowed, distinct-neighbor counts need not
  be preserved even though row-count degrees are preserved.

Consequently, this is not a control for “same input current at every neuron.”
It is a control for the same directed degree sequence plus the same global
weight/sign material. A loss of performance can reflect destroyed partner
selection, target-specific weighted input, or both.

## Scope — RESOLVED 2026-09-22: mushroom-body-only is primary

The generator requires one of these names explicitly and has no default (kept
deliberately, so every run records its scope):

1. **Mushroom-body-only.** Shuffle the induced subgraph whose two endpoints are
   in a supplied MB neuron list; leave boundary and non-MB rows untouched. This
   better isolates KC/MBON-region organization and preserves the rest of the
   sensory and central-brain pathways. It is a weaker null because upstream,
   downstream, and MB boundary structure remain native. The supplied list must
   state whether “related” includes PAM, PPL1, APL, and any other cells. The
   implementation deliberately does not guess that membership.
2. **Whole-network.** Make every connectivity row eligible. This addresses the
   broadest “any network of the same size and degree shape” question, but it can
   destroy basic sensory propagation and global dynamical regimes before the
   learning circuit is reached. A negative result is therefore less specific
   to mushroom-body computation.

**Decision (project owner, 2026-09-22; see
[`open-decisions.md`](open-decisions.md), item 1):** **mushroom-body-only is the
PRIMARY, preregistered structural control.** Membership: all annotated **KCs,
MBONs, PAM, PPL1 and APL**, plus any further class admitted only by a written
annotation rule. The rule and the resulting root-ID JSON must be frozen before
generation and never adjusted after a result. Rationale: market input enters
directly at the Kenyon cells, bypassing the antennal lobe, so the question is
whether the mushroom body's specific wiring matters. **Whole-network shuffle is
optional and exploratory, not preregistered**; a result from it cannot change a
preregistered verdict. The annotation rule and frozen root-ID file do not yet
exist in this repository.

## Pre-stated generation checks

A real shuffled artifact passes generation only if all of the following hold:

- row count, each neuron's in/out row degree, and the full `(synapse count,
  sign)` multiset match exactly;
- non-eligible rows match exactly for the MB-only scope;
- no self-loop or parallel edge appears when absent from the input;
- every requested swap was accepted; and
- endpoint-pair overlap with the original is below 0.50, counting parallel
  edges with multiplicity.

The 0.50 overlap cutoff is a minimal “specific structure was actually changed”
criterion, fixed before the real run. The observed overlap and accepted/attempted
swap counts must be reported, not only the pass/fail verdict. These checks do
not establish uniform sampling or equivalent network dynamics.

## Server generation

For the optional, exploratory whole-network scope, the simulation-free generator is:

```bash
.venv-shiu/bin/python repro/connectome/generate_shuffled_connectome.py \
  --scope whole-network --seed SEED --dry-run
```

or, for the primary MB scope (the `FROZEN_IDS.json` membership file is not yet
written):

```bash
.venv-shiu/bin/python repro/connectome/generate_shuffled_connectome.py \
  --scope mushroom-body --seed SEED --mb-root-ids FROZEN_IDS.json --dry-run
```

Dry-run does not open the connectivity file and uses an explicitly labeled
15-million-row planning assumption. The script estimates roughly 640 bytes of
peak working memory per edge for the pandas table, NumPy copies, and Python edge
membership set, then recommends twice that estimate as machine headroom. At 15
million rows this is about 8.9 GiB estimated peak and 17.9 GiB recommended RAM.
Both figures are **unverified**. Python-loop runtime for ten swaps per edge is
also **unverified** and may be substantial.

For a real run, add an output path outside `third_party/` and remove
`--dry-run`. The script reads the full parquet only then, writes through a
`.partial` file, refuses to overwrite an artifact, updates both index and root-ID
endpoint columns, and writes a small JSON audit manifest. The generated parquet
is a large server artifact and must not be committed.
