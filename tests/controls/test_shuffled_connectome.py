from __future__ import annotations

from collections import Counter

import pytest

np = pytest.importorskip("numpy")

from flyshi_research.controls.shuffled_connectome import (  # noqa: E402
    ConnectivityTable,
    mushroom_body_scope_mask,
    shuffle_connectivity,
    validate_shuffle,
)


def circulant_graph(n_neurons: int = 20) -> ConnectivityTable:
    pre = np.repeat(np.arange(n_neurons, dtype=np.int64), 3)
    post = np.concatenate(
        [[(source + offset) % n_neurons for offset in (1, 2, 3)] for source in range(n_neurons)]
    )
    count = np.arange(1, pre.size + 1, dtype=np.int64)
    sign = np.where(pre % 2 == 0, 1, -1).astype(np.int8)
    return ConnectivityTable(pre, post, count, sign)


def degrees(pre, post):
    return Counter(map(int, pre)), Counter(map(int, post))


def endpoint_pairs(table):
    return list(zip(map(int, table.pre), map(int, table.post)))


def test_degrees_and_synapse_attribute_distribution_are_preserved_exactly() -> None:
    original = circulant_graph()
    result = shuffle_connectivity(original, seed=20260921, n_swaps=300)
    shuffled = result.table
    assert degrees(original.pre, original.post) == degrees(shuffled.pre, shuffled.post)
    assert Counter(zip(original.synapse_count, original.sign)) == Counter(
        zip(shuffled.synapse_count, shuffled.sign)
    )
    # Attributes travel with rows and rows keep their presynaptic neuron.
    assert np.array_equal(shuffled.pre, original.pre)
    assert np.array_equal(shuffled.synapse_count, original.synapse_count)
    assert np.array_equal(shuffled.sign, original.sign)
    validate_shuffle(original, result, maximum_overlap=0.50)


def test_seeded_shuffle_is_reproducible_and_different_seed_changes_it() -> None:
    graph = circulant_graph()
    first = shuffle_connectivity(graph, seed=17, n_swaps=150).table
    repeat = shuffle_connectivity(graph, seed=17, n_swaps=150).table
    other = shuffle_connectivity(graph, seed=18, n_swaps=150).table
    assert np.array_equal(first.post, repeat.post)
    assert not np.array_equal(first.post, other.post)


def test_shuffle_destroys_most_specific_edges_on_synthetic_graph() -> None:
    graph = circulant_graph()
    result = shuffle_connectivity(graph, seed=41, n_swaps=600)
    assert result.overlap_fraction < 0.5


def test_default_policy_introduces_no_self_loops_or_parallel_edges() -> None:
    graph = circulant_graph()
    shuffled = shuffle_connectivity(graph, seed=91, n_swaps=400).table
    pairs = endpoint_pairs(shuffled)
    assert all(pre != post for pre, post in pairs)
    assert len(pairs) == len(set(pairs))


def test_input_loops_and_parallel_edges_make_them_permitted_by_default() -> None:
    graph = ConnectivityTable(
        pre=np.array([0, 0, 1, 2, 3, 3]),
        post=np.array([0, 1, 2, 3, 1, 1]),
        synapse_count=np.ones(6, dtype=int),
        sign=np.ones(6, dtype=int),
    )
    result = shuffle_connectivity(graph, seed=5, n_swaps=5, max_attempts=500)
    assert result.allow_self_loops is True
    assert result.allow_parallel_edges is True
    assert degrees(graph.pre, graph.post) == degrees(result.table.pre, result.table.post)


def test_mushroom_body_scope_leaves_every_other_row_unchanged() -> None:
    graph = circulant_graph()
    mb_ids = np.arange(10, dtype=np.int64)
    mask = mushroom_body_scope_mask(graph, mb_ids)
    result = shuffle_connectivity(graph, seed=7, n_swaps=50, eligible_mask=mask)
    assert np.array_equal(result.table.pre[~mask], graph.pre[~mask])
    assert np.array_equal(result.table.post[~mask], graph.post[~mask])
    assert degrees(graph.pre, graph.post) == degrees(result.table.pre, result.table.post)


def test_impossible_or_under_attempted_shuffle_fails_loudly() -> None:
    graph = ConnectivityTable(
        pre=np.array([0, 1]),
        post=np.array([1, 0]),
        synapse_count=np.ones(2, dtype=int),
        sign=np.ones(2, dtype=int),
    )
    with pytest.raises(RuntimeError, match="accepted 0 of 1"):
        shuffle_connectivity(graph, seed=1, n_swaps=1, max_attempts=1)
