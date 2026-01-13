--
-- Add cluster regions to the database
--
ALTER DATABASE nextgenreporting SET PRIMARY REGION "tx1";
ALTER DATABASE nextgenreporting ADD region 'tx2';
ALTER DATABASE nextgenreporting ADD region 'tx3';
ALTER DATABASE nextgenreporting ADD region 'ar1';
ALTER DATABASE nextgenreporting ADD region 'ar2';
ALTER DATABASE nextgenreporting ADD region 'ar3';
ALTER DATABASE nextgenreporting ADD region 'report';

--
-- This database will survive region failures
--
ALTER DATABASE nextgenreporting SURVIVE REGION FAILURE;

--
-- Create super regions
--
ALTER DATABASE nextgenreporting ADD SUPER REGION "transact" VALUES  "tx1","tx2","tx3"
ALTER DATABASE nextgenreporting ADD SUPER REGION "archive" VALUES  "ar1","ar2","ar3"

--
-- Enable vector indexing in the cluster.
--
SET CLUSTER SETTING feature.vector_index.enabled = true;
