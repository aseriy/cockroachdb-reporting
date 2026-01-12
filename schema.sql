CREATE TABLE geos (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    name STRING NOT NULL,
    crdb_region public.crdb_internal_region NOT NULL,
    CONSTRAINT geos_pkey PRIMARY KEY (id ASC),
    UNIQUE INDEX geos_name_key (name ASC),
    INDEX geos_crdb_region_rec_idx (crdb_region ASC)
) LOCALITY GLOBAL;

--
-- Populate 'geos' table
--
INSERT INTO geos (name, crdb_region)
VALUES
  -- ===============================
  -- tx1 (US-East)
  -- ===============================
  ('US East (N. Virginia)',     'tx1'),
  ('US East (Ohio)',            'tx1'),
  ('US Central (Iowa)',         'tx1'),
  ('CA Central (Montreal)',     'tx1'),
  ('South America (São Paulo)', 'tx1'),

  -- ===============================
  -- tx2 (US-West)
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
  -- tx3 (Frankfurt / EU)
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


CREATE TABLE stations (
    id UUID NOT NULL DEFAULT gen_random_uuid(),
    geo UUID NOT NULL,
    CONSTRAINT stations_pkey PRIMARY KEY (id ASC),
    CONSTRAINT stations_geo_fkey FOREIGN KEY (geo) REFERENCES geos(id) ON DELETE CASCADE,
    INDEX index_geo (geo ASC)
) LOCALITY GLOBAL;


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



CREATE TABLE datapoints (
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
    CONSTRAINT datapoints_station_fkey FOREIGN KEY (station) REFERENCES stations(id) ON DELETE CASCADE,
    INDEX datapoints_at_idx (at ASC),
    VECTOR INDEX datapoints_param6_idx (param6 vector_l2_ops)
) LOCALITY REGIONAL BY ROW AS crdb_region;


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




--
-- Materialized View
--
CREATE MATERIALIZED VIEW datapoints_mv AS
SELECT  d.at, d.station, g.name,
        d.param0, d.param1, d.param2,
        d.param3, d.param4,
        d.param5,d.param6
FROM stations as s
JOIN datapoints as d ON s.id = d.station
JOIN geos AS g ON s.geo = g.id;

CREATE INDEX ON datapoints_mv (length(param4));
CREATE INVERTED INDEX param5_keys_idx ON datapoints_mv (param5);
CREATE VECTOR INDEX ON datapoints_mv (param6);

--
-- REPORTING workloads
--



