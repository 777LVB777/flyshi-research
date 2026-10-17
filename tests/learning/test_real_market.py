"""Phase 2 (Design A) on FAKE data only: chains, runner, comparator, null control,
verdict and total-drive check. No network request, no price data, no Brian2: the
runner is driven by the synthetic tests' fake simulator, and every market file,
fill plan and job file here is made up."""

from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import math
import sys
from dataclasses import replace
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.evaluation import isotonic_comparator as ic  # noqa: E402
from flyshi_research.learning import real_market as rm  # noqa: E402
from flyshi_research.learning import synthetic_market as sm  # noqa: E402
from flyshi_research.simulator import Market  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_synthetic_market import FakeMarketSimulator  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUNNER = REPO / "repro" / "mushroom_body" / "run_real_market_experiment.py"
LAUNCHER = REPO / "repro" / "mushroom_body" / "launch_real_market_parallel.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---- locked design ------------------------------------------------------------------ #
def test_the_design_is_the_synthetic_sweeps_unchanged():
    cfg = rm.locked_config()
    assert cfg == sm.SyntheticConfig() and cfg.config_hash() == "a325e6b206"
    assert (rm.TRAIN_PER_CHAIN, rm.TEST_PER_CHAIN, rm.N_CHAINS) == (70, 180, 40)
    jobs = rm.plan_jobs()
    assert len(jobs) == 120 and sum(j.n_runs for j in jobs) == 60_000
    assert {j.condition for j in jobs} == {"profit", "learning_off", "null_permuted"}
    assert rm.NULL_PERMUTATION_SEED == 20261016 and rm.BOOTSTRAP_SEED == 20261016
    assert rm.BOOTSTRAP_RESAMPLES == 2000 and rm.CONFIDENCE_LEVEL == 0.95
    assert rm.simulation_seed(0, 0) == 20280000 and rm.simulation_seed(39, 249) == 20280000 + 39249


# ---- comparator ----------------------------------------------------------------------- #
def _reference_isotonic(p, y):
    """O(n^2) min-max formula on tie-pooled groups: the isotonic fit at group i is
    max over j <= i of min over k >= i of the weighted mean of groups j..k."""
    order = np.argsort(p, kind="mergesort")
    p, y = np.asarray(p)[order], np.asarray(y, float)[order]
    u = np.unique(p)
    n = np.array([np.sum(p == v) for v in u], float)
    s = np.array([y[p == v].sum() for v in u])
    fit = [max(min(s[j:k + 1].sum() / n[j:k + 1].sum() for k in range(i, len(u))) for j in range(i + 1))
           for i in range(len(u))]
    return u, np.array(fit)


def test_pav_matches_the_min_max_formula_with_tied_prices_pooled():
    rng = np.random.default_rng(3)
    for _ in range(30):
        p = rng.choice(np.round(rng.random(12), 2), size=40)  # many ties
        y = (rng.random(40) < p).astype(int)
        u, fit = _reference_isotonic(p, y)
        blocks = ic.pav_blocks(p, y)
        means = np.concatenate([[sy / n] * 0 + [sy / n] for n, sy, _ in blocks])
        # expand blocks back to the tied-price groups they cover
        expanded, gi = [], 0
        for n, sy, sp in blocks:
            covered = 0
            while covered < n:
                covered += int(np.sum(p == u[gi]))
                expanded.append(sy / n)
                gi += 1
        assert np.allclose(expanded, fit) and len(means) == len(blocks)


def test_shrinkage_interpolation_and_end_values_follow_the_final_method():
    p = [0.2, 0.2, 0.2, 0.8, 0.8]
    y = [0, 0, 1, 1, 1]
    cal = ic.fit_isotonic(p, y, pseudo_count=20)
    assert cal.centres == pytest.approx((0.2, 0.8)) and cal.counts == (3, 2)
    assert cal.values[0] == pytest.approx((1 + 20 * 0.2) / 23)  # (sum y + m * mean price) / (n + m)
    assert cal.values[1] == pytest.approx((2 + 20 * 0.8) / 22)
    mid = cal.predict([0.5])[0]
    assert mid == pytest.approx((cal.values[0] + cal.values[1]) / 2)  # linear between centres
    assert cal.predict([0.0, 1.0]).tolist() == [cal.values[0], cal.values[1]]  # nearest end value


def test_repooling_after_shrinkage_makes_the_map_monotone_and_is_reported():
    # a large block near 0.20 followed by a one-market block just above it
    p = [0.2] * 1000 + [0.21]
    y = [1] * 300 + [0] * 700 + [1]
    cal = ic.fit_isotonic(p, y)
    assert not np.all(np.diff(cal.shrunk_values) >= 0.0)  # shrinkage alone breaks the order
    assert cal.monotone and cal.repooled and cal.values[0] == cal.values[1]
    assert np.all(np.diff(cal.predict(np.linspace(0, 1, 101))) >= 0.0)
    d = ic.describe(ic.fit_comparator([str(i) for i in range(len(p))], p, y))
    assert d["monotone"] is True
    rng = np.random.default_rng(8)  # random data: always monotone; untouched when already ordered
    for _ in range(40):
        q = rng.uniform(0, 1, 60)
        c = ic.fit_isotonic(q, (rng.random(60) < 0.5).astype(int))
        assert c.monotone and c.values[0] >= min(c.shrunk_values) and c.values[-1] <= max(c.shrunk_values)
    ordered = ic.fit_isotonic([0.2, 0.2, 0.2, 0.8, 0.8], [0, 0, 1, 1, 1])
    assert not ordered.repooled and ordered.values == ordered.shrunk_values


def _fake_training(n, miscalibrated, seed=0):
    rng = np.random.default_rng(seed)
    q = rng.uniform(0.02, 0.98, n)
    truth = 0.5 + 0.4 * np.tanh(4 * (q - 0.5)) if miscalibrated else q
    y = (rng.random(n) < truth).astype(int)
    return [f"m{i}" for i in range(n)], q, y


def test_guard_keeps_the_raw_price_when_calibration_does_not_help_and_switches_when_it_does():
    ids, q, y = _fake_training(4000, miscalibrated=False)
    honest = ic.fit_comparator(ids, q, y)
    assert honest.choice == ic.RAW and honest.cv_brier_raw <= honest.cv_brier_calibrated
    ids, q, y = _fake_training(4000, miscalibrated=True)
    biased = ic.fit_comparator(ids, q, y)
    assert biased.choice == ic.CALIBRATED and biased.cv_brier_calibrated < biased.cv_brier_raw
    assert np.allclose(honest.predict([0.3, 0.7]), [0.3, 0.7])  # raw is the identity


def test_folds_are_a_seeded_hash_of_the_id_and_the_comparator_round_trips():
    assert ic.FOLD_SEED == "flyshi-phase2-comparator-folds-20261016" and ic.CV_FOLDS == 5
    d = hashlib.sha256(b"flyshi-phase2-comparator-folds-20261016|123").digest()
    assert ic.fold_of("123") == int.from_bytes(d[:8], "big") % 5
    ids, q, y = _fake_training(500, True)
    c = ic.fit_comparator(ids, q, y)
    assert sum(c.fold_sizes) == 500 and ic.FrozenComparator.from_dict(json.loads(json.dumps(c.to_dict()))) == c
    assert c.sha256() == ic.FrozenComparator.from_dict(c.to_dict()).sha256()
    # training markets only: there is no argument through which a test market could enter
    assert list(inspect.signature(ic.fit_comparator).parameters)[:3] == ["train_ids", "train_prices",
                                                                          "train_outcomes"]


# ---- chains --------------------------------------------------------------------------- #
def _plan(train_ids, test_ids, frozen="f" * 64):
    return {"frozen_sha256": frozen, "seed": "flyshi-phase2-sample-20261016",
            "pools": {"train": {"usable_ids": list(train_ids)}, "test": {"usable_ids": list(test_ids)}}}


def _dates(ids, base_day, seed):
    rng = np.random.default_rng(seed)
    return {i: f"2026-{base_day:02d}-{int(d):02d}T00:00:00+00:00" for i, d in zip(ids, rng.integers(1, 28, len(ids)))}


def test_chains_are_disjoint_blocks_of_the_plan_order_presented_chronologically():
    tr = [f"t{i}" for i in range(3 * 70 + 25)]
    te = [f"s{i}" for i in range(3 * 180 + 40)]
    closed, decided = _dates(tr, 1, 1), _dates(te, 5, 2)
    absent = {tr[3], te[7]}  # usable in the plan but not built: skipped
    chains = rm.assemble_chains(_plan(tr, te), {i: d for i, d in closed.items() if i not in absent},
                                {i: d for i, d in decided.items() if i not in absent}, n_chains=3)
    built_tr = [i for i in tr if i not in absent][:210]
    built_te = [i for i in te if i not in absent][:540]
    for c, e in enumerate(chains["chains"]):
        assert sorted(e["train"]) == sorted(built_tr[70 * c:70 * c + 70])
        assert sorted(e["test"]) == sorted(built_te[180 * c:180 * c + 180])
        assert e["train"] == sorted(e["train"], key=lambda i: (closed[i], i))  # resolution order
        assert e["test"] == sorted(e["test"], key=lambda i: (decided[i], i))  # decision-time order
    every = [i for e in chains["chains"] for s in ("train", "test") for i in e[s]]
    assert len(every) == len(set(every)) == 750 and not absent & set(every)
    assert chains["counts"]["train"] == {"usable_in_plan": 235, "built": 234, "in_chains": 210, "reserve": 24,
                                         "usable_not_built": 1}
    with pytest.raises(ValueError, match="test pool"):
        rm.assemble_chains(_plan(tr, te[:500]), closed, decided, n_chains=3)


def test_chain_assembly_never_sees_an_outcome_or_a_price(tmp_path):
    path = _fake_market_file(tmp_path / "a.json", n_train=150, n_test=380)
    train, test, _ = rm.load_market_file(path)
    plan = _plan(sorted(train), sorted(test))
    flipped = {i: replace(m, market=replace(m.market, outcome=1 - m.market.outcome, quote=0.5))
               for i, m in train.items()}
    assert rm.chains_from_market_file(plan, train, test, n_chains=2) == \
        rm.chains_from_market_file(plan, flipped, test, n_chains=2)
    assert set(inspect.signature(rm.assemble_chains).parameters) == {
        "plan", "train_closed", "test_decided", "n_chains", "train_per_chain", "test_per_chain"}


# ---- runner ----------------------------------------------------------------------------- #
def _real(i, rng, closed="2026-01-15T00:00:00+00:00", decided="2026-01-10T00:00:00+00:00", fv=20000.0):
    q = float(rng.uniform(0.05, 0.95))
    return rm.RealMarket(str(i), Market(math.nan, q, int(rng.random() < q), 0.5, float(rng.uniform(-0.2, 0.2)),
                                        float(rng.uniform(1, 400)), 0.5, 0), decided, closed, fv)


def _chain(seed=0):
    rng = np.random.default_rng(seed)
    return [_real(i, rng) for i in range(70)], [_real(1000 + i, rng) for i in range(180)]


def _run(arm, chain=0, sim=None, **kw):
    sim = sim or FakeMarketSimulator(True)
    tr, te = _chain(chain)
    return rm.run_chain(sim, rm.locked_config(), chain, tr, te, arm, kc_sides=sim.kc_sides, **kw)


class _SeedRecorder(FakeMarketSimulator):
    def __init__(self):
        super().__init__(True)
        self.seeds, self.weights_changed = [], []

    def present_trials(self, rates, seed, duration_ms, n_trials):
        self.seeds.append(seed)
        self.weights_changed.append(self._learned)
        return super().present_trials(rates, seed, duration_ms, n_trials)


def test_run_chain_is_the_synthetic_loop_on_real_markets_with_ignition_tracking():
    sims = {a: _SeedRecorder() for a in rm.ARMS}
    out = {a: _run(a, chain=3, sim=sims[a]) for a in rm.ARMS}
    expected = [rm.simulation_seed(3, i) for i in range(250) for _ in (0, 1)]
    for a in rm.ARMS:
        assert sims[a].seeds == expected  # same presentation seeds in every arm
        assert len(out[a]["train"]) == 70 and len(out[a]["test"]) == 180
        row = out[a]["test"][0]
        assert {"market_id", "quote", "outcome", "raw_probability", "calibrated_probability", "action",
                "drive_yes_hz", "drive_no_hz", "ignition_yes", "ignition_no", "mbon_yes"} <= set(row)
        assert "ignited_any_trial" in row["ignition_yes"]
    assert not any(sims["learning_off"].weights_changed)  # learning off never changes weights
    assert any(sims["profit"].weights_changed)
    # signal and liquidity held at the midpoint: 90 Hz in both framings
    assert out["profit"]["drift_rate"] == rm.locked_config().plasticity.drift_rate


def test_the_runner_uses_the_shared_decision_loop(monkeypatch):
    calls = []
    original = sm.decision_loop

    def spy(*a, **k):
        calls.append(k)
        return original(*a, **k)

    monkeypatch.setattr(sm, "decision_loop", spy)
    _run("profit")
    assert len(calls) == 1 and calls[0]["exploration_key"] == 0


def test_null_arm_is_the_profit_arm_taught_with_permuted_training_outcomes(monkeypatch):
    perm = rm.null_permutation(5)
    assert sorted(perm.tolist()) == list(range(70)) and perm.tolist() != list(range(70))
    assert perm.tolist() == np.random.default_rng([20261016, 5]).permutation(70).tolist()
    null = _run("null_permuted", chain=5)
    tr, _ = _chain(5)
    assert [r["teaching_outcome"] for r in null["train"]] == [tr[j].market.outcome for j in perm]
    assert [r["outcome"] for r in null["train"]] == [m.market.outcome for m in tr]  # true outcomes kept
    assert null["null_permutation"] == perm.tolist()
    # the permuted outcomes really teach: the held-out forecasts differ from the profit arm's
    profit = _run("profit", chain=5)
    assert [r["raw_probability"] for r in null["test"]] != [r["raw_probability"] for r in profit["test"]]
    # with the identity permutation the null arm IS the profit arm
    monkeypatch.setattr(rm, "null_permutation", lambda chain, n=70: np.arange(n))
    ident, profit = _run("null_permuted", chain=5), _run("profit", chain=5)
    for split in ("train", "test"):
        strip = [{k: v for k, v in r.items() if k != "teaching_outcome"} for r in ident[split]]
        assert strip == profit[split]
    assert ident["calibrator"] == profit["calibrator"]


def test_the_null_arms_own_calibrator_sees_only_permuted_outcomes(monkeypatch):
    seen = []
    original = rm.fit_and_apply_calibration

    def spy(raw, outcomes, test):
        seen.append(list(outcomes))
        return original(raw, outcomes, test)

    monkeypatch.setattr(rm, "fit_and_apply_calibration", spy)
    out = _run("null_permuted", chain=2)
    assert seen == [[r["teaching_outcome"] for r in out["train"]]]


def test_run_chain_keeps_the_left_only_guard():
    sim = FakeMarketSimulator(True)
    tr, te = _chain()
    with pytest.raises(RuntimeError, match="no left-hemisphere KCs"):
        rm.run_chain(sim, rm.locked_config(), 0, tr, te, "profit", kc_sides={k: "right" for k in sim.kc_ids})
    with pytest.raises(ValueError, match="70 training and 180 test"):
        rm.run_chain(sim, rm.locked_config(), 0, tr[:69], te, "profit", kc_sides=sim.kc_sides)


# ---- verdict (fake job files) ----------------------------------------------------------- #
def _ign(flag=False):
    return {"ignited_any_trial": flag}


def _fake_outputs(n_chains, forecasts, seed=0, ignite=()):
    """Job outputs without a simulator. ``forecasts[arm](truth, quote)`` gives the
    arm's test forecast. Returns (outputs, chains, truth, quotes, ids)."""
    rng = np.random.default_rng(seed)
    chains = {"n_chains": n_chains, "chains": []}
    outputs, ids_all = {}, []
    for c in range(n_chains):
        t = rng.uniform(0.1, 0.9, 180)
        q = np.clip(t + rng.normal(0, 0.12, 180), 0.01, 0.99)
        y = (rng.random(180) < t).astype(int)
        ids = [f"x{c}_{i}" for i in range(180)]
        ids_all += ids
        chains["chains"].append({"chain": c, "train": [f"tr{c}_{i}" for i in range(70)], "test": ids})
        for arm in rm.ARMS:
            f = forecasts[arm](t, q)
            outputs[(c, arm)] = {
                "arm": arm, "chain": c,
                "train": [{"ignition_yes": _ign(), "ignition_no": _ign()} for _ in range(70)],
                "test": [{"market_id": i, "quote": float(qq), "outcome": int(yy), "calibrated_probability": float(ff),
                          "action": "YES" if ff > qq else "NO" if ff < qq else "ABSTAIN",
                          "ignition_yes": _ign((c, k) in ignite), "ignition_no": _ign()}
                         for k, (i, qq, yy, ff) in enumerate(zip(ids, q, y, f))]}
    return outputs, chains, ids_all


RAW_COMPARATOR = ic.fit_comparator(*_fake_training(2000, miscalibrated=False))
TRUTH = lambda t, q: t  # noqa: E731
PRICE = lambda t, q: q  # noqa: E731


def test_gate_passes_only_when_profit_beats_the_comparator_and_learning_off():
    assert RAW_COMPARATOR.choice == ic.RAW
    out, chains, ids = _fake_outputs(3, {"profit": TRUTH, "learning_off": PRICE, "null_permuted": PRICE})
    v = rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])
    assert v["gate_passes"] and v["success"] and not v["null_control"]["passes"]
    assert v["gate"]["profit_improvement_vs_comparator"]["lower"] > 0
    assert v["n_test_markets"] == 540 and v["readings"]["overall"].startswith("passes")
    out, chains, _ = _fake_outputs(3, {"profit": PRICE, "learning_off": PRICE, "null_permuted": PRICE})
    v = rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])
    assert not v["gate_passes"] and not v["success"]
    assert "no detectable edge larger than the minimum detectable effect" in v["readings"]["overall"]
    assert "not evidence of no edge" in v["readings"]["overall"]
    # beating the comparator alone is not enough: learning_off must be beaten too
    out, chains, _ = _fake_outputs(3, {"profit": TRUTH, "learning_off": TRUTH, "null_permuted": PRICE})
    assert not rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])["gate_passes"]


def test_a_passing_null_arm_is_a_null_control_failure_not_a_finding():
    out, chains, _ = _fake_outputs(3, {"profit": TRUTH, "learning_off": PRICE, "null_permuted": TRUTH})
    v = rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])
    assert v["gate_passes"] and v["null_control"]["passes"] and not v["success"]
    assert v["readings"]["overall"].startswith("NULL CONTROL FAILED")


def test_realised_mde_subset_and_ignition_are_reported_and_never_gate():
    out, chains, ids = _fake_outputs(3, {"profit": PRICE, "learning_off": PRICE, "null_permuted": PRICE},
                                     ignite={(0, k) for k in range(30)})
    volume = {i: (150_000.0 if k % 4 == 0 else 20_000.0) for k, i in enumerate(ids)}
    v = rm.evaluate(out, chains, RAW_COMPARATOR, volume, [])
    s = v["realised"]["vs_learning_off"]
    assert s["mde"] == pytest.approx(2.80 * s["sigma_d"] / math.sqrt(540))
    assert v["high_volume_subset"]["n"] == 135 and v["high_volume_subset"]["available"]
    assert v["sensitivity_excluding_ignited"]["n_excluded"] == 30
    assert v["ignition_exposure"]["profit"]["test_decisions_with_ignited_framing"] == 30
    assert not v["success"]  # nothing reported-only changes the verdict


def test_verdict_refuses_leaks_gaps_and_misaligned_arms():
    out, chains, ids = _fake_outputs(2, {"profit": TRUTH, "learning_off": PRICE, "null_permuted": PRICE})
    with pytest.raises(ValueError, match="comparator's training set"):
        rm.evaluate(out, chains, RAW_COMPARATOR, {}, [ids[5]])
    gap = dict(out)
    del gap[(1, "null_permuted")]
    with pytest.raises(ValueError, match="missing"):
        rm.evaluate(gap, chains, RAW_COMPARATOR, {}, [])
    bad = json.loads(json.dumps({f"{k[0]}|{k[1]}": v for k, v in out.items()}))
    bad = {(int(k.split("|")[0]), k.split("|")[1]): v for k, v in bad.items()}
    bad[(0, "learning_off")]["test"][3]["outcome"] ^= 1
    with pytest.raises(ValueError, match="disagree"):
        rm.evaluate(bad, chains, RAW_COMPARATOR, {}, [])


def test_mde_at_the_design_size():
    assert rm.mde(0.034, 7200) == pytest.approx(0.00112, abs=1e-5)
    assert rm.mde(0.09, 7200) == pytest.approx(0.00297, abs=1e-5)


# ---- total-drive check ------------------------------------------------------------------ #
def test_synthetic_reference_reproduces_the_recorded_drive_ranges():
    decided = rm.synthetic_reference()
    assert decided["presentations"] == 40_000
    assert (round(decided["drive_khz"]["min"], 1), round(decided["drive_khz"]["max"], 1)) == (19.3, 70.7)
    assert round(100 * decided["fraction_above_60_khz"], 2) == 3.06
    old = rm.synthetic_reference(sm.pre_revision_config())
    assert (round(old["drive_khz"]["min"], 1), round(old["drive_khz"]["max"], 1)) == (22.8, 67.5)
    assert round(100 * old["fraction_above_60_khz"], 2) == 2.12


def test_drive_check_reads_features_only_and_flags_drive_outside_the_validated_condition():
    rng = np.random.default_rng(1)
    calm = [Market(math.nan, float(p), 0, 0.5, 0.0, 30.0, 0.5) for p in rng.uniform(0.2, 0.8, 200)]
    report = rm.drive_check(calm, calm)
    assert not report["flags"] and "no flag raised" in report["sign_off"]
    flipped = [replace(m, outcome=1) for m in calm]
    assert rm.drive_check(flipped, flipped)["splits"] == report["splits"]  # outcomes never read
    # all features at their maxima, and time to resolution beyond 365 days (clipped)
    hot = [Market(math.nan, 0.99, 0, 0.5, 1.0, 900.0, 0.5) for _ in range(50)]
    hot_report = rm.drive_check(hot, calm)
    assert hot_report["splits"]["train"]["clipped_markets_by_feature"] == {"time_to_resolution_high": 50}
    assert any(f.startswith("train:") for f in hot_report["flags"])


# ---- CLI on fake files ------------------------------------------------------------------- #
def _fake_market_file(path, n_train=2900, n_test=7300, seed=0):
    rng = np.random.default_rng(seed)

    def rec(i, split, k):
        q = float(rng.uniform(0.05, 0.95))
        return {"latent_probability": None, "quote": q, "outcome": int(rng.random() < q), "signal": 0.5,
                "recent_change": float(rng.uniform(-0.1, 0.1)), "time_to_resolution": float(rng.uniform(1, 200)),
                "liquidity": 0.5, "sequence": k,
                "meta": {"market_id": i, "event_id": "e" + i,
                         "decision_time": f"2026-0{3 if split == 'train' else 5}-01T00:00:00+00:00",
                         "closed_time": f"2026-0{2 if split == 'train' else 6}-{1 + k % 27:02d}T00:00:00+00:00",
                         "price_time_unix": 0, "final_volume": float(rng.choice([20_000.0, 150_000.0]))}}

    payload = {"format": "flyshi.simulator.Market/v1", "venue": "polymarket", "frozen_list_sha256": "f" * 64,
               "split": {}, "counts": {},
               "train": [rec(f"{100000 + k}", "train", k) for k in range(n_train)],
               "test": [rec(f"{500000 + k}", "test", k) for k in range(n_test)]}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(payload))
    return Path(path)


def _prepared(tmp_path):
    cli = _load(RUNNER, "run_real_market_experiment_test")
    mf = _fake_market_file(tmp_path / "markets.json")
    train, test, _ = rm.load_market_file(mf)
    plan_path = tmp_path / "fill_plan.json"
    plan_path.write_text(json.dumps(_plan(sorted(train), sorted(test))))
    run_dir = tmp_path / "run"
    return cli, mf, plan_path, run_dir, train, test


def test_prepare_writes_chains_and_a_frozen_training_only_comparator_once(tmp_path, capsys):
    cli, mf, plan_path, run_dir, train, test = _prepared(tmp_path)
    assert cli.main(["--prepare", "--market-file", str(mf), "--fill-plan", str(plan_path),
                     "--run-dir", str(run_dir)]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["chain_counts"]["test"]["in_chains"] == 7200 and printed["chain_counts"]["train"]["reserve"] == 100
    manifest, chains, comparator, training_ids, _, _ = cli.load_prepared(run_dir)
    assert sorted(training_ids) == sorted(train) and not set(training_ids) & set(test)
    assert comparator.n_train == 2900 and manifest["locked_config_hash"] == "a325e6b206"
    with pytest.raises(SystemExit, match="never overwritten"):
        cli.main(["--prepare", "--market-file", str(mf), "--fill-plan", str(plan_path), "--run-dir", str(run_dir)])


def test_a_job_refuses_before_any_simulation_if_a_prepared_file_changed(tmp_path, monkeypatch):
    cli, mf, plan_path, run_dir, _, _ = _prepared(tmp_path)
    cli.main(["--prepare", "--market-file", str(mf), "--fill-plan", str(plan_path), "--run-dir", str(run_dir)])
    monkeypatch.setattr(cli, "build_sweep_simulator", lambda *a, **k: pytest.fail("simulator built"))
    chains = json.loads((run_dir / "chains.json").read_text())
    chains["chains"][0]["test"].reverse()
    (run_dir / "chains.json").write_text(json.dumps(chains))
    with pytest.raises(SystemExit, match="does not match the manifest"):
        cli.main(["--job", "real:profit:00", "--run-dir", str(run_dir)])


def test_finish_computes_the_verdict_from_fake_job_files(tmp_path):
    cli, mf, plan_path, run_dir, train, test = _prepared(tmp_path)
    cli.main(["--prepare", "--market-file", str(mf), "--fill-plan", str(plan_path), "--run-dir", str(run_dir)])
    _, chains, _, _, _, _ = cli.load_prepared(run_dir)
    paths = cli.Paths(run_dir)
    rng = np.random.default_rng(4)
    for job in rm.plan_jobs():
        e = chains["chains"][job.chain]
        rows = [{"market_id": i, "quote": test[i].market.quote, "outcome": test[i].market.outcome,
                 "calibrated_probability": float(np.clip(test[i].market.quote + rng.normal(0, 0.01), 0, 1)),
                 "action": "YES", "ignition_yes": _ign(), "ignition_no": _ign()} for i in e["test"]]
        cli._write_json(paths.output(job), {"arm": job.condition, "chain": job.chain, "test": rows,
                                            "train": [{"ignition_yes": _ign(), "ignition_no": _ign()}] * 70})
    verdict = cli.finish(run_dir)
    assert (run_dir / "verdict.json").exists() and verdict["n_test_markets"] == 7200
    assert not verdict["success"] and verdict["high_volume_subset"]["n"] > 0


def test_dry_runs_and_drive_check_simulate_nothing_and_write_nothing(tmp_path, capsys):
    cli = _load(RUNNER, "run_real_market_experiment_test2")
    assert cli.main(["--dry-run"]) == 0
    assert "120" in capsys.readouterr().out
    mf = _fake_market_file(tmp_path / "m.json", n_train=40, n_test=60)
    assert cli.main(["--drive-check", "--market-file", str(mf)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert set(report["splits"]) == {"train", "test"} and "sign_off" in report
    launcher = _load(LAUNCHER, "launch_real_market_parallel_test")
    (tmp_path / "run").mkdir()
    (tmp_path / "run" / "manifest.json").write_text("{}")
    assert launcher.main(["--run-dir", str(tmp_path / "run"), "--dry-run", "--max-procs", "2",
                          "--gb-per-proc", "0.01", "--headroom-gb", "0"]) == 0
    assert "dry run" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.rglob("*")) == ["m.json", "manifest.json", "run"]


def test_launcher_reuses_the_synthetic_scheduling_loop_over_phase2_jobs(tmp_path):
    launcher = _load(LAUNCHER, "launch_real_market_parallel_test2")
    synth = sys.modules["launch_synthetic_market_parallel"]  # the module the launcher imported
    lr = launcher.RealLauncher(tmp_path, slots=2)
    assert len(lr.jobs) == 120 and lr._run.__func__ is synth.Launcher._run
    assert "_run" not in vars(launcher.RealLauncher) and "run" not in vars(launcher.RealLauncher)
    assert launcher.worker_argv(lr.jobs[0], tmp_path)[-4:] == ["--job", "real:profit:00", "--run-dir", str(tmp_path)]


def test_gross_pnl_is_per_market_at_the_price_with_no_fee_or_spread_and_never_gates():
    q, y = np.array([0.3, 0.3, 0.6, 0.6, 0.5]), np.array([1, 0, 1, 0, 1])
    pnl = rm.gross_pnl(["YES", "YES", "NO", "NO", "ABSTAIN"], q, y)
    assert pnl.tolist() == pytest.approx([0.7, -0.3, -0.4, 0.6, 0.0])  # no fee, no spread
    out, chains, _ = _fake_outputs(3, {"profit": TRUTH, "learning_off": PRICE, "null_permuted": PRICE})
    v = rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])
    g = v["gross_pnl"]
    assert g["label"] == "gross, before fees and spread, not achievable as stated"
    assert "never gating" in g["note"] and set(g["per_arm"]) == set(rm.ARMS)
    rows = [r for e in chains["chains"] for r in out[(e["chain"], "profit")]["test"]]
    expect = sum((r["outcome"] - r["quote"]) if r["action"] == "YES" else
                 (r["quote"] - r["outcome"]) if r["action"] == "NO" else 0.0 for r in rows)
    p = g["per_arm"]["profit"]
    assert p["total"] == pytest.approx(expect) and p["markets"] == 540
    assert p["trades"] + p["abstentions"] == 540 and p["per_market"] == pytest.approx(expect / 540)
    # changing every action changes the report but not the verdict
    flipped = json.loads(json.dumps({f"{k[0]}|{k[1]}": x for k, x in out.items()}))
    flipped = {(int(k.split("|")[0]), k.split("|")[1]): x for k, x in flipped.items()}
    for x in flipped.values():
        for r in x["test"]:
            r["action"] = "NO" if r["action"] == "YES" else "YES"
    v2 = rm.evaluate(flipped, chains, RAW_COMPARATOR, {}, [])
    assert v2["gross_pnl"] != g and v2["success"] == v["success"] and v2["gate"] == v["gate"]
    assert "gross P&L" in v["readings"]["reported_only"]


def test_the_verdict_states_the_series_correlation_limitation():
    out, chains, _ = _fake_outputs(2, {"profit": PRICE, "learning_off": PRICE, "null_permuted": PRICE})
    v = rm.evaluate(out, chains, RAW_COMPARATOR, {}, [])
    assert any("per-series caps were not applied" in t and "somewhat narrow" in t for t in v["limitations"])
