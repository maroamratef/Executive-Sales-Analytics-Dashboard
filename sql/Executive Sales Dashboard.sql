CREATE DATABASE EcommerceAnalytics;
USE EcommerceAnalytics;

CREATE TABLE Customers (
    customer_id VARCHAR(50) PRIMARY KEY,
    customer_unique_id VARCHAR(50),
    customer_zip_code_prefix VARCHAR(10),
    customer_city VARCHAR(100),
    customer_state CHAR(2)
);

CREATE TABLE Orders (
    order_id VARCHAR(50) PRIMARY KEY,
    customer_id VARCHAR(50),
    order_status VARCHAR(30),
    order_purchase_timestamp VARCHAR(30),
    order_approved_at VARCHAR(30),
    order_delivered_carrier_date VARCHAR(30),
    order_delivered_customer_date VARCHAR(30),
    order_estimated_delivery_date VARCHAR(30)
);
CREATE TABLE OrderItems (

order_id VARCHAR(50),

order_item_id INT,

product_id VARCHAR(50),

seller_id VARCHAR(50),

shipping_limit_date DATETIME,

price FLOAT,

freight_value FLOAT

);


CREATE TABLE Products (
    product_id VARCHAR(50) PRIMARY KEY,
    product_category_name VARCHAR(100),
    product_name_lenght VARCHAR(20),
    product_description_lenght VARCHAR(20),
    product_photos_qty VARCHAR(20),
    product_weight_g VARCHAR(20),
    product_length_cm VARCHAR(20),
    product_height_cm VARCHAR(20),
    product_width_cm VARCHAR(20)
);
SELECT
    product_id,
    TRY_CONVERT(INT, product_name_lenght) AS product_name_length,
    TRY_CONVERT(INT, product_description_lenght) AS product_description_length,
    TRY_CONVERT(INT, product_photos_qty) AS product_photos_qty,
    TRY_CONVERT(INT, product_weight_g) AS product_weight_g,
    TRY_CONVERT(DECIMAL(10,2), product_length_cm) AS product_length_cm,
    TRY_CONVERT(DECIMAL(10,2), product_height_cm) AS product_height_cm,
    TRY_CONVERT(DECIMAL(10,2), product_width_cm) AS product_width_cm
FROM Products;

CREATE TABLE Sellers (

    seller_id VARCHAR(50) PRIMARY KEY,

    seller_zip_code_prefix VARCHAR(10),

    seller_city VARCHAR(100),

    seller_state CHAR(2)

);

CREATE TABLE Reviews_Staging (
    review_id VARCHAR(50),
    order_id VARCHAR(50),
    review_score VARCHAR(10),
    review_comment_title NVARCHAR(MAX),
    review_comment_message NVARCHAR(MAX),
    review_creation_date VARCHAR(50),
    review_answer_timestamp VARCHAR(50)
);


CREATE TABLE Payments (

    order_id VARCHAR(50),

    payment_sequential INT,

    payment_type VARCHAR(30),

    payment_installments INT,

    payment_value DECIMAL(10,2),

    PRIMARY KEY (order_id, payment_sequential),

    CONSTRAINT FK_Payments_Orders
        FOREIGN KEY (order_id)
        REFERENCES Orders(order_id)

);

--Data Quality Checks
--Check for duplicates.
SELECT
order_id,
COUNT(*)
FROM [dbo].[reviews]
GROUP BY order_id
HAVING COUNT(*)>1;

--Missing values.
SELECT *

FROM [dbo].[Orders]

WHERE order_delivered_customer_date IS NULL;

--Orders per status.
SELECT

order_status,

COUNT(*)

FROM Orders

GROUP BY order_status;

--Delivery days
ALTER TABLE Orders

ADD DeliveryDays INT;

UPDATE [dbo].[Orders]
SET DeliveryDays =
DATEDIFF(day,
order_purchase_timestamp,
order_delivered_customer_date);

--Late delivery
ALTER TABLE Orders

ADD IsLateDelivery INT;


UPDATE Orders

SET IsLateDelivery=

CASE

WHEN order_delivered_customer_date>

order_estimated_delivery_date

THEN 1

ELSE 0

END;

--explortary data
--Monthly Revenue
SELECT

YEAR(o.order_purchase_timestamp) AS Year,

MONTH(o.order_purchase_timestamp) AS Month,

SUM(oi.price) Revenue

FROM Orders o

JOIN OrderItems oi

ON o.order_id=oi.order_id

GROUP BY

YEAR(o.order_purchase_timestamp),

MONTH(o.order_purchase_timestamp)

ORDER BY

Year,

Month;
SELECT COUNT(*) AS OrdersCount FROM Orders;

SELECT COUNT(*) AS OrderItemsCount FROM OrderItems;

SELECT COUNT(*) AS ReviewsCount FROM Reviews;

--Revenue by State
SELECT

c.customer_state,

SUM(oi.price) Revenue

FROM Customers c

JOIN Orders o

ON c.customer_id=o.customer_id

JOIN OrderItems oi

ON o.order_id=oi.order_id

GROUP BY

c.customer_state

ORDER BY Revenue DESC;

--Top Products
SELECT TOP 20

p.product_category_name,

SUM(oi.price) Revenue

FROM Products p

JOIN OrderItems oi

ON p.product_id=oi.product_id

GROUP BY

p.product_category_name

ORDER BY Revenue DESC;

--Average Order Value
SELECT

SUM(price)/COUNT(DISTINCT order_id)

AS AverageOrderValue

FROM OrderItems;

--Delivery Performance
SELECT

AVG(DeliveryDays)

AS AvgDeliveryDays,

SUM(IsLateDelivery)

AS LateOrders

FROM Orders;
