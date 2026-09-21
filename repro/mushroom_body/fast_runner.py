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

Running the real model IS a simulation: run it yourself (see --help / the docs).
Only --self-test (a tiny synthetic network) is executed during preparation.
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
            "  --self-test   verify weight persistence on a tiny synthetic network\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--self-test", action="store_true", help="Run the tiny weight-persistence check and exit (no model).")
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
