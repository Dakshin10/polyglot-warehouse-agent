-- =============================================================================
-- Enterprise Curated Views — Nexora Technologies
--
-- Source: raw_adventureworks.* (ingested from AdventureWorks 2022)
-- Target: curated_enterprise.*
--
-- Provenance chain:
--   AdventureWorks Kaggle source
--     → raw_adventureworks.* (raw layer, source semantics preserved)
--     → curated_enterprise.* (canonical enterprise model, this file)
--
-- Entity model:
--   dim_employee        — employee master data
--   dim_department      — department reference
--   dim_customer        — enterprise customer master
--   dim_product         — product catalog with category hierarchy
--   dim_product_category   — product category reference
--   dim_product_subcategory — product subcategory reference
--   dim_supplier        — vendor/supplier master
--   fact_sales_order    — sales order header
--   fact_sales_order_item — sales order line items
--   fact_purchase_order — purchase order header
--   fact_purchase_order_item — purchase order line items
--
-- Source identity: source_system = 'adventureworks'
-- All IDs preserve their AdventureWorks source key.
-- Surrogate keys (_sk) are defined as source_system + source_id for stability.
-- =============================================================================

-- ================================================================
-- dim_employee — Employee master data
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_employee` AS
SELECT
  CONCAT('adventureworks_', emp.BusinessEntityID)    AS employee_sk,
  'adventureworks'                                   AS source_system,
  CAST(emp.BusinessEntityID AS STRING)               AS source_employee_id,
  COALESCE(p.FirstName, '') || ' ' || COALESCE(p.LastName, '') AS full_name,
  p.FirstName                                        AS first_name,
  p.LastName                                         AS last_name,
  emp.JobTitle                                       AS job_title,
  emp.Gender                                         AS gender,
  emp.MaritalStatus                                  AS marital_status,
  emp.HireDate                                       AS hire_date,
  emp.BirthDate                                      AS birth_date,
  emp.SalariedFlag                                   AS is_salaried,
  emp.VacationHours                                  AS vacation_hours,
  emp.SickLeaveHours                                 AS sick_leave_hours,
  emp.CurrentFlag                                    AS is_current,
  emp._pwa_ingested_at,
  emp._pwa_run_id,
  emp._pwa_source_system,
  emp._pwa_source_table
FROM `{PROJECT}.raw_adventureworks.employee` emp
LEFT JOIN `{PROJECT}.raw_adventureworks.person` p
  ON emp.BusinessEntityID = p.BusinessEntityID;


-- ================================================================
-- dim_department — Department reference
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_department` AS
SELECT
  CONCAT('adventureworks_dept_', DepartmentID)  AS department_sk,
  'adventureworks'                              AS source_system,
  CAST(DepartmentID AS STRING)                  AS source_department_id,
  Name                                          AS department_name,
  GroupName                                     AS department_group,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_adventureworks.department`;


-- ================================================================
-- dim_customer — Enterprise customer master
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_customer` AS
SELECT
  CONCAT('adventureworks_', c.CustomerID)       AS customer_sk,
  'adventureworks'                              AS source_system,
  CAST(c.CustomerID AS STRING)                  AS source_customer_id,
  'B2B'                                         AS customer_type,
  COALESCE(p.FirstName, '') || ' ' || COALESCE(p.LastName, '')  AS customer_name,
  p.FirstName                                   AS first_name,
  p.LastName                                    AS last_name,
  CAST(c.PersonID AS STRING)                    AS person_id,
  CAST(c.StoreID AS STRING)                     AS store_id,
  CAST(c.TerritoryID AS STRING)                 AS territory_id,
  c._pwa_ingested_at,
  c._pwa_run_id,
  c._pwa_source_system
FROM `{PROJECT}.raw_adventureworks.customer` c
LEFT JOIN `{PROJECT}.raw_adventureworks.person` p
  ON c.PersonID = p.BusinessEntityID;


-- ================================================================
-- dim_product_category — Product category reference
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_product_category` AS
SELECT
  CONCAT('adventureworks_cat_', ProductCategoryID)  AS category_sk,
  'adventureworks'                                  AS source_system,
  CAST(ProductCategoryID AS STRING)                 AS source_category_id,
  Name                                              AS category_name,
  _pwa_ingested_at
FROM `{PROJECT}.raw_adventureworks.product_category`;


-- ================================================================
-- dim_product_subcategory — Product subcategory reference
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_product_subcategory` AS
SELECT
  CONCAT('adventureworks_subcat_', sc.ProductSubcategoryID)  AS subcategory_sk,
  'adventureworks'                                            AS source_system,
  CAST(sc.ProductSubcategoryID AS STRING)                    AS source_subcategory_id,
  sc.Name                                                    AS subcategory_name,
  CAST(sc.ProductCategoryID AS STRING)                       AS source_category_id,
  cat.Name                                                   AS category_name,
  sc._pwa_ingested_at
FROM `{PROJECT}.raw_adventureworks.product_subcategory` sc
LEFT JOIN `{PROJECT}.raw_adventureworks.product_category` cat
  ON sc.ProductCategoryID = cat.ProductCategoryID;


-- ================================================================
-- dim_product — Product catalog with full category hierarchy
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_product` AS
SELECT
  CONCAT('adventureworks_', p.ProductID)              AS product_sk,
  'adventureworks'                                    AS source_system,
  CAST(p.ProductID AS STRING)                         AS source_product_id,
  p.ProductNumber                                     AS product_number,
  p.Name                                              AS product_name,
  p.Color                                             AS color,
  p.Size                                              AS size,
  p.Weight                                            AS weight,
  CAST(p.StandardCost AS FLOAT64)                     AS standard_cost,
  CAST(p.ListPrice AS FLOAT64)                        AS list_price,
  p.ProductLine                                       AS product_line,
  p.Class                                             AS product_class,
  p.Style                                             AS style,
  p.SellStartDate                                     AS sell_start_date,
  p.SellEndDate                                       AS sell_end_date,
  p.DiscontinuedDate                                  AS discontinued_date,
  CAST(p.ProductSubcategoryID AS STRING)              AS source_subcategory_id,
  sc.Name                                             AS subcategory_name,
  cat.Name                                            AS category_name,
  CAST(cat.ProductCategoryID AS STRING)               AS source_category_id,
  p._pwa_ingested_at,
  p._pwa_run_id,
  p._pwa_source_system
FROM `{PROJECT}.raw_adventureworks.product` p
LEFT JOIN `{PROJECT}.raw_adventureworks.product_subcategory` sc
  ON p.ProductSubcategoryID = sc.ProductSubcategoryID
LEFT JOIN `{PROJECT}.raw_adventureworks.product_category` cat
  ON sc.ProductCategoryID = cat.ProductCategoryID;


-- ================================================================
-- dim_supplier — Vendor/supplier master
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.dim_supplier` AS
SELECT
  CONCAT('adventureworks_vendor_', BusinessEntityID)  AS supplier_sk,
  'adventureworks'                                    AS source_system,
  CAST(BusinessEntityID AS STRING)                    AS source_supplier_id,
  AccountNumber                                       AS account_number,
  Name                                                AS supplier_name,
  CreditRating                                        AS credit_rating,
  PreferredVendorStatus                               AS is_preferred,
  ActiveFlag                                          AS is_active,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_adventureworks.vendor`;


-- ================================================================
-- fact_sales_order — Sales order header
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.fact_sales_order` AS
SELECT
  CONCAT('adventureworks_so_', SalesOrderID)          AS sales_order_sk,
  'adventureworks'                                    AS source_system,
  CAST(SalesOrderID AS STRING)                        AS source_order_id,
  SalesOrderNumber                                    AS order_number,
  CAST(OrderDate AS DATE)                             AS order_date,
  CAST(DueDate AS DATE)                               AS due_date,
  CAST(ShipDate AS DATE)                              AS ship_date,
  CAST(Status AS INT64)                               AS order_status,
  CAST(CustomerID AS STRING)                          AS source_customer_id,
  CONCAT('adventureworks_', CustomerID)               AS customer_sk,
  CAST(SalesPersonID AS STRING)                       AS source_salesperson_id,
  CAST(TerritoryID AS STRING)                         AS source_territory_id,
  CAST(SubTotal AS FLOAT64)                           AS subtotal_amount,
  CAST(TaxAmt AS FLOAT64)                             AS tax_amount,
  CAST(Freight AS FLOAT64)                            AS freight_amount,
  CAST(TotalDue AS FLOAT64)                           AS total_due_amount,
  OnlineOrderFlag                                     AS is_online_order,
  _pwa_ingested_at,
  _pwa_run_id,
  _pwa_source_system
FROM `{PROJECT}.raw_adventureworks.sales_order_header`;


-- ================================================================
-- fact_sales_order_item — Sales order line items
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.fact_sales_order_item` AS
SELECT
  CONCAT('adventureworks_sod_', d.SalesOrderDetailID) AS sales_order_item_sk,
  'adventureworks'                                    AS source_system,
  CAST(d.SalesOrderID AS STRING)                      AS source_order_id,
  CONCAT('adventureworks_so_', d.SalesOrderID)        AS sales_order_sk,
  CAST(d.SalesOrderDetailID AS STRING)                AS source_order_detail_id,
  CAST(d.ProductID AS STRING)                         AS source_product_id,
  CONCAT('adventureworks_', d.ProductID)              AS product_sk,
  CAST(d.OrderQty AS INT64)                           AS quantity,
  CAST(d.UnitPrice AS FLOAT64)                        AS unit_price,
  CAST(d.UnitPriceDiscount AS FLOAT64)                AS unit_price_discount,
  CAST(d.LineTotal AS FLOAT64)                        AS line_total,
  d._pwa_ingested_at,
  d._pwa_run_id,
  d._pwa_source_system
FROM `{PROJECT}.raw_adventureworks.sales_order_detail` d;


-- ================================================================
-- fact_purchase_order — Purchase order header
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.fact_purchase_order` AS
SELECT
  CONCAT('adventureworks_po_', PurchaseOrderID)       AS purchase_order_sk,
  'adventureworks'                                    AS source_system,
  CAST(PurchaseOrderID AS STRING)                     AS source_order_id,
  CAST(VendorID AS STRING)                            AS source_supplier_id,
  CONCAT('adventureworks_vendor_', VendorID)          AS supplier_sk,
  CAST(EmployeeID AS STRING)                          AS source_employee_id,
  CAST(Status AS INT64)                               AS order_status,
  CAST(OrderDate AS DATE)                             AS order_date,
  CAST(ShipDate AS DATE)                              AS ship_date,
  CAST(SubTotal AS FLOAT64)                           AS subtotal_amount,
  CAST(TaxAmt AS FLOAT64)                             AS tax_amount,
  CAST(Freight AS FLOAT64)                            AS freight_amount,
  CAST(TotalDue AS FLOAT64)                           AS total_due_amount,
  _pwa_ingested_at,
  _pwa_run_id
FROM `{PROJECT}.raw_adventureworks.purchase_order_header`;


-- ================================================================
-- fact_purchase_order_item — Purchase order line items
-- ================================================================
CREATE OR REPLACE VIEW `{PROJECT}.curated_enterprise.fact_purchase_order_item` AS
SELECT
  CONCAT('adventureworks_pod_', d.PurchaseOrderDetailID) AS purchase_order_item_sk,
  'adventureworks'                                       AS source_system,
  CAST(d.PurchaseOrderID AS STRING)                      AS source_order_id,
  CONCAT('adventureworks_po_', d.PurchaseOrderID)        AS purchase_order_sk,
  CAST(d.PurchaseOrderDetailID AS STRING)                AS source_detail_id,
  CAST(d.ProductID AS STRING)                            AS source_product_id,
  CONCAT('adventureworks_', d.ProductID)                 AS product_sk,
  CAST(d.OrderQty AS INT64)                              AS quantity_ordered,
  CAST(d.UnitPrice AS FLOAT64)                           AS unit_price,
  CAST(d.LineTotal AS FLOAT64)                           AS line_total,
  CAST(d.ReceivedQty AS FLOAT64)                         AS quantity_received,
  CAST(d.RejectedQty AS FLOAT64)                         AS quantity_rejected,
  CAST(d.DueDate AS DATE)                                AS due_date,
  d._pwa_ingested_at,
  d._pwa_run_id
FROM `{PROJECT}.raw_adventureworks.purchase_order_detail` d;
