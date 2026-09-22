# Nexora Enterprise Dataset — Source Schema Audit

This document lists the schema audit for all source files across AdventureWorks 2022, Olist E-Commerce, and Olist Marketing Funnel.

| Source | File | Rows | Columns | Candidate PK | Candidate FK | Target DB |
| --- | --- | --- | --- | --- | --- | --- |
| adventureworks | HumanResources.Department.csv | 7 | 4 | DepartmentID | None | Cloudflare D1 |
| adventureworks | HumanResources.Employee.csv | 15 | 16 | BusinessEntityID | None | Cloudflare D1 |
| adventureworks | HumanResources.EmployeeDepartmentHistory.csv | 15 | 6 | (BusinessEntityID, DepartmentID) | BusinessEntityID -> Employee, DepartmentID -> Department | Cloudflare D1 |
| adventureworks | Person.Address.csv | 30 | 9 | AddressID | None | AlloyDB / D1 |
| adventureworks | Person.Person.csv | 30 | 13 | BusinessEntityID | None | Cloudflare D1 / AlloyDB |
| adventureworks | Production.Product.csv | 20 | 25 | ProductID | ProductSubcategoryID -> ProductSubcategory | AlloyDB |
| adventureworks | Production.ProductCategory.csv | 4 | 4 | ProductCategoryID | None | AlloyDB |
| adventureworks | Production.ProductSubcategory.csv | 6 | 5 | ProductSubcategoryID | ProductCategoryID -> ProductCategory | AlloyDB |
| adventureworks | Purchasing.PurchaseOrderDetail.csv | 40 | 11 | PurchaseOrderDetailID | PurchaseOrderID -> PurchaseOrderHeader, ProductID -> Product | Aiven MySQL |
| adventureworks | Purchasing.PurchaseOrderHeader.csv | 20 | 13 | PurchaseOrderID | VendorID -> Vendor, EmployeeID -> Employee | Aiven MySQL |
| adventureworks | Purchasing.Vendor.csv | 10 | 8 | BusinessEntityID | None | Aiven MySQL |
| adventureworks | Sales.Customer.csv | 25 | 7 | CustomerID | PersonID -> Person, TerritoryID -> SalesTerritory | AlloyDB |
| adventureworks | Sales.SalesOrderDetail.csv | 101 | 11 | SalesOrderDetailID | SalesOrderID -> SalesOrderHeader, ProductID -> Product | AlloyDB |
| adventureworks | Sales.SalesOrderHeader.csv | 50 | 26 | SalesOrderID | CustomerID -> Customer, SalesPersonID -> Employee, TerritoryID -> SalesTerritory | AlloyDB |
| adventureworks | Sales.SalesTerritory.csv | 5 | 10 | TerritoryID | None | AlloyDB |
| olist | olist_customers_dataset.csv | 100 | 5 | customer_id | None | AlloyDB / D1 |
| olist | olist_geolocation_dataset.csv | 50 | 5 | (geolocation_zip_code_prefix, geolocation_lat, geolocation_lng) | None | Aiven MySQL |
| olist | olist_order_items_dataset.csv | 150 | 7 | (order_id, order_item_id) | order_id -> olist_orders, product_id -> olist_products, seller_id -> olist_sellers | AlloyDB |
| olist | olist_order_payments_dataset.csv | 100 | 5 | (order_id, payment_sequential) | order_id -> olist_orders | AlloyDB |
| olist | olist_order_reviews_dataset.csv | 50 | 7 | review_id | order_id -> olist_orders | AlloyDB |
| olist | olist_orders_dataset.csv | 100 | 8 | order_id | customer_id -> olist_customers | AlloyDB |
| olist | olist_products_dataset.csv | 30 | 9 | product_id | None | AlloyDB |
| olist | olist_sellers_dataset.csv | 20 | 4 | seller_id | None | Aiven MySQL |
| olist | product_category_name_translation.csv | 5 | 2 | product_category_name | None | AlloyDB |
| olist_marketing | olist_closed_deals_dataset.csv | 20 | 14 | mql_id | mql_id -> olist_mqls, seller_id -> olist_sellers | Cloudflare D1 |
| olist_marketing | olist_marketing_qualified_leads_dataset.csv | 50 | 4 | mql_id | None | Cloudflare D1 |
