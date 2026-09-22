-- Cloudflare D1 Indexes
CREATE INDEX IF NOT EXISTS idx_employees_dept ON employees(department_id);
CREATE INDEX IF NOT EXISTS idx_cust_contacts_cust ON customer_contacts(customer_id);
CREATE INDEX IF NOT EXISTS idx_cust_addrs_cust ON customer_addresses(customer_id);
CREATE INDEX IF NOT EXISTS idx_tickets_cust ON support_tickets(customer_id);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_lead_events_seller ON lead_events(seller_id);
