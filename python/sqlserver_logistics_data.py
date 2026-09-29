"""
SQL Server connector for the Executive Sales Analytics Olist project.

Reads the existing EcommerceAnalytics database instead of requiring raw CSV
copies. The schema matches the repository SQL scripts:
Customers, Orders, OrderItems, Products, Sellers.

Connection is supplied through environment variables so credentials are not
stored in the repository.

Required:
    OLIST_SQL_SERVER
Optional:
    OLIST_SQL_DATABASE=EcommerceAnalytics
    OLIST_SQL_DRIVER=ODBC Driver 18 for SQL Server
    OLIST_SQL_TRUSTED=true
    OLIST_SQL_USERNAME
    OLIST_SQL_PASSWORD

For SQL authentication:
    OLIST_SQL_TRUSTED=false
    OLIST_SQL_USERNAME=...
    OLIST_SQL_PASSWORD=...

For Windows integrated authentication:
    OLIST_SQL_TRUSTED=true
"""

from __future__ import annotations

import os
from typing import Dict

import pandas as pd
import pyodbc


TABLES = {
    "orders": "Orders",
    "items": "OrderItems",
    "customers": "Customers",
    "products": "Products",
    "sellers": "Sellers",
}


def _connection_string() -> str:
    server = os.getenv("OLIST_SQL_SERVER")
    if not server:
        raise RuntimeError(
            "Set OLIST_SQL_SERVER, for example 'localhost' or "
            "'localhost\\SQLEXPRESS'."
        )

    database = os.getenv(
        "OLIST_SQL_DATABASE",
        "EcommerceAnalytics",
    )
    driver = os.getenv(
        "OLIST_SQL_DRIVER",
        "ODBC Driver 18 for SQL Server",
    )
    trusted = os.getenv(
        "OLIST_SQL_TRUSTED",
        "true",
    ).lower() in {"1", "true", "yes"}

    if trusted:
        return (
            f"DRIVER={{{driver}}};"
            f"SERVER={server};"
            f"DATABASE={database};"
            "Trusted_Connection=yes;"
            "TrustServerCertificate=yes;"
        )

    username = os.getenv("OLIST_SQL_USERNAME")
    password = os.getenv("OLIST_SQL_PASSWORD")

    if not username or not password:
        raise RuntimeError(
            "SQL authentication requires OLIST_SQL_USERNAME and "
            "OLIST_SQL_PASSWORD."
        )

    return (
        f"DRIVER={{{driver}}};"
        f"SERVER={server};"
        f"DATABASE={database};"
        f"UID={username};"
        f"PWD={password};"
        "TrustServerCertificate=yes;"
    )


def load_sqlserver_data() -> Dict[str, pd.DataFrame]:
    connection_string = _connection_string()

    queries = {
        "orders": """
            SELECT
                order_id,
                customer_id,
                order_status,
                order_purchase_timestamp,
                order_approved_at,
                order_delivered_carrier_date,
                order_delivered_customer_date,
                order_estimated_delivery_date
            FROM dbo.Orders;
        """,
        "items": """
            SELECT
                order_id,
                order_item_id,
                product_id,
                seller_id,
                shipping_limit_date,
                price,
                freight_value
            FROM dbo.OrderItems;
        """,
        "customers": """
            SELECT
                customer_id,
                customer_unique_id,
                customer_zip_code_prefix,
                customer_city,
                customer_state
            FROM dbo.Customers;
        """,
        "products": """
            SELECT
                product_id,
                product_category_name,
                product_name_lenght,
                product_description_lenght,
                product_photos_qty,
                product_weight_g,
                product_length_cm,
                product_height_cm,
                product_width_cm
            FROM dbo.Products;
        """,
        "sellers": """
            SELECT
                seller_id,
                seller_zip_code_prefix,
                seller_city,
                seller_state
            FROM dbo.Sellers;
        """,
    }

    with pyodbc.connect(
        connection_string,
        timeout=15,
    ) as connection:
        return {
            name: pd.read_sql_query(
                query,
                connection,
            )
            for name, query in queries.items()
        }
