"""
Orchestrates warm-up-then-timed runs of every required workload shape
against every connected platform adapter.

runner.py is the one module that actually drives run_traversal,
run_point_lookup, run_indexed_lookup, run_aggregation, and
run_mixed_workload against a real (or fake, in tests) GraphAdapter, and
assembles their raw latency samples into the nested
platform -> workload -> list[float] shape aggregate.build_results_matrix
expects. It performs no percentile computation itself -- that stays in
aggregate.py, which has no knowledge of any adapter or platform.

Every workload call is wrapped in a per-platform, per-workload
structlog binding so a failed or retried query can be traced back to
exactly which platform and workload produced it from the log output
alone, without needing to reproduce the failure to find out.
"""

import structlog

from graphparity.adapters.protocol import GraphAdapter
from graphparity.errors import BenchmarkError
from graphparity.workloads.aggregation import run_aggregation
from graphparity.workloads.common import Protocol
from graphparity.workloads.lookup import run_indexed_lookup, run_point_lookup
from graphparity.workloads.mixed import run_mixed_workload
from graphparity.workloads.traversal import run_traversal

logger = structlog.get_logger(__name__)

# Workload identifiers, keyed the same way aggregate.build_results_matrix's
# raw_results mapping expects under each platform. Kept as module-level
# constants rather than inlined strings so a reader of a results matrix
# and a reader of this module's tests are looking at the same literal
# values.
TRAVERSAL_HOPS: tuple[int, ...] = (1, 2, 3)
POINT_LOOKUP_WORKLOAD = "point_lookup"
INDEXED_LOOKUP_WORKLOAD = "indexed_lookup"
AGGREGATION_WORKLOAD = "aggregation"
DEFAULT_MIXED_CONCURRENCIES: tuple[int, ...] = (10, 40)


def _traversal_workload_name(hops: int) -> str:
    """Return the results-matrix key for a given traversal depth."""
    return f"{hops}_hop_traversal"


def _mixed_workload_name(concurrency: int) -> str:
    """Return the results-matrix key for a mixed run at a concurrency level."""
    return f"mixed_{concurrency}_concurrency"


async def run_platform_workloads(
    adapter: GraphAdapter,
    protocol: Protocol,
    node_ids: list[str],
    categories: list[str],
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
    mixed_concurrencies: tuple[int, ...] = DEFAULT_MIXED_CONCURRENCIES,
    mixed_duration_seconds: float = 5.0,
) -> dict[str, list[float]]:
    """Run every required workload shape once against one connected adapter.

    Assumes `adapter` is already connected -- connection lifecycle is
    `run_all_platforms`'s responsibility, not this function's, so a
    caller that already manages its own single adapter (e.g. an
    adapter's own integration test) can call this directly without
    fighting an unwanted connect/disconnect.

    Args:
        adapter: The already-connected GraphAdapter to benchmark.
        protocol: "bolt" for Cypher platforms, "http" for ArangoDB.
        node_ids: Candidate start-node identifiers for traversal, point
            lookup, and mixed workloads.
        categories: Candidate values for the indexed lookup workload's
            filtered property.
        warmup_iterations: Discarded iterations before timing starts,
            applied to every read workload.
        timed_iterations: Timed iterations kept per read workload.
        mixed_concurrencies: Concurrency levels to run the mixed
            read/write workload at. Defaults to (10, 40), the two
            levels the brief requires.
        mixed_duration_seconds: Wall-clock duration each mixed-workload
            concurrency level runs for.

    Returns:
        A mapping of workload name to its raw latency samples in
        milliseconds -- one entry per traversal depth, lookup shape,
        aggregation, and mixed-workload concurrency level. Mixed
        workload entries combine read and write latencies into a
        single list, since aggregate.py reports one summary per
        workload name rather than splitting reads and writes into
        separate rows.

    Raises:
        BenchmarkError: Whatever the underlying workload raises on its
            first failed query -- this function does not retry or
            swallow adapter failures for a single workload; that
            decision belongs to `run_all_platforms`, which decides
            whether one workload's failure should abort the whole
            platform run.
    """
    platform = adapter.name
    log = logger.bind(platform=platform)
    results: dict[str, list[float]] = {}

    for hops in TRAVERSAL_HOPS:
        workload = _traversal_workload_name(hops)
        log.info("workload.starting", workload=workload)
        try:
            results[workload] = await run_traversal(
                adapter,
                protocol,
                node_ids,
                hops=hops,
                warmup_iterations=warmup_iterations,
                timed_iterations=timed_iterations,
            )
        except BenchmarkError as exc:
            log.error("workload.failed", workload=workload, error=str(exc))
            raise

    log.info("workload.starting", workload=POINT_LOOKUP_WORKLOAD)
    try:
        results[POINT_LOOKUP_WORKLOAD] = await run_point_lookup(
            adapter,
            protocol,
            node_ids,
            warmup_iterations=warmup_iterations,
            timed_iterations=timed_iterations,
        )
    except BenchmarkError as exc:
        log.error("workload.failed", workload=POINT_LOOKUP_WORKLOAD, error=str(exc))
        raise

    log.info("workload.starting", workload=INDEXED_LOOKUP_WORKLOAD)
    try:
        results[INDEXED_LOOKUP_WORKLOAD] = await run_indexed_lookup(
            adapter,
            protocol,
            categories,
            warmup_iterations=warmup_iterations,
            timed_iterations=timed_iterations,
        )
    except BenchmarkError as exc:
        log.error("workload.failed", workload=INDEXED_LOOKUP_WORKLOAD, error=str(exc))
        raise

    log.info("workload.starting", workload=AGGREGATION_WORKLOAD)
    try:
        results[AGGREGATION_WORKLOAD] = await run_aggregation(
            adapter,
            protocol,
            warmup_iterations=warmup_iterations,
            timed_iterations=timed_iterations,
        )
    except BenchmarkError as exc:
        log.error("workload.failed", workload=AGGREGATION_WORKLOAD, error=str(exc))
        raise

    for concurrency in mixed_concurrencies:
        workload = _mixed_workload_name(concurrency)
        log.info("workload.starting", workload=workload, concurrency=concurrency)
        try:
            mixed_result = await run_mixed_workload(
                adapter,
                protocol,
                node_ids,
                concurrency=concurrency,
                duration_seconds=mixed_duration_seconds,
            )
        except BenchmarkError as exc:
            log.error("workload.failed", workload=workload, error=str(exc))
            raise
        results[workload] = (
            mixed_result.read_latencies_ms + mixed_result.write_latencies_ms
        )

    return results


async def run_all_platforms(
    adapters: list[GraphAdapter],
    protocols: dict[str, Protocol],
    node_ids: list[str],
    categories: list[str],
    warmup_iterations: int = 10,
    timed_iterations: int = 100,
    mixed_concurrencies: tuple[int, ...] = DEFAULT_MIXED_CONCURRENCIES,
    mixed_duration_seconds: float = 5.0,
) -> dict[str, dict[str, list[float]]]:
    """Connect, benchmark, and disconnect every platform in sequence.

    Platforms run one at a time, not concurrently -- concurrency in
    this harness is a property of the mixed workload's own worker pool
    (see run_mixed_workload), not of running multiple platforms against
    each other at once, which would make each platform's numbers depend
    on how busy the client machine happened to be during a neighboring
    platform's run.

    A platform whose workload run raises BenchmarkError is disconnected
    and skipped rather than aborting the entire run -- one platform
    being unreachable or throttled should not prevent the other four
    from producing results. The failure is logged with full context
    before being swallowed here; it is the caller's job to treat a
    platform missing from the returned mapping as a data-collection gap
    requiring a caveat in the results, not a silent success.

    Args:
        adapters: The GraphAdapter instances to benchmark, in the order
            they should run.
        protocols: Maps each adapter's `name` to the protocol family
            ("bolt" or "http") its queries must be expressed in.
        node_ids: Candidate start-node identifiers, shared across every
            platform so the same logical query shapes run everywhere.
        categories: Candidate values for the indexed lookup workload.
        warmup_iterations: Discarded iterations before timing starts.
        timed_iterations: Timed iterations kept per read workload.
        mixed_concurrencies: Concurrency levels for the mixed workload.
        mixed_duration_seconds: Wall-clock duration per mixed-workload
            concurrency level.

    Returns:
        A mapping of platform name to that platform's workload results,
        in the exact nested shape aggregate.build_results_matrix expects
        as its raw_results argument. A platform that failed entirely is
        omitted from this mapping rather than included with empty
        samples, since build_results_matrix treats an empty sample list
        as EMPTY_SAMPLE_SET rather than "this platform was skipped".
    """
    raw_results: dict[str, dict[str, list[float]]] = {}

    for adapter in adapters:
        platform = adapter.name
        protocol = protocols[platform]
        log = logger.bind(platform=platform)

        log.info("platform.connecting")
        await adapter.connect()
        try:
            log.info("platform.starting")
            raw_results[platform] = await run_platform_workloads(
                adapter,
                protocol,
                node_ids,
                categories,
                warmup_iterations=warmup_iterations,
                timed_iterations=timed_iterations,
                mixed_concurrencies=mixed_concurrencies,
                mixed_duration_seconds=mixed_duration_seconds,
            )
            log.info("platform.completed")
        except BenchmarkError as exc:
            log.error("platform.skipped", error=str(exc))
        finally:
            await adapter.disconnect()

    return raw_results


def main() -> None:
    """Entry point placeholder for `uv run graphparity`.

    Wiring this up to real platform adapters, environment-sourced
    PlatformConfig instances, and a loaded dataset's node_ids/categories
    is deliberately left to scripts/run_all.py rather than this
    function -- main() exists so the console-script entry point
    resolves from day one, not to own orchestration policy that depends
    on infrastructure this module doesn't import.
    """
    print("GraphParity scaffold is up. Nothing to benchmark yet.")


if __name__ == "__main__":
    main()
