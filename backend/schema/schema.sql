-- Run as MySQL root: recreates the ofs database from scratch and erases everything in it.
DROP DATABASE IF EXISTS ofs;
CREATE DATABASE ofs CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- The app's MySQL user (the same on every machine), with access to ofs and the test database ofs_test.
DROP USER IF EXISTS 'cs160team2'@'localhost';
CREATE USER 'cs160team2'@'localhost' IDENTIFIED BY 'team2_password';
GRANT ALL PRIVILEGES ON ofs.*      TO 'cs160team2'@'localhost';
GRANT ALL PRIVILEGES ON ofs_test.* TO 'cs160team2'@'localhost';
FLUSH PRIVILEGES;

-- Everything below goes into ofs.
USE ofs;

-- @@TABLES@@

-- People: customers, employees and managers (one table with a role), and guest checkouts.
CREATE TABLE users (
  user_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  full_name     VARCHAR(120) NOT NULL,
  phone         VARCHAR(30)  NULL,
  role          ENUM('customer','employee','manager') NOT NULL DEFAULT 'customer',
  is_active     BOOLEAN  NOT NULL DEFAULT TRUE,
  is_guest      BOOLEAN  NOT NULL DEFAULT FALSE,
  contact_email VARCHAR(255) NULL,
  created_at    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Delivery addresses with their map coordinates; soft-deleted so past orders keep theirs.
CREATE TABLE addresses (
  address_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id    BIGINT       NOT NULL,
  street     VARCHAR(200) NOT NULL,
  city       VARCHAR(100) NOT NULL,
  state      VARCHAR(50)  NOT NULL,
  zip_code   VARCHAR(10)  NOT NULL,
  latitude   DECIMAL(9,6) NOT NULL,
  longitude  DECIMAL(9,6) NOT NULL,
  is_deleted BOOLEAN  NOT NULL DEFAULT FALSE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- The catalog; unlisted products are hidden from the shop but kept for past orders.
CREATE TABLE products (
  product_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(160)  NOT NULL,
  description    TEXT          NULL,
  category       VARCHAR(60)   NOT NULL DEFAULT 'Other',
  price          DECIMAL(10,2) NOT NULL,
  unit_weight_lb DECIMAL(8,2)  NOT NULL,
  image_key      VARCHAR(100)  NULL,
  is_listed      BOOLEAN       NOT NULL DEFAULT TRUE,
  created_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at     DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  CHECK (unit_weight_lb > 0),
  CHECK (price >= 0)
) ENGINE=InnoDB;

-- Pictures staff upload, stored here so they travel with the database.
CREATE TABLE product_pictures (
  filename   VARCHAR(40)  NOT NULL PRIMARY KEY,
  mime_type  VARCHAR(30)  NOT NULL,
  data       MEDIUMBLOB   NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Stock level and low-stock level for each product.
CREATE TABLE inventory (
  inventory_id        BIGINT AUTO_INCREMENT PRIMARY KEY,
  product_id          BIGINT NOT NULL UNIQUE,
  quantity_in_stock   INT    NOT NULL DEFAULT 0,
  low_stock_threshold INT    NOT NULL DEFAULT 5,
  last_updated        DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  CHECK (quantity_in_stock >= 0),
  CHECK (low_stock_threshold >= 0)
) ENGINE=InnoDB;

-- Every stock change: who made it, why, and the old and new quantity.
CREATE TABLE inventory_log (
  log_id       BIGINT AUTO_INCREMENT PRIMARY KEY,
  product_id   BIGINT NOT NULL,
  changed_by   BIGINT NULL,
  order_id     BIGINT NULL,
  change_qty   INT    NOT NULL,
  old_quantity INT    NOT NULL,
  new_quantity INT    NOT NULL,
  reason       VARCHAR(255) NOT NULL,
  created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  FOREIGN KEY (changed_by) REFERENCES users(user_id),
  CHECK (old_quantity >= 0),
  CHECK (new_quantity >= 0),
  CHECK (change_qty = new_quantity - old_quantity),
  INDEX inventory_log_product (product_id, log_id)
) ENGINE=InnoDB;

-- Each delivery manifest a manager applied (by its manifest ID), so none is applied twice.
CREATE TABLE delivery_manifests (
  manifest_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  supplier_manifest_id VARCHAR(64) NOT NULL UNIQUE,
  filename     VARCHAR(255) NOT NULL,
  applied_by   BIGINT       NOT NULL,
  line_count   INT          NOT NULL,
  total_units  INT          NOT NULL,
  applied_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (applied_by) REFERENCES users(user_id),
  CHECK (line_count > 0),
  CHECK (total_units > 0)
) ENGINE=InnoDB;

-- One open cart per customer.
CREATE TABLE carts (
  cart_id    BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id    BIGINT NOT NULL UNIQUE,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- The products and quantities in a cart.
CREATE TABLE cart_items (
  cart_item_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  cart_id      BIGINT NOT NULL,
  product_id   BIGINT NOT NULL,
  quantity     INT    NOT NULL,
  UNIQUE (cart_id, product_id),
  FOREIGN KEY (cart_id)    REFERENCES carts(cart_id) ON DELETE CASCADE,
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  CHECK (quantity > 0)
) ENGINE=InnoDB;

-- Placed orders; the idempotency key stops a double-click making two.
CREATE TABLE orders (
  order_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_number       VARCHAR(20)   NOT NULL UNIQUE,
  user_id            BIGINT        NOT NULL,
  address_id         BIGINT        NOT NULL,
  status             ENUM('placed','awaiting_delivery','assigned_to_trip',
                          'out_for_delivery','delivered') NOT NULL DEFAULT 'placed',
  subtotal           DECIMAL(10,2) NOT NULL,
  tax                DECIMAL(10,2) NOT NULL,
  delivery_fee       DECIMAL(10,2) NOT NULL,
  total_weight_lb    DECIMAL(8,2)  NOT NULL,
  grand_total        DECIMAL(10,2) NOT NULL,
  idempotency_key    VARCHAR(64)   NOT NULL,
  unscheduled_reason VARCHAR(255)  NULL,
  placed_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  delivered_at       DATETIME NULL,
  UNIQUE (user_id, idempotency_key),
  FOREIGN KEY (user_id)    REFERENCES users(user_id),
  FOREIGN KEY (address_id) REFERENCES addresses(address_id),
  CHECK (total_weight_lb > 0)
) ENGINE=InnoDB;

-- What was bought, with name, price and weight copied at purchase time.
CREATE TABLE order_items (
  order_item_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id       BIGINT        NOT NULL,
  product_id     BIGINT        NOT NULL,
  product_name   VARCHAR(160)  NOT NULL,
  quantity       INT           NOT NULL,
  unit_price     DECIMAL(10,2) NOT NULL,
  unit_weight_lb DECIMAL(8,2)  NOT NULL,
  FOREIGN KEY (order_id)   REFERENCES orders(order_id),
  FOREIGN KEY (product_id) REFERENCES products(product_id),
  CHECK (quantity > 0)
) ENGINE=InnoDB;

-- Every order status change, with who or what made it.
CREATE TABLE order_status_history (
  history_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id    BIGINT NOT NULL,
  from_status VARCHAR(30) NULL,
  to_status   VARCHAR(30) NOT NULL,
  changed_by  BIGINT NULL,
  source      VARCHAR(30) NOT NULL,
  changed_at  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (order_id)   REFERENCES orders(order_id),
  FOREIGN KEY (changed_by) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- Every payment attempt, including declines; only the last four card digits are kept.
CREATE TABLE payments (
  transaction_id  BIGINT AUTO_INCREMENT PRIMARY KEY,
  order_id        BIGINT        NULL,
  user_id         BIGINT        NOT NULL,
  idempotency_key VARCHAR(64)   NOT NULL,
  amount          DECIMAL(10,2) NOT NULL,
  status          ENUM('approved','declined','refunded') NOT NULL,
  gateway_ref     VARCHAR(100)  NULL,
  card_last4      CHAR(4)       NULL,
  failure_reason  VARCHAR(255)  NULL,
  created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (order_id) REFERENCES orders(order_id),
  FOREIGN KEY (user_id)  REFERENCES users(user_id)
) ENGINE=InnoDB;

-- Delivery vehicles with their order and weight limits.
CREATE TABLE vehicles (
  vehicle_id     BIGINT AUTO_INCREMENT PRIMARY KEY,
  name           VARCHAR(60)  NOT NULL,
  max_orders     INT          NOT NULL DEFAULT 10,
  max_weight_lb  DECIMAL(8,2) NOT NULL DEFAULT 200.00,
  status         ENUM('available','on_trip','maintenance') NOT NULL DEFAULT 'available',
  api_token_hash CHAR(64)     NOT NULL,
  CHECK (max_orders > 0),
  CHECK (max_weight_lb > 0)
) ENGINE=InnoDB;

-- Delivery trips with their planned route and the vehicle's progress.
CREATE TABLE delivery_trips (
  trip_id          BIGINT AUTO_INCREMENT PRIMARY KEY,
  vehicle_id       BIGINT NOT NULL,
  status           ENUM('planned','out_for_delivery','completed') NOT NULL DEFAULT 'planned',
  route_json       JSON   NULL,
  route_planned_at DATETIME NULL,
  created_by       BIGINT NOT NULL,
  created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  started_at       DATETIME NULL,
  completed_at     DATETIME NULL,
  last_report      VARCHAR(30)  NULL,
  last_latitude    DECIMAL(9,6) NULL,
  last_longitude   DECIMAL(9,6) NULL,
  last_report_at   DATETIME     NULL,
  FOREIGN KEY (vehicle_id) REFERENCES vehicles(vehicle_id),
  FOREIGN KEY (created_by) REFERENCES users(user_id)
) ENGINE=InnoDB;

-- The orders on each trip, in stop order.
CREATE TABLE trip_orders (
  trip_order_id BIGINT AUTO_INCREMENT PRIMARY KEY,
  trip_id       BIGINT NOT NULL,
  order_id      BIGINT NOT NULL UNIQUE,
  stop_sequence INT      NULL,
  est_arrival   DATETIME NULL,
  delivered_at  DATETIME NULL,
  FOREIGN KEY (trip_id)  REFERENCES delivery_trips(trip_id),
  FOREIGN KEY (order_id) REFERENCES orders(order_id)
) ENGINE=InnoDB;

-- Demo logins: customer@ofs.test, employee@ofs.test and manager@ofs.test (passwords are in the README).
INSERT INTO users (user_id, email, password_hash, full_name, role) VALUES
  (1, 'customer@ofs.test', 'pbkdf2:sha256:600000$A89dOBMaIoqn1TRA$dfac825b86049c04bcc869c50025884f64dd70dfb1adb7d95c5e58b929ba05a4', 'Anna Rivera', 'customer'),
  (2, 'employee@ofs.test', 'pbkdf2:sha256:600000$mJ0K2YIlUHEYcTcR$e8de9fc08523d7265d2f9f3808c0563f6a03a2bbb7105018990f4d14f5b10816', 'Eli Park', 'employee'),
  (3, 'manager@ofs.test',  'pbkdf2:sha256:600000$Iidtsz7etOED4BxC$4d4242f4e1ab2465a8b146fce78255583eaf318e9b9fad1b5eaf462143681723', 'Maya Chen', 'manager');

-- The demo customer's delivery address.
INSERT INTO addresses (user_id, street, city, state, zip_code, latitude, longitude) VALUES
  (1, '1 Washington Sq', 'San Jose', 'CA', '95192', 37.335200, -121.881100);

-- Two simulated delivery vehicles (development tokens).
INSERT INTO vehicles (name, max_orders, max_weight_lb, api_token_hash) VALUES
  ('Robot 1', 10, 200.00, SHA2('dev-vehicle-token-1', 256)),
  ('Robot 2', 10, 200.00, SHA2('dev-vehicle-token-2', 256));

-- The 39 products the shop starts with.
INSERT INTO products (product_id, name, description, category, price, unit_weight_lb, image_key) VALUES
  (1, 'Organic Apples, 3 lb bag', 'Crisp, sweet organic apples, perfect for snacking or baking.', 'Fruits', 6.49, 3.00, 'apple'),
  (2, 'Organic Bananas, bunch', 'A bunch of ripe organic bananas, about five to six per bunch.', 'Fruits', 2.49, 2.00, 'banana'),
  (3, 'Organic Broccoli Crown', 'Fresh organic broccoli crown, ideal for steaming or roasting.', 'Vegetables', 2.99, 1.00, 'broccoli'),
  (4, 'Organic Eggs, dozen', 'One dozen organic free-range eggs.', 'Dairy & Eggs', 5.99, 1.50, 'egg'),
  (5, 'Organic Honey, 12 oz jar', 'Raw organic honey in a 12 oz glass jar.', 'Pantry', 8.99, 0.75, 'honey'),
  (6, 'Organic Lettuce, head', 'A crisp head of organic lettuce for salads and sandwiches.', 'Vegetables', 2.49, 1.00, 'lettuce'),
  (7, 'Organic Mango (each)', 'A ripe, juicy organic mango.', 'Fruits', 1.79, 0.75, 'mango'),
  (8, 'Organic Oranges, 4 lb bag', 'Sweet organic navel oranges in a 4 lb bag.', 'Fruits', 6.99, 4.00, 'orange'),
  (9, 'Organic Peaches, 2 lb', 'Fresh organic peaches, sold by the 2 lb pack.', 'Fruits', 5.49, 2.00, 'peaches'),
  (10, 'Organic Pineapple (each)', 'A whole organic pineapple.', 'Fruits', 4.49, 3.00, 'pineapple'),
  (11, 'Organic Red Bell Pepper (each)', 'A sweet organic red bell pepper.', 'Vegetables', 1.79, 0.50, 'redBellPepper'),
  (12, 'Organic Red Onions, 2 lb bag', 'Organic red onions in a 2 lb bag.', 'Vegetables', 3.29, 2.00, 'redOnion'),
  (13, 'Organic String Beans, 1 lb', 'Tender organic string beans, sold by the pound.', 'Vegetables', 3.99, 1.00, 'stringBeans'),
  (14, 'Organic Tomatoes, 1 lb', 'Vine-ripened organic tomatoes, sold by the pound.', 'Vegetables', 3.49, 1.00, 'tomato'),
  (15, 'Organic Almonds, 1 lb', 'Raw organic almonds, a crunchy source of protein for snacking and baking.', 'Pantry', 9.99, 1.00, 'almonds'),
  (16, 'Organic Avocados, 2 lb bag', 'Creamy organic Hass avocados, ready for toast, salads and guacamole.', 'Fruits', 5.99, 2.00, 'avocado'),
  (17, 'Organic Blueberries, 1 lb', 'Plump, sweet organic blueberries, great for breakfast and baking.', 'Fruits', 6.99, 1.00, 'blueberries'),
  (18, 'Organic Butter, 1 lb', 'Rich organic butter made from pasture-raised cream.', 'Dairy & Eggs', 6.49, 1.00, 'butter'),
  (19, 'Organic Carrots, 2 lb bag', 'Sweet, crunchy organic carrots, perfect raw or roasted.', 'Vegetables', 2.58, 2.00, 'carrot'),
  (20, 'Organic Cherries, 1 lb', 'Dark, juicy organic cherries picked at peak sweetness.', 'Fruits', 7.99, 1.00, 'cherries'),
  (21, 'Organic Sweet Corn, 4 ears', 'Tender organic sweet corn on the cob, ideal for grilling or boiling.', 'Vegetables', 4.99, 3.00, 'corn'),
  (22, 'Organic Cucumbers, 2 count', 'Crisp, refreshing organic cucumbers for salads and snacking.', 'Vegetables', 2.99, 1.50, 'cucumber'),
  (23, 'Organic Garlic, 0.5 lb', 'Fresh organic garlic bulbs with a bold, aromatic flavor.', 'Vegetables', 3.49, 0.50, 'garlic'),
  (24, 'Organic Grape Juice, 64 fl oz', '100% organic grape juice, no sugar added.', 'Beverages', 6.99, 4.50, 'grapeJuice'),
  (25, 'Organic Grapes, 2 lb', 'Sweet, seedless organic grapes sold by the bunch.', 'Fruits', 7.98, 2.00, 'grapes'),
  (26, 'Aged Italian Parmesan Cheese, 1 lb', 'Aged Italian hard cheese with a rich, nutty flavor for grating or shaving.', 'Dairy & Eggs', 6.79, 1.00, 'italianCheese'),
  (27, 'Italian Salame, 1 lb', 'Dry-cured Italian salame, sliced thin for sandwiches and charcuterie boards.', 'Meat & Deli', 12.99, 1.00, 'italianSalame'),
  (28, 'Organic Lemons, 2 lb bag', 'Bright, juicy organic lemons for cooking, baking and drinks.', 'Fruits', 3.99, 2.00, 'lemon'),
  (29, 'Organic Whole Milk, 1 gallon', 'Fresh organic whole milk from grass-fed cows.', 'Dairy & Eggs', 7.49, 8.60, 'milk'),
  (30, 'Fresh Mozzarella Cheese, 1 lb', 'Soft, milky mozzarella, perfect for pizza, caprese and pasta.', 'Dairy & Eggs', 6.99, 1.00, 'mozzarellaCheese'),
  (31, 'Organic Extra Virgin Olive Oil, 16 fl oz', 'Cold-pressed organic extra virgin olive oil with a smooth, fruity taste.', 'Pantry', 7.94, 1.25, 'oliveOil'),
  (32, 'Organic Orange Juice, 52 fl oz', 'Pulp-free organic orange juice, pressed from ripe oranges.', 'Beverages', 8.39, 3.50, 'orangeJuice'),
  (33, 'Organic Passion Fruit Juice, 32 fl oz', 'Tangy, tropical organic passion fruit juice.', 'Beverages', 5.99, 2.25, 'passionfruitJuice'),
  (34, 'Organic Pickles, 24 oz jar', 'All-natural organic pickles with no preservatives.', 'Pantry', 5.49, 2.00, 'pickles'),
  (35, 'Organic Potatoes, 5 lb bag', 'Versatile organic potatoes for baking, mashing and roasting.', 'Vegetables', 6.99, 5.00, 'potato'),
  (36, 'Organic Raspberries, 1 lb', 'Delicate, tart-sweet organic raspberries.', 'Fruits', 7.99, 1.00, 'raspberries'),
  (37, 'Organic Strawberries, 1 lb', 'Sweet, ripe organic strawberries picked fresh.', 'Fruits', 4.49, 1.00, 'strawberries'),
  (38, 'Organic Walnuts, 1 lb', 'Shelled organic walnut halves, rich and earthy for baking and salads.', 'Pantry', 9.49, 1.00, 'walnuts'),
  (39, 'Organic Watermelon, 5 lb', 'Sweet, juicy organic watermelon for hot days.', 'Fruits', 5.99, 5.00, 'watermelon');

-- Starting stock for each product.
INSERT INTO inventory (product_id, quantity_in_stock, low_stock_threshold) VALUES
  (1, 40, 5),
  (2, 60, 5),
  (3, 35, 5),
  (4, 30, 5),
  (5, 6, 5),
  (6, 45, 5),
  (7, 50, 5),
  (8, 25, 5),
  (9, 0, 5),
  (10, 20, 5),
  (11, 55, 5),
  (12, 38, 5),
  (13, 32, 5),
  (14, 42, 5),
  (15, 45, 5),
  (16, 30, 5),
  (17, 28, 5),
  (18, 35, 5),
  (19, 50, 5),
  (20, 22, 5),
  (21, 34, 5),
  (22, 40, 5),
  (23, 55, 5),
  (24, 26, 5),
  (25, 32, 5),
  (26, 18, 5),
  (27, 15, 5),
  (28, 44, 5),
  (29, 24, 5),
  (30, 20, 5),
  (31, 30, 5),
  (32, 27, 5),
  (33, 16, 5),
  (34, 29, 5),
  (35, 36, 5),
  (36, 0, 5),
  (37, 41, 5),
  (38, 33, 5),
  (39, 12, 5);

-- @@END_TABLES@@

-- Checks that the data loaded.
SELECT 'Products loaded:' AS check_name, COUNT(*) AS result FROM products;
SELECT 'Users loaded:'    AS check_name, COUNT(*) AS result FROM users;
SELECT 'MySQL version:'   AS check_name, VERSION() AS result;
