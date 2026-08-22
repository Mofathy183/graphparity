"""
PlatformConfig: the single validated shape describing one graph
database platform GraphParity will benchmark.

There is exactly one config *model* here, not five. CognoDB, AuraDB
Free, self-hosted Neo4j, and self-hosted Memgraph all speak
Bolt+Cypher through the `neo4j` driver; self-hosted ArangoDB speaks
HTTP+AQL through `python-arango`. PlatformConfig is generic across
both families -- `protocol` states which family a given instance
belongs to, and a cross-field validator enforces that `uri`'s scheme
actually matches it. Five *instances* of this one model (one per
platform, each built from its own env-var block) are what
`config/settings.py` assembles.

config describes shape and
fails fast on a bad value, it never connects to anything and never
performs I/O. Whether the URI is actually reachable is GraphAdapter's
concern (BenchmarkError.CONNECTION_FAILED at connect() time), not
this model's.
"""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from graphparity.errors import BenchmarkError, ErrorCode

# Accepted URI schemes per protocol family. Bolt covers every
# Bolt+Cypher platform (CognoDB, AuraDB, self-hosted Neo4j, Memgraph);
# http covers ArangoDB's HTTP+AQL client. Kept as module-level
# constants (not inlined in the validator) so a future platform that
# reuses an existing protocol doesn't require touching validation
# logic, only adding a scheme here if genuinely new.
_BOLT_SCHEMES = ("bolt://", "bolt+s://")
_HTTP_SCHEMES = ("http://", "https://")

Protocol = Literal["bolt", "http"]


class PlatformConfig(BaseModel):
    """Validated connection configuration for a single graph platform.

    One instance represents one platform (e.g. "cognodb", "aura",
    "self_hosted_neo4j", "memgraph", "arangodb"). All five instances
    share this one model; they differ only in their field values,
    sourced from that platform's own env-var block.

    Attributes:
        name: Short, stable platform identifier. Must match the
            `name` a GraphAdapter implementation reports on itself, so
            log lines and the results matrix key off the same string.
        protocol: Which driver family this platform's `uri` must use.
            "bolt" for every Bolt+Cypher platform (CognoDB, AuraDB,
            self-hosted Neo4j, Memgraph); "http" for ArangoDB.
        uri: The connection string. Scheme is validated against
            `protocol` -- see `validate_uri_matches_protocol`.
        username: Auth username. Required and non-blank for every
            platform currently in scope, including self-hosted
            containers configured with auth enabled.
        password: Auth credential. Same non-blank requirement as
            `username`. Never logged or included in any BenchmarkError
            context -- callers must redact it before adding platform
            details to error context.
        database: Target database/graph name. Required only for
            `protocol="http"` (ArangoDB always operates against a
            named database); optional and typically unset for `bolt`
            platforms, which default to Neo4j's single default
            database.
    """

    name: Annotated[
        str,
        Field(min_length=1, description="Stable platform identifier used in logs."),
    ]

    protocol: Annotated[
        Protocol,
        Field(description="Driver family this platform's URI must conform to."),
    ]

    uri: Annotated[
        str,
        Field(
            min_length=1,
            description="Connection URI, scheme-validated against protocol.",
        ),
    ]

    username: Annotated[
        str,
        Field(min_length=1, description="Auth username for this platform."),
    ]

    password: Annotated[
        str,
        Field(min_length=1, description="Auth credential for this platform."),
    ]

    database: Annotated[
        str | None,
        Field(
            default=None,
            description="Target database name. Required for protocol='http'.",
        ),
    ] = None

    @model_validator(mode="after")
    def validate_uri_matches_protocol(self) -> Self:
        """Ensure `uri`'s scheme is valid for the declared `protocol`.

        A bolt-protocol platform configured with an http(s) URI (or
        vice versa) is a config-authoring mistake, not a connectivity
        problem -- it should fail at startup, not surface later as a
        confusing driver-level error deep inside an adapter.

        Returns:
            The validated instance.

        Raises:
            BenchmarkError: CONFIG_INVALID if `uri`'s scheme does not
                match `protocol`.
        """
        schemes = _BOLT_SCHEMES if self.protocol == "bolt" else _HTTP_SCHEMES

        if not self.uri.startswith(schemes):
            raise BenchmarkError(
                code=ErrorCode.CONFIG_INVALID,
                context={
                    "platform": self.name,
                    "field": "uri",
                    "protocol": self.protocol,
                    "value": self.uri,
                },
            )
        return self

    @model_validator(mode="after")
    def validate_database_required_for_http(self) -> Self:
        """Enforce that an http-protocol (ArangoDB-shaped) platform names a database.

        ArangoDB has no single implicit default database the way a
        Bolt platform does -- every AQL query runs against a specific,
        named database. A missing `database` here would surface later
        as a confusing 404/database-not-found error from the client
        library instead of a clear config-time failure.

        Returns:
            The validated instance.

        Raises:
            BenchmarkError: CONFIG_INVALID if `protocol` is "http" and
                `database` is None or blank.
        """
        if self.protocol == "http" and not self.database:
            raise BenchmarkError(
                code=ErrorCode.CONFIG_INVALID,
                context={
                    "platform": self.name,
                    "field": "database",
                    "reason": "required_for_http_protocol",
                },
            )
        return self
