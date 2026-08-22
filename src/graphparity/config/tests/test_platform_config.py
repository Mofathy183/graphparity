import pytest

from graphparity.config.platform_config import PlatformConfig
from graphparity.errors import BenchmarkError, ErrorCode


def _valid_bolt_kwargs(**overrides):
    kwargs = {
        "name": "self_hosted_neo4j",
        "protocol": "bolt",
        "uri": "bolt://localhost:7687",
        "username": "neo4j",
        "password": "devpassword",
    }
    kwargs.update(overrides)
    return kwargs


def _valid_http_kwargs(**overrides):
    kwargs = {
        "name": "arangodb",
        "protocol": "http",
        "uri": "http://localhost:8529",
        "username": "root",
        "password": "devpassword",
        "database": "graphparity",
    }
    kwargs.update(overrides)
    return kwargs


@pytest.mark.unit
class TestPlatformConfigValidConstruction:
    def test_creates_valid_bolt_config(self):
        config = PlatformConfig(**_valid_bolt_kwargs())

        assert config.name == "self_hosted_neo4j"
        assert config.protocol == "bolt"
        assert config.uri == "bolt://localhost:7687"
        assert config.database is None

    def test_creates_valid_bolt_s_config(self):
        config = PlatformConfig(
            **_valid_bolt_kwargs(
                uri="bolt+s://db-9241e8c7.bravo.databases.cognodb.com:7687"
            )
        )

        assert config.uri.startswith("bolt+s://")

    def test_creates_valid_http_config(self):
        config = PlatformConfig(**_valid_http_kwargs())

        assert config.protocol == "http"
        assert config.database == "graphparity"

    def test_creates_valid_https_config(self):
        config = PlatformConfig(**_valid_http_kwargs(uri="https://example.cloud:8529"))

        assert config.uri.startswith("https://")

    def test_bolt_config_database_defaults_to_none(self):
        config = PlatformConfig(**_valid_bolt_kwargs())

        assert config.database is None

    def test_bolt_config_accepts_optional_database(self):
        config = PlatformConfig(**_valid_bolt_kwargs(database="neo4j"))

        assert config.database == "neo4j"


@pytest.mark.unit
class TestPlatformConfigUriProtocolMismatch:
    def test_raises_config_invalid_when_bolt_protocol_has_http_uri(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_bolt_kwargs(uri="http://localhost:8529"))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_raises_config_invalid_when_http_protocol_has_bolt_uri(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_http_kwargs(uri="bolt://localhost:7687"))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_uri_mismatch_error_context_includes_platform_name(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_bolt_kwargs(name="cognodb", uri="http://bad"))

        assert exc_info.value.context["platform"] == "cognodb"

    def test_uri_mismatch_error_context_includes_field(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_bolt_kwargs(uri="http://bad"))

        assert exc_info.value.context["field"] == "uri"

    def test_raises_config_invalid_for_unscheduled_uri(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_bolt_kwargs(uri="localhost:7687"))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_raises_config_invalid_for_empty_scheme_uri(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_bolt_kwargs(uri="ftp://localhost"))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID


@pytest.mark.unit
class TestPlatformConfigDatabaseRequiredForHttp:
    def test_raises_config_invalid_when_http_protocol_has_no_database(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_http_kwargs(database=None))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_raises_config_invalid_when_http_protocol_has_blank_database(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_http_kwargs(database=""))

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID

    def test_database_error_context_names_the_field(self):
        with pytest.raises(BenchmarkError) as exc_info:
            PlatformConfig(**_valid_http_kwargs(database=None))

        assert exc_info.value.context["field"] == "database"

    def test_bolt_protocol_does_not_require_database(self):
        config = PlatformConfig(**_valid_bolt_kwargs(database=None))

        assert config.database is None


@pytest.mark.unit
class TestPlatformConfigMissingCredentials:
    def test_raises_validation_error_for_blank_username(self):
        with pytest.raises(Exception):  # noqa: B017 -- pydantic.ValidationError, not BenchmarkError
            PlatformConfig(**_valid_bolt_kwargs(username=""))

    def test_raises_validation_error_for_blank_password(self):
        with pytest.raises(Exception):  # noqa: B017
            PlatformConfig(**_valid_bolt_kwargs(password=""))

    def test_raises_validation_error_for_blank_name(self):
        with pytest.raises(Exception):  # noqa: B017
            PlatformConfig(**_valid_bolt_kwargs(name=""))

    def test_raises_validation_error_for_blank_uri(self):
        with pytest.raises(Exception):  # noqa: B017
            PlatformConfig(**_valid_bolt_kwargs(uri=""))


@pytest.mark.unit
class TestPlatformConfigInvalidProtocol:
    def test_raises_validation_error_for_unknown_protocol(self):
        with pytest.raises(Exception):  # noqa: B017 -- pydantic literal validation
            PlatformConfig(**_valid_bolt_kwargs(protocol="grpc"))


@pytest.mark.unit
class TestPlatformConfigBenchmarkErrorNotWrapped:
    """Proves BenchmarkError propagates as-is from validators, rather
    than being swallowed and re-wrapped into pydantic.ValidationError.

    This matters because BenchmarkError is meant to be the single
    exception type crossing every GraphParity component boundary,
    config included -- if Pydantic silently wrapped it, callers
    catching BenchmarkError specifically would miss config failures.
    """

    def test_catching_benchmark_error_directly_works(self):
        try:
            PlatformConfig(**_valid_bolt_kwargs(uri="http://wrong"))
            pytest.fail("expected BenchmarkError to be raised")
        except BenchmarkError as exc:
            assert exc.code == ErrorCode.CONFIG_INVALID
