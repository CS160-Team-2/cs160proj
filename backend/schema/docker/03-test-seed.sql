USE ofs;

INSERT INTO products
    (product_id, name, description, category, price, unit_weight_lb, image_key, is_listed)
VALUES
    (9001, 'T03 Boundary 19.99 lb', 'T-03 test item near 20 lb limit', 'Test', 1.00, 19.99, NULL, TRUE),
    (9002, 'T03 Boundary 20.00 lb', 'T-03 test item at 20 lb limit', 'Test', 1.00, 20.00, NULL, TRUE),
    (9003, 'T03 Boundary 20.01 lb', 'T-03 test item above 20 lb limit', 'Test', 1.00, 20.01, NULL, TRUE),
    (9004, 'T03 Boundary 199.99 lb', 'T-03 test item near 200 lb limit', 'Test', 1.00, 199.99, NULL, TRUE),
    (9005, 'T03 Boundary 200.00 lb', 'T-03 test item at 200 lb limit', 'Test', 1.00, 200.00, NULL, TRUE),
    (9006, 'T03 Boundary 200.01 lb', 'T-03 test item above 200 lb limit', 'Test', 1.00, 200.01, NULL, TRUE)
ON DUPLICATE KEY UPDATE
    name = VALUES(name),
    description = VALUES(description),
    category = VALUES(category),
    price = VALUES(price),
    unit_weight_lb = VALUES(unit_weight_lb),
    image_key = VALUES(image_key),
    is_listed = VALUES(is_listed);

INSERT INTO inventory (product_id, quantity_in_stock, low_stock_threshold)
VALUES
    (9001, 100, 5),
    (9002, 100, 5),
    (9003, 100, 5),
    (9004, 100, 5),
    (9005, 100, 5),
    (9006, 100, 5)
ON DUPLICATE KEY UPDATE
    quantity_in_stock = VALUES(quantity_in_stock),
    low_stock_threshold = VALUES(low_stock_threshold);
