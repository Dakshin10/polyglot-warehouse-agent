-- AlloyDB PostgreSQL Indexes
CREATE INDEX IF NOT EXISTS idx_products_subcat ON products(subcategory_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_cust ON sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_rep ON sales_orders(sales_rep_id);
CREATE INDEX IF NOT EXISTS idx_sales_orders_terr ON sales_orders(territory_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_items_so ON sales_order_items(sales_order_id);
CREATE INDEX IF NOT EXISTS idx_sales_order_items_prod ON sales_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_mkt_orders_cust ON marketplace_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_mkt_items_order ON marketplace_order_items(order_id);
CREATE INDEX IF NOT EXISTS idx_mkt_items_prod ON marketplace_order_items(product_id);
CREATE INDEX IF NOT EXISTS idx_mkt_items_seller ON marketplace_order_items(seller_id);
