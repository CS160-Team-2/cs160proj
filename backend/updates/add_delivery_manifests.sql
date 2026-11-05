-- Adds the delivery_manifests table to an existing ofs database without
-- erasing anything. Use this instead of re-running schema.sql when you
-- want to keep your local orders, accounts and product edits.
-- SETUP.md, "Updating your database after a pull", has the commands.
--
-- Safe to run more than once: if the table already exists, nothing happens.
-- The definition matches backend/schema.sql.

USE ofs;

CREATE TABLE IF NOT EXISTS delivery_manifests (
  manifest_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  fingerprint  CHAR(64)     NOT NULL UNIQUE,
  filename     VARCHAR(255) NOT NULL,
  applied_by   BIGINT       NOT NULL,
  line_count   INT          NOT NULL,
  total_units  INT          NOT NULL,
  applied_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (applied_by) REFERENCES users(user_id),
  CHECK (line_count > 0),
  CHECK (total_units > 0)
) ENGINE=InnoDB;
