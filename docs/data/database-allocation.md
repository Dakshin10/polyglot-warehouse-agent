# Nexora Enterprise Dataset — Database Allocation Matrix

This document maps all target tables across Cloudflare D1, Google Cloud AlloyDB, and Aiven MySQL to their respective source files, keys, transformations, and provenance settings.

---

## 1. Cloudflare D1 (SQLite) — Application-Facing Domain

| Table | Domain | Source System | Source Dataset / File | Target Database | Primary Key | Foreign Keys | Provenance Tracked | Notes / Synthetic Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `offices` | Organization | Synthetic | N/A | Cloudflare D1 | `office_id` | None | Yes | `synthetic_reference_data = TRUE` |
| `departments` | Organization | AdventureWorks | `HumanResources.Department.csv` | Cloudflare D1 | `department_id` | None | Yes | Source PK: `DepartmentID` |
| `employees` | Organization | AdventureWorks | `HumanResources.Employee.csv` | Cloudflare D1 | `employee_id` | `department_id` -> `departments(department_id)` | Yes | Source PK: `BusinessEntityID` |
| `employee_department_history` | Organization | AdventureWorks | `HumanResources.EmployeeDepartmentHistory.csv` | Cloudflare D1 | `(employee_id, department_id, start_date)` | `employee_id` -> `employees(employee_id)` | Yes | Source composite |
| `employee_contact` | Organization | AdventureWorks | `Person.Person.csv` | Cloudflare D1 | `employee_id` | `employee_id` -> `employees(employee_id)` | Yes | Filtered for employee PersonType |
| `attendance` | Activity | N/A | Unsupported | Cloudflare D1 | `attendance_id` | `employee_id` -> `employees(employee_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `leave_requests` | Activity | N/A | Unsupported | Cloudflare D1 | `leave_request_id` | `employee_id` -> `employees(employee_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `employee_events` | Activity | N/A | Unsupported | Cloudflare D1 | `event_id` | `employee_id` -> `employees(employee_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `customers` | CRM | AdventureWorks | `Sales.Customer.csv` | Cloudflare D1 | `customer_id` | None | Yes | App-facing customer profile |
| `customer_contacts` | CRM | AdventureWorks | `Person.Person.csv` | Cloudflare D1 | `contact_id` | `customer_id` -> `customers(customer_id)` | Yes | Preserves `source_customer_id` |
| `customer_addresses` | CRM | AdventureWorks | `Person.Address.csv` | Cloudflare D1 | `address_id` | `customer_id` -> `customers(customer_id)` | Yes | Preserves `source_address_id` |
| `customer_preferences` | CRM | N/A | Unsupported | Cloudflare D1 | `preference_id` | `customer_id` -> `customers(customer_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `support_agents` | Support | N/A | Unsupported | Cloudflare D1 | `agent_id` | None | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `support_tickets` | Support | N/A | Unsupported | Cloudflare D1 | `ticket_id` | `customer_id` -> `customers(customer_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `ticket_messages` | Support | N/A | Unsupported | Cloudflare D1 | `message_id` | `ticket_id` -> `support_tickets(ticket_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `ticket_categories` | Support | N/A | Unsupported | Cloudflare D1 | `category_id` | None | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `ticket_status_history` | Support | N/A | Unsupported | Cloudflare D1 | `history_id` | `ticket_id` -> `support_tickets(ticket_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `campaigns` | Marketing | Olist Marketing | `olist_marketing_qualified_leads_dataset.csv` | Cloudflare D1 | `campaign_id` | None | Yes | Source: `landing_page_id` / `origin` |
| `leads` | Marketing | Olist Marketing | `olist_marketing_qualified_leads_dataset.csv` | Cloudflare D1 | `lead_id` | None | Yes | Source PK: `mql_id` |
| `lead_events` | Marketing | Olist Marketing | `olist_closed_deals_dataset.csv` | Cloudflare D1 | `event_id` | `lead_id` -> `leads(lead_id)` | Yes | Preserves `seller_id` (FK to marketplace seller) |
| `campaign_events` | Marketing | Olist Marketing | `olist_marketing_qualified_leads_dataset.csv` | Cloudflare D1 | `event_id` | `lead_id` -> `leads(lead_id)` | Yes | Lead activity log |

---

## 2. Google Cloud AlloyDB (PostgreSQL) — Core Enterprise ERP Domain

| Table | Domain | Source System | Source Dataset / File | Target Database | Primary Key | Foreign Keys | Provenance Tracked | Notes / Synthetic Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `customers` | Customer Master | AdventureWorks | `Sales.Customer.csv` | AlloyDB | `customer_id` | None | Yes | Preserves `source_system = 'adventureworks'`, `adventureworks_customer_id` |
| `customer_addresses` | Customer Master | AdventureWorks | `Person.Address.csv` | AlloyDB | `address_id` | `customer_id` -> `customers(customer_id)` | Yes | Address master |
| `customer_contacts` | Customer Master | AdventureWorks | `Person.Person.csv` | AlloyDB | `contact_id` | `customer_id` -> `customers(customer_id)` | Yes | Contact master |
| `product_categories` | Product Master | AdventureWorks | `Production.ProductCategory.csv` | AlloyDB | `category_id` | None | Yes | Source PK: `ProductCategoryID` |
| `product_subcategories` | Product Master | AdventureWorks | `Production.ProductSubcategory.csv` | AlloyDB | `subcategory_id` | `category_id` -> `product_categories(category_id)` | Yes | Source PK: `ProductSubcategoryID` |
| `products` | Product Master | AdventureWorks | `Production.Product.csv` | AlloyDB | `product_id` | `subcategory_id` -> `product_subcategories(subcategory_id)` | Yes | Source PK: `ProductID` |
| `product_prices` | Product Master | AdventureWorks | `Production.Product.csv` | AlloyDB | `product_id` | `product_id` -> `products(product_id)` | Yes | Standard cost & list price |
| `product_price_history` | Product Master | AdventureWorks | `Production.Product.csv` | AlloyDB | `history_id` | `product_id` -> `products(product_id)` | Yes | Historical list price records |
| `sales_representatives` | Sales | AdventureWorks | `HumanResources.Employee.csv` | AlloyDB | `sales_rep_id` | None | Yes | Filtered for Sales Rep job titles |
| `sales_territories` | Sales | AdventureWorks | `Sales.SalesTerritory.csv` | AlloyDB | `territory_id` | None | Yes | Source PK: `TerritoryID` |
| `sales_orders` | Sales | AdventureWorks | `Sales.SalesOrderHeader.csv` | AlloyDB | `sales_order_id` | `customer_id` -> `customers(customer_id)`, `sales_rep_id` -> `sales_representatives(sales_rep_id)`, `territory_id` -> `sales_territories(territory_id)` | Yes | Source PK: `SalesOrderID` |
| `sales_order_items` | Sales | AdventureWorks | `Sales.SalesOrderDetail.csv` | AlloyDB | `sales_order_item_id` | `sales_order_id` -> `sales_orders(sales_order_id)`, `product_id` -> `products(product_id)` | Yes | Source PK: `SalesOrderDetailID` |
| `sales_order_status_history` | Sales | AdventureWorks | `Sales.SalesOrderHeader.csv` | AlloyDB | `history_id` | `sales_order_id` -> `sales_orders(sales_order_id)` | Yes | Status tracking |
| `returns` | Returns | N/A | Unsupported | AlloyDB | `return_id` | `sales_order_id` -> `sales_orders(sales_order_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `return_items` | Returns | N/A | Unsupported | AlloyDB | `return_item_id` | `return_id` -> `returns(return_id)` | Yes | `STATUS = STRUCTURAL / NO APPROVED SOURCE` |
| `marketplace_orders` | Marketplace ERP | Olist | `olist_orders_dataset.csv` | AlloyDB | `order_id` | `customer_id` -> `marketplace_customers(customer_id)` | Yes | `source_system = 'olist_marketplace'` |
| `marketplace_customers` | Marketplace ERP | Olist | `olist_customers_dataset.csv` | AlloyDB | `customer_id` | None | Yes | Preserves both `customer_id` and `customer_unique_id` |
| `marketplace_order_items` | Marketplace ERP | Olist | `olist_order_items_dataset.csv` | AlloyDB | `(order_id, order_item_id)` | `order_id` -> `marketplace_orders(order_id)`, `product_id` -> `marketplace_products(product_id)` | Yes | Preserves `seller_id` |
| `marketplace_payments` | Marketplace ERP | Olist | `olist_order_payments_dataset.csv` | AlloyDB | `(order_id, payment_sequential)` | `order_id` -> `marketplace_orders(order_id)` | Yes | Olist payment sequential |
| `marketplace_reviews` | Marketplace ERP | Olist | `olist_order_reviews_dataset.csv` | AlloyDB | `review_id` | `order_id` -> `marketplace_orders(order_id)` | Yes | Olist review ratings |
| `marketplace_products` | Marketplace ERP | Olist | `olist_products_dataset.csv` | AlloyDB | `product_id` | None | Yes | Olist product catalog |

---

## 3. Aiven MySQL — Operations / Supply Chain Domain

| Table | Domain | Source System | Source Dataset / File | Target Database | Primary Key | Foreign Keys | Provenance Tracked | Notes / Synthetic Status |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `suppliers` | Suppliers | AdventureWorks | `Purchasing.Vendor.csv` | Aiven MySQL | `supplier_id` | None | Yes | Source PK: `BusinessEntityID` |
| `supplier_contacts` | Suppliers | AdventureWorks | `Person.Person.csv` | Aiven MySQL | `contact_id` | `supplier_id` -> `suppliers(supplier_id)` | Yes | Vendor contacts |
| `supplier_addresses` | Suppliers | AdventureWorks | `Person.Address.csv` | Aiven MySQL | `address_id` | `supplier_id` -> `suppliers(supplier_id)` | Yes | Vendor addresses |
| `supplier_products` | Suppliers | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `(supplier_id, product_id)` | `supplier_id` -> `suppliers(supplier_id)` | Yes | Vendor catalog map |
| `supplier_performance` | Suppliers | AdventureWorks | `Purchasing.Vendor.csv` | Aiven MySQL | `performance_id` | `supplier_id` -> `suppliers(supplier_id)` | Yes | Credit rating & status |
| `purchase_orders` | Procurement | AdventureWorks | `Purchasing.PurchaseOrderHeader.csv` | Aiven MySQL | `purchase_order_id` | `supplier_id` -> `suppliers(supplier_id)` | Yes | Source PK: `PurchaseOrderID` |
| `purchase_order_items` | Procurement | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `purchase_order_item_id` | `purchase_order_id` -> `purchase_orders(purchase_order_id)` | Yes | Source PK: `PurchaseOrderDetailID` |
| `purchase_order_status_history` | Procurement | AdventureWorks | `Purchasing.PurchaseOrderHeader.csv` | Aiven MySQL | `history_id` | `purchase_order_id` -> `purchase_orders(purchase_order_id)` | Yes | PO status history |
| `goods_receipts` | Procurement | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `receipt_id` | `purchase_order_id` -> `purchase_orders(purchase_order_id)` | Yes | Received & rejected Qty |
| `goods_receipt_items` | Procurement | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `receipt_item_id` | `receipt_id` -> `goods_receipts(receipt_id)` | Yes | Line-level receipts |
| `warehouses` | Warehouses | Synthetic | N/A | Aiven MySQL | `warehouse_id` | None | Yes | `synthetic_reference_data = TRUE` |
| `warehouse_locations` | Warehouses | Synthetic | N/A | Aiven MySQL | `location_id` | `warehouse_id` -> `warehouses(warehouse_id)` | Yes | `synthetic_reference_data = TRUE` |
| `inventory` | Inventory | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `inventory_id` | `warehouse_id` -> `warehouses(warehouse_id)` | Yes | Stocked quantities |
| `inventory_movements` | Inventory | AdventureWorks | `Purchasing.PurchaseOrderDetail.csv` | Aiven MySQL | `movement_id` | `inventory_id` -> `inventory(inventory_id)` | Yes | Inventory movements |
| `shipments` | Logistics | AdventureWorks | `Sales.SalesOrderHeader.csv` | Aiven MySQL | `shipment_id` | None | Yes | Shipping tracking |
| `shipment_items` | Logistics | AdventureWorks | `Sales.SalesOrderDetail.csv` | Aiven MySQL | `shipment_item_id` | `shipment_id` -> `shipments(shipment_id)` | Yes | Carrier details |
| `shipping_providers` | Logistics | AdventureWorks | `Sales.SalesOrderDetail.csv` | Aiven MySQL | `provider_id` | None | Yes | Carrier providers |
| `marketplace_sellers` | Marketplace Logistics | Olist | `olist_sellers_dataset.csv` | Aiven MySQL | `seller_id` | None | Yes | Olist marketplace sellers |
| `geolocation` | Marketplace Logistics | Olist | `olist_geolocation_dataset.csv` | Aiven MySQL | `(geolocation_zip_code_prefix, geolocation_lat, geolocation_lng)` | None | Yes | Geolocation reference |
