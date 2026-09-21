#!/usr/bin/env bash
# Prepare a fresh Ubuntu server to run the flyshi-research simulations.
#
#   bash setup.sh                  # clones the repo into ~/flyshi-research, then sets it up
#   bash scripts/cloud/setup.sh    # run from inside an existing clone: sets up that clone
#
# Safe to re-run: every step checks whether it is already done. Stops at the first
# error and says which step failed. Does NOT run any simulation of the fly brain; the
# final checks are the unit tests, fast_runner.py --self-test (tiny synthetic
# networks), and a 1-neuron Brian2 compile check proving the C++ toolchain works.
#
# Settings (environment variables, all optional):
#   REPO_URL    default https://github.com/777LVB777/flyshi-research.git (public)
#   REPO_DIR    default ~/flyshi-research (ignored when run from inside a clone)
#   REPO_REF    branch/commit to check out on FIRST clone only (default: the default branch)
#
# UNVERIFIED until run on a real server: that every pinned wheel installs on Linux
# x86-64 (all pins come from a macOS arm64 environment), that uv ${UV_VERSION} offers
# CPython ${PY_SHIU} and ${PY_MAIN}, and the versioned uv installer URL.

set -Eeuo pipefail

UV_VERSION="0.12.15"   # the uv used on the development Mac
PY_MAIN="3.11"         # .venv: core package (no numpy)
PY_SHIU="3.10.21"      # .venv-shiu: exact CPython of the development Mac's model venv
PYTEST_VERSION="9.1.1" # the pytest installed in the development venvs
UPSTREAM_URL="https://github.com/philshiu/Drosophila_brain_model"
UPSTREAM_COMMIT="91bdd1e7dcf193f3e7ca5a8933497fcef63b7960"
ANNOT_URL="https://github.com/flyconnectome/flywire_annotations"
ANNOT_TAG="v3.1.0"
ANNOT_COMMIT="8587524c1748ce5ef2080822a2fc890fc03bf597"
REPO_URL="${REPO_URL:-https://github.com/777LVB777/flyshi-research.git}"

STEP="starting"
step() { STEP="$1"; printf '\n==> %s\n' "$1"; }
fail() { printf '\nSETUP FAILED during step: %s\n  %s\n' "$STEP" "$1" >&2; exit 1; }
trap 'printf "\nSETUP FAILED during step: %s\n  command: %s (line %s, exit %s)\nFix the cause and re-run; finished steps are skipped.\n" "$STEP" "$BASH_COMMAND" "$LINENO" "$?" >&2' ERR

[ "$(uname -s)" = "Linux" ] || fail "this script is for a Linux (Ubuntu) server; this is $(uname -s)"
if [ "$(id -u)" -eq 0 ]; then SUDO=""; else SUDO="sudo"; fi

# ---------------------------------------------------------------------------
step "1/9 system packages (compiler, git, tmux, rsync)"
PKGS=(build-essential g++ git curl ca-certificates tmux rsync)
missing=()
for p in "${PKGS[@]}"; do dpkg -s "$p" >/dev/null 2>&1 || missing+=("$p"); done
if [ "${#missing[@]}" -gt 0 ]; then
  # a fresh server often runs unattended-upgrades first; wait for its lock (up to 10 min)
  $SUDO apt-get -o DPkg::Lock::Timeout=600 update
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 install -y "${missing[@]}"
else
  echo "already installed: ${PKGS[*]}"
fi
g++ --version | head -1

# ---------------------------------------------------------------------------
step "2/9 uv ${UV_VERSION}"
export PATH="$HOME/.local/bin:$PATH"
if command -v uv >/dev/null 2>&1 && uv --version | grep -q " ${UV_VERSION}"; then
  echo "already installed: $(uv --version)"
else
  curl -LsSf "https://astral.sh/uv/${UV_VERSION}/install.sh" | sh
  command -v uv >/dev/null 2>&1 || fail "uv installed but not on PATH (expected in ~/.local/bin)"
  uv --version | grep -q " ${UV_VERSION}" || fail "expected uv ${UV_VERSION}, got $(uv --version)"
fi

# ---------------------------------------------------------------------------
step "3/9 repository"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if git -C "$SCRIPT_DIR" rev-parse --show-toplevel >/dev/null 2>&1 \
   && [ -f "$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)/repro/shiu2024/requirements-lock.txt" ]; then
  ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel)"
  echo "using the clone this script is in: $ROOT"
else
  ROOT="${REPO_DIR:-$HOME/flyshi-research}"
  if [ -d "$ROOT/.git" ]; then
    echo "already cloned: $ROOT"
  elif [ -e "$ROOT" ]; then
    fail "$ROOT exists but is not a git clone; move it away or set REPO_DIR"
  else
    git clone "$REPO_URL" "$ROOT"
    [ -z "${REPO_REF:-}" ] || git -C "$ROOT" checkout "$REPO_REF"
  fi
fi
cd "$ROOT"
# an existing clone is never pulled, reset or changed: that is the user's decision
echo "repo HEAD: $(git rev-parse HEAD) ($(git rev-parse --abbrev-ref HEAD))"
[ -z "$(git status --porcelain --untracked-files=no)" ] || echo "note: the clone has uncommitted changes"

# ---------------------------------------------------------------------------
# pinned third-party checkout: clone if missing, then require exactly the pinned commit
pin_checkout() {  # url dir commit [tag]
  local url="$1" dir="$2" commit="$3" tag="${4:-}"
  if [ ! -d "$dir/.git" ]; then
    [ ! -e "$dir" ] || fail "$dir exists but is not a git clone; remove it and re-run"
    mkdir -p "$(dirname "$dir")"
    git clone "$url" "$dir"
  fi
  if [ "$(git -C "$dir" rev-parse HEAD)" != "$commit" ]; then
    [ -z "$(git -C "$dir" status --porcelain)" ] || fail "$dir has local changes; cannot move it to $commit"
    git -C "$dir" fetch --tags origin
    git -C "$dir" -c advice.detachedHead=false checkout "$commit"
  fi
  [ "$(git -C "$dir" rev-parse HEAD)" = "$commit" ] || fail "$dir is not at pinned commit $commit"
  if [ -n "$tag" ]; then
    [ "$(git -C "$dir" rev-parse "${tag}^{commit}")" = "$commit" ] \
      || fail "tag $tag in $dir does not point at $commit"
  fi
  echo "$dir at $commit${tag:+ (tag $tag)}"
}

step "4/9 upstream Shiu et al. model at ${UPSTREAM_COMMIT:0:7}"
pin_checkout "$UPSTREAM_URL" third_party/Drosophila_brain_model "$UPSTREAM_COMMIT"
for f in Connectivity_783.parquet Completeness_783.csv model.py utils.py; do
  [ -s "third_party/Drosophila_brain_model/$f" ] || fail "upstream file missing: $f"
done
# (git verifies file contents against the pinned commit; the large files are not read here)

step "5/9 FlyWire annotations ${ANNOT_TAG}"
pin_checkout "$ANNOT_URL" third_party/flywire_annotations "$ANNOT_COMMIT" "$ANNOT_TAG"
[ -s third_party/flywire_annotations/supplemental_files/Supplemental_file1_neuron_annotations.tsv ] \
  || fail "annotation TSV missing"

# ---------------------------------------------------------------------------
# create a venv only if absent; an existing one must have the right Python
ensure_venv() {  # dir version
  local dir="$1" want="$2" have
  if [ -x "$dir/bin/python" ]; then
    have="$("$dir/bin/python" -c 'import platform; print(platform.python_version())')"
    case "$have" in
      "$want"|"$want".*) echo "already exists: $dir (Python $have)";;
      *) fail "$dir has Python $have, expected $want; delete $dir and re-run";;
    esac
  else
    uv venv "$dir" --python "$want"
  fi
}

step "6/9 .venv (Python ${PY_MAIN}, core package + pytest)"
ensure_venv .venv "$PY_MAIN"
uv pip install --python .venv/bin/python -e . "pytest==${PYTEST_VERSION}"

step "7/9 .venv-shiu (Python ${PY_SHIU}, pinned model environment)"
ensure_venv .venv-shiu "$PY_SHIU"
LOCK=repro/shiu2024/requirements-lock.txt
grep -qx "cython==0.29.33" "$LOCK" || fail "$LOCK no longer pins cython==0.29.33"
grep -qx "setuptools==67.8.0" "$LOCK" || fail "$LOCK no longer pins setuptools==67.8.0"
uv pip install --python .venv-shiu/bin/python -r "$LOCK"
# the package itself without dependencies, so nothing can move a pinned version
uv pip install --python .venv-shiu/bin/python --no-deps -e .
uv pip install --python .venv-shiu/bin/python "pytest==${PYTEST_VERSION}"
# every pin must still hold after the extra installs
.venv-shiu/bin/python - "$LOCK" <<'PY'
import sys
from importlib.metadata import version, PackageNotFoundError
bad = []
for line in open(sys.argv[1]):
    line = line.split("#")[0].strip()
    if not line:
        continue
    name, want = line.split("==")
    try:
        have = version(name)
    except PackageNotFoundError:
        have = None
    if have != want:
        bad.append(f"{name}: want {want}, have {have}")
if bad:
    sys.exit("pinned versions not installed:\n  " + "\n  ".join(bad))
print("all", sum(1 for l in open(sys.argv[1]) if l.strip()), "pins installed exactly")
PY

# ---------------------------------------------------------------------------
step "8/9 tests"
.venv-shiu/bin/python -m pytest tests/ -q
.venv/bin/python -m pytest tests/ -q

step "9/9 smoke checks (no fly-brain simulation)"
# Brian2 silently falls back to slow numpy code if Cython/C++ is broken (this happened
# during the original macOS setup), so require the Cython target on a 1-neuron network.
( cd "$(mktemp -d)" && "$ROOT/.venv-shiu/bin/python" - <<'PY'
from brian2 import NeuronGroup, run, ms, prefs
prefs.codegen.target = "cython"   # raises instead of falling back to numpy
G = NeuronGroup(1, "dv/dt = -v / (10*ms) : 1")
run(1 * ms)
print("Brian2 Cython code generation works (C++ compiler OK)")
PY
)
.venv-shiu/bin/python repro/mushroom_body/fast_runner.py --self-test

printf '\nSETUP COMPLETE in %s\n' "$ROOT"
printf '  repo %s | upstream %s | annotations %s\n' \
  "$(git rev-parse --short HEAD)" "${UPSTREAM_COMMIT:0:7}" "$ANNOT_TAG"
printf '  RAM %s | cores %s\n' "$(free -h | awk '/^Mem:/ {print $2 " total, " $7 " available"}')" "$(nproc)"
printf 'Next: start tmux, then\n  .venv-shiu/bin/python repro/mushroom_body/launch_first_learning_parallel.py --dry-run\n'
