-- AI Logistics Business Insights
-- Use after the base Olist tables have been loaded into EcommerceAnalytics.

USE EcommerceAnalytics;

-- 1. Freight overview
SELECT
    COUNT(DISTINCT oi.order_id) AS Orders,
    SUM(oi.freight_value) AS TotalFreight,
    SUM(oi.price) AS ProductRevenue,
    SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0) * 100 AS FreightPctOfProductRevenue,
    AVG(oi.freight_value) AS AvgFreightPerItem
FROM OrderItems oi;

-- 2. Freight burden by product category
SELECT TOP 20
    p.product_category_name AS ProductCategory,
    COUNT(DISTINCT oi.order_id) AS Orders,
    SUM(oi.price) AS ProductRevenue,
    SUM(oi.freight_value) AS FreightCost,
    SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0) * 100 AS FreightPct
FROM OrderItems oi
JOIN Products p ON oi.product_id = p.product_id
GROUP BY p.product_category_name
ORDER BY FreightPct DESC;

-- 3. Freight burden by customer state
SELECT
    c.customer_state AS CustomerState,
    COUNT(DISTINCT o.order_id) AS Orders,
    SUM(oi.price) AS ProductRevenue,
    SUM(oi.freight_value) AS FreightCost,
    SUM(oi.freight_value) / NULLIF(SUM(oi.price), 0) * 100 AS FreightPct
FROM Orders o
JOIN Customers c ON o.customer_id = c.customer_id
JOIN OrderItems oi ON o.order_id = oi.order_id
GROUP BY c.customer_state
ORDER BY FreightPct DESC;

-- 4. Late-delivery overview at distinct-order level
SELECT
    COUNT(*) AS DeliveredOrders,
    SUM(CASE WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1 ELSE 0 END) AS LateOrders,
    CAST(SUM(CASE WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1 ELSE 0 END) AS DECIMAL(18,4))
        / NULLIF(COUNT(*),0) * 100 AS LateDeliveryPct,
    AVG(CAST(DATEDIFF(day, order_purchase_timestamp, order_delivered_customer_date) AS DECIMAL(18,2))) AS AvgDeliveryDays,
    AVG(CASE
        WHEN order_delivered_customer_date > order_estimated_delivery_date
        THEN CAST(DATEDIFF(day, order_estimated_delivery_date, order_delivered_customer_date) AS DECIMAL(18,2))
        ELSE 0
    END) AS AvgDaysLateAcrossDeliveredOrders
FROM Orders
WHERE order_delivered_customer_date IS NOT NULL
  AND order_estimated_delivery_date IS NOT NULL;

-- 5. Seller processing delay
SELECT TOP 20
    seller.seller_id AS SellerID,
    seller.seller_state AS SellerState,
    COUNT(DISTINCT o.order_id) AS DeliveredOrders,
    AVG(CAST(DATEDIFF(hour, o.order_approved_at, o.order_delivered_carrier_date) AS DECIMAL(18,2))) AS AvgApprovalToCarrierHours,
    SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END) AS LateOrders
FROM Orders o
JOIN OrderItems oi ON o.order_id = oi.order_id
JOIN Sellers seller ON oi.seller_id = seller.seller_id
WHERE o.order_approved_at IS NOT NULL
  AND o.order_delivered_carrier_date IS NOT NULL
  AND o.order_delivered_customer_date IS NOT NULL
GROUP BY seller.seller_id, seller.seller_state
ORDER BY AvgApprovalToCarrierHours DESC;

-- 6. Geographic complexity: same state vs cross state
SELECT
    CASE WHEN c.customer_state = s.seller_state THEN 'Same State' ELSE 'Cross State' END AS ShippingType,
    COUNT(DISTINCT o.order_id) AS Orders,
    AVG(CAST(DATEDIFF(day, o.order_purchase_timestamp, o.order_delivered_customer_date) AS DECIMAL(18,2))) AS AvgDeliveryDays,
    CAST(SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END) AS DECIMAL(18,4))
        / NULLIF(COUNT(DISTINCT o.order_id), 0) * 100 AS LateDeliveryPct,
    SUM(oi.freight_value) / NULLIF(SUM(oi.price),0) * 100 AS FreightPct
FROM Orders o
JOIN Customers c ON o.customer_id = c.customer_id
JOIN OrderItems oi ON o.order_id = oi.order_id
JOIN Sellers s ON oi.seller_id = s.seller_id
WHERE o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY CASE WHEN c.customer_state = s.seller_state THEN 'Same State' ELSE 'Cross State' END;

-- 7. Product physical characteristics linked to freight
SELECT TOP 20
    p.product_category_name AS ProductCategory,
    AVG(TRY_CONVERT(DECIMAL(18,2), p.product_weight_g)) AS AvgWeightG,
    AVG(
        TRY_CONVERT(DECIMAL(18,2), p.product_length_cm)
        * TRY_CONVERT(DECIMAL(18,2), p.product_height_cm)
        * TRY_CONVERT(DECIMAL(18,2), p.product_width_cm)
    ) AS AvgVolumeCm3,
    AVG(oi.freight_value) AS AvgFreight
FROM Products p
JOIN OrderItems oi ON p.product_id = oi.product_id
GROUP BY p.product_category_name
ORDER BY AvgFreight DESC;

-- 8. High-value logistics exception orders
SELECT TOP 100
    o.order_id AS OrderID,
    c.customer_state AS CustomerState,
    SUM(oi.price) AS ProductRevenue,
    SUM(oi.freight_value) AS FreightCost,
    SUM(oi.freight_value) / NULLIF(SUM(oi.price),0) * 100 AS FreightPct,
    DATEDIFF(day, o.order_purchase_timestamp, o.order_delivered_customer_date) AS DeliveryDays,
    CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 ELSE 0 END AS IsLate,
    CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN
            DATEDIFF(day, o.order_estimated_delivery_date, o.order_delivered_customer_date)
        ELSE 0
    END AS DaysLate
FROM Orders o
JOIN Customers c ON o.customer_id = c.customer_id
JOIN OrderItems oi ON o.order_id = oi.order_id
WHERE o.order_delivered_customer_date IS NOT NULL
GROUP BY o.order_id, c.customer_state, o.order_purchase_timestamp, o.order_delivered_customer_date, o.order_estimated_delivery_date
ORDER BY FreightPct DESC, IsLate DESC;