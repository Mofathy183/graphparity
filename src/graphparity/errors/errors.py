"""
BenchmarkError: the single exception type crossing every component
boundary in GraphParity.

a frozen dataclass carrying a stable ErrorCode, an optional context mapping for
logging/interpolation, and an optional original-exception cause kept
out of equality comparisons. Every adapter and config validator must
raise this type -- or let it propagate -- rather than a raw driver or
client-library exception. Proving that translation boundary holds is
the point of every adapter integration test in this project.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field

from .codes import ErrorCode


@dataclass(frozen=True)
class BenchmarkError(Exception):
    """The only exception type permitted to cross a component boundary.

    Attributes:
        code: The stable, machine-readable failure identifier. Callers
            branch on this, never on the exception's message or on
            `isinstance` checks against a driver-specific type -- there
            is only ever one exception type in this codebase.
        context: Structured key/value pairs describing the failure
            Used for logging and, where useful,
            downstream message interpolation. Never contains
            presentation text itself.
        cause: The original client-library exception this
            BenchmarkError was translated from, if any. Excluded from
            equality/hash comparisons (``compare=False``) so two
            errors with the same code and context compare equal
            regardless of which underlying exception triggered them.
    """

    code: ErrorCode
    context: Mapping[str, str] = field(default_factory=dict)
    cause: BaseException | None = field(default=None, compare=False)

    def __str__(self) -> str:
        """Render a debug-friendly string for logs and tracebacks.

        Returns:
            The error code, followed by its context mapping when one
            was supplied.
        """
        if self.context:
            return f"{self.code}: {dict(self.context)}"
        return str(self.code)
