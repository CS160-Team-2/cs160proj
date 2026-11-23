-- Adds the product_pictures table to an existing ofs database without erasing anything.
-- Product pictures used to be saved as files in backend/uploads/products on one computer; they are now
-- stored in the database so they move with it. Pictures that are still files keep working: the first
-- time one is shown it is copied into the database by itself.
-- SETUP.md, "Updating your database after a pull", has the commands.
--
-- Safe to run more than once: if the table already exists, nothing happens.

USE ofs;

CREATE TABLE IF NOT EXISTS product_pictures (
  filename   VARCHAR(40)  NOT NULL PRIMARY KEY,
  mime_type  VARCHAR(30)  NOT NULL,
  data       MEDIUMBLOB   NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;
