# Introduction

This repository contains the reference artifacts for the article "A Reference Architecture for a Next Generation Global Reporting Platform".

It accompanies the article and provides the concrete schema, configuration, stored procedures, workloads, and inspection utilities used to exercise the architecture described there. The intent is to make specific architectural claims observable, not to provide a turnkey deployment or tutorial.

All examples and outputs assume a CockroachDB cluster configured to match the architecture described in the article. Cluster creation and sizing are intentionally out of scope.

Readers can use this repository selectively: to inspect mechanics, validate behavior, experiment with individual components, or use as a starting point in their own experimentations.

# Database

All examples in this repository use a single database with a deliberately small and explicit schema. The goal is not to model a complete production domain, but to make data placement, locality, and lifecycle behavior easy to reason about and inspect.

The schema consists of three core tables:

`geos`

Models conceptual geography and its association with transactional placement. In a real system, this mapping would typically be implicit, derived from network topology and gateway locality. Here it is modeled explicitly so that placement intent can be driven as data and verified deterministically.

`stations`

Represents independent data-producing entities. Each station belongs to a geo and serves as a stable identifier that emits datapoints over time. This introduces realistic cardinality and fan-out without tying ingest behavior directly to infrastructure.

Both geos and stations are small, mostly static, and read frequently. They are therefore marked GLOBAL, so they do not participate in regional placement tradeoffs.

`datapoints`

The primary fact table and the focus of the architecture. Each row represents a single datapoint produced by a station at a specific point in time. The table is defined as REGIONAL BY ROW, using an explicit region column as the locality key. This allows individual rows to be domiciled, replicated, and later moved according to lifecycle policy without changing schema or access patterns.

The primary key (station, at) models a natural time-series pattern per station and is hashed to introduce controlled range fan-out. In addition to scalar attributes, the table includes a JSONB column for semi-structured data and a vector column for later semantic access patterns.

Together, these tables form a minimal but sufficient foundation for demonstrating transactional ingest, regional placement, online lifecycle transitions, and reporting access on a single operational dataset.

# Sample Workloads

This repository includes a small set of dbworkload workload classes used to exercise specific architectural behaviors described in the article. These workloads are not benchmarks and are not intended to model production traffic patterns. Their purpose is to make placement, execution locality, snapshot semantics, and workload isolation observable.

Each workload is executed against a specific cluster entry point. Workload intent is declared at connection time by choosing the appropriate endpoint, rather than inferred from query shape or runtime heuristics.

## Transactional Ingest

`DatapointTransactions.py`

This workload emulates application-side ingest into the system.

Each executing thread repeatedly selects a station, generates a synthetic datapoint, and inserts or upserts it into the datapoints table. An optional region argument allows ingest to be targeted to a specific transactional region. When no region is provided, ingest is distributed across all transactional regions.

This workload exists to demonstrate:
- deterministic row placement using regional-by-row locality,
- concurrent transactional ingest across multiple regions,
- ingestion of mixed data types (scalar, JSONB, vector),
- and the separation between ingest traffic and reporting execution.

The region argument is an emulation mechanism used to make placement behavior explicit and inspectable. In a real system, placement would typically be driven implicitly

## Reporting Queries

`DatapointReporting.py`

This workload executes a fixed set of representative reporting queries against the live dataset.

All queries are read-only and are executed using AS OF SYSTEM TIME follower_read_timestamp(), ensuring stable, repeatable snapshots while transactional ingest and lifecycle operations continue concurrently.

The queries include:
- aggregations by region,
- time-based rollups,
- joins across `datapoints`, `stations`, and `geos`.

This workload is used to demonstrate:
- reporting without reporting replicas,
- execution isolation via a dedicated reporting entry point,
- and consistent historical reads without coordination with transactional leaseholders.

## Historical Extracts

`DatapointHistoricExtract.py`

This workload models large historical reads and bulk data extraction.

It issues full and filtered snapshot queries using `AS OF SYSTEM TIME follower_read_timestamp()` and consumes results in bounded batches using Polars. This reflects how real extract jobs typically operate: streaming results with predictable memory usage rather than loading entire result sets at once.

The workload demonstrates:
- large, consistent historical reads without pipelines,
- extracts operating directly on operational tables,
- and flexible execution placement depending on resource needs.


## Vector Search

`DatapointVectorSearch.py`

This workload exercises semantic access patterns using vector similarity search.

It generates a synthetic datapoint, computes an embedding, and executes nearest-neighbor searches both:
- directly against the base datapoints table, and
- against the reporting materialized view.

Both query paths use snapshot semantics. The distinction is not freshness, but shape and ownership: live operational data versus a curated, reporting-owned projection.

This workload exists to demonstrate:
- vector search as a first-class query pattern,
- separation between live and curated semantic access,
- and semantic querying without introducing a separate system.


# Architecture Overview

This reference architecture is a single CockroachDB cluster deliberately shaped to support multiple reporting-related workloads without splitting data across systems.

The cluster is intentionally __non-uniform__. Nodes are grouped into regions with explicit roles, different resource profiles, and different access paths. The goal is to keep data in one place, while ensuring that transactional ingest, data lifecycle operations, and reporting queries do not interfere with each other.

At a high level, the cluster supports three distinct concerns:
- __Transactional ingest__, optimized for concurrent writes and short-lived updates
- __Historical retention__, optimized for long-term storage with different cost and survivability characteristics
- __Reporting execution__, optimized for read-heavy queries and large working sets

All of these operate on the same database and schema. What differs is __where data lives__, __how it is replicated__, and __where queries execute__.

## Regions and Super Regions

This architecture makes explicit use of __regions__ and __super regions__ as policy boundaries.

Transactional regions are grouped into a __transactional super region__, which defines placement, replication, and survivability guarantees for hot data. Archive regions are grouped into a separate archive super region, with different lifecycle and cost assumptions. These super regions directly control where replicas may live and what failures the system is designed to survive.

Super regions are the mechanism that allows data to move through its lifecycle inside the database. When data transitions from transactional to archival storage, its regional locality changes. That single change is sufficient to trigger CockroachDB to re-replicate and re-domicile the affected ranges according to the archive super region’s policy—without copying data, changing schemas, or introducing pipelines.

The __reporting region__ is intentionally __not part of any super region__. It does not define survivability for primary data and does not own replicas for transactional or archival ranges. Its role is execution, not storage.

## Transactional Regions

Transactional regions handle application ingest.

They are sized and configured to support concurrent inserts and updates rather than large scans or aggregations. Data written by the application is placed using regional-by-row locality so that rows land in the intended transactional region and are replicated according to the transactional super region’s policy.

Transactional traffic enters the system through __transactional entry points__, ensuring that ingest does not compete with reporting, extraction, or lifecycle workloads at the execution layer.

## Archive Regions

Archive regions exist to retain historical data with different performance and cost characteristics.

Archived data is assumed to be stable: no longer updated frequently, but still queryable. Rows are moved into archive regions explicitly as part of their lifecycle by changing their regional locality. This reassigns placement and replication policy without changing how the data is accessed.

Archive regions are accessed through their own entry points so that long-running historical reads and bulk scans do not interfere with transactional ingest.

## Reporting Region

The reporting region is built differently from the rest of the cluster.

It consists of a small number of larger nodes sized primarily for CPU and memory. Its role is not to store primary copies of transactional or archival data, but to __execute reporting queries efficiently__.

Reporting queries enter the system through a dedicated reporting entry point and are executed using MVCC snapshot semantics (`AS OF SYSTEM TIME`). Data is read from follower replicas in transactional and archive regions, while execution, memory pressure, and query coordination are isolated to the reporting nodes.

This separation decouples __query execution__ from __data placement__, allowing reporting capacity to scale independently of ingest and storage.

## Explicit Access Paths

A defining characteristic of this architecture is that __workload intent is explicit at connection time__.

Transactional ingest, reporting queries, historical extracts, semantic access patterns, and changefeeds each use different entry points. The system does not attempt to infer intent from query shape or rely on throttling and heuristics to protect critical workloads.

This makes workload isolation, capacity planning, and failure analysis explicit and observable.

## What Follows

The sections below make this architecture concrete.

They show how regions and super regions are defined, how data is placed and moved, how reporting and archival workloads execute, and how these behaviors can be inspected directly using SQL and system introspection tools.



```sql
SHOW REGIONS FROM DATABASE nextgenreporting;             
```

```bash
      database     | region | primary | secondary | zones
-------------------+--------+---------+-----------+--------
  nextgenreporting | tx1    |    t    |     f     | {}
  nextgenreporting | ar1    |    f    |     f     | {}
  nextgenreporting | ar2    |    f    |     f     | {}
  nextgenreporting | ar3    |    f    |     f     | {}
  nextgenreporting | report |    f    |     f     | {}
  nextgenreporting | tx2    |    f    |     f     | {}
  nextgenreporting | tx3    |    f    |     f     | {}
(7 rows)
```




```sql
SELECT
  crdb_region,                                             
  count(*) AS row_count                                        
FROM datapoints                                                
GROUP BY crdb_region
ORDER BY crdb_region; 
```

```bash
  crdb_region | row_count
--------------+------------
  ar1         |      8426
  ar2         |     11264
  ar3         |     12617
  tx1         |      1495
  tx2         |      3013
  tx3         |      3204
(6 rows)
```


## Inspecting Range Placement

This repository includes a small inspection utility, `show_ranges.py`, used to make data placement and lifecycle behavior observable at the range level.

The script inspects range ownership via row-level inspection, then aggregates the results per range. It walks a table row by row and uses `SHOW RANGE … FOR ROW` to determine:
- which ranges own the rows,
- where leaseholders are located,
- and how replicas are distributed across regions.

Results are aggregated per range and printed in a human-readable table showing row counts, leaseholder locality, and replica placement.

This tool is used throughout the walkthrough to validate claims such as:
- transactional data being leased in transactional regions,
- archived data being re-domiciled into archive regions,
- and both populations coexisting in the same table under different placement policies.

### Usage

The script requires:
- a SQL connection string, and
- a table name.

Example:

```bash
python show_ranges.py \
  --url "<CockroachDB connection string>" \
  --table <table>
```

The script discovers the table’s primary key automatically and streams rows in batches to avoid loading the entire table into memory at once.

```bash
python3 show-ranges.py --url "postgresql://<user>:******@<server_ip>:26257/nextgenreporting?sslmode=verify-full" --table datapoints
```

produces something similar to

```bash
┌───┬──────────┬───────┬─────────────┬──────────────────────────────────────────────────┐
│   │ range_id │ rows  │ leaseholder │ replicas                                         │
╞───╪──────────╪───────╪─────────────╪──────────────────────────────────────────────────╡
│ 1 │ 528      │ 6426  │ ar1 (13)    │ ar1 (12), ar1 (13), ar2 (17), ar2 (18), ar3 (21) │
│ 2 │ 530      │ 9264  │ ar2 (16)    │ ar1 (10), ar1 (12), ar2 (16), ar2 (18), ar3 (19) │
│ 3 │ 532      │ 11615 │ ar3 (21)    │ ar1 (12), ar1 (13), ar2 (16), ar3 (19), ar3 (21) │
│ 4 │ 536      │ 1509  │ tx1 (1)     │ tx1 (1), tx1 (3), tx2 (5), tx2 (9), tx3 (7)      │
│ 5 │ 538      │ 2201  │ tx2 (9)     │ tx1 (1), tx1 (3), tx2 (5), tx2 (9), tx3 (8)      │
│ 6 │ 670      │ 3226  │ tx3 (2)     │ tx1 (1), tx1 (6), tx2 (9), tx3 (2), tx3 (8)      │
├───┼──────────┼───────┼─────────────┼──────────────────────────────────────────────────┤
│   │ TOTAL    │ 34241 │             │                                                  │
└───┴──────────┴───────┴─────────────┴──────────────────────────────────────────────────┘
```

or

```bash
python3 show-ranges.py --url "postgresql://<user>:******@<server_ip>:26257/nextgenreporting?sslmode=verify-full" --table datapoints_mv
```

```bash
┌───┬──────────┬───────┬─────────────┬───────────────────────────────────────┐
│   │ range_id │ rows  │ leaseholder │ replicas                              │
╞───╪──────────╪───────╪─────────────╪───────────────────────────────────────╡
│ 1 │ 1479     │ 18041 │ report (14) │ report (11), report (14), report (15) │
├───┼──────────┼───────┼─────────────┼───────────────────────────────────────┤
│   │ TOTAL    │ 18041 │             │                                       │
└───┴──────────┴───────┴─────────────┴───────────────────────────────────────┘
```

### Scope and limitations

`show_ranges.py` is intentionally __not a production tool__.

It does not scale to large or long-lived datasets, as it iterates through all rows in the table and issues per-row range inspection queries. On large tables, this would consume excessive time and cluster resources.

The script exists purely as a __demonstration and validation utility__ to accompany the article:
- to make placement and lifecycle behavior concrete,
- to verify that configuration changes have the intended effect,
- and to provide observable evidence for the architecture being described.

It is not intended for monitoring, automation, or continuous use.

While we're on the subject of inspecting range placement, let's quickly talk about inspecting disk storage associated with each workload intent, i.e. __transact__, __archive__ and __report__. File `procs_funcs.sql` defines function `workload_intent_space()` that looks at the disk space used by the individual nodes associated with each workload intent and then aggregates the findings into a table. The function can be invoked as

```sql
SELECT * FROM workload_intent_space();
```

and produces the output similar to

```bash
  workload_intent | gbytes
------------------+---------
  transact        |  12.35
  archive         |  12.67
  report          |   5.00
(3 rows)
```

An obvious observation here is that the disk space associated with __report__ is relatively low to __transact__ and __archive__ since the rows in the `datapoints` table are stored exclusively in either __transact__ or __archive__. Please be aware that the results above are only indicative of which workload intents consume more or less space relative to each other. Outside the actual space required to store data ranges associated with the `datapoints` table, these number include indexes, logs, system ranges, etc.



## Archiving

Our `datapoints` table is `REGIONAL BY ROW` where the `crdb_region` column, although `NOT VISIBLE`, determines the regions where the row is physically stored. Our transaction workload sets this column to `tx1`, `tx2` or `tx3` regions at `INSERT` time.

Moving a row's physical data to another region is accomplished by simply updating the `crdb_region` column to the destination region. The cluster will relocate the physical data to a range in the specified region while the row logically remains intact. This is the underlying mechanism of the `archive_datapoints()` stored procedure. The code is in `procs_funcs.sql` file.

Here is how this stored proc works:
1. It selects rows from the transactional regions (`tx1`, `tx2` or `tx3`) based on the `at` column value, looking for this timestamp to be older than 1 month. It does it in batches of 1000 rows.
2. For every row selected, an `UPDATE` query is run that changes the `crdb_region` column to one of the archive regions (`ar1`, `ar2` or `ar3`). The target archive region is picked randomly to maintain an even distribution of the archived rows amongs the archive regions.

That's it!

```sql
CALL archive_datapoints();
```

The only caveat is that since `CALL`ing a stored procedure is wrapped inside a transaction, archving a large number of rows may cause a serialization error. In that case the stored procedure call needs to be re-tried until it succedes. The more frequently the archiing process is invoked, the less likely it is to create a contention, naturally. It's worth mentioning that this stored proc is here for the demo purposes and likely won't pass your production muster. It's only here to demonstrate the architectural principals.


# Materialized View


```sql
CREATE MATERIALIZED VIEW public.datapoints_mv (
      at,
      station,
      name,
      param0,
      param1,
      param2,
      param3,
      param4,
      param5,
      param6,
      rowid,
      crdb_internal_idx_expr
  ) AS SELECT
          d.at,
          d.station,
          g.name,
          d.param0,
          d.param1,
          d.param2,
          d.param3,
          d.param4,
          d.param5,
          d.param6
      FROM
          nextgenreporting.public.stations AS s
          JOIN nextgenreporting.public.datapoints AS d ON s.id = d.station
          JOIN nextgenreporting.public.geos AS g ON s.geo = g.id;
```

A materialized view is a table under the hood and shows up alongside regular tables:

```sql
> SHOW TABLES;                                                       
  schema_name |  table_name   |       type        | owner  | estimated_row_count |            locality
--------------+---------------+-------------------+--------+---------------------+---------------------------------
  public      | datapoints    | table             | aseriy |               40019 | REGIONAL BY ROW AS crdb_region
  public      | datapoints_mv | materialized view | aseriy |                   0 | GLOBAL
  public      | geos          | table             | aseriy |                  23 | GLOBAL
  public      | stations      | table             | aseriy |                2300 | GLOBAL
```

Since this materialized view is used for reporting, we explicitly pin it to the `report` region.

```sql
ALTER TABLE datapoints_mv CONFIGURE ZONE USING
    range_min_bytes = 134217728,
    range_max_bytes = 536870912,
    gc.ttlseconds = 600,
    global_reads = true,
    num_replicas = 3,
    num_voters = 3,
    constraints = '{+region=report: 3}',
    voter_constraints = '[+region=report]',
    lease_preferences = '[[+region=report]]';
```

Then we inspect the associated data range placement with

```bash
$ python3 show-ranges.py --url "postgresql://<user>:******@<server_ip>:26257/nextgenreporting?sslmode=verify-full" --table datapoints_mv
```

The output should look something like this:

```
┌───┬──────────┬───────┬─────────────┬───────────────────────────────────────┐
│   │ range_id │ rows  │ leaseholder │ replicas                              │
╞───╪──────────╪───────╪─────────────╪───────────────────────────────────────╡
│ 1 │ 1479     │ 18041 │ report (14) │ report (11), report (14), report (15) │
├───┼──────────┼───────┼─────────────┼───────────────────────────────────────┤
│   │ TOTAL    │ 18041 │             │                                       │
└───┴──────────┴───────┴─────────────┴───────────────────────────────────────┘
```

As we can see, the materialize view is pinned to the `report` region.

# JSONB

Section "Semi-Structured Data Without Breaking the Model", discusses working with JSONB column in the `datapoints` table. Below are the queries mentioned along with their outcomes.

```sql
SELECT jsonb_pretty(param5) AS param5 FROM datapoints_mv LIMIT 5;
```

```json
                param5
--------------------------------------
  {
      "incvuiptc": 862.868
  }
  {
      "ycwf": false
  }
  {
      "eml": 254.922,
      "jof": 152.68,
      "lwwvu": 993.504,
      "mjxguc": 94.98,
      "sgzlauc": 474.846,
      "uxfbenm": "iEOVgEKB",
      "ycajw": "LZAVvdINHbJA"
  }
  {
      "nzxpr": true,
      "smkmlqcixv": false
  }
  {
      "ekzny": {
          "pawkfrrle": {
              "tfc": 704,
              "tvt": 312,
              "zpbgclk": 0,
              "zwmucravy": true
          }
      },
      "ewn": null,
      "hcazpa": null,
      "kdkrd": {
          "kozwcgfdkv": false,
          "ujgppcgx": "CwJCtazaYrL",
          "wozqtcak": {
              "dirdtl": 698,
              "knzdwpbqp": null
          }
      },
      "lqhrlctbyx": false,
      "tvuqcy": 635
  }
(5 rows)
```

```sql
SELECT rowid, param5 FROM datapoints_mv
CROSS JOIN LATERAL jsonb_object_keys(param5) AS key
GROUP BY rowid, param5
HAVING count(*) BETWEEN 3 AND 10
LIMIT 10;
```

```json
         rowid         |                                                                                                                                                                                                                                                param5
-----------------------+-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
  -9215490737506877438 | {"eml": 254.922, "jof": 152.68, "lwwvu": 993.504, "mjxguc": 94.98, "sgzlauc": 474.846, "uxfbenm": "iEOVgEKB", "ycajw": "LZAVvdINHbJA"}
  -9215490737506877436 | {"ekzny": {"pawkfrrle": {"tfc": 704, "tvt": 312, "zpbgclk": 0, "zwmucravy": true}}, "ewn": null, "hcazpa": null, "kdkrd": {"kozwcgfdkv": false, "ujgppcgx": "CwJCtazaYrL", "wozqtcak": {"dirdtl": 698, "knzdwpbqp": null}}, "lqhrlctbyx": false, "tvuqcy": 635}
  -9215490737506877435 | {"crujty": 969.319, "dahssb": {"iotgjm": {"fxuilxaeas": false}, "okpxijj": null, "wzqwjemuyi": true, "xomkmgfgxa": 687.162}, "hpyltnfq": 985.929, "hrzglp": null, "kmhstla": {"rkj": {"pncz": "seIAF", "xxoaniomw": null, "xzuamqifv": null}, "tazfepg": 983, "ybks": {"coi": null, "gdeobevhi": 549.419, "iwtjtzvo": 42.916, "kyo": 271.808, "vvm": {"nobp": false, "olqzgqphj": "unknown", "qdwu": "unknown", "snp": false}}, "yri": 339.172, "ywotn": true}, "liyvfugm": true, "nqoydiqpu": null}
  -9215490737506877433 | {"efoksqfaj": 820, "fqfsstpjsr": 813.509, "hhrtm": true, "hivwwkrken": 648, "jtfbz": true, "nkt": 352}
  -9215490737506877432 | {"avdcbiueo": null, "kgzz": null, "zjinksf": 274}
  -9215490737506877431 | {"cua": false, "oztxyve": null, "rnjhi": 269}
  -9215490737506877427 | {"bditgzj": "NwcjwfZPdVud", "dyuxvso": true, "fxvlb": "mrVkig", "gllqix": null, "kqgmpqqy": true, "kxy": 750.904, "lnicmbl": true, "nagv": 581.597}
  -9215490737506877426 | {"dwsbuomwdm": 635, "sdsasvxedc": true, "xgzf": "ctUqk", "zkbwgehwt": true}
  -9215490737506877425 | {"dgqgn": 887.754, "ifgsihcz": 365.034, "stv": 79, "tnco": 938, "vwh": 52.981, "yfyojkqsr": {"qojeyeotku": true, "vptmw": "aRNfFdqjD"}}
  -9215490737506877423 | {"gzs": true, "rabzecxk": "uqBqsekKqvzT", "ygrvcmz": 235}
(10 rows)

Time: 109ms total (execution 108ms / network 1ms)
```


```sql
SELECT rowid
FROM datapoints_mv
WHERE param5 ? 'ekzny';
```

```sql
         rowid
------------------------
  -9215490737506877436
(1 row)
```

or nested

```sql
SELECT rowid
FROM datapoints_mv
WHERE param5 @> '{"ekzny": {}}';
```

Even with totally unstructured JSON, CockroachDB can index and answer shape questions efficiently.

Deep nesting:

```sql
SELECT rowid
FROM datapoints_mv
WHERE param5 @> '{"ekzny":{"pawkfrrle":{}}}';
```





# CDC

Although a lot can be accomplished without leaving the cluster, there are cases where data still needs to be pipelined out. Even in those cases, the multi-regional configuration can be leveraged to control where that work runs.

First, let’s set up a `CHANGEFEED` for our table. This feature is not enabled by default and must be explicitly turned on:

```sql
SET CLUSTER SETTING kv.rangefeed.enabled = true;
CREATE CHANGEFEED FOR TABLE datapoints INTO 'kafka://<KafkaBrokerIP>:29092' WITH resolved, execution_locality='region=report';
```

Changefeeds run as background jobs inside the cluster. In this setup, CDC events are emitted to Kafka. By default, messages are sent to a topic named after the source table (in this case, `datapoints`); if the topic does not exist, it is created automatically.

Enabling `resolved` causes periodic watermark messages to be emitted. A resolved timestamp indicates that all CDC events up to that point in time have been produced. The most important parameter here is `execution_locality`, which pins the compute responsible for generating and emitting CDC messages to a specific region. In this case, the changefeed is pinned to the `report` region to avoid burdening business-critical transactional regions.


```bash
        job_id
-----------------------
  1139202968564137995
(1 row)

NOTICE: Changefeeds will filter out values for virtual column crdb_internal_at_station_shard_16 in table datapoints
NOTICE: changefeed will emit to topic datapoints
NOTICE: resolved (0s by default) messages will not be emitted more frequently than the default min_checkpoint_frequency (30s), but may be emitted less frequently
Time: 65ms total (execution 64ms / network 1ms)
```

Once the changefeed is created, the `datapoints` topic appears in Kafka.

```bash
$ kafka-topics.sh --bootstrap-server <KafkaBrokerIP>:29092 --list
__consumer_offsets
datapoints
```

You can observe CDC messages being queued in the Kafka topic using:

```bash
kafka-console-consumer.sh --bootstrap-server  <KafkaBrokerIP>:29092 --topic datapoints --from-beginning --group nextgenreporting
```

If you run `dbworkload` using `dbworkload/DatapointTransactions.py`, you will observe output similar to the following:


```bash
{"resolved":"1767732288000000000.0000000000"}
{"resolved":"1767732290000000000.0000000000"}
{"resolved":"1767732320000000000.0000000000"}
{"after": {"at": "2024-09-30T05:33:33.745089", "crdb_region": "tx3", "param0": 126, "param1": 976, "param2": -256.564, "param3": -836.58, "param4": "FXEGR4XUYZ4A6SOLMWTHM18ETF2QV4H", "param5": {"bwhjd": {"enpnkuysd": 442, "gpcv": "unknown", "gxdwkgjvoa": true, "pcfzj": null, "qjlrb": null, "ysdwthphaa": 875}, "hjfa": false, "ihfwzjj": true}, "param6": "[-0.04945485,0.035283387,-0.05331334,-0.06431558,0.0013536239,-0.021089302,0.008496434,-0.0012711094,0.012409213,-0.07063804,-0.0031446926,-0.08539505,-0.089421466,0.020613987,-0.024228146,-0.02744185,-0.124668494,-0.035698388,-0.05088658,-0.010635151,0.01999203,-0.011885636,0.020757886,-0.053302415,0.00057117484,0.0837939,-0.01698184,0.09682554,0.034397192,-0.019165076,0.11399852,0.05073319,0.04467571,0.00599676,0.09242804,0.03461753,-0.057008356,-0.104726344,0.009000856,0.009006238,-0.003953547,0.010425006,0.022779245,0.05720431,0.013569724,0.041798256,-0.07641224,0.019861901,0.07159342,-0.0010442417,-0.06021544,0.030914811,-0.0049393657,0.027270544,0.023459898,0.026526218,-0.09485016,0.0015284559,0.055704724,0.027313767,0.07742048,-0.0041592373,-0.00060104684,0.016174635,-0.0008582325,-0.022232302,0.027786274,0.00078134093,-0.05710625,-0.02263993,-0.028470663,0.0581774,-0.055478282,0.027555674,-0.02617091,-0.002453138,-0.013763356,-0.076753825,0.0742671,-0.05760708,-0.02024811,-0.16637361,0.035648853,0.09105271,0.009995321,0.042359523,-0.038917594,-0.0060258675,-0.035721317,0.07533159,-0.023958383,-0.047498252,0.049170703,0.00863289,0.020730013,0.07997965,0.053457137,0.01614541,-0.052703053,0.090975545,-0.027500574,-0.06308213,0.036410015,0.0204492,0.0020412586,0.02087935,-0.0121434,0.10393978,-0.032611985,0.0071192184,-0.039177656,0.040136274,0.03469972,-0.075694695,-0.012835615,0.053542454,-0.0077326745,0.045050003,-0.050190024,0.008152453,0.018267138,-0.011511588,-0.045290377,0.036656786,-0.094803415,-0.0478401,-0.008717031,1.2643132e-32,0.03495239,-0.03262954,0.038080372,-0.05503811,-0.022312246,-0.013734057,-0.025526607,0.007873531,-0.11024708,0.04511932,-0.049440283,-0.017158967,-0.023087105,-0.033266317,0.003237362,-0.054787546,-0.0077042994,-0.023684788,-0.050102744,0.050050206,0.052040454,0.0337843,-0.008191103,-0.008413322,-0.09474559,0.10428696,-0.016690455,-0.00994924,0.04828933,0.041022457,-0.019454714,-0.042885877,-0.037142184,-0.019146541,0.065420315,-0.018184844,0.017965613,-0.02115881,-0.12353823,-0.08074793,0.019085985,-0.037918404,-0.11492281,-0.07900079,-0.024713125,0.018328905,0.03937014,-0.030502025,0.026220543,0.11670004,-0.10290603,0.030581746,-0.07352648,-0.024321077,0.04549976,-0.046950646,0.065384775,0.041204993,-0.0031836492,-0.003911754,0.02873027,0.09811412,-0.016562283,-0.041700512,0.0054365774,-0.052435376,0.026427638,-0.06553357,-0.08824371,0.030461786,-0.018345151,0.0064328117,0.113312915,0.00011923106,0.007837559,-0.05233573,-0.07229339,-0.010629322,0.0023233965,-0.06255369,-0.04106316,-0.04033373,0.013426551,0.01807705,-0.012405901,0.039690536,-0.022971604,-0.013355165,-0.0017034716,0.021431146,-0.05793702,-0.06671131,0.04469472,-0.1128124,-0.07466636,-1.18974046e-32,0.0039308444,0.029771976,-0.058876522,0.03078267,0.00067882007,0.0051330244,0.0985479,0.12409738,0.08479376,0.020192018,0.072078474,-0.032530595,-0.028642222,-0.062262118,0.038285434,0.0022630205,-0.0052264235,0.0050966777,-0.060096085,-0.023426188,-0.0051636216,0.045650374,0.006001259,0.13639852,-0.0032486778,0.034493472,0.11361087,0.032336056,-0.08119076,0.03931292,0.0013076272,0.009041424,-0.07417815,0.046322558,-0.06369869,-0.085366555,0.065732256,0.075677104,-0.033907022,-0.029465854,-0.007031779,0.05537753,-0.076982774,0.06943809,-0.015832707,0.020249333,0.0068455776,0.099687,0.058506057,0.0006809786,0.017990638,-0.017833265,-0.012848681,0.0027844976,0.0009575627,0.04861774,-0.011867273,-0.011344493,-0.010334337,0.050016094,0.025783505,-0.07523145,-0.062844,0.0072499253,0.11620606,-0.02269544,-0.0921677,0.055881422,0.05656852,-0.063409165,0.030837594,-0.000937081,0.008048968,0.024648225,0.0904575,-0.06547014,-0.02554363,0.01323329,0.063652314,0.047055133,0.016959533,0.069689415,0.0032076484,0.079234146,0.10265414,-0.057664935,0.022292035,0.06242136,-0.04683419,-0.024928082,-0.026192563,0.1044085,-0.0004551781,0.06984736,0.058423173,-5.8449064e-08,-0.056161955,-0.04135348,-0.08780524,-0.060354687,0.030534098,0.052206453,-0.026841301,-0.07548705,0.008134245,-0.069055095,0.11214366,0.060592316,-0.09839324,0.013845879,0.00027639337,-0.06028514,-0.12161261,0.075631686,-0.03679432,-0.03618438,0.05129827,-0.043918643,-0.0006098156,0.012535481,0.0002157127,-0.030432848,0.019568125,0.08265027,-0.008378966,0.031409327,-0.08191383,0.017178928,-0.013158863,-0.06204901,-0.05963415,0.043851867,-0.018800786,0.055585954,-0.036187746,0.014434083,-0.002567869,-0.0042291894,-0.047580402,0.0030682548,-0.0042965403,0.008338617,-0.006555092,0.062471017,0.09801734,-0.057997603,-0.020562872,-0.0020934248,-0.044513904,0.019873956,-0.013019204,-0.01909584,0.005436555,0.0119882235,-0.043446805,0.0019466076,0.09816543,0.010949063,0.0073363287,-0.01437815]", "station": "ecc6ba1f-fbce-4c9f-9069-54dcc80e3ab3"}}
{"resolved":"1767732321000000000.0000000000"}
{"resolved":"1767732323000000000.0000000000"}
{"resolved":"1767732353000000000.0000000000"}
```

Next, archive transactions by running:

```sql
CALL archive_datapoints();
```

while tailing the Kafka topic. Notice that the `crdb_region` is now `ar3` below. This shows that the changefeed emits events for both inserts and updates to the datapoints table.

```bash
{"after": {"at": "2025-11-24T16:51:36.308289", "crdb_region": "ar3", "param0": 707, "param1": -576, "param2": 174.572, "param3": 331.6, "param4": "VP2LQ6PG7MPYU3PS5A", "param5": {"naakte": true, "okuxp": "VHwryoqfMXJd", "unia": "ngw"}, "param6": "[-0.08537057,0.093126215,-0.02882478,0.02820951,0.026901562,0.009424237,0.009382922,-0.048541863,-0.027433647,-0.02817741,0.020998016,-0.096752115,-0.029697388,0.03091466,0.0537911,-0.0172052,-0.06356142,0.0053564464,-0.039093208,-0.07588757,0.0033053495,0.023931561,0.05579399,-0.062271792,0.07222255,0.044362254,0.009974899,0.09507848,0.048783563,-0.06169546,0.017391955,0.0579861,-0.010919972,0.025425948,0.025830297,0.0086943265,-0.045465127,-0.095017165,-0.0048425943,0.017242962,0.05562694,-0.054665145,-0.022783061,0.03830903,-0.024321381,0.01742396,-0.1053865,0.046571482,0.05056797,-0.01146427,-0.0859389,-0.072017856,-0.033495784,0.016209105,-0.00025413648,0.04104426,-0.060398377,-0.023918288,0.040227793,0.027060373,0.07106003,-0.0071643502,-0.068755195,0.017481513,-0.0051833545,-0.042315286,-0.0013830147,-0.035037063,-0.07402905,-0.019929131,0.010300572,0.025221199,0.032857243,0.054500204,0.015857669,-0.0021379958,-0.03755164,-0.0044584963,0.047725104,-0.03179945,-0.010152821,-0.0488274,0.015293413,0.03649445,0.007665908,0.061443757,-0.013604128,0.013390088,0.03469534,-0.010522804,0.004467144,-0.008709656,0.048571777,0.019104293,0.0066460227,0.082431026,-0.014514468,0.016303377,-0.09599133,0.084277615,0.052125484,0.041785028,-0.012758107,0.022046326,0.0100912,0.02525812,-0.027952405,0.06829357,-0.05670089,0.01824109,-0.006112334,-0.026785785,0.054643866,-0.022609267,-0.039532308,0.026928999,-0.008799164,0.00014472878,-0.023215104,0.037227124,0.03809622,-0.08013754,-0.08846239,0.026347024,-0.15834594,-0.045169085,0.093819134,8.590922e-33,0.00867094,-0.035871215,0.0018731535,-0.02629795,-0.0054222336,0.0045699608,-0.070516855,-0.026580928,-0.097372465,0.0048535937,-0.02952227,-0.00560195,-0.03671155,-0.026597848,-0.0041590002,-0.029313218,0.031599984,0.023297718,-0.0077708615,0.015196708,-0.007081372,0.107177496,-0.020762818,0.018742885,-0.052481882,0.11070353,-0.039202332,-0.041835435,0.06495447,0.011446832,0.090374835,-0.056448642,-0.03864471,0.04522802,-0.04685675,-0.00013952493,-0.04637371,-0.03574875,-0.10174928,-0.009938862,0.026233518,0.01610412,-0.08950903,0.002229426,-0.072140425,-0.02563677,0.0034535467,-0.023983872,0.07782561,0.054934163,-0.09947756,0.078710176,-0.1342039,-0.015290272,0.023406696,-0.041623782,0.034741323,0.09204499,0.030499492,-0.08295253,0.011310558,0.07677338,0.038761456,-0.08301199,9.0982474e-05,-0.03695373,-0.04914765,-0.03721228,-0.0029663213,0.0007136498,-0.007976408,0.010652596,0.103724465,0.08308389,-0.03504547,-0.09324804,0.0016165721,-0.012689658,0.0035157974,0.010270199,-0.022701511,0.0038330588,-0.07504033,0.08606065,-0.0010407628,-0.019171081,-0.00917156,-0.02195973,0.00808662,0.019469282,-0.050138198,0.07633099,0.0036751542,-0.08258909,-0.031851366,-8.008214e-33,0.08585649,-0.009242262,-0.08247292,0.05219084,-0.028678825,-0.063508704,0.06988389,0.10791763,0.0043086926,0.01713288,0.103680246,-0.014682068,0.10162455,-0.039797083,0.05830351,-0.008386827,0.021594642,0.049289532,-0.0116948495,0.02499161,-0.058656685,0.03565204,-0.019493634,0.12776795,0.011140408,0.0022159936,0.11557138,-0.0706413,-0.12818877,0.06769191,0.03657696,0.008447117,-0.14649689,0.083624884,-0.057578824,-0.11690286,0.075197026,0.050938793,0.00934451,1.5277308e-05,0.0251469,0.059460875,-0.010228345,0.003859267,-0.02934309,-0.009709237,0.048618753,0.00563722,-0.015535763,-0.07648743,0.07267267,0.035891484,-0.008068753,0.015103617,-8.4516825e-05,0.051696353,-0.022773169,-0.034352552,0.088182695,-0.017086098,0.036857657,-0.024318814,-0.04530589,-0.031789936,0.08148961,-0.0391316,-0.11486345,0.07451222,0.06142979,-0.084551014,-0.012456609,-0.012500153,0.00043600218,0.026282325,0.008602927,-0.046667766,0.030422881,0.05899045,0.024153706,0.020871665,0.030298878,0.029900333,-0.0551599,-0.011450362,0.030047417,0.006378884,0.020285306,0.08958011,-0.0077368813,-0.005635802,0.012450613,0.037418738,-0.05259178,0.068801805,0.054264378,-5.0139622e-08,-0.06270949,-0.078771986,-0.008500376,-0.044614438,0.08906843,0.034785405,-0.04051438,-0.041191597,0.025299598,-0.011614067,0.09316638,0.050454337,-0.111673355,0.020210467,-0.014519851,0.021392323,-0.061561424,0.1512491,0.031946883,-0.022910194,0.05379749,-0.052394487,0.034804083,0.03202329,-0.011647016,0.023379797,-0.016545111,0.07218778,-0.074419826,-0.06353027,-0.039484736,0.002413956,0.016671069,-0.09615672,-0.010066096,0.017102325,-0.00035778977,0.015736591,-0.009770903,-0.050013475,0.077166,0.01128682,0.026153795,0.008262513,-0.05439526,-0.03157804,0.08243735,0.031730406,0.030229734,-0.10081583,-0.011651286,-0.106420554,0.018312354,-0.020499025,0.010302509,-0.03603244,0.0050526336,0.012031303,-0.06624725,9.589684e-06,0.076693185,0.06757109,-0.012323587,-0.013522255]", "station": "f57735e6-edc5-483a-a74c-cc7f581556ea"}}
{"after": {"at": "2020-08-27T01:38:56.99684", "crdb_region": "ar3", "param0": 394, "param1": -390, "param2": -268.303, "param3": -286.92, "param4": "PA5GF495WQH4PT4", "param5": {"gdzuohzyo": null}, "param6": "[-0.021200033,0.099679604,-0.033546187,-0.049485985,-0.02907414,-0.0146092735,0.03643893,0.034653924,-0.040711947,-0.02938859,0.09226406,-0.10506832,-0.036005404,0.008940524,-0.0731484,0.0865537,-0.095382005,-0.04743947,-0.0156211415,-0.050005496,0.029939627,0.068494886,-0.0064426768,-0.029055957,0.0460691,0.011043383,-0.054294635,0.007720534,0.023679193,-0.019506613,-0.005413189,0.04364974,0.02037544,-0.046833884,0.12883927,0.046118245,-0.013177143,-0.09261074,0.048410762,0.016107144,0.04477795,0.0314635,-0.065428376,0.09148203,-0.06733414,-0.008760356,-0.041784793,0.09779295,0.009640269,-0.044907354,-0.047916364,-0.05609683,-0.052256346,0.004724179,-0.002360127,0.040410277,-0.040901307,-0.0067921784,0.034198932,0.07537096,0.052123528,-0.014034009,-0.036093105,-0.0019409832,0.073947154,-0.034299813,0.012422687,-0.09126212,-0.095713854,-0.0008602066,0.03908493,0.0011099493,0.0027333712,0.021392565,-0.0505495,-0.018396743,-0.10109695,-0.037524875,0.0724126,-0.01885735,-0.010384563,-0.10048741,0.06592471,-0.0018459763,0.08272342,0.06743006,-0.045553524,0.012020335,0.02612091,0.0025854714,-0.034706462,-0.03852545,-0.0735402,-0.0041265483,-0.06934031,0.089587085,0.039574794,-0.027759021,-0.06172839,0.08130076,0.045207463,0.020892527,0.00023949244,-0.0011063964,-0.017098054,0.060094077,-0.0118511105,0.07978733,-0.048161186,-0.053484533,-0.08485519,0.009899143,-0.00848747,0.019407984,-0.0950874,-0.005510019,0.058731835,-0.018465014,-0.0404782,0.056425806,0.10552213,-0.050919052,-0.047502775,-0.054457504,-0.076822534,0.01073599,-0.003190587,4.6290406e-33,0.11743455,0.01918467,0.08633718,-0.00045277554,0.034146525,-0.030607132,-0.10338159,0.009813668,-0.0698219,0.057434555,-0.07015509,-0.094195426,0.014998163,-0.03673881,-0.026344985,0.04799896,0.039606728,0.0010581386,-0.01733966,0.027009327,0.023835791,0.080987334,-0.071263425,0.003167835,-0.033036366,0.16968343,-0.044175405,-0.043836284,0.052194368,0.049112286,-0.002951359,-0.03785379,-0.057603315,-0.033709403,0.023458026,-0.0073321317,0.045534108,-0.03425878,-0.0859871,-0.040388137,-0.021858191,-0.032177053,-0.08068363,-0.063715436,0.03437559,-0.05309209,0.017605452,-0.047885988,0.030757934,0.076352306,-0.08311966,-0.0022167058,-0.047132853,0.054068636,0.0024358793,-0.013866147,-0.013271479,0.0015346499,0.0055182152,-0.022007735,0.07440912,0.07269563,-0.002915417,-0.07055811,0.0366911,-0.0801639,-0.02200657,-0.044434216,-0.047366776,0.0059638685,0.009888472,-0.07841241,0.11345613,0.07726987,0.002295773,-0.10891622,-0.010032189,0.03272977,0.022634245,-0.030913202,-0.010735248,-0.027233997,-0.055097327,0.0015276638,-0.039644916,0.034151267,0.060016096,-0.00021207705,-0.027526231,0.047413304,-0.023127755,-0.010702399,-0.045548175,-0.092033684,-0.053420175,-6.603517e-33,0.03941173,0.01915295,-0.015082937,-0.022257105,-0.03266916,-0.049780093,0.0636123,0.045487583,0.0055868262,-0.0038638401,0.059246585,0.036789726,0.023759611,-0.036338612,0.029890273,0.114555284,0.002808552,-0.027224747,-0.07161691,0.0046220375,-0.0009326196,0.08539001,0.01316837,0.06481647,-0.029268365,0.007547643,0.13045612,-0.007429404,-0.049403664,0.06531211,-0.01911457,0.02781074,-0.114013284,0.015650807,0.012339369,-0.038924426,0.04868821,0.055113103,0.030852107,0.02122013,0.0048904708,0.05882731,0.04979412,0.062562324,0.030745033,-0.011663454,0.00069650094,-0.020671375,0.023321537,-0.025831759,0.065607384,-0.032409113,0.005553087,-0.0038067119,-0.013801591,0.037438508,0.020513939,-0.00875399,-0.031205552,0.045089178,-0.028514337,0.010933492,-0.063090846,0.0065324875,0.08754994,-0.037634023,-0.068895444,0.12182541,0.073097125,-0.062568575,-0.033390142,-0.014994147,0.026930612,0.029873313,0.028123062,0.02838337,-0.053751726,0.0384415,0.030125216,0.00094733696,0.04568842,0.047075726,-0.034442067,-0.053485643,0.02792171,-0.10947605,0.00441756,0.12701322,-0.023849597,-0.055922795,-0.036771476,0.10667786,-0.054100532,0.030337853,-0.009174443,-3.8944904e-08,-0.024162093,-0.021782108,-0.023702346,-0.050062403,0.09129517,0.019070288,-0.0017590417,-0.05769832,0.06923126,0.011163473,0.0013671565,0.055647966,-0.105533,0.011680609,0.011971145,-0.05426879,-0.14205912,0.06790957,-0.013569826,0.0057345745,-0.028460547,-0.0076535637,-0.051548835,-0.0374469,0.022535555,-0.03296334,0.082086235,0.064468436,-0.0705671,0.028502686,0.01941848,0.12550408,-0.06368431,-0.033810426,-0.04710273,0.0077699074,0.04197648,0.038503136,-0.033496663,-0.023535496,0.035517495,-0.034122422,-0.0091995085,-0.004654036,-0.027021797,-0.05945259,0.0019088361,0.023380507,0.07573554,0.00044499774,-0.03407134,-0.03592311,-0.027615657,-0.015782537,-0.06467355,-0.039071694,0.076723546,0.010593594,-0.051109616,-0.048909098,0.049518306,-0.0044917664,0.034586065,0.00450364]", "station": "f65946cc-7098-4167-aa9b-0398d5374cde"}}
{"resolved":"1767732614000000000.0000000000"}
{"resolved":"1767732633000000000.0000000000"}
```
