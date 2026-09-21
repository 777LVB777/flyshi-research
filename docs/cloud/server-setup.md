# Running the simulations on a rented server: step by step

This guide is for someone who has never rented a server. It covers the whole
cycle: create a Hetzner Cloud server, log in safely, lock it down, install the
project, run the learning test so it survives a dropped connection, copy the
results home, and **delete the server**.

The server is **disposable**. Everything that matters lives in Git and on your Mac.
If anything on the server goes wrong, delete it and start again from Step 1.

**Status:** written 2026-09-21, **not yet tried on a real server.** Console menu names
may differ slightly from what is written here. Commands marked *(on the server)* are
standard Ubuntu commands, but they have not been run on this project's server.

---

## Who does what

| You must do these personally | An AI agent can do these (with your approval) |
|---|---|
| Create the Hetzner account, add payment, pass identity checks | Harden SSH (Step 7) |
| Create your SSH key on your Mac, keeping the private key private | Enable the server's firewall (Step 6) |
| Add the public key to Hetzner and create the server (Steps 2–3) | Run `setup.sh` and read its output (Step 8) |
| Create the Hetzner Cloud Firewall (Step 4) | Start the run in tmux and check progress (Steps 9–10) |
| The first login, confirming it really is your server (Step 5) | Copy results back and prepare a commit for you to review (Step 11) |
| **Delete the server** (Step 12) | |
| Approve every commit and push | |

**Never give an AI agent:**

- your Hetzner password;
- a Hetzner API token;
- payment details;
- the *contents* of your private key (`~/.ssh/id_ed25519`, the file **without** `.pub`).

An agent running on your Mac (for example Claude Code) can work on the server by
running `ssh flyshi '<command>'` (Step 5 sets up the name `flyshi`). It uses your key
through macOS's SSH agent, without ever reading the key file. **Deleting the server
is your job:** it is the step that stops the billing, and you should see it done
with your own eyes.

---

## Before you start (on your Mac)

The server downloads the project from GitHub, so **the scripts it needs must be
pushed to GitHub first**:

- `scripts/cloud/setup.sh`
- `repro/mushroom_body/launch_first_learning_parallel.py`
- `repro/mushroom_body/report_first_learning.py`
- the updated `run_first_learning_test.py` and `first_learning.py`

Check on github.com that they are there on the `main` branch.

## Step 1 — Hetzner account *(you)*

1. Sign up at the Hetzner Cloud Console (console.hetzner.cloud), add a payment
   method, and complete any identity check they ask for.
2. Create a **Project** (for example "flyshi"). Servers live inside projects.

## Step 2 — Create an SSH key and give Hetzner the public half *(you, on your Mac)*

An SSH key is a pair of files: a **private key** that never leaves your Mac, and a
**public key** that you can share freely. The server lets in only whoever holds
the private key. That is much safer than a password.

```bash
ls ~/.ssh/id_ed25519.pub   # already have one? then skip the next line
ssh-keygen -t ed25519 -C "flyshi-server"
```

Press Enter to accept the file name. **Choose a passphrase**; it protects the key if
your Mac is ever stolen. Then store the passphrase in the macOS keychain, so neither
you nor an agent has to type it again:

```bash
ssh-add --apple-use-keychain ~/.ssh/id_ed25519
```

Show the **public** key and copy it:

```bash
cat ~/.ssh/id_ed25519.pub     # one line starting with "ssh-ed25519"
```

In the Hetzner console: **Security → SSH Keys → Add SSH Key**, paste that line and
name it. (Never paste the file without `.pub` anywhere.)

## Step 3 — Create the server *(you)*

In your project, click **Add Server** (or **Create Server**) and choose:

- **Location:** any. Nuremberg, Falkenstein or Helsinki are in the EU.
- **Image:** Ubuntu 24.04.
- **Type:** Dedicated vCPU → **CCX33** (8 vCPU, 32 GB), recommended in
  [`cost-estimate.md`](cost-estimate.md). **Check the hourly price shown.**
- **SSH keys:** tick the key from Step 2. Hetzner then sets no root password, so
  only your key can log in.
- **Firewall:** you can create it here, or in Step 4.
- **Name:** e.g. `flyshi-1`.

Create it and note the **IPv4 address** shown (e.g. `203.0.113.7`). **Billing starts
now** and continues until you delete the server (Step 12).

## Step 4 — Cloud firewall that allows only SSH *(you)*

**Firewalls → Create Firewall.** Inbound rules: keep only **TCP, port 22** (SSH).
Delete any other inbound rules, apart from ICMP (ping), which is harmless to keep.
For extra safety, set the source to your own IP address; if your home IP changes,
you will then need to edit the rule. Leave outbound rules at their default (allow
all), because the server must download software. Under **Apply to**, select your
server.

Step 6 adds a second firewall on the server itself, so a mistake in one is caught by
the other.

## Step 5 — First login *(you)*

On your Mac, give the server a short name. Add this to `~/.ssh/config`, creating the
file if needed and using your IP:

```
Host flyshi
    HostName 203.0.113.7
    User root
    IdentityFile ~/.ssh/id_ed25519
    UseKeychain yes
    AddKeysToAgent yes
    ServerAliveInterval 60
```

Then:

```bash
ssh flyshi
```

The first time, SSH asks whether you trust the server's fingerprint. Type `yes`.
(A newly created server has no other record to compare against. If this message
ever appears again for the same server, stop and find out why.) You now have a
prompt like `root@flyshi-1:~#`: you are on the server.

**Logging in as `root`**, the all-powerful administrator account, is acceptable here
because the server is disposable, holds no secrets, and only your key can log in. If
you keep a server for longer, create a normal user instead.

## Step 6 — Update the system and turn on the firewall *(agent can do; on the server)*

```bash
apt-get update && apt-get -y upgrade
ufw allow OpenSSH        # FIRST allow SSH ...
ufw --force enable       # ... THEN switch the firewall on
ufw status verbose       # should show 22/tcp ALLOW, everything else denied
```

The order matters: enabling the firewall before allowing SSH would lock you out.
If that happens, the server is disposable: delete it and start again.

If `apt-get upgrade` says a restart is required, run `reboot`. Wait a minute, then
`ssh flyshi` again.

## Step 7 — Turn off password login *(agent can do; on the server)*

Your key already works. This makes sure nobody can even *try* a password.

```bash
cat > /etc/ssh/sshd_config.d/00-flyshi-hardening.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh
sshd -T | grep -Ei 'passwordauthentication|kbdinteractive|permitrootlogin'
```

The last command should print `passwordauthentication no`,
`kbdinteractiveauthentication no` and `permitrootlogin without-password` (the same
thing as `prohibit-password`). The file name starts with `00-` on purpose: SSH uses
the *first* value it reads, and Ubuntu may ship a `50-cloud-init.conf` that turns
passwords on.

**Before closing this window, test in a NEW terminal on your Mac** that `ssh flyshi`
still works. If it does not, fix the problem from the window that is still open.

## Step 8 — Install the project *(agent can do; on the server)*

Start tmux first (Step 9 explains it), because setup takes a while:

```bash
tmux new -s setup
apt-get install -y git
git clone https://github.com/777LVB777/flyshi-research.git ~/flyshi-research
bash ~/flyshi-research/scripts/cloud/setup.sh
```

`setup.sh` does the following:

1. Installs the C++ compiler and tools.
2. Installs `uv`.
3. Clones the pinned upstream model and FlyWire annotations.
4. Creates both Python environments with the exact pinned versions.
5. Runs every unit test, a Brian2 compile check, and `fast_runner.py --self-test`.
   It simulates no fly brain.

It ends with **SETUP COMPLETE**. If it fails, it names the step that failed. Fix the
cause and run the same command again; finished steps are skipped.

## Step 9 — Run the learning test inside tmux *(agent can do; on the server)*

**tmux** keeps programs running on the server after you disconnect: closing the
laptop or losing Wi-Fi does not stop the run.

| What | Keys / command |
|---|---|
| start a session | `tmux new -s fly` |
| leave it running and disconnect | press **Ctrl-b**, release, then press **d** |
| come back later (after `ssh flyshi`) | `tmux attach -t fly` |
| list sessions | `tmux ls` |

Inside tmux:

```bash
cd ~/flyshi-research
.venv-shiu/bin/python repro/mushroom_body/run_first_learning_test.py --dry-run
.venv-shiu/bin/python repro/mushroom_body/launch_first_learning_parallel.py --dry-run
```

The second command shows the RAM it found and how many processes it will run
(expect 5 on CCX33), plus a time estimate. If that looks right, start it:

```bash
.venv-shiu/bin/python repro/mushroom_body/launch_first_learning_parallel.py
```

Then detach (Ctrl-b, d). **Measure first:** before relying on the estimate, you may
want to time a smoke run
(`... launch_first_learning_parallel.py --smoke`; not the pre-stated test, and it
writes to a separate folder).

## Step 10 — Check progress *(agent can do)*

From your Mac, without attaching:

```bash
ssh flyshi 'cd ~/flyshi-research && .venv-shiu/bin/python repro/mushroom_body/run_first_learning_test.py --list-jobs'
ssh flyshi 'free -h'                                   # memory in use
ssh flyshi 'ls ~/flyshi-research/repro/mushroom_body/results/logs_first_learning_*/'
```

If the launcher stops, or the server reboots, run the same launcher command again
inside tmux. Finished jobs are skipped, and an interrupted training job resumes from
its last presentation. At the end the launcher prints the verdict.

## Step 11 — Copy the results home *(agent can do; you commit)*

**Recommended: pull the results to your Mac with rsync**, so the server never needs
GitHub credentials. On your Mac, from the project folder:

```bash
rsync -av flyshi:flyshi-research/repro/mushroom_body/results/ repro/mushroom_body/results/
.venv-shiu/bin/python repro/mushroom_body/report_first_learning.py
git status        # new first_learning_<hash>/ and logs_first_learning_<hash>/ folders
```

Check that the report on your Mac shows the same verdict the server printed. Then
commit and push from your Mac as usual. The results folder is well under 1 MB.

*(Alternative: commit and push from the server. That needs a GitHub credential
on the server, such as a deploy key with write access, which you must create
yourself and remove afterwards. It is more steps and more risk, so it is not
recommended here.)*

**Do not delete the server until the results are on your Mac and pushed to GitHub.**

## Step 12 — DELETE the server *(you)*

**Powering the server off does NOT stop billing.** Hetzner keeps charging for a
server as long as it exists.

1. Hetzner console → your project → the server → **Delete**, and confirm.
2. Check that the **Servers** list is empty. Also delete anything else you created
   and no longer need: snapshots, backups, volumes, and a kept **Primary IP**. Each of
   these can be billed on its own. The firewall rule set costs nothing, and you can
   reuse it.
3. On your Mac, forget the old server's fingerprint, so a future server that gets
   the same IP address does not trigger a warning:

   ```bash
   ssh-keygen -R 203.0.113.7
   ```

   Also remove the `Host flyshi` block from `~/.ssh/config`, or update its IP address
   next time.
4. A day later, glance at **Billing / Usage** in the console to confirm nothing is
   still running.

---

## If something goes wrong

- **Locked out (SSH refuses you):** the server is disposable. Delete it and repeat
  from Step 3. (Hetzner's browser console is an alternative, but only after you
  reset the root password in the Hetzner console; recreating the server is simpler.)
- **`setup.sh` fails:** the message names the step. Common causes are a network
  hiccup (just re-run) or a package version with no Linux build (tell your
  collaborator or agent the exact message).
- **Out of memory** (jobs fail and the logs mention `Killed` or `MemoryError`):
  re-run the launcher with fewer processes, e.g. `--max-procs 3`, or with a larger
  budget, e.g. `--gb-per-proc 6`.
- **Something looks wrong with the results:** do not re-run with changed settings.
  The settings are fixed in the pre-stated test. Copy everything home and discuss
  it first.
