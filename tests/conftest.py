"""
Root pytest configuration: fixture registration and marker enforcement.

Mirrors PyLedger's root conftest.py exactly in mechanism -- only the
layer taxonomy changes, since this project has errors/adapters/
workloads/aggregate instead of core/infra/cli/api. The hook doesn't
know or care that it's not accounting domains anymore.

Two-axis marker discipline:

    Speed axis   {"unit", "integration"} -- hand-written on the test
                itself. Whether a test performs real I/O is a fact
                about its own body, not its file location.

    Layer axis   {"errors", "adapters", "workloads", "aggregate"} --
                derived from the test file's path and applied
                automatically. Hand-writing a layer marker is a
                collection error.

Every collected test must resolve to exactly one marker from each
axis, or collection fails loudly with a batched report -- the same
correctness-gate behavior PyLedger's own conftest.py documents.
"""

import pathlib

import pytest

_SPEED_MARKERS: frozenset[str] = frozenset({"unit", "integration"})
_LAYER_MARKERS: frozenset[str] = frozenset(
    {"errors", "config", "adapters", "workloads", "aggregate"}
)

# Directory name -> layer marker. First match wins.
_LAYER_DIRS: dict[str, str] = {
    "errors": "errors",
    "config": "config",
    "adapters": "adapters",
    "workloads": "workloads",
}

# Files that live directly under tests/ and cover aggregate.py/runner.py
# rather than a per-platform or per-workload directory.
_AGGREGATE_FILENAMES: frozenset[str] = frozenset(
    {"test_aggregate.py", "test_runner.py"}
)


def _derive_layer(path_parts: tuple[str, ...], filename: str) -> str | None:
    """Infer a test's layer marker from its file path.

    Returns None when the path matches nothing known, which the
    caller treats as a hard collection error rather than an
    unclassified test.
    """
    for dirname, marker in _LAYER_DIRS.items():
        if dirname in path_parts:
            return marker

    if filename in _AGGREGATE_FILENAMES:
        return "aggregate"

    return None


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Enforce and auto-apply the two-axis test marker discipline."""
    violations: list[str] = []

    for item in items:
        path = pathlib.Path(str(item.fspath))
        path_parts = path.parts
        own_markers = {marker.name for marker in item.iter_markers()}

        declared_speed = _SPEED_MARKERS.intersection(own_markers)
        if len(declared_speed) != 1:
            violations.append(
                f"{item.nodeid}: must carry exactly one of "
                f"{sorted(_SPEED_MARKERS)}, found {sorted(declared_speed)}"
            )

        derived_layer = _derive_layer(path_parts, path.name)
        declared_layer = _LAYER_MARKERS.intersection(own_markers)

        if derived_layer is None:
            violations.append(
                f"{item.nodeid}: path does not map to any known layer "
                f"{sorted(_LAYER_MARKERS)}; move the file under a "
                f"recognized directory or update _LAYER_DIRS/"
                f"_AGGREGATE_FILENAMES in conftest.py"
            )
        elif declared_layer and declared_layer != {derived_layer}:
            violations.append(
                f"{item.nodeid}: path implies layer marker "
                f"'{derived_layer}' but test declares "
                f"{sorted(declared_layer)} -- remove the hand-written "
                f"layer marker; layer markers are derived from file "
                f"path, never authored on the test"
            )
        else:
            item.add_marker(getattr(pytest.mark, derived_layer))

    if violations:
        report = "\n".join(f"  - {violation}" for violation in violations)
        raise pytest.UsageError(f"Marker validation failed:\n{report}")
