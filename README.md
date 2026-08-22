# GraphParity

GraphParity is a benchmark harness for graph databases built for a backend take-home submission. It runs a shared workload suite through a common adapter contract, measures per-query latency with one percentile method, and turns the samples into a reproducible results matrix. This repository contains one completed benchmark run against CognoDB Cloud and the supporting harness needed to repeat that run or add more platforms later.

## Scope of this submission

This submission is intentionally scoped to one platform only: CognoDB. A working run adapter exists only for CognoDB, and the saved benchmark results in this repository come from that single platform run. The other four platforms named by the brief, AuraDB Free, self-hosted Neo4j, Memgraph, and ArangoDB, do not have platform-specific adapter implementations in this repo.

That said, the shared harness is platform-agnostic. The adapter boundary, workload runner, aggregator, and config loading are all written against common contracts and are covered by unit tests with `FakeGraphAdapter` or other in-memory fixtures, so adding another platform is mechanical: implement one `GraphAdapter`-conforming class for that platform and wire it into the existing entrypoint. The shared layers do not need platform-specific redesign.

The reason for the reduced scope is time. This submission was finished against a 48-hour deadline, and the honest choice was to complete one real platform end to end rather than claim broader coverage than the repo actually has.

## Architecture

- `GraphAdapter` is a structural `Protocol`, not a base class. Every platform adapter must provide `connect()`, `disconnect()`, `run_query()`, and `load_batch()`, and the rest of the code depends only on that shape.
- `BenchmarkError` is the one exception type that crosses component boundaries, and `ErrorCode` is the shared vocabulary attached to it. Each adapter is responsible for translating its own client-library exceptions before they escape into the harness.
- `workloads/common.py` owns the warm-up then timed pattern used by every read workload. Warm-up iterations are executed first and discarded; timed iterations are the ones reported.
- The implemented workload shapes are 1-hop traversal, 2-hop traversal, 3-hop traversal, point lookup, indexed lookup, aggregation, and mixed read/write at configurable concurrency.
- `aggregate.py` computes p50 and p95 using linear interpolation between nearest ranks, the same convention used by NumPy's default percentile behavior. The exact formula is documented in code and reproduced here so the matrix can be reconstructed from this README alone.
- `FakeGraphAdapter` provides zero-I/O unit tests for the runner, workloads, loader, and aggregate code. Real integration tests would need a live database and the actual driver boundaries, which are not present for this submission.

## Platform Specs

| Platform          | Status                      | Tier                        | CPU                         | RAM                         | Disk                        | Max connections             | Max result rows             | Region                      | Protocol                     |
| ----------------- | --------------------------- | --------------------------- | --------------------------- | --------------------------- | --------------------------- | --------------------------- | --------------------------- | --------------------------- | ---------------------------- |
| CognoDB           | run                         | free c0                     | burst 0.5 vCPU              | 512 MB                      | 1 GB                        | 200                         | 50,000                      | us-east4                    | Bolt+Cypher over `bolt+s://` |
| AuraDB Free       | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section  |
| self-hosted Neo4j | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section  |
| Memgraph          | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section  |
| ArangoDB          | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section | not run - see Scope section  |

## Dataset

The benchmark run in `results/cognodb_results.json` used a synthetic placeholder graph generated in-process by `scripts/run_all.py`. The generator starts from `_EDGE_COUNT = 5_000` and builds a simple chain-plus-branch structure that stays connected enough for the traversal workloads to complete. The saved run loaded 5,001 nodes and 5,714 relationships.

This is not the target SNAP Pokec-scale dataset described in the original plan. The result numbers below should therefore be read as a small placeholder run, not as full-scale benchmark results.

The repository does already contain the real loader path for a public edge-list corpus. `loader/dataset.py` can parse raw `source target` edge lists, trim them to the requested relationship band, and convert them into node and relationship records. A real dataset run would download a public edge-list file first, then feed it through that loader.

## Results Matrix

The table below is built directly from `results/cognodb_results.json`. It is based on the synthetic placeholder graph described above, not on the target SNAP Pokec-scale dataset.

| Workload             | p50 (ms)           | p95 (ms)           | min (ms)           | max (ms)           | mean (ms)          | sample count |
| -------------------- | ------------------ | ------------------ | ------------------ | ------------------ | ------------------ | ------------ |
| 1_hop_traversal      | 142.8332999930717  | 156.82140497374348 | 136.83999999193475 | 179.7493000049144  | 144.6232210000744  | 100          |
| 2_hop_traversal      | 144.30530002573505 | 184.1051200201036  | 137.17260002158582 | 237.42550000315532 | 150.30033699818887 | 100          |
| 3_hop_traversal      | 143.0265000090003  | 164.70204502693377 | 136.00930001121014 | 208.74889998231083 | 145.0652290013386  | 100          |
| point_lookup         | 144.22930000000633 | 173.83749499567784 | 137.1816999744624  | 466.61419997690246 | 150.71241699857637 | 100          |
| indexed_lookup       | 147.4253500055056  | 169.2001000308664  | 139.87439998891205 | 483.5598000208847  | 153.9207260031253  | 100          |
| aggregation          | 148.42174999648705 | 175.8083550055744  | 144.82849999330938 | 600.9231999632902  | 158.15370499913115 | 100          |
| mixed_10_concurrency | 145.4412000020966  | 205.6978200096637  | 135.66670002182946 | 3179.2365000001155 | 204.25571847485423 | 249          |
| mixed_40_concurrency | 265.1205000001937  | 2284.029880008893  | 135.91840001754463 | 8220.185699989088  | 521.1087417653217  | 419          |

## Written Analysis

The read-only workloads are tightly clustered. On this run, 1-hop, 2-hop, 3-hop traversal, point lookup, indexed lookup, and aggregation all land in roughly the same latency band, which suggests fixed client, network, and managed-service overhead dominate more than hop count alone on this small graph.

Within the read workloads, 2-hop traversal is the slowest by both p95 and mean. 3-hop traversal is not strictly slower than 2-hop here, so this run does not show a clean monotonic "more hops always means slower" curve.

Aggregation is slightly slower than the lookup workloads, which is expected for a query that groups and sorts across the whole node set. The differences are visible, but still modest at this dataset size.

The mixed workload is where contention shows up. At concurrency 10, the median is still close to the read workloads, but the mean rises because of tail latency. At concurrency 40, the median jumps to 265 ms and the p95 climbs above 2.2 s, which is consistent with queueing and contention under heavier parallel load.

What this data does not show is just as important: it does not compare CognoDB with any other platform, it does not demonstrate behavior at the target dataset scale, and it does not include throughput as a persisted metric. The mixed workload in the JSON file stores latency samples only, so throughput cannot be claimed from the saved artifact alone.

## Methodology & Fairness Notes

The harness was designed around a fairness principle even though only one platform was run. Every platform adapter is expected to satisfy the same `GraphAdapter` contract, every read workload uses the same warm-up policy, and every result summary uses the same percentile interpolation rule. That means results become directly comparable the moment another platform adapter is added.

Fairness also shaped the self-hosted Docker setup. `docker/compose.yml` caps Neo4j, Memgraph, and ArangoDB to 0.5 vCPU and 512 MB RAM so the local comparators are sized to CognoDB's confirmed free-tier envelope rather than being unconstrained. Those containers were not benchmarked in this submission, but the resource-capping decision is already baked into the repo.

## Testing & Code Quality

The repository uses `pytest` with strict marker enforcement from `tests/conftest.py`. The marker scheme is two-axis: a speed marker of `unit` or `integration`, plus a layer marker derived from file location. The layer markers cover `errors`, `config`, `adapters`, `workloads`, `aggregate`, and `loader`.

The current test suite is unit-heavy and intentionally so. `FakeGraphAdapter` covers the runner, workloads, and loader paths, while `errors`, `config`, and `aggregate` use in-memory fixtures and pure inputs. That gives strong coverage for the pure logic, the error vocabulary, the config validators, the percentile math, and the orchestration code without needing live I/O.

The adapter tests follow a narrower philosophy. The code explicitly covers the pure translation boundary in the CognoDB adapter and the no-network guard clauses, while the real connection and query path is left for live integration testing against an actual database. No integration-marked tests are present in this submission, and there is no separate end-to-end smoke-test file in the repo.

`ruff` and `ty` are configured in `pyproject.toml` for linting and type checking.

## Caveats and Honest Limitations

- Only CognoDB has a working run adapter and a completed benchmark run.
- The benchmark dataset is a synthetic placeholder graph, not the target SNAP Pokec-scale dataset from the original plan.
- The saved results are for one platform only, so no comparative claim about CognoDB versus another engine is possible from this submission.
- No integration-marked tests were written for this repo snapshot.
- No dedicated full-pipeline smoke test is present.
- The mixed-workload results do not persist throughput as a reported metric, only latency samples.
- A Windows-specific connectivity issue was encountered during development: the neo4j async driver failed TLS handshake against CognoDB under Python's default Windows Proactor event loop with `ConnectionResetError` and `BoltSecurityError` during `verify_connectivity()`. The fix was to switch to `asyncio.WindowsSelectorEventLoopPolicy()`.
- The self-hosted comparators in `docker/compose.yml` are configured for fairness, but they were not benchmarked in this submission.
- The repo still contains placeholder defaults for unrun platforms, so `not run - see Scope section` is the only honest status for them here.

## How to Reproduce

```powershell
git clone <repo-url>
cd graphparity
Copy-Item .env.example .env
```

Fill in real CognoDB credentials in `.env`, then run:

```powershell
uv sync
uv run pytest -m unit
uv run python scripts/run_all.py
```

If you are reproducing on Windows and hit the known TLS or event-loop issue during `verify_connectivity()`, set `asyncio.WindowsSelectorEventLoopPolicy()` in the benchmark entrypoint before connecting.

## Project Structure

- `src/graphparity/errors/`: `ErrorCode` and `BenchmarkError`, the shared error vocabulary.
- `src/graphparity/config/`: `PlatformConfig` validation and environment-backed platform settings.
- `src/graphparity/adapters/`: the `GraphAdapter` protocol and the CognoDB adapter implementation.
- `src/graphparity/loader/`: edge-list parsing, relationship trimming, dataset building, and idempotent batch loading.
- `src/graphparity/workloads/`: the common warm-up runner plus traversal, lookup, aggregation, and mixed workloads.
- `src/graphparity/aggregate.py`: percentile computation and results-matrix assembly.
- `src/graphparity/runner.py`: platform orchestration, workload sequencing, and result collection.
- `src/graphparity/__init__.py`: package root.
