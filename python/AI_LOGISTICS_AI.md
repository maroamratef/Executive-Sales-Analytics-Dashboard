# AI Freight & Late-Delivery Intelligence

This module adds machine-learning decision support for freight cost and late-delivery risk.

## AI capabilities

### Freight cost prediction
Predicts observed `freight_value` from item price, product weight/dimensions, volume, category, seller/customer geography, same-state shipping, purchase timing, and time to shipping limit.

### Late-delivery prediction
Predicts the probability that an order will be delivered after its estimated date. The predictive model intentionally excludes final delivery timestamps and post-delivery delay fields to avoid target leakage.

### Late-cause diagnosis
For completed late orders, the diagnostic layer identifies the strongest observable operational driver among seller processing delay, carrier transit delay, tight delivery estimate, geographic complexity, heavy/bulky shipment, and high freight burden.

### Recommended action
Each cause maps to an operational response such as seller SLA monitoring, carrier/route review, delivery-buffer recalibration, regional fulfillment, packaging optimization, or freight-rate negotiation.

## Run

Install:

```bash
pip install -r python/requirements-ai.txt
```

Then:

```bash
python python/ai_freight_delivery.py --data-dir "PATH_TO_OLIST_DATA"
```

The script expects these Olist files:

- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_customers_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`

Outputs are written to `ai_output/`.

## Main outputs

- `freight_cost_model.joblib`
- `late_delivery_model.joblib`
- `freight_predictions.csv`
- `late_delivery_predictions.csv`
- `freight_feature_importance.csv`
- `late_delivery_feature_importance.csv`
- `late_delivery_causes.csv`
- `late_cause_summary.csv`
- `recommended_actions.json`
- `model_summary.json`

## Power BI page

Add an **AI Logistics Command Center** page with:

1. Actual vs predicted freight cost
2. Freight as % of sales
3. Late-delivery risk distribution
4. Late orders by AI cause
5. Average days late by cause
6. Order-level recommended action table
7. High-risk order list

## Important data limitation

`freight_value` is the observed freight charge/value in the Olist dataset, not an internal accounting measure of carrier cost. For a production model, add carrier, route distance, service level, fuel surcharge, warehouse, package dimensions, and negotiated contract-rate data.
