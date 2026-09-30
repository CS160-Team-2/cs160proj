-- OFS feasibility spike — database setup
-- =====================================================================
-- Run this whole file once, as root, from MySQL Workbench:
--   File > Open SQL Script...  choose this file
--   then click the lightning-bolt "Execute" button.
--
-- It is safe to re-run: it drops and recreates everything.
-- =====================================================================

DROP DATABASE IF EXISTS ofs;
CREATE DATABASE ofs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ofs;


-- --- Application user -------------------------------------------------
-- Every team member creates this same user locally with the same
-- password, so one .env file works on all six machines and nobody has to
-- put their personal MySQL root password into a project file.

DROP USER IF EXISTS 'cs160team2'@'localhost';
CREATE USER 'cs160team2'@'localhost' IDENTIFIED BY 'team2_password';
GRANT ALL PRIVILEGES ON ofs.* TO 'cs160team2'@'localhost';
FLUSH PRIVILEGES;


-- --- Schema -----------------------------------------------------------
-- Just enough to exercise the two main use cases. The full schema is in
-- the Low-Level Design Document, section I.

CREATE TABLE products (
  product_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(160)  NOT NULL,
  price          DECIMAL(10,2) NOT NULL,
  unit_weight_lb DECIMAL(8,2)  NOT NULL,
  is_listed      BOOLEAN       NOT NULL DEFAULT TRUE,
  CHECK (unit_weight_lb > 0),
  CHECK (price >= 0)
) ENGINE=InnoDB;

CREATE TABLE customers (
  customer_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email       VARCHAR(255) NOT NULL UNIQUE,
  full_name   VARCHAR(120) NOT NULL
) ENGINE=InnoDB;

CREATE TABLE carts (
  cart_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  customer_id BIGINT NOT NULL UNIQUE,          -- one open cart per customer
  updated_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                       ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
) ENGINE=InnoDB;

CREATE TABLE cart_items (
  cart_id    BIGINT NOT NULL,
  product_id BIGINT NOT NULL,
  quantity   INT    NOT NULL,
  PRIMARY KEY (cart_id, product_id),
  FOREIGN KEY (cart_id)    REFERENCES carts(cart_id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  CHECK (quantity > 0)
) ENGINE=InnoDB;


-- --- Seed data --------------------------------------------------------
INSERT INTO products (name, price, unit_weight_lb) VALUES
  ('Organic Lemon (each)',      0.79,  0.10),
  ('Organic Apples, 3 lb bag',  6.49,  3.00),
  ('Spring Water, 24-pack',     5.99, 25.00);

INSERT INTO customers (email, full_name) VALUES
  ('anna@example.com', 'Anna Rivera');

-- Why these three products:
--   Lemon at 0.10 lb  -> 10 of them must total EXACTLY 1.00, not
--                        0.9999999. This is the floating-point trap the
--                        whole 20 lb rule depends on avoiding.
--   Apples at 3.00 lb -> 6 bags = 18.00 lb, just under the threshold.
--                        Add 20 lemons and the cart is exactly 20.00 lb.
--   Water at 25.00 lb -> a single item that crosses the threshold alone.


-- --- Verify -----------------------------------------------------------
SELECT 'Products loaded:'  AS check_name, COUNT(*) AS result FROM products;
SELECT 'Customers loaded:' AS check_name, COUNT(*) AS result FROM customers;
SELECT 'MySQL version:'    AS check_name, VERSION() AS result;
SELECT * FROM products;
