"""Reusable-network fast path for repeated KC-direct simulations.

Upstream `model.py` rebuilds the whole Brian2 network from the connectivity
parquet on EVERY trial (run_trial -> create_model). This module builds the
network ONCE and resets neuron/monitor/clock state between trials with Brian2
store()/restore(), while keeping synaptic weights and letting the RNG stream
advance across trials (matching the existing path's seed-once behaviour).

It leaves the existing path (check_mb_response.py / run_single_cue.py) untouched,
so those remain the reproducible reference. Equivalence criteria and commands are
in docs/design/fast-runner.md.

Stimulation is delivered by a PoissonGroup + one-to-one input synapses (not
upstream's per-neuron PoissonInput), so the stimulated set and rate can be
changed between runs WITHOUT rebuilding the 15M-synapse network. That input
mechanism differs from upstream's, which is why bit-identical output is not
expected (see docs). The heavy neuron/synapse construction reuses upstream
create_model() verbatim, so the network itself is built identically.

Two entry points:
  * run_cue(...)        one SCALAR rate for the whole stimulated set (original path);
  * run_cue_rates(...)  a PER-NEURON rate for each stimulated neuron, which is what
                        the learning encoder produces (Stimulus.rates_by_kc_id()).
run_cue is unchanged; run_cue_rates has the same seeding, reset and weight-
persistence behaviour (see docs/design/fast-runner.md, section 6).

Running the real model IS a simulation: run it yourself (see --help / the docs).
Only --self-test (tiny synthetic networks, never net.run) is executed during
preparation.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from time import perf_counter

import numpy as np
import pandas as pd

import check_mb_response as mbr
from brian2 import Hz, mV, ms, volt, seed as brian_seed, PoissonGroup, Synapses, Network
import model as shiu_model
from model import default_params
import utils as utl


# ----------------------------------------------------------------------------
# network build (once) + per-trial reset run
# ----------------------------------------------------------------------------
def build_network(params: dict, path_comp: Path, path_con: Path) -> dict:
    """Build the reusable network ONCE. Returns a bundle dict. Times the build."""
    t0 = perf_counter()
    # Reuse upstream construction verbatim so the neuron/synapse network is
    # byte-for-byte the same as the existing path.
    neu, syn, spk_mon = shiu_model.create_model(str(path_comp), str(path_con), params)
    # Retargetable Poisson drive: one Poisson source per neuron, one-to-one
    # synapse adding weight to v (same target_var and weight as upstream poi()).
    n = len(neu)
    pin = PoissonGroup(n, rates=0 * Hz, name="stim_poisson")
    syn_in = Synapses(
        pin, neu, on_pre="v_post += w_in",
        namespace={"w_in": params["w_syn"] * params["f_poi"]},
        name="stim_synapses",
    )
    syn_in.connect(j="i")  # source i -> neuron i
    net = Network(neu, syn, spk_mon, pin, syn_in)
    # snapshot pristine state (v=v_0, g=0, rfc=t_rfc, weights, empty monitor, t=0)
    net.store("init")
    build_seconds = perf_counter() - t0

    df_comp = pd.read_csv(path_comp, index_col=0)
    i2flyid = {i: int(j) for i, j in enumerate(df_comp.index)}
    flyid2i = {j: i for i, j in i2flyid.items()}

    return {
        "net": net, "neu": neu, "syn": syn, "spk_mon": spk_mon, "pin": pin,
        "n": n, "i2flyid": i2flyid, "flyid2i": flyid2i, "params": params,
        "build_seconds": build_seconds,
    }


def run_cue(bundle: dict, stim_flyids: list[int], rate_hz: float, n_trials: int,
            base_seed: int, exp_name: str) -> tuple[pd.DataFrame, dict]:
    """Run `n_trials` of one cue on the prebuilt network, resetting state between
    trials but PRESERVING synaptic weights (so later learned weights survive).

    Returns (spikes_df matching upstream construct_dataframe, timing dict).
    """
    net, neu, syn, spk_mon, pin = (
        bundle["net"], bundle["neu"], bundle["syn"], bundle["spk_mon"], bundle["pin"]
    )
    params, i2flyid, n = bundle["params"], bundle["i2flyid"], bundle["n"]
    flyid2i = bundle["flyid2i"]

    stim_idx = np.array([flyid2i[f] for f in stim_flyids if f in flyid2i], dtype=int)
    rates_vec = np.zeros(n)
    rates_vec[stim_idx] = rate_hz

    # Seed ONCE before the trial loop, exactly like the existing path
    # (check_mb_response.run_condition sets np.random.seed + brian_seed once,
    # then trials advance the same stream). restore(restore_random_state=False,
    # the default) does NOT reset the RNG, so the stream advances across trials.
    np.random.seed(base_seed)
    brian_seed(base_seed)

    ids, ts, nrun = [], [], []
    sim_seconds = []
    for trial in range(n_trials):
        # Preserve current (possibly learned) weights across the state reset.
        # np.array() strips Brian2 units (values are in volt/SI), so reapply * volt.
        weights_now = np.array(syn.w[:])
        net.restore("init")                       # resets v/g/rfc/clock/monitor; NOT rng, NOT (re)applied weights
        syn.w[:] = weights_now * volt             # re-apply -> weights persist (no-op when unchanged)
        # (re)apply stimulation for this cue
        pin.rates = rates_vec * Hz
        neu.rfc = params["t_rfc"]
        neu.rfc[stim_idx] = 0 * ms                # Poisson targets have no refractory (upstream poi())
        t0 = perf_counter()
        net.run(params["t_run"])
        sim_seconds.append(perf_counter() - t0)
        # collect this trial's spikes
        i_arr = np.asarray(spk_mon.i[:])
        t_arr = np.asarray(spk_mon.t[:])
        ids.extend(int(x) for x in i_arr)
        ts.extend(float(x) for x in t_arr)
        nrun.extend(trial for _ in i_arr)

    spikes = pd.DataFrame({
        "t": ts, "trial": nrun,
        "flywire_id": [i2flyid[i] for i in ids],
        "exp_name": exp_name,
    })
    timing = {"build_seconds": bundle["build_seconds"],
              "sim_seconds_per_trial": sim_seconds,
              "sim_seconds_total": float(sum(sim_seconds))}
    return spikes, timing


# ----------------------------------------------------------------------------
# per-neuron-rate variant (added for the learning encoder; run_cue is untouched)
# ----------------------------------------------------------------------------
def rate_vector(flyid2i: dict, rates_by_flyid: dict, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Dense per-neuron rate vector (Hz) and the indices of DRIVEN neurons.

    ``rates_by_flyid`` maps FlyWire root ID -> Hz. Stricter than run_cue, which
    silently skips IDs it cannot find: here an unknown ID, a non-integer ID key
    (float64 cannot hold 64-bit root IDs exactly), or a negative/non-finite rate
    raises, because a silently dropped stimulus would corrupt an experiment.
    Neurons at exactly 0 Hz are NOT driven: they are left out of the returned
    indices, so (as with run_cue) only neurons that actually receive Poisson
    input get their refractory period cleared.
    """
    vec = np.zeros(n)
    for fid, rate in rates_by_flyid.items():
        if not isinstance(fid, (int, np.integer)):
            raise TypeError(f"root IDs must be integers, got {type(fid).__name__} {fid!r}")
        if int(fid) not in flyid2i:
            raise ValueError(f"root ID {int(fid)} is not in the network")
        r = float(rate)
        if not np.isfinite(r) or r < 0:
            raise ValueError(f"rate for {int(fid)} must be finite and >= 0, got {rate!r}")
        vec[flyid2i[int(fid)]] = r
    return vec, np.flatnonzero(vec > 0)


def _apply_trial_state(bundle: dict, rates_vec: np.ndarray, stim_idx: np.ndarray) -> None:
    """Everything run_cue does at the top of a trial, up to (not including) net.run:
    save current weights, restore the pristine state, re-apply the weights, then set
    the per-neuron Poisson rates and clear the refractory period of driven neurons.
    Kept separate so --self-test can exercise it without running a simulation."""
    net, neu, syn, pin, params = (
        bundle["net"], bundle["neu"], bundle["syn"], bundle["pin"], bundle["params"]
    )
    weights_now = np.array(syn.w[:])
    net.restore("init")                       # resets v/g/rfc/clock/monitor; NOT rng, NOT (re)applied weights
    syn.w[:] = weights_now * volt             # re-apply -> weights persist (no-op when unchanged)
    pin.rates = rates_vec * Hz                # one rate PER NEURON (this is the new part)
    neu.rfc = params["t_rfc"]
    neu.rfc[stim_idx] = 0 * ms                # Poisson targets have no refractory (upstream poi())


def run_cue_rates(bundle: dict, rates_by_flyid: dict, n_trials: int,
                  base_seed: int, exp_name: str) -> tuple[pd.DataFrame, dict]:
    """Per-neuron-rate twin of run_cue: each stimulated neuron gets ITS OWN rate.

    ``rates_by_flyid``: {FlyWire root ID: Hz}, e.g. ``Stimulus.rates_by_kc_id()``
    from flyshi_research.learning.encoder. Seeding (once, before the trial loop),
    per-trial store()/restore() reset, weight preservation across resets, spike
    collection and return values are the same as run_cue. With every rate equal,
    the operations are the same as run_cue's, so results are EXPECTED to match it
    for the same seed (UNVERIFIED: needs one real paired run to confirm).
    """
    net, spk_mon = bundle["net"], bundle["spk_mon"]
    params, i2flyid, n = bundle["params"], bundle["i2flyid"], bundle["n"]
    rates_vec, stim_idx = rate_vector(bundle["flyid2i"], rates_by_flyid, n)

    np.random.seed(base_seed)
    brian_seed(base_seed)

    ids, ts, nrun = [], [], []
    sim_seconds = []
    for trial in range(n_trials):
        _apply_trial_state(bundle, rates_vec, stim_idx)
        t0 = perf_counter()
        net.run(params["t_run"])
        sim_seconds.append(perf_counter() - t0)
        i_arr = np.asarray(spk_mon.i[:])
        t_arr = np.asarray(spk_mon.t[:])
        ids.extend(int(x) for x in i_arr)
        ts.extend(float(x) for x in t_arr)
        nrun.extend(trial for _ in i_arr)

    spikes = pd.DataFrame({
        "t": ts, "trial": nrun,
        "flywire_id": [i2flyid[i] for i in ids],
        "exp_name": exp_name,
    })
    timing = {"build_seconds": bundle["build_seconds"],
              "sim_seconds_per_trial": sim_seconds,
              "sim_seconds_total": float(sum(sim_seconds))}
    return spikes, timing


def mbon_rates(spikes: pd.DataFrame, payload: dict, params: dict, exp_name: str) -> list[dict]:
    """Reproduce the existing path's MBON-rate output exactly, via utl.get_rate
    and mbr.annotated_rates, so the CSV is directly comparable."""
    t_run_s = float(params["t_run"] / ms) / 1000.0
    n_run = int(params["n_run"])
    if len(spikes):
        rates, _ = utl.get_rate(spikes, t_run_s, n_run)
    else:
        rates = pd.DataFrame()
    mbons = payload["mbons"]["records"]
    rates_by_id = mbr.rates_for(rates, exp_name, mbr.ids(mbons))
    return mbr.annotated_rates(mbons, rates_by_id)


# ----------------------------------------------------------------------------
# self-test: weight persistence across store/restore (tiny synthetic network)
# ----------------------------------------------------------------------------
def self_test() -> None:
    """Verify the CRITICAL claim behind the learning design (task item 3):
    restore() reverts synaptic weights to the stored snapshot, so blanket
    restore would WIPE learned weights; our save-then-reapply pattern preserves
    them. Runs a 3-neuron network in milliseconds (not the real model)."""
    from brian2 import start_scope, NeuronGroup
    start_scope()
    eqs = "dv/dt = -v/(10*ms) : volt"
    g = NeuronGroup(3, eqs, threshold="v>1*mV", reset="v=0*mV", method="exact")
    s = Synapses(g, g, "w : volt", on_pre="v_post += w")
    s.connect(i=[0, 1], j=[1, 2])
    s.w = [1 * mV, 2 * mV]
    net = Network(g, s)
    net.store("init")
    original = np.array(s.w[:])           # SI (volt) values, units stripped by np.array

    # simulate "learning": change the weights (mirror run_cue's capture/reapply)
    s.w[:] = (original + 0.005) * volt    # + 5 mV
    learned = np.array(s.w[:])

    # naive restore would wipe them:
    net.restore("init")
    after_plain_restore = np.array(s.w[:])
    wiped = np.allclose(after_plain_restore, original) and not np.allclose(after_plain_restore, learned)

    # our pattern: save -> restore -> reapply (exactly as run_cue does)
    s.w[:] = learned * volt               # pretend these are the current learned weights
    keep = np.array(s.w[:])
    net.restore("init")
    s.w[:] = keep * volt
    after_reapply = np.array(s.w[:])
    preserved = np.allclose(after_reapply, learned)

    print("[self-test] plain restore() reverts weights to snapshot :", wiped)
    print("[self-test] save->restore->reapply preserves weights    :", preserved)
    if not (wiped and preserved):
        raise SystemExit("[self-test] FAILED: weight-handling assumptions do not hold")
    print("[self-test] PASS: weights are reverted by restore() and preserved by reapply.")


def self_test_rates() -> None:
    """Check the per-neuron-rate path WITHOUT a model and WITHOUT running anything:
    (1) rate_vector on 64-bit IDs and bad input; (2) on a tiny synthetic network,
    _apply_trial_state sets a distinct rate per neuron, clears rfc only on driven
    neurons, resets state, replaces (not accumulates) rates between calls, and
    preserves learned weights. No net.run is ever called."""
    from brian2 import start_scope, NeuronGroup

    # ---- (1) rate_vector: pure numpy -------------------------------------------
    base = 720575940600000000                       # > 2**53: float64 cannot tell +1 from +2
    ids = [base + k for k in (1, 2, 3, 4)]
    flyid2i = {f: i for i, f in enumerate(ids)}
    vec, idx = rate_vector(flyid2i, {ids[0]: 30.0, ids[2]: 150.0, ids[3]: 0.0}, 4)
    ok_vec = np.allclose(vec, [30.0, 0.0, 150.0, 0.0])
    ok_idx = idx.tolist() == [0, 2]                 # 0 Hz and unlisted neurons are not driven
    ok_big = len({float(f) for f in ids}) < len(ids)  # premise: float64 WOULD merge these IDs
    ok_np_key = rate_vector(flyid2i, {np.int64(ids[1]): 60.0}, 4)[0][1] == 60.0
    errors = 0
    for bad in ({base + 99: 10.0}, {float(ids[0]): 10.0}, {ids[0]: -1.0}, {ids[0]: float("nan")}):
        try:
            rate_vector(flyid2i, bad, 4)
        except (ValueError, TypeError):
            errors += 1
    ok_errors = errors == 4
    print("[self-test-rates] rate_vector values / driven indices     :", ok_vec and ok_idx)
    print("[self-test-rates] 64-bit IDs kept exact (float64 would not):", ok_big and ok_np_key)
    print("[self-test-rates] unknown/float/negative/NaN input raises  :", ok_errors)

    # ---- (2) _apply_trial_state on a tiny synthetic network (no run) -----------
    start_scope()
    n = 4
    neu = NeuronGroup(n, "dv/dt = -v/(10*ms) : volt\nrfc : second", threshold="v>1*mV",
                      reset="v=0*mV", method="exact")
    syn = Synapses(neu, neu, "w : volt", on_pre="v_post += w")
    syn.connect(i=[0, 1], j=[1, 2])
    syn.w = [1 * mV, 2 * mV]
    pin = PoissonGroup(n, rates=0 * Hz)
    syn_in = Synapses(pin, neu, on_pre="v_post += w_in", namespace={"w_in": 1 * mV})
    syn_in.connect(i=np.arange(n), j=np.arange(n))  # build_network uses connect(j="i"); same wiring
    net = Network(neu, syn, pin, syn_in)
    net.store("init")
    bundle = {"net": net, "neu": neu, "syn": syn, "pin": pin, "params": {"t_rfc": 2 * ms}}

    learned = np.array([0.0005, 0.0007])            # volt; pretend learning changed the weights
    syn.w[:] = learned * volt
    neu.v = 5 * mV                                   # state that a reset must wipe
    _apply_trial_state(bundle, vec, idx)
    got_rates = np.array(pin.rates[:])
    got_rfc = np.array(neu.rfc[:])
    ok_rates = np.allclose(got_rates, [30.0, 0.0, 150.0, 0.0])    # distinct rate PER neuron
    ok_rfc = np.allclose(got_rfc, [0.0, 0.002, 0.0, 0.002])       # cleared only on driven neurons
    ok_reset = np.allclose(np.array(neu.v[:]), 0.0)               # restore() ran
    ok_weights = np.allclose(np.array(syn.w[:]), learned)         # learned weights survived it
    print("[self-test-rates] per-neuron Poisson rates applied         :", ok_rates)
    print("[self-test-rates] rfc cleared only on driven neurons       :", ok_rfc)
    print("[self-test-rates] state reset by restore()                 :", ok_reset)
    print("[self-test-rates] learned weights preserved across reset   :", ok_weights)

    vec2, idx2 = rate_vector(flyid2i, {ids[1]: 60.0}, 4)          # a different stimulus next
    _apply_trial_state(bundle, vec2, idx2)
    ok_replace = (np.allclose(np.array(pin.rates[:]), [0.0, 60.0, 0.0, 0.0])
                  and np.allclose(np.array(neu.rfc[:]), [0.002, 0.0, 0.002, 0.002])
                  and np.allclose(np.array(syn.w[:]), learned))
    print("[self-test-rates] next stimulus replaces (not adds to) old :", ok_replace)

    checks = [ok_vec, ok_idx, ok_big, ok_np_key, ok_errors, ok_rates, ok_rfc, ok_reset,
              ok_weights, ok_replace]
    if not all(checks):
        raise SystemExit("[self-test-rates] FAILED: per-neuron-rate path assumptions do not hold")
    print("[self-test-rates] PASS: per-neuron rates, resets and weight persistence behave as intended.")


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------
def parser() -> argparse.ArgumentParser:
    example = (
        "uv run --python .venv-shiu/bin/python --no-project -- "
        ".venv-shiu/bin/python repro/mushroom_body/fast_runner.py "
        "--cue a --seed 20260317 --duration-ms 1000 --trials 5"
    )
    p = argparse.ArgumentParser(
        description="Reusable-network fast path for one KC-direct cue (see docs/design/fast-runner.md).",
        epilog=(
            f"Example (a real simulation — run yourself, use caffeinate -i):\n  {example}\n\n"
            "Quick checks that do NOT run the model:\n"
            "  --self-test   verify weight persistence and the per-neuron-rate path on tiny\n"
            "                synthetic networks (never calls net.run)\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--self-test", action="store_true",
                   help="Run the tiny checks (weight persistence, per-neuron-rate path) and exit (no model, no net.run).")
    p.add_argument("--cue", choices=["a", "b"], default="a", help="Which disjoint KC set to stimulate (default: a).")
    p.add_argument("--seed", type=int, help="Base simulation seed (set once; trials advance the stream).")
    p.add_argument("--duration-ms", type=float, default=1000.0, help="Trial duration in ms (default: 1000).")
    p.add_argument("--trials", type=int, default=5, help="Trials per run (default: 5).")
    p.add_argument("--pn-rate", type=float, default=150.0, help="KC stimulation rate in Hz (default: 150).")
    p.add_argument("--kc-set-size", type=int, default=100, help="KC set size per cue (default: 100).")
    p.add_argument("--kc-set-seed", type=int, default=20260316, help="Seed selecting the disjoint KC sets (default: 20260316).")
    return p


def output_path(args: argparse.Namespace) -> Path:
    name = (
        f"fast_mbon_cue_{args.cue}"
        f"_duration_ms_{args.duration_ms:g}_trials_{args.trials}"
        f"_pn_rate_hz_{args.pn_rate:g}"
        f"_kc_size_{args.kc_set_size}_kc_seed_{args.kc_set_seed}"
        f"_seed_{args.seed}.csv"
    )
    return mbr.RESULTS_DIR / name


def main() -> None:
    args = parser().parse_args()
    if args.self_test:
        self_test()
        self_test_rates()
        return
    if args.seed is None:
        raise SystemExit("--seed is required unless --self-test is given")
    if args.trials <= 0 or args.duration_ms <= 0 or args.kc_set_size <= 0:
        raise ValueError("trials, duration, and kc-set-size must be positive")

    out_path = output_path(args)
    if out_path.exists():
        print(f"Output already exists, skipping (restartable): {out_path}")
        return

    params = default_params.copy()
    params["t_run"] = args.duration_ms * ms
    params["n_run"] = args.trials
    params["r_poi"] = args.pn_rate * Hz

    payload = mbr.read_ids()
    set_a, set_b = mbr.select_disjoint_kc_sets(
        payload["kenyon_cells"]["records"], args.kc_set_size, args.kc_set_seed
    )
    stim_ids = set_a if args.cue == "a" else set_b
    exp_name = "kc_set_a" if args.cue == "a" else "kc_set_b"

    bundle = build_network(params, mbr.UPSTREAM_ROOT / "Completeness_783.csv",
                           mbr.UPSTREAM_ROOT / "Connectivity_783.parquet")
    spikes, timing = run_cue(bundle, stim_ids, args.pn_rate, args.trials, args.seed, exp_name)
    rows = mbon_rates(spikes, payload, params, exp_name)

    mbr.RESULTS_DIR.mkdir(exist_ok=True)
    with out_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["seed", "duration_ms", "trials", "cue", "root_id", "cell_type", "side", "rate_hz"]
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({"seed": args.seed, "duration_ms": args.duration_ms,
                             "trials": args.trials, "cue": args.cue, **row})

    b = timing["build_seconds"]; s = timing["sim_seconds_total"]
    print(f"cue {args.cue} @ seed {args.seed}, {args.duration_ms:g}ms x {args.trials} trials (FAST path):")
    print(f"  build once = {b:.1f}s ; simulate = {s:.1f}s total "
          f"({', '.join(f'{x:.1f}' for x in timing['sim_seconds_per_trial'])} per trial)")
    print(f"  {len(rows)} nonzero MBONs. Wrote {out_path}")
    print(f"  [timing] build_seconds={b:.3f} sim_seconds_total={s:.3f}")


if __name__ == "__main__":
    main()
