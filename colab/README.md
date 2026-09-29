# Run AI Logistics on Real Olist Data in Google Colab

## Open the notebook

The notebook is:

`colab/AI_Logistics_Real_Olist.ipynb`

Open it from the repository branch `ai-freight-delivery` using the Colab link in the project documentation.

## What it downloads

The notebook downloads the official Kaggle dataset:

Olist Brazilian E-Commerce Public Dataset

It automatically finds:

- orders
- order items
- customers
- products
- sellers
- geolocation

The official dataset contains approximately 100k orders and the geolocation file maps ZIP-code prefixes to latitude/longitude observations. citeturn819213search0

## What it runs

1. Correct order-level business KPIs.
2. Freight-cost regression.
3. Late-delivery classification.
4. Freight feature importance.
5. Late-delivery feature importance.
6. ZIP-prefix geolocation and Haversine seller distance.
7. Automated seller selection.
8. Automated carrier selection.
9. CSV outputs for Power BI.

## Kaggle access

KaggleHub supports downloading Kaggle resources and can use a Colab Secret named `KAGGLE_API_TOKEN` when authentication is required. citeturn579587search0

Do not put your token in the notebook code.

## Carrier limitation

The Olist public dataset does not provide historical carrier/shipping-company records. Therefore the notebook uses `config/carriers.csv` as the carrier decision interface. Replace the placeholder carrier names, prices, capacities, and ETA assumptions with real shipping-company data before treating carrier selection as a production decision.

## Outputs

`ai_output/model_summary.json`

`ai_output/freight_feature_importance.csv`

`ai_output/late_delivery_feature_importance.csv`

`ai_output/late_delivery_causes.csv`

`ai_output/automated_logistics_assignments.csv`

`ai_output/carrier_options_by_order.csv`