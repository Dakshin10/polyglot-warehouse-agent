-- =============================================================================
-- Aiven MySQL — Nexora Operational Supply Chain Schema
-- =============================================================================

-- 1. SUPPLIERS
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id BIGINT PRIMARY KEY,
    account_number VARCHAR(50),
    supplier_name VARCHAR(255) NOT NULL,
    credit_rating INT,
    preferred_vendor_status TINYINT DEFAULT 1,
    active_flag TINYINT DEFAULT 1,
    purchasing_web_url VARCHAR(255),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_contacts (
    contact_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    title VARCHAR(20),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_addresses (
    address_id BIGINT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    address_line1 VARCHAR(255) NOT NULL,
    address_line2 VARCHAR(255),
    city VARCHAR(100) NOT NULL,
    postal_code VARCHAR(30) NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_products (
    supplier_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    standard_price DECIMAL(15, 2),
    last_receipt_cost DECIMAL(15, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    PRIMARY KEY (supplier_id, product_id),
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS supplier_performance (
    performance_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    supplier_id BIGINT NOT NULL,
    on_time_delivery_pct DECIMAL(5, 2),
    quality_rating DECIMAL(5, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. PROCUREMENT
CREATE TABLE IF NOT EXISTS purchase_orders (
    purchase_order_id BIGINT PRIMARY KEY,
    revision_number INT DEFAULT 1,
    status INT NOT NULL,
    employee_id BIGINT,
    supplier_id BIGINT NOT NULL,
    ship_method_id INT DEFAULT 1,
    order_date DATETIME NOT NULL,
    ship_date DATETIME,
    sub_total DECIMAL(15, 2),
    tax_amt DECIMAL(15, 2),
    freight DECIMAL(15, 2),
    total_due DECIMAL(15, 2),
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (supplier_id) REFERENCES suppliers(supplier_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS purchase_order_items (
    purchase_order_item_id BIGINT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    due_date DATETIME,
    order_qty INT NOT NULL,
    product_id BIGINT NOT NULL,
    unit_price DECIMAL(15, 2) NOT NULL,
    line_total DECIMAL(15, 2) NOT NULL,
    received_qty DECIMAL(15, 2) DEFAULT 0.0,
    rejected_qty DECIMAL(15, 2) DEFAULT 0.0,
    stocked_qty DECIMAL(15, 2) DEFAULT 0.0,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(purchase_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS purchase_order_status_history (
    history_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    status INT NOT NULL,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(purchase_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS goods_receipts (
    receipt_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    purchase_order_id BIGINT NOT NULL,
    receipt_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(purchase_order_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS goods_receipt_items (
    receipt_item_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    receipt_id BIGINT NOT NULL,
    purchase_order_item_id BIGINT NOT NULL,
    received_qty DECIMAL(15, 2) NOT NULL,
    rejected_qty DECIMAL(15, 2) DEFAULT 0.0,
    FOREIGN KEY (receipt_id) REFERENCES goods_receipts(receipt_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. WAREHOUSES & INVENTORY
CREATE TABLE IF NOT EXISTS warehouses (
    warehouse_id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_name VARCHAR(100) NOT NULL,
    location_city VARCHAR(100) NOT NULL,
    synthetic_reference_data TINYINT DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS warehouse_locations (
    location_id INT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id INT NOT NULL,
    zone_name VARCHAR(50),
    bin_number VARCHAR(50),
    synthetic_reference_data TINYINT DEFAULT 1,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS inventory (
    inventory_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    warehouse_id INT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity_on_hand INT NOT NULL,
    source_system VARCHAR(50) DEFAULT 'adventureworks',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (warehouse_id) REFERENCES warehouses(warehouse_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS inventory_movements (
    movement_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    inventory_id BIGINT NOT NULL,
    movement_type VARCHAR(50) NOT NULL,
    quantity INT NOT NULL,
    movement_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_id) REFERENCES inventory(inventory_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. LOGISTICS & MARKETPLACE SELLERS
CREATE TABLE IF NOT EXISTS shipping_providers (
    provider_id INT AUTO_INCREMENT PRIMARY KEY,
    provider_name VARCHAR(100) NOT NULL,
    active_flag TINYINT DEFAULT 1
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS shipments (
    shipment_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    purchase_order_id BIGINT,
    provider_id INT,
    ship_date DATETIME,
    status VARCHAR(50),
    FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(purchase_order_id),
    FOREIGN KEY (provider_id) REFERENCES shipping_providers(provider_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS shipment_items (
    shipment_item_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    shipment_id BIGINT NOT NULL,
    product_id BIGINT NOT NULL,
    quantity INT NOT NULL,
    FOREIGN KEY (shipment_id) REFERENCES shipments(shipment_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS marketplace_sellers (
    seller_id VARCHAR(100) PRIMARY KEY,
    seller_zip_code_prefix INT,
    seller_city VARCHAR(100),
    seller_state VARCHAR(10),
    source_system VARCHAR(50) DEFAULT 'olist_marketplace',
    load_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS geolocation (
    geolocation_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    zip_code_prefix INT NOT NULL,
    lat DECIMAL(10, 8),
    lng DECIMAL(11, 8),
    city VARCHAR(100),
    state VARCHAR(10),
    source_system VARCHAR(50) DEFAULT 'olist_marketplace'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
