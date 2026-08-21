# GraphParity

A fairness-first benchmark harness comparing CognoDB against 4 other
graph database platforms on identical hardware, data, and queries.

## Objective

<!-- 2-3 sentences: what this repo does and what it deliberately doesn't. -->

## Platforms Compared

<!-- CognoDB, AuraDB Free, self-hosted Neo4j, self-hosted Memgraph,
     self-hosted ArangoDB -- table of specs (vCPU/RAM/storage/tier). -->

## Methodology

<!-- Same resources, same dataset, same queries, same client machine.
     Include the CognoDB second-workspace note here explicitly. -->

## Dataset

<!-- Source, node count, relationship count, load method per platform. -->

## Setup & Reproduction

<!-- One-command run instructions: uv sync, docker compose up,
     .env from .env.example, uv run graphparity. -->

## Results

<!-- Full results matrix: every metric x every platform, p50/p95. -->

## Analysis

<!-- What the numbers show and why the platforms differ. -->

## Caveats

<!-- Throttling, AQL-vs-Cypher differences, timeouts, failed runs,
     anything observed but not controlled for. -->

## Architecture

<!-- GraphAdapter Protocol, BenchmarkError catalog, why this shape --
     see CONTEXT-style rationale if useful. -->
