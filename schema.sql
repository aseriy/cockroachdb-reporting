CREATE TABLE geos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name STRING UNIQUE NOT NULL,
    crdb_region crdb_internal_region NOT NULL
);

CREATE INDEX IF NOT EXISTS geos_crdb_region_rec_idx ON nextgenreporting.public.geos (crdb_region); 

--
-- Populate 'geos' table
--
INSERT INTO geos (name, crdb_region)
VALUES
  -- ===============================
  -- Group 1: tx1 (US-East)
  -- ===============================
  ('US East (N. Virginia)',     'tx1'),
  ('US East (Ohio)',            'tx1'),
  ('US Central (Iowa)',         'tx1'),
  ('CA Central (Montreal)',     'tx1'),
  ('South America (São Paulo)', 'tx1'),

  -- ===============================
  -- Group 2: tx2 (US-West)
  -- ===============================
  ('US Mountain (Utah)',        'tx2'),
  ('US West (N. California)',   'tx2'),
  ('US West (Oregon)',          'tx2'),
  ('AP Southeast (Sydney)',     'tx2'),
  ('AP Southeast (Singapore)',  'tx2'),
  ('AP South (Mumbai)',         'tx2'),
  ('AP East (Hong Kong)',       'tx2'),
  ('AP Northeast (Tokyo)',      'tx2'),
  ('AP Northeast (Seoul)',      'tx2'),

  -- ==========================================
  -- Group 3: tx3 (Frankfurt / EU)
  -- ==========================================
  ('EU Central (Frankfurt)',    'tx3'),
  ('EU West (Ireland)',         'tx3'),
  ('EU North (Stockholm)',      'tx3'),
  ('EU South (Milan)',          'tx3'),
  ('EU West (London)',          'tx3'),
  ('EU West (Paris)',           'tx3'),
  ('Middle East (Bahrain)',     'tx3'),
  ('Middle East (UAE)',         'tx3'),
  ('Africa (Cape Town)',        'tx3');


CREATE TABLE IF NOT EXISTS stations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    geo UUID NOT NULL REFERENCES geos(id) ON DELETE CASCADE,
    INDEX index_geo (geo)
);


--
-- Create 100 stations in every geo
--
INSERT INTO stations (geo)
SELECT id                         
FROM geos                                                   
CROSS JOIN generate_series(1, 100);


--
-- Make both 'geos' and 'stations' tables GLOBAL
--
ALTER TABLE geos SET LOCALITY GLOBAL;
ALTER TABLE stations SET LOCALITY GLOBAL;



CREATE TABLE public.datapoints (
	at TIMESTAMP NOT NULL,
	station UUID NOT NULL,
	param0 INT8 NULL,
	param1 INT8 NULL,
	param2 FLOAT8 NULL,
	param3 FLOAT8 NULL,
	param4 STRING NULL,
	param5 JSONB NULL,
	param6 VECTOR(384) NULL,
	crdb_region public.crdb_internal_region NOT VISIBLE NOT NULL DEFAULT gateway_region()::public.crdb_internal_region,
	crdb_internal_at_station_shard_16 INT8 NOT VISIBLE NOT NULL AS (mod(fnv32(md5(crdb_internal.datums_to_bytes(at, station))), 16:::INT8)) VIRTUAL,
	CONSTRAINT datapoints_pkey PRIMARY KEY (station ASC, at ASC) USING HASH WITH (bucket_count=16),
	CONSTRAINT datapoints_station_fkey FOREIGN KEY (station) REFERENCES public.stations(id) ON DELETE CASCADE
) LOCALITY REGIONAL BY ROW AS crdb_region;

-- -- Example: Force any rows coming from 'report' to 'tx1' instead
-- ALTER TABLE datapoints ALTER COLUMN crdb_region 
-- SET DEFAULT CASE WHEN gateway_region() = 'report' THEN 'tx1'::crdb_internal_region ELSE gateway_region() END;


--
-- REPORTING workloads
--

--
-- Create a vector index (will set it later in the reporting region)
--
SET CLUSTER SETTING feature.vector_index.enabled = true;
CREATE VECTOR INDEX ON datapoints (param6);


--
-- ????
--
CREATE INDEX IF NOT EXISTS datapoints_station_storing_rec_idx
    ON datapoints (station) STORING (param0, param1, param2, param3, param4); 

CREATE INDEX IF NOT EXISTS datapoints_at ON datapoints USING btree (at ASC);
CREATE INDEX IF NOT EXISTS datapoints_param0_rec_idx ON datapoints (param0);

