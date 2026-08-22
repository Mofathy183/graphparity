"""
Unit tests for the CognoDB adapter's pure-logic surfaces.

Scoped deliberately narrow: only `_translate_query_error` (a pure
function, no I/O) and the not-connected guard clauses in `run_query`
and `load_batch` (branches that raise before ever touching the
network) are covered here. Everything else in CognoDBAdapter --
connect(), the actual session.run() calls, real MERGE batching -- is
real network I/O against a live neo4j driver and belongs in an
`@pytest.mark.integration` suite against a real CognoDB instance, not
here. Mocking `AsyncDriver`/`AsyncGraphDatabase` deeply enough to fake
that boundary would mostly test the mock, not the adapter.

This keeps the file consistent with the project's own coverage policy
for `adapters/*`: the translation boundary (client exception ->
BenchmarkError) is the one piece of adapter logic that must have a
real assertion regardless of how thin the surrounding I/O plumbing's
test coverage is.
"""

import pytest
from neo4j.exceptions import ClientError, ServiceUnavailable, TransientError

from graphparity.adapters.cognodb import (
    _RESULT_LIMIT_ERROR_CODE,
    CognoDBAdapter,
    _translate_query_error,
)
from graphparity.errors import BenchmarkError, ErrorCode


class _FakeClientError(ClientError):
    """A ClientError with a settable `.code`, for exercising
    `_translate_query_error`'s code-inspection branch.

    The real neo4j driver only produces a ClientError with a specific
    `.code` value through its own private wire-hydration path, which
    is version-fragile internal machinery not meant to be constructed
    directly by a test. This subclass sets the same public attributes
    the driver's hydration populates, so `_translate_query_error` sees
    exactly the shape it would see from a real driver-raised error,
    without depending on that private construction path.
    """

    def __init__(self, message: str, code: str) -> None:
        Exception.__init__(self, message)
        self._neo4j_code = code
        self._classification = "ClientError"
        self._category = "Statement"
        self._title = "GeneratedForTest"
        self._from_server = False


@pytest.mark.unit
class TestTranslateQueryErrorConnectionFailed:
    def test_maps_service_unavailable_to_connection_failed(self):
        original = ServiceUnavailable("no route to host")

        result = _translate_query_error(original)

        assert isinstance(result, BenchmarkError)
        assert result.code == ErrorCode.CONNECTION_FAILED

    def test_preserves_original_exception_as_cause(self):
        original = ServiceUnavailable("no route to host")

        result = _translate_query_error(original)

        assert result.cause is original


@pytest.mark.unit
class TestTranslateQueryErrorQueryTimeout:
    def test_maps_transient_error_to_query_timeout(self):
        original = TransientError("deadlock, retry")

        result = _translate_query_error(original)

        assert result.code == ErrorCode.QUERY_TIMEOUT

    def test_preserves_original_exception_as_cause(self):
        original = TransientError("deadlock, retry")

        result = _translate_query_error(original)

        assert result.cause is original


@pytest.mark.unit
class TestTranslateQueryErrorResultLimitExceeded:
    def test_maps_result_limit_client_error_to_result_limit_exceeded(self):
        original = _FakeClientError("row cap hit", code=_RESULT_LIMIT_ERROR_CODE)

        result = _translate_query_error(original)

        assert result.code == ErrorCode.RESULT_LIMIT_EXCEEDED

    def test_preserves_original_exception_as_cause(self):
        original = _FakeClientError("row cap hit", code=_RESULT_LIMIT_ERROR_CODE)

        result = _translate_query_error(original)

        assert result.cause is original


@pytest.mark.unit
class TestTranslateQueryErrorGenericClientError:
    def test_maps_other_client_error_codes_to_query_failed(self):
        original = _FakeClientError(
            "invalid Cypher", code="Neo.ClientError.Statement.SyntaxError"
        )

        result = _translate_query_error(original)

        assert result.code == ErrorCode.QUERY_FAILED


@pytest.mark.unit
class TestTranslateQueryErrorFallback:
    def test_maps_unrecognized_exception_type_to_query_failed(self):
        original = ValueError("something unrelated to neo4j")

        result = _translate_query_error(original)

        assert result.code == ErrorCode.QUERY_FAILED

    def test_preserves_original_exception_as_cause_for_fallback_case(self):
        original = ValueError("something unrelated to neo4j")

        result = _translate_query_error(original)

        assert result.cause is original


@pytest.mark.unit
class TestCognoDBAdapterConstruction:
    def test_stores_connection_parameters_without_connecting(self):
        adapter = CognoDBAdapter(
            uri="bolt+s://example.databases.cognodb.com:7687",
            username="cognodb",
            password="secret",
        )

        assert adapter.name == "cognodb"

    def test_name_is_always_cognodb_regardless_of_uri(self):
        adapter = CognoDBAdapter(
            uri="bolt+s://anything:7687", username="u", password="p"
        )

        assert adapter.name == "cognodb"


@pytest.mark.unit
class TestCognoDBAdapterNotConnectedGuards:
    """Covers the fail-fast branches that raise before any network I/O --
    calling run_query or load_batch before connect() has succeeded.
    """

    async def test_run_query_raises_connection_failed_when_never_connected(self):
        adapter = CognoDBAdapter(
            uri="bolt+s://example.databases.cognodb.com:7687",
            username="cognodb",
            password="secret",
        )

        with pytest.raises(BenchmarkError) as exc_info:
            await adapter.run_query("RETURN 1", {})

        assert exc_info.value.code == ErrorCode.CONNECTION_FAILED

    async def test_load_batch_raises_connection_failed_when_never_connected(self):
        adapter = CognoDBAdapter(
            uri="bolt+s://example.databases.cognodb.com:7687",
            username="cognodb",
            password="secret",
        )

        with pytest.raises(BenchmarkError) as exc_info:
            await adapter.load_batch([{"id": "n1", "category": "standard"}], [])

        assert exc_info.value.code == ErrorCode.CONNECTION_FAILED

    async def test_disconnect_is_safe_to_call_without_prior_connect(self):
        adapter = CognoDBAdapter(
            uri="bolt+s://example.databases.cognodb.com:7687",
            username="cognodb",
            password="secret",
        )

        await adapter.disconnect()  # must not raise
