# Automated Seller + Shipping Company Assignment

## What it does

For an order, the optimizer automatically creates a decision:

**customer -> eligible seller -> distance -> predicted freight -> late risk -> shipping carrier -> expected cost/ETA**

The result is written to:

`ai_output/automated_logistics_assignments.csv`

and carrier alternatives to:

`ai_output/carrier_options_by_order.csv`

## 1. Automatic seller selection

Seller candidates come from sellers that have historically sold the product(s) in the order.

The seller score is:

`0.50 * distance + 0.20 * predicted_freight + 0.30 * late_risk`

Lower is better.

This means distance is the strongest component, while the AI also avoids a seller that is close but historically expected to be expensive or risky.

### Distance

With a geo file containing customer and seller latitude/longitude, the optimizer uses exact Haversine distance.

Geo file schema:

```text
entity_type,entity_id,lat,lon
customer,customer_id_here,-23.55,-46.63
seller,seller_id_here,-23.56,-46.64
```

Without coordinates, the system uses a transparent ZIP-prefix/city/state proximity proxy. That proxy is for ranking sellers only and is explicitly labelled in the output.

## 2. Automatic shipping-company selection

The Olist dataset does **not** contain historical carrier/shipping-company records. Therefore the carrier engine reads:

`config/carriers.csv`

You should replace the template names and commercial parameters with your actual carrier contracts and measured performance.

Required carrier fields:

- carrier_id
- carrier_name
- base_fee
- per_km
- per_kg
- max_weight_kg
- base_days
- days_per_500km
- enabled

The carrier score combines:

- estimated shipping cost
- predicted late risk
- expected transit time

Lower is better.

When exact coordinates are unavailable, the engine does not pretend the ZIP-prefix proxy is physical kilometers. In that case carrier price uses base fee + weight pricing and carrier ETA uses the configured base days.

## 3. Run the full system

First train the freight and late-delivery models:

```bash
python python/ai_freight_delivery.py --data-dir "PATH_TO_OLIST_DATA"
```

Then configure the carriers:

```text
config/carriers_template.csv -> config/carriers.csv
```

Fill in real carrier data.

Then run automated assignment:

```bash
python python/logistics_optimizer.py --data-dir "PATH_TO_OLIST_DATA"
```

For one order:

```bash
python python/logistics_optimizer.py --data-dir "PATH_TO_OLIST_DATA" --order-id "YOUR_ORDER_ID"
```

For exact geography:

```bash
python python/logistics_optimizer.py --data-dir "PATH_TO_OLIST_DATA" --geo-file "PATH_TO_GEO.csv"
```

## 4. Recommended production architecture

`New order
-> identify required products
-> find eligible sellers
-> calculate seller distance
-> estimate freight
-> predict late risk
-> rank sellers
-> select seller
-> rank eligible carriers
-> select carrier
-> create shipment
-> monitor live status
-> update risk
-> re-route/escalate if risk increases`

The last three steps require integration with the seller, carrier, order-management, and shipment-tracking systems.

## 5. What to automate next

The strongest production upgrade is a live re-optimization loop:

- At order creation: choose seller and carrier.
- At seller approval: recompute risk.
- At carrier handoff: update ETA.
- During transit: detect exception.
- Before SLA breach: automatically escalate or switch service when contractually possible.
- After delivery: store actual freight, ETA, and service outcome for model retraining.

That creates a closed-loop logistics AI rather than a one-time recommendation model.
