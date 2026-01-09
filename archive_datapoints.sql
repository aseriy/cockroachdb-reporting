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
