"""Generate realistic source CSV datasets matching Kaggle schemas for AdventureWorks, Olist, and Olist Marketing.

Used to populate data/source/ directories when local Kaggle API credentials are not provided.
Manifests and provenance metadata will be written automatically by the ingestion pipeline.
"""

from __future__ import annotations

from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_BASE = REPO_ROOT / "data" / "source"

AW_DIR = SOURCE_BASE / "adventureworks"
OLIST_DIR = SOURCE_BASE / "olist"
MKT_DIR = SOURCE_BASE / "olist_marketing"


def generate_adventureworks():
    AW_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating AdventureWorks source dataset...")

    # 1. Department
    depts = pd.DataFrame(
        [
            {
                "DepartmentID": 1,
                "Name": "Engineering",
                "GroupName": "Research and Development",
                "ModifiedDate": "2022-01-01",
            },
            {
                "DepartmentID": 2,
                "Name": "Tool Design",
                "GroupName": "Research and Development",
                "ModifiedDate": "2022-01-01",
            },
            {"DepartmentID": 3, "Name": "Sales", "GroupName": "Sales and Marketing", "ModifiedDate": "2022-01-01"},
            {"DepartmentID": 4, "Name": "Marketing", "GroupName": "Sales and Marketing", "ModifiedDate": "2022-01-01"},
            {
                "DepartmentID": 5,
                "Name": "Purchasing",
                "GroupName": "Inventory Management",
                "ModifiedDate": "2022-01-01",
            },
            {
                "DepartmentID": 6,
                "Name": "Human Resources",
                "GroupName": "Executive General and Administration",
                "ModifiedDate": "2022-01-01",
            },
            {
                "DepartmentID": 7,
                "Name": "Finance",
                "GroupName": "Executive General and Administration",
                "ModifiedDate": "2022-01-01",
            },
        ]
    )
    depts.to_csv(AW_DIR / "HumanResources.Department.csv", index=False)

    # 2. Person
    persons = []
    first_names = ["Ken", "Terri", "Roberto", "Rob", "Gail", "Jossef", "Dylan", "Diane", "Gigi", "Michael"]
    last_names = [
        "Sanchez",
        "Duffy",
        "Tamburello",
        "Walters",
        "Erickson",
        "Goldberg",
        "Miller",
        "Margheim",
        "Matthew",
        "Raheem",
    ]
    for i in range(1, 31):
        fn = first_names[(i - 1) % len(first_names)]
        ln = last_names[(i - 1) % len(last_names)]
        persons.append(
            {
                "BusinessEntityID": i,
                "PersonType": "EM" if i <= 15 else "IN",
                "NameStyle": 0,
                "Title": "Mr." if i % 2 == 1 else "Ms.",
                "FirstName": fn,
                "MiddleName": chr(65 + (i % 26)),
                "LastName": ln,
                "Suffix": None,
                "EmailPromotion": i % 3,
                "AdditionalContactInfo": None,
                "Demographics": None,
                "rowguid": f"guid-person-{i}",
                "ModifiedDate": "2022-01-01 00:00:00",
            }
        )
    pd.DataFrame(persons).to_csv(AW_DIR / "Person.Person.csv", index=False)

    # 3. Employee
    employees = []
    job_titles = [
        "Chief Executive Officer",
        "Vice President of Engineering",
        "Engineering Manager",
        "Senior Tool Designer",
        "Sales Representative",
        "Marketing Manager",
        "Purchasing Manager",
        "HR Specialist",
        "Finance Manager",
    ]
    for i in range(1, 16):
        employees.append(
            {
                "BusinessEntityID": i,
                "NationalIDNumber": f"2958472{i:02d}",
                "LoginID": f"adventure-works\\emp{i}",
                "OrganizationNode": f"/1/{i}/",
                "OrganizationLevel": 1 if i <= 2 else 2,
                "JobTitle": job_titles[(i - 1) % len(job_titles)],
                "BirthDate": f"198{i % 10}-05-15",
                "MaritalStatus": "M" if i % 2 == 0 else "S",
                "Gender": "M" if i % 2 == 1 else "F",
                "HireDate": f"201{i % 10}-01-15",
                "SalariedFlag": 1,
                "VacationHours": 40 + i * 2,
                "SickLeaveHours": 20 + i,
                "CurrentFlag": 1,
                "rowguid": f"guid-emp-{i}",
                "ModifiedDate": "2022-01-01 00:00:00",
            }
        )
    pd.DataFrame(employees).to_csv(AW_DIR / "HumanResources.Employee.csv", index=False)

    # 4. EmployeeDepartmentHistory
    edh = []
    for i in range(1, 16):
        dept_id = (i % 7) + 1
        edh.append(
            {
                "BusinessEntityID": i,
                "DepartmentID": dept_id,
                "ShiftID": 1,
                "StartDate": f"201{i % 10}-01-15",
                "EndDate": None,
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(edh).to_csv(AW_DIR / "HumanResources.EmployeeDepartmentHistory.csv", index=False)

    # 5. Address
    addresses = []
    cities = ["Bothell", "Bellingham", "Calgary", "Carson", "Edmonds", "Seattle", "Redmond", "Vancouver"]
    for i in range(1, 31):
        addresses.append(
            {
                "AddressID": i,
                "AddressLine1": f"{1000 + i * 10} Main St",
                "AddressLine2": f"Suite {i}" if i % 5 == 0 else None,
                "City": cities[i % len(cities)],
                "StateProvinceID": (i % 10) + 1,
                "PostalCode": f"9800{i % 10}",
                "SpatialLocation": "0xE6100000010C",
                "rowguid": f"guid-addr-{i}",
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(addresses).to_csv(AW_DIR / "Person.Address.csv", index=False)

    # 6. ProductCategory & Subcategory
    cat_df = pd.DataFrame(
        [
            {"ProductCategoryID": 1, "Name": "Bikes", "rowguid": "guid-cat-1", "ModifiedDate": "2022-01-01"},
            {"ProductCategoryID": 2, "Name": "Components", "rowguid": "guid-cat-2", "ModifiedDate": "2022-01-01"},
            {"ProductCategoryID": 3, "Name": "Clothing", "rowguid": "guid-cat-3", "ModifiedDate": "2022-01-01"},
            {"ProductCategoryID": 4, "Name": "Accessories", "rowguid": "guid-cat-4", "ModifiedDate": "2022-01-01"},
        ]
    )
    cat_df.to_csv(AW_DIR / "Production.ProductCategory.csv", index=False)

    subcat_df = pd.DataFrame(
        [
            {
                "ProductSubcategoryID": 1,
                "ProductCategoryID": 1,
                "Name": "Mountain Bikes",
                "rowguid": "guid-subcat-1",
                "ModifiedDate": "2022-01-01",
            },
            {
                "ProductSubcategoryID": 2,
                "ProductCategoryID": 1,
                "Name": "Road Bikes",
                "rowguid": "guid-subcat-2",
                "ModifiedDate": "2022-01-01",
            },
            {
                "ProductSubcategoryID": 3,
                "ProductCategoryID": 1,
                "Name": "Touring Bikes",
                "rowguid": "guid-subcat-3",
                "ModifiedDate": "2022-01-01",
            },
            {
                "ProductSubcategoryID": 4,
                "ProductCategoryID": 2,
                "Name": "Handlebars",
                "rowguid": "guid-subcat-4",
                "ModifiedDate": "2022-01-01",
            },
            {
                "ProductSubcategoryID": 5,
                "ProductCategoryID": 3,
                "Name": "Jerseys",
                "rowguid": "guid-subcat-5",
                "ModifiedDate": "2022-01-01",
            },
            {
                "ProductSubcategoryID": 6,
                "ProductCategoryID": 4,
                "Name": "Helmets",
                "rowguid": "guid-subcat-6",
                "ModifiedDate": "2022-01-01",
            },
        ]
    )
    subcat_df.to_csv(AW_DIR / "Production.ProductSubcategory.csv", index=False)

    # 7. Product
    products = []
    prod_names = [
        "Mountain-100 Black, 42",
        "Mountain-100 Black, 44",
        "Road-150 Red, 62",
        "Road-150 Red, 44",
        "Touring-1000 Blue, 46",
        "Full-Finger Gloves, L",
        "Classic Vest, M",
        "Sport-100 Helmet, Red",
    ]
    for i in range(1, 21):
        subid = (i % 6) + 1
        products.append(
            {
                "ProductID": 500 + i,
                "Name": prod_names[(i - 1) % len(prod_names)] + f" #{i}",
                "ProductNumber": f"BK-M18B-{i:02d}",
                "MakeFlag": 1,
                "FinishedGoodsFlag": 1,
                "Color": "Black" if i % 2 == 0 else "Red",
                "SafetyStockLevel": 500,
                "ReorderPoint": 375,
                "StandardCost": round(150.00 + i * 20.5, 2),
                "ListPrice": round(300.00 + i * 35.0, 2),
                "Size": "42" if i % 2 == 0 else "44",
                "SizeUnitMeasureCode": "CM",
                "WeightUnitMeasureCode": "LB",
                "Weight": round(15.5 + i, 2),
                "DaysToManufacture": 4,
                "ProductLine": "M",
                "Class": "H",
                "Style": "U",
                "ProductSubcategoryID": subid,
                "ProductModelID": i,
                "SellStartDate": "2021-01-01",
                "SellEndDate": None,
                "DiscontinuedDate": None,
                "rowguid": f"guid-prod-{i}",
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(products).to_csv(AW_DIR / "Production.Product.csv", index=False)

    # 8. Customer
    customers = []
    for i in range(1, 26):
        customers.append(
            {
                "CustomerID": 1000 + i,
                "PersonID": 15 + i if i <= 15 else None,
                "StoreID": 200 + i if i > 15 else None,
                "TerritoryID": (i % 5) + 1,
                "AccountNumber": f"AW0000{1000 + i}",
                "rowguid": f"guid-cust-{i}",
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(customers).to_csv(AW_DIR / "Sales.Customer.csv", index=False)

    # 9. SalesTerritory
    territories = [
        {
            "TerritoryID": 1,
            "Name": "Northwest",
            "CountryRegionCode": "US",
            "Group": "North America",
            "SalesYTD": 7887186.79,
            "SalesLastYear": 3298694.49,
            "CostYTD": 0,
            "CostLastYear": 0,
            "rowguid": "guid-terr-1",
            "ModifiedDate": "2022-01-01",
        },
        {
            "TerritoryID": 2,
            "Name": "Northeast",
            "CountryRegionCode": "US",
            "Group": "North America",
            "SalesYTD": 2402176.85,
            "SalesLastYear": 1797068.09,
            "CostYTD": 0,
            "CostLastYear": 0,
            "rowguid": "guid-terr-2",
            "ModifiedDate": "2022-01-01",
        },
        {
            "TerritoryID": 3,
            "Name": "Central",
            "CountryRegionCode": "US",
            "Group": "North America",
            "SalesYTD": 3072175.12,
            "SalesLastYear": 2556557.06,
            "CostYTD": 0,
            "CostLastYear": 0,
            "rowguid": "guid-terr-3",
            "ModifiedDate": "2022-01-01",
        },
        {
            "TerritoryID": 4,
            "Name": "Southwest",
            "CountryRegionCode": "US",
            "Group": "North America",
            "SalesYTD": 10510853.87,
            "SalesLastYear": 5716942.57,
            "CostYTD": 0,
            "CostLastYear": 0,
            "rowguid": "guid-terr-4",
            "ModifiedDate": "2022-01-01",
        },
        {
            "TerritoryID": 5,
            "Name": "Southeast",
            "CountryRegionCode": "US",
            "Group": "North America",
            "SalesYTD": 2538667.25,
            "SalesLastYear": 1600218.42,
            "CostYTD": 0,
            "CostLastYear": 0,
            "rowguid": "guid-terr-5",
            "ModifiedDate": "2022-01-01",
        },
    ]
    pd.DataFrame(territories).to_csv(AW_DIR / "Sales.SalesTerritory.csv", index=False)

    # 10. SalesOrderHeader
    orders = []
    for i in range(1, 51):
        cust_id = 1000 + ((i - 1) % 25) + 1
        sales_rep = (i % 5) + 1  # employee 1..5
        terr_id = (i % 5) + 1
        orders.append(
            {
                "SalesOrderID": 43650 + i,
                "RevisionNumber": 8,
                "OrderDate": f"2022-{(i % 12) + 1:02d}-15 00:00:00",
                "DueDate": f"2022-{(i % 12) + 1:02d}-27 00:00:00",
                "ShipDate": f"2022-{(i % 12) + 1:02d}-22 00:00:00",
                "Status": 5,  # Shipped
                "OnlineOrderFlag": 0 if i % 2 == 0 else 1,
                "SalesOrderNumber": f"SO{43650 + i}",
                "PurchaseOrderNumber": f"PO{10000 + i}",
                "AccountNumber": f"AW0000{cust_id}",
                "CustomerID": cust_id,
                "SalesPersonID": sales_rep,
                "TerritoryID": terr_id,
                "BillToAddressID": (i % 30) + 1,
                "ShipToAddressID": (i % 30) + 1,
                "ShipMethodID": 1,
                "CreditCardID": 100 + i,
                "CreditCardApprovalCode": f"1050{i}Vi",
                "CurrencyRateID": None,
                "SubTotal": round(500.00 + i * 45.0, 2),
                "TaxAmt": round(40.00 + i * 3.6, 2),
                "Freight": round(12.50 + i * 1.1, 2),
                "TotalDue": round(552.50 + i * 49.7, 2),
                "Comment": None,
                "rowguid": f"guid-soh-{i}",
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(orders).to_csv(AW_DIR / "Sales.SalesOrderHeader.csv", index=False)

    # 11. SalesOrderDetail
    details = []
    detail_id = 1
    for i in range(1, 51):
        so_id = 43650 + i
        num_items = (i % 3) + 1
        for j in range(num_items):
            prod_id = 500 + ((detail_id % 20) + 1)
            qty = (j + 1) * 2
            unit_price = round(300.00 + (prod_id - 500) * 35.0, 2)
            details.append(
                {
                    "SalesOrderID": so_id,
                    "SalesOrderDetailID": detail_id,
                    "CarrierTrackingNumber": f"4911-403C-{detail_id:02d}",
                    "OrderQty": qty,
                    "ProductID": prod_id,
                    "SpecialOfferID": 1,
                    "UnitPrice": unit_price,
                    "UnitPriceDiscount": 0.0,
                    "LineTotal": round(qty * unit_price, 2),
                    "rowguid": f"guid-sod-{detail_id}",
                    "ModifiedDate": "2022-01-01",
                }
            )
            detail_id += 1
    pd.DataFrame(details).to_csv(AW_DIR / "Sales.SalesOrderDetail.csv", index=False)

    # 12. Purchasing Vendor
    vendors = []
    for i in range(1, 11):
        vendors.append(
            {
                "BusinessEntityID": 100 + i,
                "AccountNumber": f"VENDOR00{i}",
                "Name": f"Supplier Partner {i} Corp",
                "CreditRating": (i % 5) + 1,
                "PreferredVendorStatus": 1,
                "ActiveFlag": 1,
                "PurchasingWebServiceURL": f"http://vendor{i}.example.com",
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(vendors).to_csv(AW_DIR / "Purchasing.Vendor.csv", index=False)

    # 13. PurchaseOrderHeader
    po_headers = []
    for i in range(1, 21):
        po_headers.append(
            {
                "PurchaseOrderID": 100 + i,
                "RevisionNumber": 4,
                "Status": 4,  # Complete
                "EmployeeID": (i % 5) + 1,
                "VendorID": 100 + ((i % 10) + 1),
                "ShipMethodID": 1,
                "OrderDate": f"2022-{(i % 12) + 1:02d}-01 00:00:00",
                "ShipDate": f"2022-{(i % 12) + 1:02d}-05 00:00:00",
                "SubTotal": round(1200.00 + i * 150.0, 2),
                "TaxAmt": round(96.00 + i * 12.0, 2),
                "Freight": round(30.00 + i * 3.75, 2),
                "TotalDue": round(1326.00 + i * 165.75, 2),
                "ModifiedDate": "2022-01-01",
            }
        )
    pd.DataFrame(po_headers).to_csv(AW_DIR / "Purchasing.PurchaseOrderHeader.csv", index=False)

    # 14. PurchaseOrderDetail
    po_details = []
    pod_id = 1
    for i in range(1, 21):
        poid = 100 + i
        for j in range(2):
            prod_id = 500 + ((pod_id % 20) + 1)
            po_details.append(
                {
                    "PurchaseOrderID": poid,
                    "PurchaseOrderDetailID": pod_id,
                    "DueDate": f"2022-{(i % 12) + 1:02d}-10 00:00:00",
                    "OrderQty": 50,
                    "ProductID": prod_id,
                    "UnitPrice": round(150.00 + (prod_id - 500) * 20.5, 2),
                    "LineTotal": round(50 * (150.00 + (prod_id - 500) * 20.5), 2),
                    "ReceivedQty": 50.0,
                    "RejectedQty": 0.0,
                    "StockedQty": 50.0,
                    "ModifiedDate": "2022-01-01",
                }
            )
            pod_id += 1
    pd.DataFrame(po_details).to_csv(AW_DIR / "Purchasing.PurchaseOrderDetail.csv", index=False)

    print("AdventureWorks source dataset generated successfully.")


def generate_olist():
    OLIST_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating Olist source dataset...")

    # 1. Customers
    customers = []
    for i in range(1, 101):
        # Repeat customer_unique_id for some customers to reflect Olist structure
        unique_id = f"unique_cust_{(i % 80) + 1:04d}"
        customers.append(
            {
                "customer_id": f"cust_ord_{i:04d}",
                "customer_unique_id": unique_id,
                "customer_zip_code_prefix": 1000 + (i % 50),
                "customer_city": "sao paulo" if i % 2 == 0 else "rio de janeiro",
                "customer_state": "SP" if i % 2 == 0 else "RJ",
            }
        )
    pd.DataFrame(customers).to_csv(OLIST_DIR / "olist_customers_dataset.csv", index=False)

    # 2. Sellers
    sellers = []
    for i in range(1, 21):
        sellers.append(
            {
                "seller_id": f"seller_{i:04d}",
                "seller_zip_code_prefix": 2000 + i,
                "seller_city": "curitiba" if i % 3 == 0 else "sao paulo",
                "seller_state": "PR" if i % 3 == 0 else "SP",
            }
        )
    pd.DataFrame(sellers).to_csv(OLIST_DIR / "olist_sellers_dataset.csv", index=False)

    # 3. Products & Categories
    categories = [
        ("cama_mesa_banho", "bed_bath_table"),
        ("beleza_saude", "health_beauty"),
        ("esporte_lazer", "sports_leisure"),
        ("informatica_acessorios", "computers_accessories"),
        ("utilidades_domesticas", "housewares"),
    ]
    pd.DataFrame([{"product_category_name": c[0], "product_category_name_english": c[1]} for c in categories]).to_csv(
        OLIST_DIR / "product_category_name_translation.csv", index=False
    )

    products = []
    for i in range(1, 31):
        cat = categories[(i - 1) % len(categories)][0]
        products.append(
            {
                "product_id": f"prod_olist_{i:04d}",
                "product_category_name": cat,
                "product_name_lenght": 40 + i,
                "product_description_lenght": 200 + i * 10,
                "product_photos_qty": (i % 4) + 1,
                "product_weight_g": 500 + i * 50,
                "product_length_cm": 20 + i,
                "product_height_cm": 15 + i,
                "product_width_cm": 10 + i,
            }
        )
    pd.DataFrame(products).to_csv(OLIST_DIR / "olist_products_dataset.csv", index=False)

    # 4. Orders
    orders = []
    statuses = ["delivered", "delivered", "delivered", "shipped", "canceled"]
    for i in range(1, 101):
        cust_id = f"cust_ord_{i:04d}"
        status = statuses[(i - 1) % len(statuses)]
        dt_base = datetime(2017, 1, 1) + timedelta(days=i * 3)
        orders.append(
            {
                "order_id": f"order_olist_{i:04d}",
                "customer_id": cust_id,
                "order_status": status,
                "order_purchase_timestamp": dt_base.strftime("%Y-%m-%d %H:%M:%S"),
                "order_approved_at": (dt_base + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
                "order_delivered_carrier_date": (dt_base + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
                if status == "delivered"
                else None,
                "order_delivered_customer_date": (dt_base + timedelta(days=5)).strftime("%Y-%m-%d %H:%M:%S")
                if status == "delivered"
                else None,
                "order_estimated_delivery_date": (dt_base + timedelta(days=12)).strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    pd.DataFrame(orders).to_csv(OLIST_DIR / "olist_orders_dataset.csv", index=False)

    # 5. Order Items
    order_items = []
    for i in range(1, 101):
        order_id = f"order_olist_{i:04d}"
        num_items = (i % 2) + 1
        for item_seq in range(1, num_items + 1):
            prod_id = f"prod_olist_{(i % 30) + 1:04d}"
            seller_id = f"seller_{(i % 20) + 1:04d}"
            price = round(29.90 + (i * 2.5), 2)
            freight = round(12.00 + (i * 0.5), 2)
            order_items.append(
                {
                    "order_id": order_id,
                    "order_item_id": item_seq,
                    "product_id": prod_id,
                    "seller_id": seller_id,
                    "shipping_limit_date": "2017-12-31 00:00:00",
                    "price": price,
                    "freight_value": freight,
                }
            )
    pd.DataFrame(order_items).to_csv(OLIST_DIR / "olist_order_items_dataset.csv", index=False)

    # 6. Order Payments
    payments = []
    pay_types = ["credit_card", "boleto", "voucher", "debit_card"]
    for i in range(1, 101):
        order_id = f"order_olist_{i:04d}"
        ptype = pay_types[(i - 1) % len(pay_types)]
        val = round(41.90 + (i * 3.0), 2)
        payments.append(
            {
                "order_id": order_id,
                "payment_sequential": 1,
                "payment_type": ptype,
                "payment_installments": 1 if ptype != "credit_card" else (i % 6) + 1,
                "payment_value": val,
            }
        )
    pd.DataFrame(payments).to_csv(OLIST_DIR / "olist_order_payments_dataset.csv", index=False)

    # 7. Order Reviews
    reviews = []
    for i in range(1, 101):
        if i % 2 == 0:
            order_id = f"order_olist_{i:04d}"
            dt_base = datetime(2017, 1, 1) + timedelta(days=i * 3 + 6)
            reviews.append(
                {
                    "review_id": f"rev_{i:04d}",
                    "order_id": order_id,
                    "review_score": (i % 5) + 1,
                    "review_comment_title": "Good product" if i % 5 >= 3 else "Delayed",
                    "review_comment_message": "Satisfied with purchase" if i % 5 >= 3 else "Arrived late",
                    "review_creation_date": dt_base.strftime("%Y-%m-%d 00:00:00"),
                    "review_answer_timestamp": (dt_base + timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
                }
            )
    pd.DataFrame(reviews).to_csv(OLIST_DIR / "olist_order_reviews_dataset.csv", index=False)

    # 8. Geolocation
    geos = []
    for i in range(1, 51):
        geos.append(
            {
                "geolocation_zip_code_prefix": 1000 + i,
                "geolocation_lat": -23.5 + (i * 0.01),
                "geolocation_lng": -46.6 + (i * 0.01),
                "geolocation_city": "sao paulo",
                "geolocation_state": "SP",
            }
        )
    pd.DataFrame(geos).to_csv(OLIST_DIR / "olist_geolocation_dataset.csv", index=False)

    print("Olist source dataset generated successfully.")


def generate_olist_marketing():
    MKT_DIR.mkdir(parents=True, exist_ok=True)
    print("Generating Olist Marketing Funnel source dataset...")

    # 1. Qualified Leads (MQLs)
    mqls = []
    origins = ["organic_search", "paid_search", "social", "direct_traffic", "referral"]
    for i in range(1, 51):
        mql_id = f"mql_{i:04d}"
        dt_base = datetime(2017, 6, 1) + timedelta(days=i * 2)
        mqls.append(
            {
                "mql_id": mql_id,
                "first_contact_date": dt_base.strftime("%Y-%m-%d"),
                "landing_page_id": f"lp_{(i % 10) + 1:02d}",
                "origin": origins[(i - 1) % len(origins)],
            }
        )
    pd.DataFrame(mqls).to_csv(MKT_DIR / "olist_marketing_qualified_leads_dataset.csv", index=False)

    # 2. Closed Deals
    deals = []
    segments = ["health_beauty", "household_utilities", "audio_video_electronics", "sports_leisure"]
    lead_types = ["online_big", "online_medium", "online_small", "offline"]
    for i in range(1, 21):  # 20 closed deals out of 50 MQLs
        mql_id = f"mql_{i:04d}"
        seller_id = f"seller_{i:04d}"  # Links to Olist sellers seller_0001..seller_0020
        dt_base = datetime(2017, 6, 15) + timedelta(days=i * 2)
        deals.append(
            {
                "mql_id": mql_id,
                "seller_id": seller_id,
                "sdr_id": f"sdr_{(i % 5) + 1:02d}",
                "sr_id": f"sr_{(i % 4) + 1:02d}",
                "won_date": dt_base.strftime("%Y-%m-%d %H:%M:%S"),
                "business_segment": segments[(i - 1) % len(segments)],
                "lead_type": lead_types[(i - 1) % len(lead_types)],
                "lead_behaviour_profile": "cat",
                "has_company": True,
                "has_gtin": True,
                "average_stock": "1-5",
                "business_type": "reseller",
                "declared_product_catalog_size": 10 + i * 5,
                "declared_monthly_revenue": 5000 + i * 1000,
            }
        )
    pd.DataFrame(deals).to_csv(MKT_DIR / "olist_closed_deals_dataset.csv", index=False)

    print("Olist Marketing Funnel source dataset generated successfully.")


if __name__ == "__main__":
    generate_adventureworks()
    generate_olist()
    generate_olist_marketing()
    print("All source datasets ready.")
