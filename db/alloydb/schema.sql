-- =============================================================================
-- Google Cloud AlloyDB (PostgreSQL Engine) — Nexora Core Enterprise ERP Schema
-- =============================================================================

-- 1. CUSTOMER MASTER
CREATE TABLE IF NOT EXISTS customers (
    customer_id BIGINT PRIMARY KEY,
    account_number VARCHAR(50),
    person_id BIGINT,
    store_id BIGINT,
    territory_id INTEGER,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    adventureworks_customer_id BIGINT,
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_addresses (
    address_id BIGINT PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(customer_id),
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(30) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_contacts (
    contact_id SERIAL PRIMARY KEY,
    customer_id BIGINT REFERENCES customers(customer_id),
    first_name VARCHAR(100) NOT NULL,
    middle_name VARCHAR(100),
    last_name VARCHAR(100) NOT NULL,
    title VARCHAR(20),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 2. PRODUCT MASTER
CREATE TABLE IF NOT EXISTS product_categories (
    category_id INT PRIMARY KEY,
    category_name VARCHAR(100) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_subcategories (
    subcategory_id INT PRIMARY KEY,
    category_id INT REFERENCES product_categories(category_id),
    subcategory_name VARCHAR(100) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS products (
    product_id BIGINT PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    product_number VARCHAR(50) NOT NULL,
    color VARCHAR(30),
    standard_cost NUMERIC(15, 2),
    list_price NUMERIC(15, 2),
    subcategory_id INT REFERENCES product_subcategories(subcategory_id),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS product_prices (
    product_id BIGINT PRIMARY KEY REFERENCES products(product_id),
    standard_cost NUMERIC(15, 2),
    list_price NUMERIC(15, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks'
);

CREATE TABLE IF NOT EXISTS product_price_history (
    history_id SERIAL PRIMARY KEY,
    product_id BIGINT REFERENCES products(product_id),
    list_price NUMERIC(15, 2) NOT NULL,
    start_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 3. SALES
CREATE TABLE IF NOT EXISTS sales_representatives (
    sales_rep_id BIGINT PRIMARY KEY,
    rep_name VARCHAR(150),
    job_title VARCHAR(100),
    source_system VARCHAR(50) DEFAULT 'adventureworks'
);

CREATE TABLE IF NOT EXISTS sales_territories (
    territory_id INT PRIMARY KEY,
    territory_name VARCHAR(100) NOT NULL,
    country_code VARCHAR(10) NOT NULL,
    group_name VARCHAR(50) NOT NULL,
    sales_ytd NUMERIC(15, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks'
);

CREATE TABLE IF NOT EXISTS sales_orders (
    sales_order_id BIGINT PRIMARY KEY,
    revision_number INT DEFAULT 1,
    order_date TIMESTAMP WITH TIME ZONE NOT NULL,
    due_date TIMESTAMP WITH TIME ZONE,
    ship_date TIMESTAMP WITH TIME ZONE,
    status INT NOT NULL,
    online_order_flag BOOLEAN DEFAULT FALSE,
    sales_order_number VARCHAR(50) NOT NULL,
    customer_id BIGINT REFERENCES customers(customer_id),
    sales_rep_id BIGINT REFERENCES sales_representatives(sales_rep_id),
    territory_id INT REFERENCES sales_territories(territory_id),
    sub_total NUMERIC(15, 2),
    tax_amt NUMERIC(15, 2),
    freight NUMERIC(15, 2),
    total_due NUMERIC(15, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_order_items (
    sales_order_item_id BIGINT PRIMARY KEY,
    sales_order_id BIGINT REFERENCES sales_orders(sales_order_id),
    carrier_tracking_number VARCHAR(50),
    order_qty INT NOT NULL,
    product_id BIGINT REFERENCES products(product_id),
    unit_price NUMERIC(15, 2) NOT NULL,
    unit_price_discount NUMERIC(5, 4) DEFAULT 0.0,
    line_total NUMERIC(15, 2) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sales_order_status_history (
    history_id SERIAL PRIMARY KEY,
    sales_order_id BIGINT REFERENCES sales_orders(sales_order_id),
    status INT NOT NULL,
    changed_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 4. RETURNS (STRUCTURAL / NO APPROVED SOURCE)
CREATE TABLE IF NOT EXISTS returns (
    return_id BIGINT PRIMARY KEY,
    sales_order_id BIGINT REFERENCES sales_orders(sales_order_id),
    return_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    reason TEXT,
    source_status VARCHAR(100) DEFAULT 'STRUCTURAL / NO APPROVED SOURCE'
);

CREATE TABLE IF NOT EXISTS return_items (
    return_item_id BIGINT PRIMARY KEY,
    return_id BIGINT REFERENCES returns(return_id),
    product_id BIGINT REFERENCES products(product_id),
    quantity INT NOT NULL,
    source_status VARCHAR(100) DEFAULT 'STRUCTURAL / NO APPROVED SOURCE'
);

-- 5. MARKETPLACE ERP (Olist Marketplace Engine)
CREATE TABLE IF NOT EXISTS marketplace_customers (
    customer_id VARCHAR(100) PRIMARY KEY,
    customer_unique_id VARCHAR(100) NOT NULL,
    zip_code_prefix INT,
    city VARCHAR(100),
    state VARCHAR(10),
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_products (
    product_id VARCHAR(100) PRIMARY KEY,
    product_category_name VARCHAR(100),
    photos_qty INT,
    weight_g INT,
    length_cm INT,
    height_cm INT,
    width_cm INT,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_orders (
    order_id VARCHAR(100) PRIMARY KEY,
    customer_id VARCHAR(100) REFERENCES marketplace_customers(customer_id),
    order_status VARCHAR(50) NOT NULL,
    purchase_timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    approved_at TIMESTAMP WITH TIME ZONE,
    delivered_carrier_date TIMESTAMP WITH TIME ZONE,
    delivered_customer_date TIMESTAMP WITH TIME ZONE,
    estimated_delivery_date TIMESTAMP WITH TIME ZONE,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    load_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS marketplace_order_items (
    order_id VARCHAR(100) REFERENCES marketplace_orders(order_id),
    order_item_id INT NOT NULL,
    product_id VARCHAR(100) REFERENCES marketplace_products(product_id),
    seller_id VARCHAR(100) NOT NULL,
    shipping_limit_date TIMESTAMP WITH TIME ZONE,
    price NUMERIC(15, 2) NOT NULL,
    freight_value NUMERIC(15, 2) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    PRIMARY KEY (order_id, order_item_id)
);

CREATE TABLE IF NOT EXISTS marketplace_payments (
    order_id VARCHAR(100) REFERENCES marketplace_orders(order_id),
    payment_sequential INT NOT NULL,
    payment_type VARCHAR(50) NOT NULL,
    payment_installments INT DEFAULT 1,
    payment_value NUMERIC(15, 2) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    PRIMARY KEY (order_id, payment_sequential)
);

CREATE TABLE IF NOT EXISTS marketplace_reviews (
    review_id VARCHAR(100) PRIMARY KEY,
    order_id VARCHAR(100) REFERENCES marketplace_orders(order_id),
    review_score INT NOT NULL,
    review_title TEXT,
    review_message TEXT,
    creation_date TIMESTAMP WITH TIME ZONE,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace'
);

CREATE TABLE IF NOT EXISTS product_category_translation (
    product_category_name VARCHAR(100) PRIMARY KEY,
    product_category_name_english VARCHAR(100) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'olist_marketplace'
);
