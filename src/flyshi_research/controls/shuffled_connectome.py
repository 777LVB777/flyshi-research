"""Seeded degree-preserving shuffles of directed connectivity tables.

The implementation performs directed double-edge swaps::

    a -> b, c -> d   becomes   a -> d, c -> b

Sources never move between rows, and the two targets are exchanged.  Thus each
neuron's unweighted in-degree and out-degree are exact invariants.  Synapse
count and sign also stay attached to their original rows: their global joint
distribution and each source neuron's outgoing attribute multiset are exact
invariants.  Weighted in-degree, signed input, motifs, compartments, paths, and
cell-type preferences are intentionally not preserved.

By default, self-loops or parallel edges are permitted only if at least one is
present in the input.  Callers can set either policy explicitly.  No claim is
made that a finite number of swaps is a perfectly uniform draw from all graphs
with the same degree sequence; shuffle adequacy must be reported separately.
The method description is not tied to an independently verified citation.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Iterable

import numpy as np


def _integer_vector(values: object, name: str) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1:
        raise ValueError(f"{name} must be one-dimensional")
    if not np.issubdtype(array.dtype, np.integer):
        raise TypeError(f"{name} must contain integers")
    return np.array(array, dtype=np.int64, copy=True)


def _attribute_vector(values: object, name: str, length: int) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim != 1 or array.size != length:
        raise ValueError(f"{name} must be one-dimensional and match pre/post")
    return np.array(array, copy=True)


@dataclass(frozen=True, eq=False)
class ConnectivityTable:
    """Four aligned columns describing a directed, possibly weighted graph."""

    pre: np.ndarray
    post: np.ndarray
    synapse_count: np.ndarray
    sign: np.ndarray

    def __post_init__(self) -> None:
        pre = _integer_vector(self.pre, "pre")
        post = _integer_vector(self.post, "post")
        if pre.size == 0 or post.size != pre.size:
            raise ValueError("pre and post must be non-empty and have equal length")
        count = _attribute_vector(self.synapse_count, "synapse_count", pre.size)
        sign = _attribute_vector(self.sign, "sign", pre.size)
        try:
            numeric_count = count.astype(np.float64)
        except (TypeError, ValueError) as exc:
            raise TypeError("synapse_count must be numeric") from exc
        if not np.all(np.isfinite(numeric_count)) or np.any(numeric_count <= 0):
            raise ValueError("synapse_count must be finite and positive")
        try:
            numeric_sign = sign.astype(np.float64)
        except (TypeError, ValueError) as exc:
            raise TypeError("sign must be numeric") from exc
        if not np.all(np.isfinite(numeric_sign)) or np.any(
            (numeric_sign != -1) & (numeric_sign != 1)
        ):
            raise ValueError("sign must contain only -1 and 1")
        object.__setattr__(self, "pre", pre)
        object.__setattr__(self, "post", post)
        object.__setattr__(self, "synapse_count", count)
        object.__setattr__(self, "sign", sign)

    @property
    def n_edges(self) -> int:
        return int(self.pre.size)


@dataclass(frozen=True, eq=False)
class ShuffleResult:
    """Shuffled table plus diagnostics needed to audit the randomization."""

    table: ConnectivityTable
    requested_swaps: int
    accepted_swaps: int
    attempts: int
    eligible_edges: int
    overlap_fraction: float
    allow_self_loops: bool
    allow_parallel_edges: bool


def _edge_counter(pre: np.ndarray, post: np.ndarray) -> Counter[tuple[int, int]]:
    return Counter(zip(map(int, pre), map(int, post)))


def edge_overlap_fraction(original: ConnectivityTable, shuffled: ConnectivityTable) -> float:
    """Fraction of original endpoint pairs retained, counting multiplicity."""
    if original.n_edges != shuffled.n_edges:
        raise ValueError("tables must have the same number of edges")
    before = _edge_counter(original.pre, original.post)
    after = _edge_counter(shuffled.pre, shuffled.post)
    overlap = sum(min(count, after.get(edge, 0)) for edge, count in before.items())
    return float(overlap / original.n_edges)


def mushroom_body_scope_mask(
    table: ConnectivityTable, mushroom_body_neuron_ids: Iterable[int]
) -> np.ndarray:
    """Select the induced subgraph on an explicitly supplied MB neuron set.

    The caller, not this function, decides whether the set contains only KCs
    and MBONs or also DANs, APL, and other related cells.  Requiring both
    endpoints to be members leaves every boundary edge unchanged.
    """
    ids = np.asarray(list(mushroom_body_neuron_ids))
    if ids.ndim != 1 or not np.issubdtype(ids.dtype, np.integer):
        raise TypeError("mushroom_body_neuron_ids must be a one-dimensional integer collection")
    if ids.size == 0:
        raise ValueError("mushroom_body_neuron_ids must not be empty")
    unique_ids = np.unique(ids.astype(np.int64))
    return np.isin(table.pre, unique_ids) & np.isin(table.post, unique_ids)


def validate_shuffle(
    original: ConnectivityTable,
    result: ShuffleResult,
    *,
    eligible_mask: object | None = None,
    maximum_overlap: float | None = None,
) -> None:
    """Raise if a result violates the documented exact invariants.

    ``maximum_overlap`` is an optional pre-stated upper bound.  The server
    generator uses 0.50, as fixed in the design record before generation.
    """
    shuffled = result.table
    if original.n_edges != shuffled.n_edges:
        raise RuntimeError("shuffle changed the row count")
    if Counter(map(int, original.pre)) != Counter(map(int, shuffled.pre)):
        raise RuntimeError("shuffle changed out-degrees")
    if Counter(map(int, original.post)) != Counter(map(int, shuffled.post)):
        raise RuntimeError("shuffle changed in-degrees")
    if not np.array_equal(original.synapse_count, shuffled.synapse_count):
        raise RuntimeError("shuffle changed or moved synapse counts between rows")
    if not np.array_equal(original.sign, shuffled.sign):
        raise RuntimeError("shuffle changed or moved signs between rows")
    if not result.allow_self_loops and np.any(shuffled.pre == shuffled.post):
        raise RuntimeError("shuffle introduced a self-loop")
    if not result.allow_parallel_edges:
        pairs = _edge_counter(shuffled.pre, shuffled.post)
        if any(count > 1 for count in pairs.values()):
            raise RuntimeError("shuffle introduced a parallel edge")
    if eligible_mask is not None:
        eligible = np.asarray(eligible_mask)
        if eligible.ndim != 1 or eligible.size != original.n_edges or eligible.dtype.kind != "b":
            raise ValueError("eligible_mask must be a matching boolean vector")
        outside = ~eligible
        if not (
            np.array_equal(original.pre[outside], shuffled.pre[outside])
            and np.array_equal(original.post[outside], shuffled.post[outside])
        ):
            raise RuntimeError("shuffle changed a row outside its scope")
    measured_overlap = edge_overlap_fraction(original, shuffled)
    if not np.isclose(measured_overlap, result.overlap_fraction, rtol=0.0, atol=1e-15):
        raise RuntimeError("stored overlap diagnostic does not match the shuffled table")
    if maximum_overlap is not None:
        if not 0.0 <= maximum_overlap <= 1.0:
            raise ValueError("maximum_overlap must be in [0, 1]")
        if measured_overlap >= maximum_overlap:
            raise RuntimeError(
                f"edge overlap {measured_overlap:.6f} is not below {maximum_overlap:.6f}"
            )


def shuffle_connectivity(
    table: ConnectivityTable,
    *,
    seed: int,
    n_swaps: int | None = None,
    max_attempts: int | None = None,
    eligible_mask: object | None = None,
    allow_self_loops: bool | None = None,
    allow_parallel_edges: bool | None = None,
) -> ShuffleResult:
    """Shuffle selected directed edges with seeded double-edge swaps.

    ``eligible_mask`` restricts swaps to selected rows.  Non-selected rows are
    byte-for-byte unchanged, while degree is still preserved over the complete
    graph.  The default request is ten accepted swaps per eligible edge.

    A ``RuntimeError`` is raised rather than silently returning an insufficient
    shuffle when the requested number cannot be accepted within
    ``max_attempts``.  Sparse biological graphs normally offer many legal
    swaps; very small or dense synthetic graphs may not.
    """
    if eligible_mask is None:
        eligible = np.ones(table.n_edges, dtype=bool)
    else:
        eligible = np.asarray(eligible_mask)
        if eligible.ndim != 1 or eligible.size != table.n_edges:
            raise ValueError("eligible_mask must be one-dimensional and match the table")
        if not np.issubdtype(eligible.dtype, np.bool_):
            raise TypeError("eligible_mask must contain booleans")
        eligible = eligible.astype(bool, copy=True)
    indices = np.flatnonzero(eligible)
    if indices.size < 2:
        raise ValueError("at least two eligible edges are required")

    # Build the membership set once.  Unlike Counter, this does not retain an
    # additional Python integer count for every unique edge in the common
    # no-parallel-edge case.
    input_edges: set[tuple[int, int]] = set()
    input_has_parallel = False
    for edge in zip(map(int, table.pre), map(int, table.post)):
        if edge in input_edges:
            input_has_parallel = True
        input_edges.add(edge)
    input_has_loops = bool(np.any(table.pre == table.post))
    permit_loops = input_has_loops if allow_self_loops is None else bool(allow_self_loops)
    permit_parallel = input_has_parallel if allow_parallel_edges is None else bool(allow_parallel_edges)
    if not permit_loops and input_has_loops:
        raise ValueError("input has self-loops but allow_self_loops is false")
    if not permit_parallel and input_has_parallel:
        raise ValueError("input has parallel edges but allow_parallel_edges is false")

    requested = 10 * int(indices.size) if n_swaps is None else n_swaps
    if not isinstance(requested, int) or isinstance(requested, bool) or requested < 0:
        raise ValueError("n_swaps must be a non-negative integer")
    attempt_limit = max(100 * max(requested, 1), 1000) if max_attempts is None else max_attempts
    if not isinstance(attempt_limit, int) or isinstance(attempt_limit, bool) or attempt_limit < requested:
        raise ValueError("max_attempts must be an integer at least n_swaps")

    pre = table.pre.copy()
    post = table.post.copy()
    occupied = None if permit_parallel else input_edges
    rng = np.random.default_rng(seed)
    accepted = 0
    attempts = 0
    while accepted < requested and attempts < attempt_limit:
        attempts += 1
        first_pos = int(rng.integers(indices.size))
        second_pos = int(rng.integers(indices.size - 1))
        if second_pos >= first_pos:
            second_pos += 1
        first = int(indices[first_pos])
        second = int(indices[second_pos])
        a, b = int(pre[first]), int(post[first])
        c, d = int(pre[second]), int(post[second])
        # Equal sources or targets merely permute indistinguishable endpoints.
        if a == c or b == d:
            continue
        new_first = (a, d)
        new_second = (c, b)
        if not permit_loops and (a == d or c == b):
            continue
        if occupied is not None:
            old_first = (a, b)
            old_second = (c, d)
            occupied.remove(old_first)
            occupied.remove(old_second)
            legal = new_first not in occupied and new_second not in occupied and new_first != new_second
            if not legal:
                occupied.add(old_first)
                occupied.add(old_second)
                continue
            occupied.add(new_first)
            occupied.add(new_second)
        post[first], post[second] = d, b
        accepted += 1

    if accepted != requested:
        raise RuntimeError(
            f"accepted {accepted} of {requested} requested swaps in {attempts} attempts"
        )
    shuffled = ConnectivityTable(pre, post, table.synapse_count, table.sign)
    return ShuffleResult(
        table=shuffled,
        requested_swaps=requested,
        accepted_swaps=accepted,
        attempts=attempts,
        eligible_edges=int(indices.size),
        overlap_fraction=edge_overlap_fraction(table, shuffled),
        allow_self_loops=permit_loops,
        allow_parallel_edges=permit_parallel,
    )
