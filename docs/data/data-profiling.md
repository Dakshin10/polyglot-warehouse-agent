# Nexora Enterprise Dataset — Data Profiling Report

## adventureworks / HumanResources.Department.csv
- **Rows**: 7
- **Columns**: 4

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| DepartmentID | int64 | 0 | 0.0% | 7 |
| Name | object | 0 | 0.0% | 7 |
| GroupName | object | 0 | 0.0% | 4 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / HumanResources.Employee.csv
- **Rows**: 15
- **Columns**: 16

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| BusinessEntityID | int64 | 0 | 0.0% | 15 |
| NationalIDNumber | int64 | 0 | 0.0% | 15 |
| LoginID | object | 0 | 0.0% | 15 |
| OrganizationNode | object | 0 | 0.0% | 15 |
| OrganizationLevel | int64 | 0 | 0.0% | 2 |
| JobTitle | object | 0 | 0.0% | 9 |
| BirthDate | object | 0 | 0.0% | 10 |
| MaritalStatus | object | 0 | 0.0% | 2 |
| Gender | object | 0 | 0.0% | 2 |
| HireDate | object | 0 | 0.0% | 10 |
| SalariedFlag | int64 | 0 | 0.0% | 1 |
| VacationHours | int64 | 0 | 0.0% | 15 |
| SickLeaveHours | int64 | 0 | 0.0% | 15 |
| CurrentFlag | int64 | 0 | 0.0% | 1 |
| rowguid | object | 0 | 0.0% | 15 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / HumanResources.EmployeeDepartmentHistory.csv
- **Rows**: 15
- **Columns**: 6

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| BusinessEntityID | int64 | 0 | 0.0% | 15 |
| DepartmentID | int64 | 0 | 0.0% | 7 |
| ShiftID | int64 | 0 | 0.0% | 1 |
| StartDate | object | 0 | 0.0% | 10 |
| EndDate | float64 | 15 | 100.0% | 0 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Person.Address.csv
- **Rows**: 30
- **Columns**: 9

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| AddressID | int64 | 0 | 0.0% | 30 |
| AddressLine1 | object | 0 | 0.0% | 30 |
| AddressLine2 | object | 24 | 80.0% | 6 |
| City | object | 0 | 0.0% | 8 |
| StateProvinceID | int64 | 0 | 0.0% | 10 |
| PostalCode | int64 | 0 | 0.0% | 10 |
| SpatialLocation | object | 0 | 0.0% | 1 |
| rowguid | object | 0 | 0.0% | 30 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Person.Person.csv
- **Rows**: 30
- **Columns**: 13

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| BusinessEntityID | int64 | 0 | 0.0% | 30 |
| PersonType | object | 0 | 0.0% | 2 |
| NameStyle | int64 | 0 | 0.0% | 1 |
| Title | object | 0 | 0.0% | 2 |
| FirstName | object | 0 | 0.0% | 10 |
| MiddleName | object | 0 | 0.0% | 26 |
| LastName | object | 0 | 0.0% | 10 |
| Suffix | float64 | 30 | 100.0% | 0 |
| EmailPromotion | int64 | 0 | 0.0% | 3 |
| AdditionalContactInfo | float64 | 30 | 100.0% | 0 |
| Demographics | float64 | 30 | 100.0% | 0 |
| rowguid | object | 0 | 0.0% | 30 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Production.Product.csv
- **Rows**: 20
- **Columns**: 25

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| ProductID | int64 | 0 | 0.0% | 20 |
| Name | object | 0 | 0.0% | 20 |
| ProductNumber | object | 0 | 0.0% | 20 |
| MakeFlag | int64 | 0 | 0.0% | 1 |
| FinishedGoodsFlag | int64 | 0 | 0.0% | 1 |
| Color | object | 0 | 0.0% | 2 |
| SafetyStockLevel | int64 | 0 | 0.0% | 1 |
| ReorderPoint | int64 | 0 | 0.0% | 1 |
| StandardCost | float64 | 0 | 0.0% | 20 |
| ListPrice | float64 | 0 | 0.0% | 20 |
| Size | int64 | 0 | 0.0% | 2 |
| SizeUnitMeasureCode | object | 0 | 0.0% | 1 |
| WeightUnitMeasureCode | object | 0 | 0.0% | 1 |
| Weight | float64 | 0 | 0.0% | 20 |
| DaysToManufacture | int64 | 0 | 0.0% | 1 |
| ProductLine | object | 0 | 0.0% | 1 |
| Class | object | 0 | 0.0% | 1 |
| Style | object | 0 | 0.0% | 1 |
| ProductSubcategoryID | int64 | 0 | 0.0% | 6 |
| ProductModelID | int64 | 0 | 0.0% | 20 |
| SellStartDate | object | 0 | 0.0% | 1 |
| SellEndDate | float64 | 20 | 100.0% | 0 |
| DiscontinuedDate | float64 | 20 | 100.0% | 0 |
| rowguid | object | 0 | 0.0% | 20 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Production.ProductCategory.csv
- **Rows**: 4
- **Columns**: 4

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| ProductCategoryID | int64 | 0 | 0.0% | 4 |
| Name | object | 0 | 0.0% | 4 |
| rowguid | object | 0 | 0.0% | 4 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Production.ProductSubcategory.csv
- **Rows**: 6
- **Columns**: 5

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| ProductSubcategoryID | int64 | 0 | 0.0% | 6 |
| ProductCategoryID | int64 | 0 | 0.0% | 4 |
| Name | object | 0 | 0.0% | 6 |
| rowguid | object | 0 | 0.0% | 6 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Purchasing.PurchaseOrderDetail.csv
- **Rows**: 40
- **Columns**: 11

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| PurchaseOrderID | int64 | 0 | 0.0% | 20 |
| PurchaseOrderDetailID | int64 | 0 | 0.0% | 40 |
| DueDate | object | 0 | 0.0% | 12 |
| OrderQty | int64 | 0 | 0.0% | 1 |
| ProductID | int64 | 0 | 0.0% | 20 |
| UnitPrice | float64 | 0 | 0.0% | 20 |
| LineTotal | float64 | 0 | 0.0% | 20 |
| ReceivedQty | float64 | 0 | 0.0% | 1 |
| RejectedQty | float64 | 0 | 0.0% | 1 |
| StockedQty | float64 | 0 | 0.0% | 1 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Purchasing.PurchaseOrderHeader.csv
- **Rows**: 20
- **Columns**: 13

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| PurchaseOrderID | int64 | 0 | 0.0% | 20 |
| RevisionNumber | int64 | 0 | 0.0% | 1 |
| Status | int64 | 0 | 0.0% | 1 |
| EmployeeID | int64 | 0 | 0.0% | 5 |
| VendorID | int64 | 0 | 0.0% | 10 |
| ShipMethodID | int64 | 0 | 0.0% | 1 |
| OrderDate | object | 0 | 0.0% | 12 |
| ShipDate | object | 0 | 0.0% | 12 |
| SubTotal | float64 | 0 | 0.0% | 20 |
| TaxAmt | float64 | 0 | 0.0% | 20 |
| Freight | float64 | 0 | 0.0% | 20 |
| TotalDue | float64 | 0 | 0.0% | 20 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Purchasing.Vendor.csv
- **Rows**: 10
- **Columns**: 8

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| BusinessEntityID | int64 | 0 | 0.0% | 10 |
| AccountNumber | object | 0 | 0.0% | 10 |
| Name | object | 0 | 0.0% | 10 |
| CreditRating | int64 | 0 | 0.0% | 5 |
| PreferredVendorStatus | int64 | 0 | 0.0% | 1 |
| ActiveFlag | int64 | 0 | 0.0% | 1 |
| PurchasingWebServiceURL | object | 0 | 0.0% | 10 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Sales.Customer.csv
- **Rows**: 25
- **Columns**: 7

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| CustomerID | int64 | 0 | 0.0% | 25 |
| PersonID | float64 | 10 | 40.0% | 15 |
| StoreID | float64 | 15 | 60.0% | 10 |
| TerritoryID | int64 | 0 | 0.0% | 5 |
| AccountNumber | object | 0 | 0.0% | 25 |
| rowguid | object | 0 | 0.0% | 25 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Sales.SalesOrderDetail.csv
- **Rows**: 101
- **Columns**: 11

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| SalesOrderID | int64 | 0 | 0.0% | 50 |
| SalesOrderDetailID | int64 | 0 | 0.0% | 101 |
| CarrierTrackingNumber | object | 0 | 0.0% | 101 |
| OrderQty | int64 | 0 | 0.0% | 3 |
| ProductID | int64 | 0 | 0.0% | 20 |
| SpecialOfferID | int64 | 0 | 0.0% | 1 |
| UnitPrice | float64 | 0 | 0.0% | 20 |
| UnitPriceDiscount | float64 | 0 | 0.0% | 1 |
| LineTotal | float64 | 0 | 0.0% | 40 |
| rowguid | object | 0 | 0.0% | 101 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Sales.SalesOrderHeader.csv
- **Rows**: 50
- **Columns**: 26

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| SalesOrderID | int64 | 0 | 0.0% | 50 |
| RevisionNumber | int64 | 0 | 0.0% | 1 |
| OrderDate | object | 0 | 0.0% | 12 |
| DueDate | object | 0 | 0.0% | 12 |
| ShipDate | object | 0 | 0.0% | 12 |
| Status | int64 | 0 | 0.0% | 1 |
| OnlineOrderFlag | int64 | 0 | 0.0% | 2 |
| SalesOrderNumber | object | 0 | 0.0% | 50 |
| PurchaseOrderNumber | object | 0 | 0.0% | 50 |
| AccountNumber | object | 0 | 0.0% | 25 |
| CustomerID | int64 | 0 | 0.0% | 25 |
| SalesPersonID | int64 | 0 | 0.0% | 5 |
| TerritoryID | int64 | 0 | 0.0% | 5 |
| BillToAddressID | int64 | 0 | 0.0% | 30 |
| ShipToAddressID | int64 | 0 | 0.0% | 30 |
| ShipMethodID | int64 | 0 | 0.0% | 1 |
| CreditCardID | int64 | 0 | 0.0% | 50 |
| CreditCardApprovalCode | object | 0 | 0.0% | 50 |
| CurrencyRateID | float64 | 50 | 100.0% | 0 |
| SubTotal | float64 | 0 | 0.0% | 50 |
| TaxAmt | float64 | 0 | 0.0% | 50 |
| Freight | float64 | 0 | 0.0% | 50 |
| TotalDue | float64 | 0 | 0.0% | 50 |
| Comment | float64 | 50 | 100.0% | 0 |
| rowguid | object | 0 | 0.0% | 50 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## adventureworks / Sales.SalesTerritory.csv
- **Rows**: 5
- **Columns**: 10

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| TerritoryID | int64 | 0 | 0.0% | 5 |
| Name | object | 0 | 0.0% | 5 |
| CountryRegionCode | object | 0 | 0.0% | 1 |
| Group | object | 0 | 0.0% | 1 |
| SalesYTD | float64 | 0 | 0.0% | 5 |
| SalesLastYear | float64 | 0 | 0.0% | 5 |
| CostYTD | int64 | 0 | 0.0% | 1 |
| CostLastYear | int64 | 0 | 0.0% | 1 |
| rowguid | object | 0 | 0.0% | 5 |
| ModifiedDate | object | 0 | 0.0% | 1 |

## olist / olist_customers_dataset.csv
- **Rows**: 100
- **Columns**: 5

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| customer_id | object | 0 | 0.0% | 100 |
| customer_unique_id | object | 0 | 0.0% | 80 |
| customer_zip_code_prefix | int64 | 0 | 0.0% | 50 |
| customer_city | object | 0 | 0.0% | 2 |
| customer_state | object | 0 | 0.0% | 2 |

## olist / olist_geolocation_dataset.csv
- **Rows**: 50
- **Columns**: 5

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| geolocation_zip_code_prefix | int64 | 0 | 0.0% | 50 |
| geolocation_lat | float64 | 0 | 0.0% | 50 |
| geolocation_lng | float64 | 0 | 0.0% | 50 |
| geolocation_city | object | 0 | 0.0% | 1 |
| geolocation_state | object | 0 | 0.0% | 1 |

## olist / olist_order_items_dataset.csv
- **Rows**: 150
- **Columns**: 7

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| order_id | object | 0 | 0.0% | 100 |
| order_item_id | int64 | 0 | 0.0% | 2 |
| product_id | object | 0 | 0.0% | 30 |
| seller_id | object | 0 | 0.0% | 20 |
| shipping_limit_date | object | 0 | 0.0% | 1 |
| price | float64 | 0 | 0.0% | 100 |
| freight_value | float64 | 0 | 0.0% | 100 |

## olist / olist_order_payments_dataset.csv
- **Rows**: 100
- **Columns**: 5

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| order_id | object | 0 | 0.0% | 100 |
| payment_sequential | int64 | 0 | 0.0% | 1 |
| payment_type | object | 0 | 0.0% | 4 |
| payment_installments | int64 | 0 | 0.0% | 4 |
| payment_value | float64 | 0 | 0.0% | 100 |

## olist / olist_order_reviews_dataset.csv
- **Rows**: 50
- **Columns**: 7

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| review_id | object | 0 | 0.0% | 50 |
| order_id | object | 0 | 0.0% | 50 |
| review_score | int64 | 0 | 0.0% | 5 |
| review_comment_title | object | 0 | 0.0% | 2 |
| review_comment_message | object | 0 | 0.0% | 2 |
| review_creation_date | object | 0 | 0.0% | 50 |
| review_answer_timestamp | object | 0 | 0.0% | 50 |

## olist / olist_orders_dataset.csv
- **Rows**: 100
- **Columns**: 8

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| order_id | object | 0 | 0.0% | 100 |
| customer_id | object | 0 | 0.0% | 100 |
| order_status | object | 0 | 0.0% | 3 |
| order_purchase_timestamp | object | 0 | 0.0% | 100 |
| order_approved_at | object | 0 | 0.0% | 100 |
| order_delivered_carrier_date | object | 40 | 40.0% | 60 |
| order_delivered_customer_date | object | 40 | 40.0% | 60 |
| order_estimated_delivery_date | object | 0 | 0.0% | 100 |

## olist / olist_products_dataset.csv
- **Rows**: 30
- **Columns**: 9

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| product_id | object | 0 | 0.0% | 30 |
| product_category_name | object | 0 | 0.0% | 5 |
| product_name_lenght | int64 | 0 | 0.0% | 30 |
| product_description_lenght | int64 | 0 | 0.0% | 30 |
| product_photos_qty | int64 | 0 | 0.0% | 4 |
| product_weight_g | int64 | 0 | 0.0% | 30 |
| product_length_cm | int64 | 0 | 0.0% | 30 |
| product_height_cm | int64 | 0 | 0.0% | 30 |
| product_width_cm | int64 | 0 | 0.0% | 30 |

## olist / olist_sellers_dataset.csv
- **Rows**: 20
- **Columns**: 4

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| seller_id | object | 0 | 0.0% | 20 |
| seller_zip_code_prefix | int64 | 0 | 0.0% | 20 |
| seller_city | object | 0 | 0.0% | 2 |
| seller_state | object | 0 | 0.0% | 2 |

## olist / product_category_name_translation.csv
- **Rows**: 5
- **Columns**: 2

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| product_category_name | object | 0 | 0.0% | 5 |
| product_category_name_english | object | 0 | 0.0% | 5 |

## olist_marketing / olist_closed_deals_dataset.csv
- **Rows**: 20
- **Columns**: 14

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| mql_id | object | 0 | 0.0% | 20 |
| seller_id | object | 0 | 0.0% | 20 |
| sdr_id | object | 0 | 0.0% | 5 |
| sr_id | object | 0 | 0.0% | 4 |
| won_date | object | 0 | 0.0% | 20 |
| business_segment | object | 0 | 0.0% | 4 |
| lead_type | object | 0 | 0.0% | 4 |
| lead_behaviour_profile | object | 0 | 0.0% | 1 |
| has_company | bool | 0 | 0.0% | 1 |
| has_gtin | bool | 0 | 0.0% | 1 |
| average_stock | object | 0 | 0.0% | 1 |
| business_type | object | 0 | 0.0% | 1 |
| declared_product_catalog_size | int64 | 0 | 0.0% | 20 |
| declared_monthly_revenue | int64 | 0 | 0.0% | 20 |

## olist_marketing / olist_marketing_qualified_leads_dataset.csv
- **Rows**: 50
- **Columns**: 4

| Column | Type | Null Count | Null % | Distinct Count |
| --- | --- | --- | --- | --- |
| mql_id | object | 0 | 0.0% | 50 |
| first_contact_date | object | 0 | 0.0% | 50 |
| landing_page_id | object | 0 | 0.0% | 10 |
| origin | object | 0 | 0.0% | 5 |

