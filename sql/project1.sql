USE EcommerceAnalytics;
GO

IF OBJECT_ID('FactSales','U') IS NOT NULL
DROP TABLE FactSales;

IF OBJECT_ID('DimCustomer','U') IS NOT NULL
DROP TABLE DimCustomer;

IF OBJECT_ID('DimProduct','U') IS NOT NULL
DROP TABLE DimProduct;

IF OBJECT_ID('DimSeller','U') IS NOT NULL
DROP TABLE DimSeller;

IF OBJECT_ID('DimDate','U') IS NOT NULL
DROP TABLE DimDate;



CREATE TABLE DimCustomer
(
    CustomerKey INT IDENTITY(1,1) PRIMARY KEY,

    customer_id VARCHAR(50) NOT NULL,

    customer_unique_id VARCHAR(50),

    customer_city VARCHAR(100),

    customer_state CHAR(2)
);



INSERT INTO DimCustomer
(
customer_id,
customer_unique_id,
customer_city,
customer_state
)

SELECT DISTINCT

customer_id,
customer_unique_id,
customer_city,
customer_state

FROM Customers;



SELECT TOP 10 *
FROM DimCustomer;




CREATE TABLE DimProduct
(
ProductKey INT IDENTITY(1,1) PRIMARY KEY,

product_id VARCHAR(50),

product_category_name VARCHAR(200),

product_weight_g FLOAT,

product_length_cm FLOAT,

product_height_cm FLOAT,

product_width_cm FLOAT
);



INSERT INTO DimProduct

SELECT DISTINCT

product_id,
product_category_name,
product_weight_g,
product_length_cm,
product_height_cm,
product_width_cm

FROM Products;



CREATE TABLE DimSeller
(
SellerKey INT IDENTITY(1,1) PRIMARY KEY,

seller_id VARCHAR(50),

seller_city VARCHAR(100),

seller_state CHAR(2)
);



INSERT INTO DimSeller

SELECT DISTINCT

seller_id,
seller_city,
seller_state

FROM Sellers;



CREATE TABLE DimDate
(
DateKey INT PRIMARY KEY,

Date DATE,

DayNumber INT,

MonthNumber INT,

MonthName VARCHAR(20),

QuarterNumber INT,

YearNumber INT
);


DECLARE @Date DATE='2016-01-01';

WHILE @Date<='2019-12-31'
BEGIN

INSERT INTO DimDate

VALUES

(
CONVERT(INT,FORMAT(@Date,'yyyyMMdd')),
@Date,
DAY(@Date),
MONTH(@Date),
DATENAME(MONTH,@Date),
DATEPART(QUARTER,@Date),
YEAR(@Date)
);

SET @Date=DATEADD(DAY,1,@Date);

END;



CREATE TABLE FactSales
(
SalesKey INT IDENTITY(1,1) PRIMARY KEY,

CustomerKey INT,

ProductKey INT,

SellerKey INT,

DateKey INT,

order_id VARCHAR(50),

price DECIMAL(10,2),

freight_value DECIMAL(10,2),

payment_value DECIMAL(10,2),

quantity INT,

review_score INT,

order_status VARCHAR(30)
);



INSERT INTO FactSales
(
CustomerKey,
ProductKey,
SellerKey,
DateKey,
order_id,
price,
freight_value,
payment_value,
quantity,
review_score,
order_status
)

SELECT

dc.CustomerKey,

dp.ProductKey,

ds.SellerKey,

CONVERT(
INT,
CONVERT(
CHAR(8),
CAST(o.order_purchase_timestamp AS DATE),
112
)),

o.order_id,

oi.price,

oi.freight_value,

p.payment_value,

oi.order_item_id,

r.review_score,

o.order_status

FROM Orders o

INNER JOIN OrderItems oi

ON o.order_id=oi.order_id

LEFT JOIN Payments p

ON o.order_id=p.order_id

LEFT JOIN Reviews r

ON o.order_id=r.order_id

INNER JOIN DimCustomer dc

ON o.customer_id=dc.customer_id

INNER JOIN DimProduct dp

ON oi.product_id=dp.product_id

INNER JOIN DimSeller ds

ON oi.seller_id=ds.seller_id;


ALTER TABLE FactSales
ADD CONSTRAINT FK_FactSales_Customer
FOREIGN KEY(CustomerKey)
REFERENCES DimCustomer(CustomerKey);

ALTER TABLE FactSales
ADD CONSTRAINT FK_FactSales_Product
FOREIGN KEY(ProductKey)
REFERENCES DimProduct(ProductKey);

ALTER TABLE FactSales
ADD CONSTRAINT FK_FactSales_Seller
FOREIGN KEY(SellerKey)
REFERENCES DimSeller(SellerKey);

ALTER TABLE FactSales
ADD CONSTRAINT FK_FactSales_Date
FOREIGN KEY(DateKey)
REFERENCES DimDate(DateKey);


CREATE INDEX IX_FactSales_Customer
ON FactSales(CustomerKey);

CREATE INDEX IX_FactSales_Product
ON FactSales(ProductKey);

CREATE INDEX IX_FactSales_Seller
ON FactSales(SellerKey);

CREATE INDEX IX_FactSales_Date
ON FactSales(DateKey);

ALTER TABLE FactSales
ADD IsLateDelivery INT;

UPDATE fs
SET fs.IsLateDelivery =
    CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN 1
        ELSE 0
    END
FROM FactSales fs
INNER JOIN Orders o
    ON fs.order_id = o.order_id;

ALTER TABLE FactSales
ADD DeliveryDays INT;

UPDATE fs
SET fs.DeliveryDays =
    CASE
        WHEN o.order_delivered_customer_date IS NULL THEN NULL
        ELSE DATEDIFF(
            DAY,
            CAST(o.order_purchase_timestamp AS DATETIME),
            CAST(o.order_delivered_customer_date AS DATETIME)
        )
    END
FROM FactSales fs
INNER JOIN Orders o
    ON fs.order_id = o.order_id;
