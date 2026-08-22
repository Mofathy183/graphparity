"""
Percentile computation and results-matrix assembly for GraphParity.

This module turns raw per-iteration latency samples (one float,
milliseconds, per timed workload run) into the summary numbers the
README's results matrix actually reports: p50, p95, min, max, mean,
and sample count, per (platform, workload) pair.

Percentile method
------------------
`compute_percentile` uses linear interpolation between the two nearest
ranks (the same method NumPy's `percentile` uses by default). For a
sorted sample list of length n and a requested percentile p (0-100):

    rank = (p / 100) * (n - 1)
    lower, upper = floor(rank), ceil(rank)
    result = samples[lower] + (samples[upper] - samples[lower]) * (rank - lower)

This is stated explicitly, rather than left implicit, because a
nearest-rank method (which snaps to an existing sample rather than
interpolating between two) would produce different numbers on the same
input -- and every number in the results matrix has to be reproducible
from this module alone, without a reader having to guess which
percentile convention was used.

Nothing in this module performs I/O. It consumes plain `list[float]`
samples -- collected by `runner.py` -- and produces plain summary
objects; it has no knowledge of any platform, adapter, or driver.
"""

import math
from statistics import fmean

from pydantic import BaseModel, Field

from graphparity.errors import BenchmarkError, ErrorCode

# Percentiles reported in every workload summary. p50 and p95 are the
# two the brief requires; kept as a module-level constant (rather than
# a caller-supplied argument on every call site) so every summary in
# the results matrix reports the exact same set, with no risk of one
# workload silently omitting p95 because a caller forgot to ask for it.
REPORTED_PERCENTILES: tuple[float, ...] = (50.0, 95.0)


class MetricSummary(BaseModel):
    """Aggregated latency statistics for one (platform, workload) pair.

    One instance corresponds to exactly one cell-group in the results
    matrix -- e.g. "CognoDB, 2-hop traversal". `percentiles` holds
    every percentile in `REPORTED_PERCENTILES`, keyed by the requested
    percentile value (e.g. `50.0`, `95.0`), so the README table
    generator can look up `summary.percentiles[95.0]` without this
    module hard-coding a `p95_ms` field that would need editing if the
    reported percentile set ever changes.

    Attributes:
        platform: Platform identifier, matching a `GraphAdapter.name`.
        workload: Workload identifier (e.g. "1_hop_traversal",
            "point_lookup", "aggregation").
        sample_count: Number of samples this summary was computed
            from, after warm-up samples have already been discarded by
            the caller.
        percentiles: Computed percentile values in milliseconds, keyed
            by the percentile requested (50.0 -> p50 value, etc.).
        min_ms: The fastest observed sample.
        max_ms: The slowest observed sample.
        mean_ms: The arithmetic mean of all samples.
    """

    platform: str
    workload: str
    sample_count: int = Field(gt=0)
    percentiles: dict[float, float]
    min_ms: float = Field(ge=0)
    max_ms: float = Field(ge=0)
    mean_ms: float = Field(ge=0)


def compute_percentile(samples: list[float], percentile: float) -> float:
    """Compute one percentile from a list of latency samples.

    Uses linear interpolation between the two nearest ranks (see the
    module docstring for the exact formula). Samples do not need to be
    pre-sorted -- this function sorts a copy internally, so the
    caller's original ordering (e.g. chronological run order) is never
    mutated.

    Args:
        samples: Latency values in milliseconds. Must be non-empty.
        percentile: The percentile to compute, in the range [0, 100].
            50.0 is the median; 95.0 is the p95 the brief requires.

    Returns:
        The interpolated percentile value, in the same units as
        `samples` (milliseconds).

    Raises:
        BenchmarkError: EMPTY_SAMPLE_SET if `samples` is empty -- there
            is no meaningful percentile of zero observations.
        ValueError: If `percentile` is outside the [0, 100] range.
    """
    if not samples:
        raise BenchmarkError(
            code=ErrorCode.EMPTY_SAMPLE_SET,
            context={"operation": "compute_percentile"},
        )

    if not 0 <= percentile <= 100:
        raise ValueError(f"percentile must be within [0, 100], got {percentile}")

    ordered = sorted(samples)
    n = len(ordered)

    if n == 1:
        return ordered[0]

    rank = (percentile / 100) * (n - 1)
    lower_index = math.floor(rank)
    upper_index = math.ceil(rank)

    if lower_index == upper_index:
        return ordered[lower_index]

    weight = rank - lower_index
    lower_value = ordered[lower_index]
    upper_value = ordered[upper_index]
    return lower_value + (upper_value - lower_value) * weight


def summarize(
    platform: str,
    workload: str,
    samples: list[float],
    percentiles: tuple[float, ...] = REPORTED_PERCENTILES,
) -> MetricSummary:
    """Build a full MetricSummary from one platform/workload's raw samples.

    Args:
        platform: Platform identifier, matching a `GraphAdapter.name`.
        workload: Workload identifier this batch of samples came from.
        samples: Latency values in milliseconds, one per timed
            iteration, warm-up iterations already excluded by the
            caller. Must be non-empty.
        percentiles: Which percentiles to compute. Defaults to
            `REPORTED_PERCENTILES` (p50, p95); overridable for a
            one-off deeper look (e.g. p99) without changing what every
            other summary in the matrix reports.

    Returns:
        The aggregated statistics for this platform/workload pair.

    Raises:
        BenchmarkError: EMPTY_SAMPLE_SET if `samples` is empty.
    """
    if not samples:
        raise BenchmarkError(
            code=ErrorCode.EMPTY_SAMPLE_SET,
            context={"platform": platform, "workload": workload},
        )

    return MetricSummary(
        platform=platform,
        workload=workload,
        sample_count=len(samples),
        percentiles={p: compute_percentile(samples, p) for p in percentiles},
        min_ms=min(samples),
        max_ms=max(samples),
        mean_ms=fmean(samples),
    )


def build_results_matrix(
    raw_results: dict[str, dict[str, list[float]]],
    percentiles: tuple[float, ...] = REPORTED_PERCENTILES,
) -> list[MetricSummary]:
    """Build every MetricSummary needed for the README's results matrix.

    Args:
        raw_results: Nested mapping of platform -> workload -> raw
            latency samples in milliseconds, e.g.
            `{"cognodb": {"1_hop_traversal": [12.1, 13.4, ...]}}`.
            This is the shape `runner.py` is expected to produce after
            warm-up samples have already been discarded.
        percentiles: Which percentiles each summary should report.
            Defaults to `REPORTED_PERCENTILES`.

    Returns:
        One `MetricSummary` per (platform, workload) pair, ordered
        first by platform (in `raw_results`' own key order) and then
        by workload (also in that platform's own key order) -- so the
        matrix reads in the same sequence the caller built
        `raw_results`, rather than being silently re-sorted
        alphabetically.

    Raises:
        BenchmarkError: EMPTY_SAMPLE_SET if any (platform, workload)
            entry has zero samples. A gap here means every iteration
            of that workload failed for that platform, which belongs
            in the README's caveats section, not a silently-skipped
            row in the matrix.
    """
    summaries: list[MetricSummary] = []

    for platform, workloads in raw_results.items():
        for workload, samples in workloads.items():
            summaries.append(
                summarize(
                    platform=platform,
                    workload=workload,
                    samples=samples,
                    percentiles=percentiles,
                )
            )

    return summaries
