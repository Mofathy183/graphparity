"""
Error code vocabulary for the GraphParity benchmark harness.

Defines the complete, stable set of machine-readable failure
identifiers that can cross an adapter or config boundary. ErrorCode
values are never user-facing strings and never carry presentation
text -- they are the single vocabulary every BenchmarkError instance
is built from

Adding a new failure mode means adding a new member here first;
nothing downstream should invent an ad hoc string in its place.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable, machine-readable identifiers for every failure this harness can raise.

    Grouped by the boundary that raises them:

    - Adapter-boundary codes (``adapter.*``) are raised only by
      ``GraphAdapter`` implementations, after translating that
      platform's own client-library exception into a BenchmarkError.
    - Config-boundary codes (``config.*``) are raised by
      ``PlatformConfig`` validation at startup.

    Members are intentionally coarse rather than one-per-driver-
    exception: a workload runner or aggregator only needs to know
    *which kind* of failure occurred, not which of the five underlying
    client libraries produced it.
    """

    # --- Adapter boundary --------------------------------------------
    CONNECTION_FAILED = "adapter.connection_failed"
    """The adapter could not establish or maintain a connection to its platform."""

    QUERY_TIMEOUT = "adapter.query_timeout"
    """A query did not complete within the platform's or driver's own timeout."""

    QUERY_FAILED = "adapter.query_failed"
    """A query failed for a reason other than a timeout or lost connection
    (e.g. invalid Cypher/AQL, constraint violation, server-side error)."""

    LOAD_FAILED = "adapter.load_failed"
    """A batch load (``load_batch``) failed partway through or entirely."""

    RESULT_LIMIT_EXCEEDED = "adapter.result_limit_exceeded"
    """A query's result set exceeded a platform-imposed row cap
    (e.g. CognoDB Free's 50,000 max result rows)."""

    # --- Config boundary -----------------------------------------------
    CONFIG_INVALID = "config.invalid"
    """A ``PlatformConfig`` failed validation (bad URI scheme, missing
    credential, or malformed tier spec)."""
