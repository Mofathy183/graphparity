"""
Environment loading for GraphParity's five platform configurations.

PlatformConfig (platform_config.py) describes the *shape* one platform
must satisfy; this module is the one place that actually reads the
environment and assembles all five named instances from it

Only this module touches `pydantic_settings.BaseSettings`. Everything
downstream (the workload runner, adapters, aggregate.py) receives an
already-constructed `PlatformConfig` and never reads an environment
variable directly.

pydantic-settings nested-model quirk (read this before editing further)
-------------------------------------------------------------------------
When *any* `GRAPHPARITY_<PLATFORM>__*` env var is set for a nested
field, pydantic-settings builds that nested model **entirely from env
vars** -- it does not merge env values on top of the field's
`default_factory`. A default_factory only applies when *zero* env vars
touch that platform's block at all.

Concretely: if only `GRAPHPARITY_COGNODB__URI`,
`GRAPHPARITY_COGNODB__USERNAME`, and `GRAPHPARITY_COGNODB__PASSWORD`
are set, `name` and `protocol` are NOT silently filled in from the
default factory -- they are simply missing, and construction fails
with a `Field required` error.

The practical fix is: `.env`/`.env.example` set every field explicitly
for every platform block that has *any* variable set, including
`NAME`/`PROTOCOL`, even though those two rarely change. Leaving them
out for a platform that has other env vars set breaks construction; it
does not fall back to a default.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from .platform_config import PlatformConfig


def _cognodb_default() -> PlatformConfig:
    return PlatformConfig(
        name="cognodb",
        protocol="bolt",
        uri="bolt+s://replace-me.databases.cognodb.com:7687",
        username="cognodb",
        password="replace-me",
    )


def _aura_default() -> PlatformConfig:
    return PlatformConfig(
        name="aura",
        protocol="bolt",
        uri="bolt+s://replace-me.databases.neo4j.io:7687",
        username="neo4j",
        password="replace-me",
    )


def _self_hosted_neo4j_default() -> PlatformConfig:
    return PlatformConfig(
        name="self_hosted_neo4j",
        protocol="bolt",
        uri="bolt://localhost:7687",
        username="neo4j",
        password="devpassword",
    )


def _memgraph_default() -> PlatformConfig:
    return PlatformConfig(
        name="memgraph",
        protocol="bolt",
        uri="bolt://localhost:7688",
        username="memgraph",
        password="devpassword",
    )


def _arangodb_default() -> PlatformConfig:
    return PlatformConfig(
        name="arangodb",
        protocol="http",
        uri="http://localhost:8529",
        username="root",
        password="devpassword",
        database="graphparity",
    )


class PlatformsSettings(BaseSettings):
    """Root settings object assembling every platform's PlatformConfig.

    Each field is one platform, populated from its own
    double-underscore-delimited env-var block (e.g.
    `GRAPHPARITY_COGNODB__URI`, `GRAPHPARITY_COGNODB__USERNAME`,
    `GRAPHPARITY_COGNODB__PASSWORD`, `GRAPHPARITY_COGNODB__NAME`,
    `GRAPHPARITY_COGNODB__PROTOCOL`).

    Only a platform with **zero** `GRAPHPARITY_<PLATFORM>__*` variables
    set falls back to its full default (see module docstring for the
    all-or-nothing rule this depends on). Because of that rule,
    `.env`/`.env.example` set every field explicitly for every
    platform block that has any variable set at all, including
    `NAME`/`PROTOCOL` even though those two rarely change.

    `PlatformConfig`'s own validators still run on construction of
    each nested field, so a bad scheme or missing credential on any
    single platform fails loudly here, at startup, rather than deep
    inside an adapter mid-benchmark.
    """

    model_config = SettingsConfigDict(
        env_prefix="GRAPHPARITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    cognodb: PlatformConfig = Field(default_factory=_cognodb_default)
    aura: PlatformConfig = Field(default_factory=_aura_default)
    self_hosted_neo4j: PlatformConfig = Field(
        default_factory=_self_hosted_neo4j_default
    )
    memgraph: PlatformConfig = Field(default_factory=_memgraph_default)
    arangodb: PlatformConfig = Field(default_factory=_arangodb_default)

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
    explicitly via `get_platforms_settings.cache_clear()`.

    Returns:
        The process-wide PlatformsSettings instance.
    """
    return PlatformsSettings()
