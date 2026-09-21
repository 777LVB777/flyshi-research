# First learning test on a rented server: time and cost estimate

**Status: estimate, written 2026-09-21. Nothing here has been measured on a server.**
Every time below comes from an assumed time per simulation run. **Prices must be
checked** on Hetzner's site before renting (see "Prices" below).

## What is being run

The pre-stated first learning test ([`../design/first-learning-test.md`](../design/first-learning-test.md))
has **260 simulation runs**, split into **35 jobs** (Section 10 of the spec):

| Job | Count | Runs each | Must wait for |
|---|---|---|---|
| training, one per condition | 5 | 40, strictly one after another | nothing |
| pre-training test, one per seed | 5 | 2 | nothing |
| post-training test, one per condition and seed | 25 | 2 | that condition's training |

**Only the training runs are forced into a sequence.** Each condition's 40 training
presentations must run in order, because each one uses the weights learned from the
ones before. So however big the server, the job cannot finish faster than **42 runs
back to back**: one training job of 40 runs, then one 2-run test job.

## Assumptions

1. **Time per run:** optimistic **30 s**; pessimistic **10 min** (the figures given
   for this estimate). The 10-minute figure comes from this 8 GB Mac running the
   *original* code path, which rebuilds the whole network for every trial. That Mac
   may also have been short of memory. The server uses the fast path, which builds the
   network once per process, so 10 min is likely pessimistic. **Neither figure has been
   measured on a server.**
2. **Every run is counted as the same length.** In reality a training run simulates 1
   trial and a test run 5 trials, so training runs may be up to 5× shorter (see
   "If run time scales with simulated time" below).
3. **Memory:** about 4–5 GB per process; the launcher budgets 5 GB, keeps headroom of
   max(2 GB, 10% of RAM) free, and uses `floor((available − headroom) / 5 GB)`
   processes:
   - **CCX33** (32 GB, about 31 GB available): (31 − 3.2) / 5 → **5 processes**.
   - **CCX43** (64 GB, about 62.5 GB available): (62.5 − 6.4) / 5 → **11 processes**.

   The "available" figures are assumptions; the launcher reads the real value.
   Cores (8 and 16) are not the limit in either case.
4. **Network build:** each job builds the network once. Build time on the server is
   unknown. The main table leaves it out, and a separate row shows its effect at 2 min
   per build.
5. **Setup:** about 30 min of billed time for creating the server, `setup.sh` and
   copying results back (a guess).
6. **Scheduling:** exactly the launcher's order (all training jobs first, then
   pre-tests, then post-tests as they become ready). The numbers come from
   `estimate_makespan` in `repro/mushroom_body/launch_first_learning_parallel.py`,
   which is tested against this table.

## Wall-clock time

| Machine | Parallel processes | Length in runs | Optimistic (30 s/run) | Pessimistic (10 min/run) |
|---|---:|---:|---:|---:|
| one process (e.g. this Mac, if it had the RAM) | 1 | 260 | 2.2 h | 43.3 h |
| **CCX33** | 5 | 52 | **26 min** | **8.7 h** |
| **CCX43** | 11 | 46 | **23 min** | **7.7 h** |
| any machine (the limit set by the training chain) | 25+ | 42 | 21 min | 7.0 h |
| CCX33, adding 2 min per network build | 5 | — | 40 min | 8.9 h |
| CCX43, adding 2 min per network build | 11 | — | 31 min | 7.8 h |

CCX43 has more than twice the processes but finishes only about 12% sooner. The
40-run training chain dominates; extra processes help only with the short test jobs.

## Cost

Prices are the ones given for this estimate, **unverified** (see "Prices" below):
CCX33 about €0.22/hour, CCX43 about €0.44/hour. Billed time = run time + about 30 min
of setup and copying.

| Machine | Optimistic | Pessimistic |
|---|---|---|
| **CCX33** | about 1 h billed → **≈ €0.25** | about 9.5 h billed → **≈ €2.10** |
| **CCX43** | about 1 h billed → **≈ €0.45** | about 8.5 h billed → **≈ €3.75** |

**Recommendation: CCX33.** For this test it is nearly as fast and about half the
price. CCX43 would only pay off for later experiments with many more independent
jobs, for example many seeds or parameter settings.

**The real risk is forgetting to delete the server.** Billing continues while the
server exists, even when it is powered off. A forgotten CCX33 costs about €5 per
day, or about €160 per month at the hourly rate; Hetzner may cap the monthly charge
(**unverified**). See the deletion step in [`server-setup.md`](server-setup.md).

## If run time scales with simulated time

If a 1-trial training run takes a fifth as long as a 5-trial test run, the work is
100 test-run-equivalents in total and the training chain shrinks to 8. The
wall-clock times, in test-run lengths, become:

| Processes | Length (test-run lengths) |
|---:|---:|
| 1 | 100 |
| 5 (CCX33) | 20 |
| 11 (CCX43) | 14 |
| no limit | 10 |

At 10 min per test run, that is about 3.3 h on CCX33 and 2.3 h on CCX43. Which model
is closer depends on the fixed cost per run, which is unknown. **Measure it first:**
time `--smoke` or a single job on the server before committing to a machine size.

## Prices: to verify before renting

- **Hourly prices of CCX33 and CCX43.** Hetzner has changed its prices before, and
  prices differ by location.
- **VAT** (added for EU customers) and whether prices shown include it.
- **The primary IPv4 address**, which may be billed separately.
- **Billing granularity** (per hour, or finer) and any monthly cap.
- **Minimum charge** for a server that exists for less than an hour.

None of these were checked for this estimate.
