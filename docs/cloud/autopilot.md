# Server autopilot: Phase 1 finish, Phase 2 run, publish, notify

The autopilot runs on the CCX33 (`ssh flyshi`) as the systemd service
`flyshi-autopilot`. Once it is set up, the rest of the experiment needs no input,
apart from the decisions that are yours by design (listed at the end). Your Mac can
be off.

**What it does, in order.** The state is kept in `~/flyshi-autopilot/state.json`.
Every step can be repeated safely, so the service can stop and restart at any point.

1. **Watches Phase 1:** the synthetic sweep's 160 jobs, config `a325e6b206`, running
   in tmux session `setup`. If the launcher is gone before all 160 are done, it
   restarts it with the same arguments (`--max-procs 4 --gb-per-proc 3.6 --phase 1`).
2. **Finishes Phase 1** with `finish_day.py`'s own checks and copy, run on the
   server. It commits exactly what finish_day's printed `git add` covers, with its
   commit message, pushes to `main`, and checks the pushed files on GitHub.
3. **Writes the Phase 1 verdict.** First it moves the main tree to the git tag
   `phase2-frozen`, after checking the tag against GitHub. It then runs
   `--finish-phase1` there, and commits and pushes `verdict_phase1.json`.
4. **Applies the preregistration's rule** for whether Phase 2 runs (Section 12,
   `run-regardless`). With no rule, or an unclear one, it waits and notifies you.
5. **Checks Phase 2's inputs:**
   - the market file's SHA-256 must be `0777ae92…c2c686`;
   - your drive-check sign-off must be recorded (it already is, in
     `docs/records/phase2_build_signoff.md`);
   - `drive_check.py` must exit 0.

   Then it runs `--prepare`.
6. **Runs Phase 2:** 3 arms × 40 chains, 120 jobs, with
   `--max-procs 4 --gb-per-proc 3.6`, on exactly the commit of `phase2-frozen`.
   It refuses to start if the tag is missing on GitHub, points elsewhere there, or
   the main tree is not at that commit.
7. **Publishes Phase 2:** computes the verdict, then commits and pushes
   `verdict.json` and `hashes.json` only. A data guard aborts any commit that
   stages a file under `data/`, a private file name, or (for Phase 2) anything that
   looks like per-market records.
8. **Final check:** confirms that every file it pushed matches its SHA-256 on
   GitHub, then sends **SAFE TO DELETE THE SERVER**. The message includes the scp
   command that copies the private Phase 2 job files to your Mac. It never deletes
   the server and never calls the Hetzner API.

**Notifications** (ntfy.sh) are status lines only:
- started and done for each phase;
- the two verdict lines;
- waiting and halted messages;
- crashes, out-of-memory kills, low disk, no job finished for 12 h;
- estimated Phase 2 spend passing $85, and the budget stop at $95 (no new job
  starts);
- a daily "still alive" line with jobs done / total.

**Files:**
- `scripts/cloud/autopilot/autopilot.py`: the state machine, standard library only.
- `project_steps.py`: the steps that need the project's code, run with the model venv.
- `flyshi-autopilot.service`: the systemd unit.
- `config.example.json`: a template for your config.
- Tests: `tests/cloud/test_autopilot.py` (fakes only) and a stop-file test in
  `tests/learning/test_server_run.py`.

## Setup (numbered; do these in order)

**1. On the Mac: run the tests, then commit and push, all before Phase 1 ends.**

```bash
cd ~/Projects/flyshi-research
.venv-shiu/bin/python -m pytest tests/cloud/test_autopilot.py tests/learning/test_server_run.py -q
```

Only if every test passes:

```bash
git add scripts/cloud/autopilot docs/cloud/autopilot.md tests/cloud/test_autopilot.py \
        tests/learning/test_server_run.py docs/design/phase2-preregistration.md \
        repro/mushroom_body/launch_synthetic_market_parallel.py repro/mushroom_body/launch_real_market_parallel.py
git commit -m "Server autopilot; Phase 2 runs regardless of the Phase 1 verdict (prereg Section 12)"
git push
```

The preregistration's Section 12 says the rule was fixed before any verdict was
computed. That is only true if this commit is pushed before Phase 1 finishes.

**Do not `git pull` in `~/flyshi-research` on the server while Phase 1 runs.**
- The model venv has the package installed in editable mode, so every new phase 1
  worker would run the new code.
- The autopilot uses its own clone, and moves the main tree only after Phase 1 has
  finished.

**2. On the Mac, after the tests pass and step 1 is pushed: create and push the tag
`phase2-frozen`.**

```bash
cd ~/Projects/flyshi-research
git status --short          # must print nothing: the tag must name exactly what you tested
git tag -a phase2-frozen -m "Phase 2 code, frozen before the Phase 1 verdict"
git push origin phase2-frozen
git ls-remote origin refs/tags/phase2-frozen^{} && git rev-parse HEAD   # the two hashes must be equal
```

- Phase 1's verdict and all of Phase 2 run exactly this commit.
  - Without the tag on GitHub, the autopilot waits after pushing Phase 1's results
    and notifies you.
  - If the tag later moves or is deleted on GitHub, it refuses to start Phase 2.
- Never move the tag after Phase 2 has started. To change the code before then,
  delete the tag and create it again (`git tag -d phase2-frozen`, then
  `git push origin :refs/tags/phase2-frozen`, then repeat this step). This works
  only until the autopilot has pinned the tag, which it does once all 160 Phase 1
  jobs are done.

**3. Copy the Phase 2 inputs to the server once.**

All five files go into the main tree's git-ignored `data/polymarket/`.
- `--prepare` needs the market file and the fill plan.
- `drive_check.py` also needs the frozen list, its `.sha256` file and the histories
  (conflict 3).

```bash
cd ~/Projects/flyshi-research/data/polymarket
scp markets_f3d41123e20e_cutoff_2026-03-01.json fill_plan_f3d41123e20e.json \
    frozen_market_list.json frozen_market_list.json.sha256 histories_f3d41123e20e.jsonl \
    flyshi:flyshi-research/data/polymarket/
ssh flyshi 'sha256sum flyshi-research/data/polymarket/markets_f3d41123e20e_cutoff_2026-03-01.json'
```

The hash it prints must be `0777ae92f0dd6b950e1a0e3495c72c3a89280b421265f2a53cdac3c3b9e2c686`.

**4. Drive check sign-off: already done.**

`docs/records/phase2_build_signoff.md` (commit `227fdc2`) names the market file's
SHA-256 and "Signed off by". The autopilot accepts that record as the owner's
sign-off. It reads the record from the pinned Phase 2 code, and the SHA-256 must
match the file on the server. The config's `drive_signoff_sha256` is an
alternative; leave it empty. The autopilot still runs `drive_check.py` on the
server and needs exit 0.

**5. Add the deploy key and install ntfy.**

On the server, create the key and print its public half:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/flyshi_deploy -N "" -C "flyshi-autopilot"
cat ~/.ssh/flyshi_deploy.pub
```

- On GitHub, open 777LVB777/flyshi-research → Settings → Deploy keys → Add deploy
  key. Paste the key and tick **Allow write access**. A deploy key only reaches
  this one repository.
- If `main` has branch protection that blocks direct pushes, the autopilot's push
  will fail. Check this now.

On the server, add this to `~/.ssh/config`:

```
Host github-flyshi
    HostName github.com
    User git
    IdentityFile ~/.ssh/flyshi_deploy
    IdentitiesOnly yes
```

Then check GitHub's host key and the connection:

```bash
ssh-keyscan -t ed25519 github.com >> ~/.ssh/known_hosts
ssh-keygen -lf ~/.ssh/known_hosts | grep github
ssh -T git@github-flyshi
```

- The fingerprint must match GitHub's published ed25519 key,
  `SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU` (check it on docs.github.com,
  "GitHub's SSH key fingerprints").
- `ssh -T` should answer "Hi 777LVB777/flyshi-research! You've successfully
  authenticated".

For ntfy, make a topic name on the Mac:

```bash
python3 -c "import secrets; print('flyshi-' + secrets.token_urlsafe(32))"
```

Install the **ntfy** app (App Store or Google Play) → **+** → server `ntfy.sh`,
topic = that name → Subscribe. Anyone who knows the name can read the messages,
which is why they are statuses only. Keep the name out of the repository.

**6. Install the autopilot on the server.**

```bash
git clone --branch main git@github-flyshi:777LVB777/flyshi-research.git ~/flyshi-autopilot/publish
mkdir -p ~/flyshi-autopilot/bin ~/.config/flyshi-autopilot
cp ~/flyshi-autopilot/publish/scripts/cloud/autopilot/{autopilot.py,project_steps.py} ~/flyshi-autopilot/bin/
cp ~/flyshi-autopilot/publish/scripts/cloud/autopilot/config.example.json ~/.config/flyshi-autopilot/config.json
chmod 600 ~/.config/flyshi-autopilot/config.json
nano ~/.config/flyshi-autopilot/config.json   # ntfy_topic, git_user_email
python3 ~/flyshi-autopilot/bin/autopilot.py notify-test
```

The phone should show "flyshi autopilot: notifications work".

**7. Run the simulation test.**

On the Mac:

```bash
cd ~/Projects/flyshi-research
python3 scripts/cloud/autopilot/autopilot.py --simulate
```

On the server, after step 6:

```bash
python3 ~/flyshi-autopilot/bin/autopilot.py --simulate
```

- It runs the whole state machine in a new temporary folder:
  - fake job folders and a fake clock;
  - a phase 1 launcher that dies once;
  - fake verdicts;
  - a local bare repository instead of GitHub.
- It reads no real result, starts no simulation, sends no ntfy message and makes no
  network request.
- It ends with **SIMULATION OK** and prints the notifications it would have sent.
- `--sim-rule do-not-run`, `--sim-rule run-regardless` and `--sim-rule none` try the
  other rule cases.

**8. Install and enable the service.**

```bash
cp ~/flyshi-autopilot/publish/scripts/cloud/autopilot/flyshi-autopilot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now flyshi-autopilot
systemctl status flyshi-autopilot
tail -f ~/flyshi-autopilot/autopilot.log
python3 ~/flyshi-autopilot/bin/autopilot.py status
```

- It starts at boot and restarts after a failure.
- `KillMode=process` means stopping the service never stops a launcher.

**9. When notified, act as follows.**

- **Waiting …**: a condition that is yours to meet (the tag, the rule, the inputs,
  the sign-off). The autopilot checks again every 5 minutes.
- **HALTED …**: something failed or a guard fired. The reason is in the message and
  in `~/flyshi-autopilot/autopilot.log`. Fix it, then run
  `python3 ~/flyshi-autopilot/bin/autopilot.py resume`.
- **Phase 2 budget stop**: no new job starts and no verdict is computed, because it
  needs all 120 jobs. To continue, raise `spend_stop_usd` in the config, delete
  `data/polymarket/phase2_0777ae92f0dd/STOP_LAUNCHING`, then `resume`.

**10. After "SAFE TO DELETE THE SERVER": copy the private Phase 2 job files, then delete.**

The Phase 2 run directory exists only on the server. It holds the job files,
chains, comparator, manifest and logs. Copy it to the Mac with this one command,
which the SAFE notification also contains:

```bash
scp -r flyshi:flyshi-research/data/polymarket/phase2_0777ae92f0dd ~/Projects/flyshi-research/data/polymarket/
```

Then delete the server yourself (server-setup.md, Step 12), remove the deploy key on
GitHub, and unsubscribe from the ntfy topic.

## Conflicts with running unattended

1. **Whether Phase 2 runs given the Phase 1 verdict: resolved by Section 12
   (2026-10-17).**
   - The preregistration had no such rule. Section 12, added now, says Phase 2 runs
     regardless, with the marker line `run-regardless`.
   - It must be pushed before Phase 1 finishes, to be true as written (step 1).
   - With no marker, or an unclear one, the autopilot would still wait and notify,
     never guess.
2. **Drive check sign-off.** "The owner signs off on the drive check before any job
   runs" (Section 10, step 3) is a human decision.
   - You made it on your Mac, for this file (`docs/records/phase2_build_signoff.md`).
     The autopilot accepts that record (step 4) and re-runs `drive_check.py` on the
     server.
   - It does not judge the drive flags. If the server's report differed from the
     one you signed, it would still go ahead, because the exit status covers only
     structure, counts, timestamps and look-ahead.
   - The report is saved under `data/polymarket/` on the server.
3. **More than the market file is needed.**
   - `--prepare` needs the fill plan.
   - `drive_check.py` needs the frozen list, its hash and the histories. The
     histories contain prices; they stay under the git-ignored `data/` on the
     server.
4. **`finish_day.py` is written for the Mac.** On the server:
   - step (b), the pull, becomes a re-check of the files in place, so there is no
     off-server copy until the push;
   - its "SAFE TO DELETE THE SERVER" line is ignored, because the server is still
     needed for Phase 2;
   - it never commits or pushes itself; the autopilot runs its printed commands and
     adds the push.
5. **Results go to `main`.** `backup_results.py push` was designed to push only to
   `results-backup/a325e6b206`, never to `main`. The autopilot pushes finish_day's
   commit to `main`, as you asked.
6. **The main tree is moved, once.**
   - After Phase 1 is pushed, `~/flyshi-research` is moved to the commit of
     `phase2-frozen` (detached) with `checkout -f`. Any untracked file that would be
     replaced is first checked to be identical.
   - It is moved only to the tag, never to the results commit. Moving to the results
     commit first and then to the tag would make git delete the now-tracked job
     files from the working tree.
   - It halts if a tracked file was changed on the server, for example a tracked
     run log written there. A later `git pull` there needs `git checkout main`
     first.
7. **`--finish-phase1` also runs the frozen code.** Because the main tree moves
   only to the tag, the Phase 1 verdict is computed with the code of
   `phase2-frozen`, not with the older commit the sweep ran on. The verdict code
   was written before any Phase 1 result was read (synthetic-market-experiment.md,
   2026-10-12 revision), and the tag must contain it.
8. **The 12 h "no job finished" alarm.** A job takes about 9.4 h, so a normal
   cycle stays under 12 h. Network builds and staggered starts add a little, and a
   job slower than about 12 h would raise it.
9. **The budget thresholds.**
   - Design A is about 282 h, or $75. The $85 warning comes at about 320 h, and the
     $95 stop at about 357 h.
   - That leaves about 75 h for restarts (each can lose up to 9.4 h of up to 4 jobs)
     and slower runs.
   - A stopped Phase 2 has no preregistered analysis: the verdict needs all 120
     jobs. The autopilot halts and leaves the decision to you.
   - The estimate is wall-clock time from the Phase 2 launch. It does not count the
     server hours before it.
10. **The data guard covers Phase 2 only.** Phase 1 job files hold per-market rows of
    synthetic markets, and finish_day normally commits them. The per-market check
    therefore applies to Phase 2 commits only. The `data/` check and the private
    file names apply to every commit.
11. **Phase 1 restart after a reboot.**
    - The run plan restarts the launcher by hand in tmux. The autopilot restarts it
      itself, with the same arguments, logging to `~/flyshi-autopilot/logs/`.
    - It gives up and halts after 3 restarts without a job finishing.
    - It never stops a launcher (the run plan allows only Ctrl+C).
12. **"SAFE" means the pushed files are verified, not that nothing is lost.**
    Phase 2's job files, chains and comparator are private and are never pushed.
    Deleting the server deletes them, and rebuilding them means re-running Phase 2
    (about $75). Step 10, and the SAFE notification itself, give the one scp
    command that copies them.
13. **Verdict output.**
    - When all 120 jobs exist, the Phase 2 launcher computes the verdict itself and
      prints `success: …` to its log under `data/`.
    - `--finish-phase1` and `--finish` print the full verdict JSON, which the
      autopilot discards. The same aggregates are committed.
    - The autopilot itself reads only `readings.overall` from the two verdict files.
14. **Root and the deploy key.** The server runs as root (server-setup.md), so the
    service runs as root. Anyone with root on the server can push to the repository
    until you remove the deploy key.
