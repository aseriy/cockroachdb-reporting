# cockroachdb-reporting
Reference implementation for Part 2 of “Rethinking the Reporting Platform.” Demonstrates a multi-region CockroachDB setup for unified transactional and reporting workloads, with example schema, queries, and supporting code.



Regions

```sql
-- South Carolina (us-east1) -- PRIMARY
ALTER DATABASE nextgenreporting ADD REGION "gcp-us-east1";
-- Iowa (us-central1)
ALTER DATABASE nextgenreporting ADD REGION "gcp-us-central1";
-- California (us-west2)
ALTER DATABASE nextgenreporting ADD REGION "gcp-us-west2";
-- London (europe-west2)
ALTER DATABASE nextgenreporting ADD REGION "gcp-europe-west2";
-- Frankfurt (europe-west3)
ALTER DATABASE nextgenreporting ADD REGION "gcp-europe-west3";
-- São Paulo (southamerica-east1)
ALTER DATABASE nextgenreporting ADD REGION "gcp-southamerica-east1";
```


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



Add regions to the database:

```sql
ALTER DATABASE nextgenreporting SURVIVE REGION FAILURE;
```

```sql
ALTER DATABASE nextgenreporting SET PRIMARY REGION "tx1";
ALTER DATABASE nextgenreporting SET SECONDARY REGION 'tx2';
ALTER DATABASE nextgenreporting ADD region 'tx3';
ALTER DATABASE nextgenreporting ADD SUPER REGION "transact" VALUES  "tx1","tx2","tx3"
ALTER DATABASE nextgenreporting ADD region 'report';
ALTER DATABASE nextgenreporting ADD region 'ar1';
ALTER DATABASE nextgenreporting ADD region 'ar2';
ALTER DATABASE nextgenreporting ADD region 'ar3';
ALTER DATABASE nextgenreporting ADD SUPER REGION "archive" VALUES  "ar1","ar2","ar3"
```

```sql
ALTER DATABASE nextgenreporting ADD SUPER REGION "transact" VALUES "tx1", "tx2", "tx3";
ALTER TABLE datapoints SET LOCALITY REGIONAL BY ROW;
```




```bash
> show regions;                                                  
  region  | zones |   database_names   | primary_region_of  | secondary_region_of
----------+-------+--------------------+--------------------+----------------------
  archive | {}    | {nextgenreporting} | {}                 | {}
  report  | {}    | {nextgenreporting} | {}                 | {}
  tx1     | {}    | {nextgenreporting} | {nextgenreporting} | {}
  tx2     | {}    | {nextgenreporting} | {}                 | {}
  tx3     | {}    | {nextgenreporting} | {}                 | {}
(5 rows)

Time: 47ms total (execution 46ms / network 1ms)
```





```sql
SET override_multi_region_zone_config = true;
ALTER TABLE datapoints CONFIGURE ZONE USING
range_min_bytes = 134217728,
range_max_bytes = 536870912,
gc.ttlseconds = 14400,
num_replicas = 5,
num_voters = 5,
constraints = '{+region=tx1: 1, +region=tx2: 1, +region=tx3: 1}',
voter_constraints = '{+region=tx1: 1, +region=tx2: 1, +region=tx3: 1}',
lease_preferences = '[]';
```


```sql
SELECT range_id, replicas, voting_replicas,
non_voting_replicas, replica_localities FROM
[show ranges from table datapoints]
ORDER BY range_id;                           
```


```bash
  range_id |    replicas    | voting_replicas | non_voting_replicas |                          replica_localities
-----------+----------------+-----------------+---------------------+-----------------------------------------------------------------------
       199 | {2,3,5,10,15}  | {15,3,10,2,5}   | {}                  | {region=tx3,region=tx1,region=tx2,region=archive,region=report}
       200 | {1,7,10,12,13} | {10,12,13}      | {1,7}               | {region=tx1,region=tx3,region=archive,region=archive,region=archive}
       201 | {4,6,8,12,14}  | {14,12,6,8,4}   | {}                  | {region=tx2,region=tx1,region=tx3,region=archive,region=report}
       202 | {3,9,11,14,15} | {14,15,11}      | {3,9}               | {region=tx1,region=tx2,region=report,region=report,region=report}
       203 | {4,6,7,12,15}  | {15,12,6,7,4}   | {}                  | {region=tx2,region=tx1,region=tx3,region=archive,region=report}
       204 | {2,3,4,5,9}    | {9,4,5}         | {3,2}               | {region=tx3,region=tx1,region=tx2,region=tx2,region=tx2}
       205 | {1,5,7,10,14}  | {1,14,10,7,5}   | {}                  | {region=tx1,region=tx2,region=tx3,region=archive,region=report}
       206 | {2,5,6,7,8}    | {7,8,2}         | {6,5}               | {region=tx3,region=tx2,region=tx1,region=tx3,region=tx3}
       207 | {2,3,5,13,15}  | {13,3,15,2,5}   | {}                  | {region=tx3,region=tx1,region=tx2,region=archive,region=report}
       211 | {1,3,4,6,7}    | {1,3,6}         | {7,4}               | {region=tx1,region=tx1,region=tx2,region=tx1,region=tx3}
       212 | {3,4,7,11,13}  | {11,3,13,7,4}   | {}                  | {region=tx1,region=tx2,region=tx3,region=report,region=archive}
(11 rows)

Time: 15ms total (execution 14ms / network 1ms)
```

```sql
SELECT 
    crdb_region, 
    count(*) AS row_count
FROM datapoints
GROUP BY crdb_region ORDER BY crdb_region;
```

```sql
SELECT                 
crdb_internal_at_station_shard_16 AS shard,                
count(*) AS row_count                                      
FROM datapoints                                                
GROUP BY crdb_internal_at_station_shard_16 ORDER BY            
crdb_internal_at_station_shard_16;
```


```sql
SELECT crdb_region, crdb_internal_at_station_shard_16, station, at 
FROM datapoints 
WHERE station = '00ee18f6-60a4-4bf0-af36-37b50861e798' 
  AND at = '2025-03-26 03:00:53.323479';
```

```sql
SELECT crdb_region, crdb_internal_at_station_shard_16, station, at 
FROM datapoints 
WHERE crdb_internal_at_station_shard_16 = 0
ORDER BY random();
```


```bash
  crdb_region | crdb_internal_at_station_shard_16 |               station                |             at
--------------+-----------------------------------+--------------------------------------+-----------------------------
  tx1         |                                 0 | 00ee18f6-60a4-4bf0-af36-37b50861e798 | 2025-03-26 03:00:53.323479
(1 row)
```

```sql
SELECT range_id, lease_holder, lease_holder_locality, replicas, replica_localities
FROM [SHOW RANGE FROM TABLE datapoints FOR ROW ('tx1', 0, '00ee18f6-60a4-4bf0-af36-37b50861e798', '2025-03-26 03:00:53.323479')];
```

```bash
  range_id | lease_holder | lease_holder_locality |  replicas   |                    replica_localities
-----------+--------------+-----------------------+-------------+-----------------------------------------------------------
       536 |            6 | region=tx1            | {1,4,5,6,7} | {region=tx1,region=tx2,region=tx2,region=tx1,region=tx3}
(1 row)
```






## Archiving


```sql
WITH rows_updated AS (
WITH
batch AS (
    SELECT at, station
    FROM datapoints
    WHERE crdb_region IN ('tx1', 'tx2', 'tx3') AND at < now() - INTERVAL '1 month'
    LIMIT 1000
),
region AS (
    SELECT r::crdb_internal_region
    FROM (VALUES ('ar1'), ('ar2'), ('ar3')) v(r)
    ORDER BY random()
    LIMIT 1
)
UPDATE datapoints
SET crdb_region = region.r
FROM batch, region
WHERE datapoints.station = batch.station AND datapoints.at = batch.at RETURNING 1
) SELECT count(*) FROM rows_updated;
```


```sql
CREATE OR REPLACE PROCEDURE archive_datapoints() AS $$
DECLARE
  rows_updated_c INT := 0;

BEGIN
  LOOP
    WITH rows_updated AS (
    WITH
    batch AS (
        SELECT at, station
        FROM datapoints
        WHERE crdb_region IN ('tx1', 'tx2', 'tx3') AND at < now() - INTERVAL '1 month'
        LIMIT 1000
    ),
    region AS (
        SELECT r::crdb_internal_region
        FROM (VALUES ('ar1'), ('ar2'), ('ar3')) v(r)
        ORDER BY random()
        LIMIT 1
    )
    UPDATE datapoints
    SET crdb_region = region.r
    FROM batch, region
    WHERE datapoints.station = batch.station AND datapoints.at = batch.at RETURNING 1
    ) SELECT count(*) INTO rows_updated_c FROM rows_updated;

    RAISE NOTICE 'Updated % rows', rows_updated_c;
    IF rows_updated_c < 1 THEN
      RAISE NOTICE 'Done.';
      EXIT;
    END IF;
    
  END LOOP;
END;
$$ LANGUAGE PLpgSQL;
```


```sql
CALL archive_datapoints();
```






List ranges associated with a table:

```sql
SELECT range_id, range_size, lease_holder, replicas, replica_localities FROM                
crdb_internal.ranges WHERE range_id IN (SELECT range_id FROM   
[show ranges from table datapoints]) ORDER BY range_id;  
```



```sql
SELECT range_id, lease_holder, lease_holder_locality, replicas, replica_localities
FROM [SHOW RANGE FROM TABLE datapoints FOR ROW ('tx1', 0, '00ee18f6-60a4-4bf0-af36-37b50861e798', '2025-03-26 03:00:53.323479')];
```

```sql
WITH batch AS (
  SELECT crdb_region, crdb_internal_at_station_shard_16,
  station, at
  FROM datapoints LIMIT 1000 OFFSET 0
)
SELECT batch.crdb_region FROM batch;
```

Disk space per node:

```sql
SELECT
  s.node_id,
  n.locality,
  sum(s.used) AS used_bytes
FROM crdb_internal.kv_store_status AS s
JOIN crdb_internal.gossip_nodes AS n
  ON s.node_id = n.node_id
GROUP BY s.node_id, n.locality
ORDER BY s.node_id;
```

```bash
  node_id |   locality    | used_bytes
----------+---------------+-------------
        1 | region=tx1    |  765351302
        2 | region=tx3    | 1113006946
        3 | region=tx1    |  854952805
        4 | region=tx2    | 1216570863
        5 | region=tx2    |  858028263
        6 | region=tx1    | 1026987534
        7 | region=tx3    |  938442685
        8 | region=tx3    | 1196339104
        9 | region=tx2    | 1291928021
       10 | region=ar1    |  551337131
       11 | region=report | 1398067654
       12 | region=ar1    | 1069884182
       13 | region=ar1    | 1049924737
       14 | region=report | 1024862887
       15 | region=report |  562929292
       16 | region=ar2    | 1123908082
       17 | region=ar2    | 1465644347
       18 | region=ar2    |  614112864
       19 | region=ar3    |  947927277
       20 | region=ar3    | 1040088485
       21 | region=ar3    | 1127466613
(21 rows)
```


Reporting queries:

```sql
CREATE INDEX IF NOT EXISTS ON datapoints (at);
```



Materialized View (Reporting Region)

```sql
CREATE MATERIALIZED VIEW datapoints_mv AS
SELECT  d.at, d.station, g.name,
        d.param0, d.param1, d.param2,
        d.param3, d.param4,
        d.param5,d.param6
FROM stations as s
JOIN datapoints as d ON s.id = d.station
JOIN geos AS g ON s.geo = g.id;
```

```sql
ALTER TABLE datapoints_mv CONFIGURE ZONE USING
    range_min_bytes = 134217728,
    range_max_bytes = 536870912,
    gc.ttlseconds = 14400,
    global_reads = true,
    num_replicas = 3,
    num_voters = 3,
    constraints = '{+region=report: 3}',
    voter_constraints = '{+region=report}',
    lease_preferences = '[[+region=report]]';
```



