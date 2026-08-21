"""
Environment loading for GraphParity's five platform configurations.

PlatformConfig (platform_config.py) describes the *shape* one platform
must satisfy; this module is the one place that actually reads the
environment and assembles all five named instances from it -- mirroring
how PyLedger's `packages/config/src/pyledger/config/base.py::Settings`
nests `MongoSettings`/`ApiSettings` under one root `BaseSettings` rather
than having each nested model load itself independently.

Only this module touches `pydantic_settings.BaseSettings`. Everything
downstream (the workload runner, adapters, aggregate.py) receives an
already-constructed `PlatformConfig` and never reads an environment
variable directly.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .platform_config import PlatformConfig


class PlatformsSettings(BaseSettings):
    """Root settings object assembling every platform's PlatformConfig.

    Each field is one platform, populated from its own
    double-underscore-delimited env-var block (e.g.
    `GRAPHPARITY_COGNODB__URI`, `GRAPHPARITY_COGNODB__USERNAME`,
    `GRAPHPARITY_COGNODB__PASSWORD`). `PlatformConfig`'s own validators
    still run on construction of each nested field, so a bad scheme or
    missing credential on any single platform fails loudly here, at
    startup, rather than 20 hours into a load run against a
    misconfigured instance.

    `name`/`protocol` are given sensible defaults per field so a
    contributor only has to set connection details in `.env` -- not
    repeat `protocol=bolt` for every Bolt platform by hand. Defaults
    are overridable via the same env-var block if a platform's
    protocol ever changes (e.g. a future ArangoDB Bolt-compatible
    proxy).
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAPHPARITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    cognodb: PlatformConfig = Field(
        default_factory=lambda: PlatformConfig(
            name="cognodb",
            protocol="bolt",
            uri="bolt+s://replace-me.databases.cognodb.com:7687",
            username="cognodb",
            password="replace-me",
        )
    )
    aura: PlatformConfig = Field(
        default_factory=lambda: PlatformConfig(
            name="aura",
            protocol="bolt",
            uri="bolt+s://replace-me.databases.neo4j.io:7687",
            username="neo4j",
            password="replace-me",
        )
    )
    self_hosted_neo4j: PlatformConfig = Field(
        default_factory=lambda: PlatformConfig(
            name="self_hosted_neo4j",
            protocol="bolt",
            uri="bolt://localhost:7687",
            username="neo4j",
            password="devpassword",
        )
    )
    memgraph: PlatformConfig = Field(
        default_factory=lambda: PlatformConfig(
            name="memgraph",
            protocol="bolt",
            uri="bolt://localhost:7688",
            username="memgraph",
            password="devpassword",
        )
    )
    arangodb: PlatformConfig = Field(
        default_factory=lambda: PlatformConfig(
            name="arangodb",
            protocol="http",
            uri="http://localhost:8529",
            username="root",
            password="devpassword",
            database="graphparity",
        )
    )

    def all_platforms(self) -> list[PlatformConfig]:
        """Return every configured platform, in a stable, deliberate order.

        Order is CognoDB first (the one live, confirmed endpoint),
        then AuraDB Free, then the three self-hosted engines --
        matching the build order and the load-run order documented in
        the project plan, so log output and the results matrix read in
        the same sequence a reader would expect from the README.

        Returns:
            One PlatformConfig per platform, in build/run order.
        """
        return [
            self.cognodb,
            self.aura,
            self.self_hosted_neo4j,
            self.memgraph,
            self.arangodb,
        ]


@lru_cache
def get_platforms_settings() -> PlatformsSettings:
    """Return the cached PlatformsSettings instance for this process.

    Cached the same way PyLedger's `get_settings()` is -- parsed once
    per process, not re-read from the environment on every access.
    Tests that mutate environment variables must clear this cache
    explicitly (e.g. via `get_platforms_settings.cache_clear()`).

    Returns:
        The process-wide PlatformsSettings instance.
    """
    return PlatformsSettings()
