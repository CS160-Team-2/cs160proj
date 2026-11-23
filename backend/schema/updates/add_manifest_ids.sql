-- Gives every delivery manifest its own ID, which is how duplicates are now
-- caught. Replaces the old check that compared whole files.
-- Keeps all your local data. Manifests already applied get an ID like LEGACY-3.
-- SETUP.md, "Updating your database after a pull", has the commands.
--
-- Safe to run more than once. Run add_delivery_manifests.sql first if your
-- database does not have the delivery_manifests table yet.

USE ofs;

-- 1. Add the ID column, if it is not there yet.
SET @found = (SELECT COUNT(*) FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'delivery_manifests'
                AND COLUMN_NAME = 'supplier_manifest_id');
SET @step = IF(@found = 0,
  'ALTER TABLE delivery_manifests ADD COLUMN supplier_manifest_id VARCHAR(64) NULL AFTER manifest_id',
  'DO 0');
PREPARE run_step FROM @step; EXECUTE run_step; DEALLOCATE PREPARE run_step;

-- 2. Give existing manifests an ID, then make the ID required and one of a kind.
UPDATE delivery_manifests SET supplier_manifest_id = CONCAT('LEGACY-', manifest_id)
WHERE manifest_id > 0 AND supplier_manifest_id IS NULL;
ALTER TABLE delivery_manifests MODIFY supplier_manifest_id VARCHAR(64) NOT NULL;

SET @found = (SELECT COUNT(*) FROM information_schema.STATISTICS
              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'delivery_manifests'
                AND INDEX_NAME = 'supplier_manifest_id');
SET @step = IF(@found = 0,
  'ALTER TABLE delivery_manifests ADD UNIQUE KEY supplier_manifest_id (supplier_manifest_id)',
  'DO 0');
PREPARE run_step FROM @step; EXECUTE run_step; DEALLOCATE PREPARE run_step;

-- 3. Remove the old check, if it is still there.
SET @found = (SELECT COUNT(*) FROM information_schema.STATISTICS
              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'delivery_manifests'
                AND INDEX_NAME = 'uq_manifest_file_date');
SET @step = IF(@found > 0, 'ALTER TABLE delivery_manifests DROP INDEX uq_manifest_file_date', 'DO 0');
PREPARE run_step FROM @step; EXECUTE run_step; DEALLOCATE PREPARE run_step;

SET @found = (SELECT COUNT(*) FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'delivery_manifests'
                AND COLUMN_NAME = 'delivery_date');
SET @step = IF(@found > 0, 'ALTER TABLE delivery_manifests DROP COLUMN delivery_date', 'DO 0');
PREPARE run_step FROM @step; EXECUTE run_step; DEALLOCATE PREPARE run_step;

SET @found = (SELECT COUNT(*) FROM information_schema.COLUMNS
              WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'delivery_manifests'
                AND COLUMN_NAME = 'fingerprint');
SET @step = IF(@found > 0, 'ALTER TABLE delivery_manifests DROP COLUMN fingerprint', 'DO 0');
PREPARE run_step FROM @step; EXECUTE run_step; DEALLOCATE PREPARE run_step;
