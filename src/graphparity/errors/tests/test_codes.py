import pytest

from graphparity.errors.codes import ErrorCode


@pytest.mark.unit
class TestErrorCode:
    def test_every_member_has_a_string_value(self):
        assert all(isinstance(member.value, str) for member in ErrorCode)

    def test_every_member_value_is_unique(self):
        values = [member.value for member in ErrorCode]

        assert len(values) == len(set(values))

    @pytest.mark.parametrize(
        "code",
        [
            ErrorCode.CONNECTION_FAILED,
            ErrorCode.QUERY_TIMEOUT,
            ErrorCode.QUERY_FAILED,
            ErrorCode.LOAD_FAILED,
            ErrorCode.RESULT_LIMIT_EXCEEDED,
        ],
    )
    def test_adapter_boundary_codes_use_adapter_prefix(self, code):
        assert code.value.startswith("adapter.")

    def test_config_invalid_uses_config_prefix(self):
        assert ErrorCode.CONFIG_INVALID.value.startswith("config.")