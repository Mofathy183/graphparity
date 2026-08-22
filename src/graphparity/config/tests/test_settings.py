import pytest

from graphparity.config.settings import PlatformsSettings, get_platforms_settings
from graphparity.errors import BenchmarkError, ErrorCode

_ALL_ENV_KEYS = [
    key
    for platform in ("COGNODB", "AURA", "SELF_HOSTED_NEO4J", "MEMGRAPH", "ARANGODB")
    for key in (
        f"GRAPHPARITY_{platform}__NAME",
        f"GRAPHPARITY_{platform}__PROTOCOL",
        f"GRAPHPARITY_{platform}__URI",
        f"GRAPHPARITY_{platform}__USERNAME",
        f"GRAPHPARITY_{platform}__PASSWORD",
        f"GRAPHPARITY_{platform}__DATABASE",
    )
]


@pytest.fixture
def isolated_env(monkeypatch):
    """Clear every GraphParity env var and block real `.env` file reads.

    Two separate leak paths have to be closed for these tests to be
    trustworthy regardless of what's on a developer's disk:

    1. `os.environ` -- closed by clearing every known
       `GRAPHPARITY_<PLATFORM>__*` key via `monkeypatch.delenv`.
    2. The `.env` file itself -- `pydantic-settings` reads this file
       directly as its own source, entirely separate from
       `os.environ`. Clearing env vars does nothing to stop it, so a
       developer's real `.env` (with real CognoDB credentials) would
       otherwise leak into every "default" assertion in this file,
       including through `get_platforms_settings()`'s cached path,
       which does not accept a per-call `_env_file` override. Patching
       `model_config["env_file"]` to `None` for the duration of the
       test is what actually closes this off, for both direct
       `PlatformsSettings()` construction and the cached accessor.
    """
    for key in _ALL_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setitem(PlatformsSettings.model_config, "env_file", None)
    get_platforms_settings.cache_clear()
    yield
    get_platforms_settings.cache_clear()


def _settings(**env_overrides) -> PlatformsSettings:
    """Build a PlatformsSettings instance for a test.

    `isolated_env` has already disabled `.env` file loading at the
    model-config level, so this no longer needs its own `_env_file`
    override -- construction here goes through the exact same path
    `get_platforms_settings()` uses, which is what makes the two
    accessors comparable within a test.
    """
    return PlatformsSettings(**env_overrides)


@pytest.mark.unit
class TestPlatformsSettingsDefaults:
    def test_falls_back_to_default_when_no_env_vars_set(self, isolated_env):
        settings = _settings()

        assert settings.cognodb.name == "cognodb"
        assert settings.aura.name == "aura"
        assert settings.self_hosted_neo4j.name == "self_hosted_neo4j"
        assert settings.memgraph.name == "memgraph"
        assert settings.arangodb.name == "arangodb"

    def test_default_cognodb_uses_bolt_protocol(self, isolated_env):
        settings = _settings()

        assert settings.cognodb.protocol == "bolt"
        assert settings.cognodb.uri.startswith("bolt+s://")

    def test_default_arangodb_uses_http_protocol_with_database(self, isolated_env):
        settings = _settings()

        assert settings.arangodb.protocol == "http"
        assert settings.arangodb.database == "graphparity"

    def test_default_self_hosted_platforms_point_at_localhost(self, isolated_env):
        settings = _settings()

        assert "localhost" in settings.self_hosted_neo4j.uri
        assert "localhost" in settings.memgraph.uri
        assert "localhost" in settings.arangodb.uri

    def test_self_hosted_neo4j_and_memgraph_use_different_ports(self, isolated_env):
        settings = _settings()

        assert settings.self_hosted_neo4j.uri != settings.memgraph.uri


@pytest.mark.unit
class TestPlatformsSettingsEnvOverride:
    def test_full_cognodb_block_overrides_default(self, monkeypatch, isolated_env):
        monkeypatch.setenv("GRAPHPARITY_COGNODB__NAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PROTOCOL", "bolt")
        monkeypatch.setenv(
            "GRAPHPARITY_COGNODB__URI",
            "bolt+s://db-9241e8c7.bravo.databases.cognodb.com:7687",
        )
        monkeypatch.setenv("GRAPHPARITY_COGNODB__USERNAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PASSWORD", "realpassword")

        settings = _settings()

        assert settings.cognodb.uri == (
            "bolt+s://db-9241e8c7.bravo.databases.cognodb.com:7687"
        )
        assert settings.cognodb.password == "realpassword"

    def test_overriding_one_platform_does_not_affect_others(
        self, monkeypatch, isolated_env
    ):
        monkeypatch.setenv("GRAPHPARITY_COGNODB__NAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PROTOCOL", "bolt")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__URI", "bolt+s://real:7687")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__USERNAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PASSWORD", "realpassword")

        settings = _settings()

        assert settings.aura.uri.startswith("bolt+s://replace-me")

    def test_full_arangodb_block_override_including_database(
        self, monkeypatch, isolated_env
    ):
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__NAME", "arangodb")
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__PROTOCOL", "http")
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__URI", "http://myhost:8529")
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__USERNAME", "root")
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__PASSWORD", "pw")
        monkeypatch.setenv("GRAPHPARITY_ARANGODB__DATABASE", "custom_db")

        settings = _settings()

        assert settings.arangodb.uri == "http://myhost:8529"
        assert settings.arangodb.database == "custom_db"


@pytest.mark.unit
class TestPlatformsSettingsPartialEnvBlockFails:
    """Documents the pydantic-settings all-or-nothing nested-field rule
    described in settings.py's module docstring: setting only some of
    a platform's variables (omitting NAME/PROTOCOL) fails construction
    rather than falling back to defaults for the missing ones.
    """

    def test_missing_name_and_protocol_raises_when_other_fields_set(
        self, monkeypatch, isolated_env
    ):
        monkeypatch.setenv("GRAPHPARITY_COGNODB__URI", "bolt+s://x:7687")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__USERNAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PASSWORD", "pw")

        with pytest.raises(Exception):  # noqa: B017 -- pydantic "Field required"
            _settings()


@pytest.mark.unit
class TestPlatformsSettingsValidatorsStillApply:
    def test_env_supplied_uri_still_validated_against_protocol(
        self, monkeypatch, isolated_env
    ):
        monkeypatch.setenv("GRAPHPARITY_COGNODB__NAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PROTOCOL", "bolt")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__URI", "http://wrong-scheme")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__USERNAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PASSWORD", "pw")

        with pytest.raises(BenchmarkError) as exc_info:
            _settings()

        assert exc_info.value.code == ErrorCode.CONFIG_INVALID


@pytest.mark.unit
class TestAllPlatforms:
    def test_returns_five_platforms(self, isolated_env):
        settings = _settings()

        assert len(settings.all_platforms()) == 5

    def test_returns_cognodb_first(self, isolated_env):
        settings = _settings()

        assert settings.all_platforms()[0].name == "cognodb"

    def test_returns_platforms_in_documented_order(self, isolated_env):
        settings = _settings()

        names = [p.name for p in settings.all_platforms()]

        assert names == [
            "cognodb",
            "aura",
            "self_hosted_neo4j",
            "memgraph",
            "arangodb",
        ]

    def test_every_returned_item_is_a_platform_config(self, isolated_env):
        from graphparity.config.platform_config import PlatformConfig

        settings = _settings()

        assert all(isinstance(p, PlatformConfig) for p in settings.all_platforms())


@pytest.mark.unit
class TestGetPlatformsSettingsCaching:
    def test_returns_same_instance_on_repeated_calls(self, isolated_env):
        first = get_platforms_settings()
        second = get_platforms_settings()

        assert first is second

    def test_cache_clear_allows_picking_up_new_env_vars(
        self, monkeypatch, isolated_env
    ):
        first = get_platforms_settings()
        assert first.cognodb.password == "replace-me"

        monkeypatch.setenv("GRAPHPARITY_COGNODB__NAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PROTOCOL", "bolt")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__URI", "bolt+s://x:7687")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__USERNAME", "cognodb")
        monkeypatch.setenv("GRAPHPARITY_COGNODB__PASSWORD", "newpassword")
        get_platforms_settings.cache_clear()

        second = get_platforms_settings()

        assert second.cognodb.password == "newpassword"
