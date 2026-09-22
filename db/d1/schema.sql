-- =============================================================================
-- Cloudflare D1 (SQLite Engine) — Nexora Application-Facing Operational Schema
-- =============================================================================

PRAGMA foreign_keys = ON;

-- 1. ORGANIZATION
CREATE TABLE IF NOT EXISTS offices (
    office_id INTEGER PRIMARY KEY AUTOINCREMENT,
    office_name TEXT NOT NULL,
    city TEXT NOT NULL,
    country TEXT NOT NULL,
    timezone TEXT NOT NULL,
    synthetic_reference_data BOOLEAN DEFAULT TRUE,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS departments (
    department_id INTEGER PRIMARY KEY,
    department_name TEXT NOT NULL,
    group_name TEXT,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS employees (
    employee_id INTEGER PRIMARY KEY,
    national_id_number TEXT,
    login_id TEXT,
    job_title TEXT NOT NULL,
    birth_date TEXT,
    marital_status TEXT,
    gender TEXT,
    hire_date TEXT,
    department_id INTEGER,
    salaried_flag INTEGER DEFAULT 1,
    vacation_hours INTEGER DEFAULT 0,
    sick_leave_hours INTEGER DEFAULT 0,
    current_flag INTEGER DEFAULT 1,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS employee_department_history (
    employee_id INTEGER NOT NULL,
    department_id INTEGER NOT NULL,
    shift_id INTEGER DEFAULT 1,
    start_date TEXT NOT NULL,
    end_date TEXT,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (employee_id, department_id, start_date),
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id),
    FOREIGN KEY (department_id) REFERENCES departments(department_id)
);

CREATE TABLE IF NOT EXISTS employee_contact (
    employee_id INTEGER PRIMARY KEY,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    title TEXT,
    email_promotion INTEGER DEFAULT 0,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 2. EMPLOYEE ACTIVITY (STRUCTURAL / NO APPROVED SOURCE)
CREATE TABLE IF NOT EXISTS attendance (
    attendance_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    work_date TEXT NOT NULL,
    check_in_time TEXT,
    check_out_time TEXT,
    status TEXT,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS leave_requests (
    leave_request_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    leave_type TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    approval_status TEXT,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

CREATE TABLE IF NOT EXISTS employee_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    event_timestamp TEXT NOT NULL,
    description TEXT,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (employee_id) REFERENCES employees(employee_id)
);

-- 3. CUSTOMER / CRM
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY,
    account_number TEXT,
    person_id INTEGER,
    store_id INTEGER,
    territory_id INTEGER,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS customer_contacts (
    contact_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    middle_name TEXT,
    last_name TEXT NOT NULL,
    title TEXT,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS customer_addresses (
    address_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    address_line1 TEXT NOT NULL,
    address_line2 TEXT,
    city TEXT NOT NULL,
    postal_code TEXT NOT NULL,
    source_system TEXT DEFAULT 'adventureworks',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

CREATE TABLE IF NOT EXISTS customer_preferences (
    preference_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    communication_channel TEXT,
    opt_in_marketing INTEGER DEFAULT 0,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id)
);

-- 4. SUPPORT (STRUCTURAL / NO APPROVED SOURCE)
CREATE TABLE IF NOT EXISTS support_agents (
    agent_id INTEGER PRIMARY KEY AUTOINCREMENT,
    employee_id INTEGER,
    agent_name TEXT NOT NULL,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE'
);

CREATE TABLE IF NOT EXISTS ticket_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    category_name TEXT NOT NULL,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE'
);

CREATE TABLE IF NOT EXISTS support_tickets (
    ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    category_id INTEGER,
    agent_id INTEGER,
    subject TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (customer_id) REFERENCES customers(customer_id),
    FOREIGN KEY (category_id) REFERENCES ticket_categories(category_id),
    FOREIGN KEY (agent_id) REFERENCES support_agents(agent_id)
);

CREATE TABLE IF NOT EXISTS ticket_messages (
    message_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    sender_type TEXT NOT NULL,
    message_text TEXT NOT NULL,
    sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
);

CREATE TABLE IF NOT EXISTS ticket_status_history (
    history_id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id INTEGER NOT NULL,
    old_status TEXT,
    new_status TEXT NOT NULL,
    changed_at TEXT DEFAULT CURRENT_TIMESTAMP,
    source_status TEXT DEFAULT 'STRUCTURAL / NO APPROVED SOURCE',
    FOREIGN KEY (ticket_id) REFERENCES support_tickets(ticket_id)
);

-- 5. MARKETING APPLICATION EVENTS (Olist Marketing Funnel)
CREATE TABLE IF NOT EXISTS campaigns (
    campaign_id TEXT PRIMARY KEY,
    origin TEXT,
    landing_page_id TEXT,
    source_system TEXT DEFAULT 'olist_marketing',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS leads (
    lead_id TEXT PRIMARY KEY,
    first_contact_date TEXT,
    landing_page_id TEXT,
    origin TEXT,
    source_system TEXT DEFAULT 'olist_marketing',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id TEXT NOT NULL,
    seller_id TEXT,
    sdr_id TEXT,
    sr_id TEXT,
    won_date TEXT,
    business_segment TEXT,
    lead_type TEXT,
    business_type TEXT,
    declared_monthly_revenue REAL,
    source_system TEXT DEFAULT 'olist_marketing',
    load_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);

CREATE TABLE IF NOT EXISTS campaign_events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    campaign_id TEXT,
    lead_id TEXT,
    event_type TEXT NOT NULL,
    event_timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
    source_system TEXT DEFAULT 'olist_marketing',
    FOREIGN KEY (lead_id) REFERENCES leads(lead_id)
);
