from dataclasses import FrozenInstanceError

import pytest

from graphparity.errors.codes import ErrorCode
from graphparity.errors.errors import BenchmarkError


@pytest.mark.unit
class TestBenchmarkErrorConstruction:
    def test_creates_error_with_code_only(self):
        error = BenchmarkError(code=ErrorCode.QUERY_FAILED)

        assert error.code == ErrorCode.QUERY_FAILED
        assert error.context == {}
        assert error.cause is None

    def test_creates_error_with_context(self):
        error = BenchmarkError(
            code=ErrorCode.CONNECTION_FAILED,
            context={"platform": "aura"},
        )

        assert error.context["platform"] == "aura"

    def test_creates_error_with_cause(self):
        original = ValueError("boom")

        error = BenchmarkError(code=ErrorCode.QUERY_FAILED, cause=original)

        assert error.cause is original

    def test_is_an_exception(self):
        error = BenchmarkError(code=ErrorCode.QUERY_FAILED)

        assert isinstance(error, Exception)


@pytest.mark.unit
class TestBenchmarkErrorImmutability:
    def test_raises_when_code_is_mutated(self):
        error = BenchmarkError(code=ErrorCode.QUERY_FAILED)

        with pytest.raises(FrozenInstanceError):
            error.code = ErrorCode.LOAD_FAILED  # ty:ignore[invalid-assignment]

    def test_raises_when_context_is_mutated(self):
        error = BenchmarkError(code=ErrorCode.QUERY_FAILED)

        with pytest.raises(FrozenInstanceError):
            error.context = {"x": "1"}  # ty:ignore[invalid-assignment]


@pytest.mark.unit
class TestBenchmarkErrorEquality:
    def test_equal_when_code_and_context_match(self):
        error_a = BenchmarkError(code=ErrorCode.QUERY_FAILED, context={"x": "1"})
        error_b = BenchmarkError(code=ErrorCode.QUERY_FAILED, context={"x": "1"})

        assert error_a == error_b

    def test_not_equal_when_codes_differ(self):
        error_a = BenchmarkError(code=ErrorCode.QUERY_FAILED)
        error_b = BenchmarkError(code=ErrorCode.LOAD_FAILED)

        assert error_a != error_b

    def test_equality_ignores_cause(self):
        error_a = BenchmarkError(code=ErrorCode.QUERY_FAILED, cause=ValueError("a"))
        error_b = BenchmarkError(code=ErrorCode.QUERY_FAILED, cause=ValueError("b"))

        assert error_a == error_b


@pytest.mark.unit
class TestBenchmarkErrorStringRepresentation:
    def test_str_includes_code_when_context_is_empty(self):
        error = BenchmarkError(code=ErrorCode.QUERY_TIMEOUT)

        assert str(error) == "adapter.query_timeout"

    def test_str_includes_context_when_present(self):
        error = BenchmarkError(
            code=ErrorCode.QUERY_TIMEOUT,
            context={"platform": "cognodb"},
        )

        assert "adapter.query_timeout" in str(error)
        assert "cognodb" in str(error)


@pytest.mark.unit
class TestBenchmarkErrorRaising:
    def test_can_be_raised_and_caught_by_type(self):
        with pytest.raises(BenchmarkError) as exc_info:
            raise BenchmarkError(code=ErrorCode.LOAD_FAILED)

        assert exc_info.value.code == ErrorCode.LOAD_FAILED

    def test_preserves_cause_through_raise_from(self):
        original = ConnectionError("refused")

        with pytest.raises(BenchmarkError) as exc_info:
            try:
                raise original
            except ConnectionError as exc:
                raise BenchmarkError(
                    code=ErrorCode.CONNECTION_FAILED, cause=exc
                ) from exc

        assert exc_info.value.cause is original
        assert exc_info.value.__cause__ is original
