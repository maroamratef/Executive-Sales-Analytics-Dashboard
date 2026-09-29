# AI Freight & Late-Delivery Business Insights Report

## Executive summary

The existing dashboard identifies two important logistics issues: freight represents 16.60% of revenue, while the analysis reports a 7.61% late-delivery rate and 12.02 average delivery days.

| KPI | Observed value |
| --- | ---: |
| Revenue | 14.27M |
| Orders | 99,441 |
| Customers | 96,096 |
| Average Order Value | 143.54 |
| Average Delivery Time | 12.02 days |
| Late Delivery Rate | 7.61% |
| Freight Cost / Revenue | 16.60% |
| Repeat Customers | 2,997 |
| New Customers | 93,099 |
| Estimated Profit* | 4.28M |

*Estimated profit is based on the project's 30% gross-margin assumption; the source dataset does not contain true product cost.

## 1. Freight-cost opportunity

Freight is a material part of the commercial economics. The AI freight model predicts observed freight_value using product price, weight, dimensions, calculated volume, category, seller/customer geography, same-state shipping, purchase timing, and shipping-limit timing.

### Business questions

- Which products have unusually high freight relative to item value?
- Which origin/destination state combinations have the highest freight burden?
- Does heavy or bulky merchandise explain high freight charges?
- Are cross-state orders systematically more expensive?
- Which categories have freight economics that require operational intervention?

### Recommended actions

Heavy or bulky products: optimize packaging, compare dimensional-weight rates, and negotiate carrier rules for frequent bulky SKUs.

High freight-to-price ratios: identify SKU/lane combinations where shipping consumes a large share of selling value, then review packaging, consolidation, carrier choice, and pricing.

Cross-state shipments: analyze slow and expensive lanes and evaluate regional fulfillment or closer inventory placement.

## 2. Late-delivery opportunity

The project reports approximately 7.61% late deliveries and 12.02 average delivery days. The new AI system converts historical order information into a pre-delivery late-risk probability so operations can intervene before the SLA is missed.

Suggested starting operating bands:

| Risk | Operating response |
| --- | --- |
| Below 0.30 | Normal monitoring |
| 0.30 to 0.60 | Exception monitoring |
| Above 0.60 | Proactive intervention |

These bands are starting thresholds and should be calibrated using the business cost of false alarms and missed late orders.

## 3. Why orders become late

The diagnostic layer separates six observable driver groups.

### Seller processing delay
Long approval-to-carrier handoff indicates that delivery time is being consumed before carrier transit starts.
Action: monitor seller SLA, create seller alerts, and escalate repeated slow handoffs.

### Carrier transit delay
Long carrier-to-customer time indicates transport or last-mile delay after handoff.
Action: compare route and carrier performance and intervene on high-risk lanes.

### Tight delivery estimate
A short promised delivery window can leave little tolerance for normal variation.
Action: recalibrate estimated delivery dates using historical lane performance.

### Geographic complexity
Cross-state movement can increase transport distance, cost, and uncertainty.
Action: analyze expensive and slow lanes and evaluate regional fulfillment.

### Heavy or bulky shipment
High weight or package volume can increase transport cost and handling complexity.
Action: optimize packaging and compare dimensional-weight carrier pricing.

### High freight burden
Freight that is high relative to item value can damage order economics even when delivery is on time.
Action: monitor freight-to-price ratio by SKU and lane, consolidate where practical, and renegotiate expensive routes.

## 4. Management view: risk + cost + cause

The strongest decision-support view should combine three dimensions for every order:

Late risk + freight burden + primary cause.

Example management table:

| Order | Late risk | Freight burden | Primary cause | Recommended response |
| --- | ---: | ---: | --- | --- |
| Order A | High | High | Carrier transit | Review carrier/route |
| Order B | High | Low | Seller processing | Escalate seller SLA |
| Order C | Medium | High | Bulky shipment | Packaging/carrier review |
| Order D | High | High | Geographic complexity | Regional fulfillment analysis |
| Order E | Medium | High | Tight estimate | Recalibrate delivery promise |

## 5. Customer-retention analysis opportunity

The project contains 96,096 unique customers, with 2,997 repeat customers and 93,099 single-purchase customers in the current analysis.

The next business test should connect delivery experience with review score and repeat purchase behavior:

Delivery performance -> review outcome -> repeat purchase.

This will determine whether late delivery is merely an operations issue or is also associated with weaker customer retention.

## 6. AI Logistics Command Center

Recommended Power BI page:

Top KPIs: Revenue, Freight Cost, Freight %, Late %, Average Delivery Days, High-Risk Orders.

Freight Intelligence: actual vs predicted freight, freight-to-price ratio, freight by customer state, freight by seller state, freight by category.

Delivery Intelligence: late-risk distribution, late rate by state, late rate by category, average days late.

Root Cause & Action: Order ID, Late Risk, Freight, Freight Ratio, Cause, Days Late, Recommended Action.

## 7. Important modeling note

The original notebook merges order-level and item-level tables. Because one order can contain multiple item rows, order KPIs should ideally be calculated from a distinct order-level dataset to avoid duplicated-order weighting.

The new late-delivery prediction pipeline aggregates item information to order level and intentionally excludes the final delivery date and actual days-late fields from prediction features. This avoids obvious target leakage.

The freight model predicts the dataset's observed freight_value. It is not a true internal carrier-cost accounting model because the Olist data does not provide negotiated carrier rates, fuel surcharge, route distance, warehouse cost, or internal logistics cost.

## 8. Target operating model

Order data -> feature engineering -> freight prediction -> late-risk prediction -> root-cause diagnosis -> recommended intervention -> measured outcome.

The measured outcome should be fed back into the process so the business can track whether interventions reduce freight cost, late deliveries, days late, and customer dissatisfaction.

## 10. Automated seller and shipping-company assignment

The new optimizer turns the analysis into an order-routing decision.

For each order:

`Customer -> eligible sellers -> seller proximity -> predicted freight -> late risk -> selected seller -> carrier options -> selected carrier`

### Seller assignment

The engine creates a candidate seller pool from sellers that historically handled the products in the order.

The default seller score is:

`50% proximity + 20% predicted freight + 30% late-delivery risk`

A lower score is preferred.

When coordinates are supplied, proximity is calculated with Haversine distance. With the raw Olist files, the system uses a ZIP-prefix/city/state proxy and labels it explicitly so it is not confused with physical distance.

### Carrier assignment

The optimizer reads carrier contracts and operating assumptions from:

`config/carriers.csv`

It evaluates:

- carrier base fee
- price per kilometer
- price per kilogram
- maximum supported weight
- base transit days
- distance-based transit time
- late-risk penalty

The selected carrier minimizes the combined carrier score.

Because the Olist dataset has no carrier history, the carrier table must be populated with the organization's actual shipping companies, contract rates, capacity limits, and measured delivery performance before using the result as a real operational decision.

### Operational automation

The recommended production flow is:

`New order
-> identify products
-> find eligible sellers
-> select seller
-> select carrier
-> create shipment
-> monitor status
-> recalculate risk
-> trigger exception
-> measure actual result`

The current repository implements the analytical selection stage. Actual shipment creation, carrier booking, and automatic rerouting require API integrations with the company's order-management, seller, and carrier systems.
