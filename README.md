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
ALTER DATABASE nextgenreporting SET SECONDARY REGION "gcp-europe-west3";
```


```sql
SHOW REGIONS FROM DATABASE nextgenreporting;             
```

```bash
      database     |         region         | primary | secondary |                                    zones
-------------------+------------------------+---------+-----------+-------------------------------------------------------------------------------
  nextgenreporting | gcp-us-east1           |    t    |     f     | {gcp-us-east1-b,gcp-us-east1-c,gcp-us-east1-d}
  nextgenreporting | gcp-europe-west3       |    f    |     t     | {gcp-europe-west3-a,gcp-europe-west3-b,gcp-europe-west3-c}
  nextgenreporting | gcp-europe-west2       |    f    |     f     | {gcp-europe-west2-a,gcp-europe-west2-b,gcp-europe-west2-c}
  nextgenreporting | gcp-southamerica-east1 |    f    |     f     | {gcp-southamerica-east1-a,gcp-southamerica-east1-b,gcp-southamerica-east1-c}
  nextgenreporting | gcp-us-central1        |    f    |     f     | {gcp-us-central1-b,gcp-us-central1-c,gcp-us-central1-f}
  nextgenreporting | gcp-us-west2           |    f    |     f     | {gcp-us-west2-a,gcp-us-west2-b,gcp-us-west2-c}
(6 rows)
```


