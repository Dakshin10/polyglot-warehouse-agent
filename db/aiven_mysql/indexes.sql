-- Aiven MySQL Indexes
CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_poi_po ON purchase_order_items(purchase_order_id);
CREATE INDEX IF NOT EXISTS idx_poi_product ON purchase_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_inventory_wh ON inventory(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_inventory_prod ON inventory(product_id);
CREATE INDEX IF NOT EXISTS idx_geo_zip ON geolocation(zip_code_prefix);
