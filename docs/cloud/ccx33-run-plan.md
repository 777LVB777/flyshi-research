# Synthetic-market sweep on a CCX33: run plan

**Status: written 2026-10-11, before the server exists. Nothing here has been
run on a server.** Every command below was tested on the development Mac with
fakes or dry runs only.

| | |
|---|---|
| Sweep | design (b′), config **`a325e6b206`**: 320 jobs, 160,000 runs, each job a 500-run chain |
| Server | Hetzner **CCX33**: 8 dedicated vCPUs (probably 4 physical cores with SMT, unverified), 32 GB RAM. The account cannot create anything larger for several weeks. |
| Price | **$0.266/h**, as given 2026-10-11. Check the console. |
| Run order | phase 1 = `profit`, `learning_off`; phase 2 = `accuracy`, `profit_drift_off` ([spec, Section 7, revision 2026-10-11](../design/synthetic-market-experiment.md)) |

Setup follows [`server-setup.md`](server-setup.md) Steps 1–8 unchanged. This
document replaces Steps 9–11 for the sweep.

## 0. First session, in order

All commands run on the server inside tmux (`tmux new -s fly`), from `~/flyshi-research`.

1. **Cross-platform check** (about 2 min; Section 3). Go or no-go.
   `.venv-shiu/bin/python repro/mushroom_body/cross_platform_check.py`
2. **Recovery settings** (Section 6): check automatic reboots; decide on automatic updates.
3. **Calibration** (about 1 h; Section 2).
   `.venv-shiu/bin/python repro/mushroom_body/calibrate_server.py`
4. **ETA and process count:**
   `.venv-shiu/bin/python repro/mushroom_body/server_eta.py --budget 170`
5. **Start the sweep** with the command `server_eta.py` prints. Run `--dry-run` first.
6. **Start backups** on the Mac (Section 4), then **check** with the monitor (Section 5).

## 1. Planning figures before calibration (unmeasured)

These figures use the Mac's **55 s per run, measured with one process**, and the
launcher's memory rule at 5 GB per process, which allows 5 processes on 32 GB.
Neither figure is measured on a CCX33. With 5 processes on about 4 physical
cores, each run will probably take longer than 55 s.

| Processes | Phase 1 done | Whole sweep | Phase 1 cost | Whole sweep cost |
|---:|---:|---:|---:|---:|
| 4 | 306 h (12.7 d) | 611 h (25.5 d) | $81 | $163 |
| **5** | **244 h (10.2 d)** | **489 h (20.4 d)** | **$65** | **$130** |
| 8 (if 55 s held, which it will not with SMT) | 153 h | 306 h | $41 | $81 |

The calibration replaces this table with measured figures.

## 2. Calibration: the first hour

```bash
.venv-shiu/bin/python repro/mushroom_body/calibrate_server.py --dry-run   # plan only
.venv-shiu/bin/python repro/mushroom_body/calibrate_server.py             # about 1 h
```

- **Process counts.** For each N = 1, 4 and 8, the script starts N real sweep
  jobs. Each is a different job, the first N in run order.
- **Workers.** Each worker runs `run_synthetic_market_experiment.py --job`,
  exactly as the launcher does, with one thread per process. Starts are
  30 s apart.
- **Memory.** A worker starts only while memory allows: MemAvailable minus
  headroom must be at least 5 GB. A level that runs short starts fewer workers
  and says so.
- **Measurement.** Each level waits until every worker has built its network
  and finished its first run. It then measures for 12 minutes and stops the
  workers.
- **Reports per N:**
  - seconds per run, per process;
  - peak memory per process (the highest `VmHWM` of any worker);
  - runs per hour for the machine;
  - the lowest MemAvailable during the level.
- **Nothing is saved from the jobs.** Each job is stopped long before its 500th
  run, in a scratch directory that is then deleted. The real results directory
  is not touched.
- **Output.** `results/server_calibration/calibration_<host>_<time>.json`
  records the figures and the environment: CPU, `lscpu`, gcc and git HEAD.
  Commit it with the results.
- **Other process counts.** `--procs 5,6` measures more process counts. Run
  it if the best N is 8, or if 4 and 8 differ little.

Then:

```bash
.venv-shiu/bin/python repro/mushroom_body/server_eta.py --budget 170
```

For each measured N, `server_eta.py`:

- checks that N processes fit the launcher's memory rule, using the measured
  peak plus 15%;
- schedules the remaining jobs as the launcher does: phase 1 first, at that N's
  measured seconds per run plus build time.

It prints:

- **the best N**: the most runs per hour among those that fit, preferring
  fewer processes within 2%;
- **dates:** when phase 1 and the whole sweep finish;
- **costs:** of phase 1, of phase 2 and in total, at $0.266/h;
- **the launcher command:** `--max-procs N --gb-per-proc <peak × 1.15>`.

Re-run it at any time: it subtracts jobs already done. Only measured N are
candidates. Throughput between them is not interpolated.

## 3. Cross-platform check (pre-stated)

**Stimulus.** The pool-identity control's reproducibility stimulus: the
left-only mirrored validation's price arm at v = 0.94, YES, seed 20260316. Its
Mac result is `graded_left_mirrored_value_0p94_YES_seed_20260316.json`. The Mac
re-simulated it identically on 2026-09-30 (`pool_identity_repro_check.json`).
The server simulates it **twice**, with the same seed, in one process.

**Readings, decided before the run:**

| Reading | Condition | What we do |
|---|---|---|
| `SERVER_NONDETERMINISTIC` | the two server runs differ at all | **Do not start the sweep.** Restarted jobs and arms run apart would not reproduce. Investigate (threads, Brian2 codegen target). |
| `IDENTICAL` | run 1 equals the Mac file exactly: every population's trial-mean and per-trial rates, and the population IDs | Start the sweep. Server results are bit-comparable with the Mac's diagnostics. |
| `CONSISTENT_WITHIN_NOISE` | not identical, but every difference is at most its noise floor (below) | Start the sweep. Record the reading in the spec's Results. Label any comparison of server results with Mac-run diagnostics "across a platform change". Re-run no Mac diagnostic. |
| `INCONSISTENT` | any difference beyond its floor | **Do not start the sweep.** Keep the result file. Compare the environment it records (`pip freeze`, gcc, Python) with the Mac's lock file and the Brian2 codegen target. The owner decides, and records the decision, before any sweep compute is spent. If this will take more than a day, delete the server meanwhile (it bills about $6.40/day). |

**Noise floor.** For each quantity, the floor is the largest of the 15 pairwise
differences between the six Mac seeds (20260316–20260321) of this same stimulus.
That is the measured difference between two runs that differ only in noise. The
script recomputes the floors from the saved files. The values at the time of
writing are:

| Quantity | Floor |
|---|---:|
| CIRCUIT-80 per-type-mean score, absolute difference | **3.22 Hz** |
| MBON rate vector, Euclidean distance | **11.94 Hz** |
| KC rate vector | **143.70 Hz** |
| APL rate vector | **5.02 Hz** |
| PAM rate vector | 7.72 Hz |
| PPL1 rate vector | 7.81 Hz |

**What a non-identical reading means.** The sweep runs entirely on the server,
so its own comparisons are unaffected by any platform difference. What changes
is the comparison with Mac-run diagnostics, such as the ignition statistics of
the low-drive follow-up. A single presentation within the floors shows only
that no difference is detectable at single-run noise. It does not show that the
two platforms produce the same distribution.

**Command:** `.venv-shiu/bin/python repro/mushroom_body/cross_platform_check.py`
(exit status 0 for `IDENTICAL` or `CONSISTENT_WITHIN_NOISE`, 1 otherwise). It
writes `results/cross_platform_check_<host>.json`, with the server run and the
environment. `--dry-run` prints the floors without simulating.

## 4. Backups

**Recommended: pull to the Mac.** The server then needs no GitHub credentials.
Run this on the Mac, in a tmux session or a spare terminal:

```bash
cd ~/Projects/flyshi-research
caffeinate -i python3 scripts/cloud/backup_results.py pull --every-hours 3
```

- **What it copies.** Every 3 hours, `rsync` copies the sweep's job files and
  logs, the calibration files and the cross-platform file into
  `~/flyshi-backups/`. That folder is outside the git working tree, so nothing
  half-finished can be committed by accident.
- **What it never does.** It never deletes anything at either end. It never
  copies `*.partial` files (a write in progress).
- **Checks.** After each cycle, every job file is checked: not empty, under
  5 MB (expected about 0.5 MB), whole JSON with the job fields. Failures are
  printed and written to `~/flyshi-backups/backup.log`.
- **Failed cycles.** A failed cycle (Mac asleep or offline, server down) is
  logged and the next cycle catches up.
- **Run one cycle now:** `... pull --once` (exit status 0 means all good).

**Alternative: push from the server.**
`python3 scripts/cloud/backup_results.py push --every-hours 3`, in a second tmux
window on the server.

- **What it does.** It commits the checked job files, logs and calibration
  files to the server's clone, and pushes them to the branch
  `results-backup/a325e6b206`, never to `main`. Files that fail the check are
  reported and not committed.
- **What it needs.** A GitHub deploy key with write access, which you create
  and delete afterwards. You also need `git config user.name` and
  `user.email` on the server.
- **Use it** if the Mac cannot stay awake for three weeks.

At the end, as in `server-setup.md` Step 11: copy the results into the repo on
the Mac, check them, and commit from the Mac.

## 5. Monitoring

```bash
ssh flyshi 'cd ~/flyshi-research && .venv-shiu/bin/python repro/mushroom_body/monitor_sweep.py'
```

It prints:

- **Jobs:** done, running and remaining, overall and per phase.
- **Runs:** in finished jobs and in running jobs (from the jobs'
  `[progress]` log lines).
- **Rate and ETA:** runs per hour over the last 6 h, and an ETA for phase 1
  and for the whole sweep at that rate.
- **Each running job:** its run count, memory and attempt number, flagged
  `STALLED?` after 15 min without progress.
- **Failed or interrupted jobs:** with each one's last log line.
- **Damaged job files.**
- **Resources:** memory (total, available, workers) and free disk.
- **The launcher's state.**
- **Ignition:** the number of decisions with an ignited framing in finished
  jobs, as one total.

It shows nothing else from the results (spec Section 7, 2026-10-11): no score,
action, forecast, outcome, P/L or gate statistic.

## 6. Recovery

**A worker process dies, or the server reboots, in the middle of a job:**

- **The job restarts from market 0.** It loses up to one 500-run chain per
  running process. With 5 processes at 55 s per run, that is at most about
  7.6 h of each process. There is no per-market checkpoint.
- **No partial output can count as done.** The job file is written once, at
  the end of the job:
  - it is first written in full to `<job>.json.partial`, then `fsync`ed;
  - it is renamed to `<job>.json`, and the directory is `fsync`ed;
  - so after a crash or power loss there is either no job file or a whole one.
- **A damaged file is re-run.** A job counts as done only if its file is whole
  JSON. A damaged file (impossible with the above, but checked anyway) makes
  the job re-run and is replaced.
- **Leftovers are harmless.** A leftover `.partial` file is ignored and
  overwritten next time.
- **The restarted job reproduces exactly.** Every presentation is seeded from
  (strength, seed, market), and the network is restored before every trial. A
  restarted job therefore writes the same file an uninterrupted one would have.
  The cross-platform check's two identical server runs are the evidence for
  this on the server.
- **Job logs are appended to, not replaced.** Each attempt begins with a
  `[start]` line. The monitor counts the latest attempt.
- **Finished jobs are never re-run.**

**After a reboot nothing restarts by itself.** The launcher and tmux die with the
server. Run the launcher again:

```bash
ssh flyshi
tmux new -s fly
cd ~/flyshi-research
.venv-shiu/bin/python repro/mushroom_body/launch_synthetic_market_parallel.py --max-procs N --gb-per-proc X
```

Use the same arguments as before. Finished jobs are skipped.

- **Lock from before the reboot.** The launcher removes a lock file written
  before the last boot. Its process ID may since have been reused, which would
  otherwise block the start.
- **Monitor the gap.** The monitor's "launcher: NOT RUNNING" line, or a backup
  cycle that cannot connect, is how a reboot shows up. Billing continues while
  the server sits idle.

**Can Ubuntu's automatic updates reboot the server?** Not by default. Check on
the server:

```bash
apt-config dump | grep -i 'Unattended-Upgrade::Automatic-Reboot'   # expect "false" or nothing
systemctl is-enabled unattended-upgrades apt-daily-upgrade.timer
cat /var/run/reboot-required 2>/dev/null                            # a pending reboot, if any
```

- **What the updates do.** Ubuntu 24.04 installs security updates daily
  (`unattended-upgrades`). `Unattended-Upgrade::Automatic-Reboot` defaults to
  `false`, so they do not reboot the machine. A new kernel waits for a manual
  reboot (`/var/run/reboot-required`).
- **Running jobs are safe.** `needrestart` may restart system services after
  an update, but not processes inside tmux.
- **Unverified.** The defaults above are Ubuntu's documented defaults. Run the
  commands above to confirm them on the actual image.

**The remaining risk is a change to the environment during the sweep.** An
update to gcc or libc between job starts would change the toolchain that
Brian2's compiled code depends on. The Python environment is not at risk: it is
uv-managed and pinned, and system updates do not touch it.

**Recommendation:**

1. Run the full upgrade of `server-setup.md` Step 6.
2. Reboot if asked.
3. Run the cross-platform check.
4. Then stop automatic upgrades for the duration of the run:

   ```bash
   systemctl disable --now unattended-upgrades apt-daily.timer apt-daily-upgrade.timer
   ```

The server accepts only key-based SSH behind two firewalls, and it will be
deleted after the run, so three weeks without updates is a small risk. This is
the owner's decision. If updates stay on, nothing reboots, but the toolchain
may change during the sweep.

**Other causes of an unplanned stop:**

- **Hetzner host maintenance:** rare, and announced by email.
- **The kernel's out-of-memory killer:** prevented by the launcher's memory
  rule at the calibrated figure, and visible in `dmesg` and in the monitor as
  a failed job.

**Deleting the server** is unchanged: `server-setup.md` Step 12, only after the
results are on the Mac and pushed.
