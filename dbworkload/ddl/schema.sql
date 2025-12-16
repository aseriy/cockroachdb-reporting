CREATE TABLE geos (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name STRING UNIQUE NOT NULL,
    crdb_region crdb_internal_region NOT NULL
);


--
-- Populate 'geos' table
--
INSERT INTO geos (name, crdb_region)
VALUES
  -- ===============================
  -- Group 1: gcp-us-east1 (US-East)
  -- ===============================
  ('US East (N. Virginia)',     'gcp-us-east1'),
  ('US East (Ohio)',            'gcp-us-east1'),
  ('US Central (Iowa)',         'gcp-us-east1'),
  ('CA Central (Montreal)',     'gcp-us-east1'),
  ('South America (São Paulo)', 'gcp-us-east1'),

  -- ===============================
  -- Group 2: gcp-us-west2 (US-West)
  -- ===============================
  ('US Mountain (Utah)',        'gcp-us-west2'),
  ('US West (N. California)',   'gcp-us-west2'),
  ('US West (Oregon)',          'gcp-us-west2'),
  ('AP Southeast (Sydney)',     'gcp-us-west2'),
  ('AP Southeast (Singapore)',  'gcp-us-west2'),
  ('AP South (Mumbai)',         'gcp-us-west2'),
  ('AP East (Hong Kong)',       'gcp-us-west2'),
  ('AP Northeast (Tokyo)',      'gcp-us-west2'),
  ('AP Northeast (Seoul)',      'gcp-us-west2'),

  -- ==========================================
  -- Group 3: gcp-europe-west3 (Frankfurt / EU)
  -- ==========================================
  ('EU Central (Frankfurt)',    'gcp-europe-west3'),
  ('EU West (Ireland)',         'gcp-europe-west3'),
  ('EU North (Stockholm)',      'gcp-europe-west3'),
  ('EU South (Milan)',          'gcp-europe-west3'),
  ('EU West (London)',          'gcp-europe-west3'),
  ('EU West (Paris)',           'gcp-europe-west3'),
  ('Middle East (Bahrain)',     'gcp-europe-west3'),
  ('Middle East (UAE)',         'gcp-europe-west3'),
  ('Africa (Cape Town)',        'gcp-europe-west3');


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



CREATE TABLE IF NOT EXISTS datapoints (
    at TIMESTAMP,
    station UUID NOT NULL REFERENCES stations (id) ON DELETE CASCADE,
    param0 INT,
    param1 INT,
    param2 FLOAT,
    param3 FLOAT,
    param4 STRING,
    param5 JSONB,
    PRIMARY KEY (station ASC, at ASC) USING HASH
);


CREATE TABLE datapoints (
    at TIMESTAMP NOT NULL,
    station UUID NOT NULL REFERENCES stations(id) ON DELETE CASCADE,
    param0 INT,
    param1 INT,
    param2 FLOAT,
    param3 FLOAT,
    param4 STRING,
    param5 JSONB,
    param6 VECTOR(384),
    region crdb_internal_region NOT VISIBLE NOT NULL DEFAULT gateway_region()::crdb_internal_region STORED,
    PRIMARY KEY (station ASC, at ASC) USING HASH
) LOCALITY REGIONAL BY ROW AS crdb_region;


CREATE INDEX IF NOT EXISTS datapoints_station_storing_rec_idx
    ON datapoints (station) STORING (param0, param1, param2, param3, param4); 

CREATE INDEX IF NOT EXISTS datapoints_at ON datapoints USING btree (at ASC);
CREATE INDEX IF NOT EXISTS datapoints_param0_rec_idx ON datapoints (param0);

