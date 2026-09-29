# Executive Sales Analytics Dashboard

Executive e-commerce analytics project using SQL, Python, and Power BI.

## AI Logistics Intelligence

This repository now includes an AI logistics layer covering:

- Freight cost prediction
- Late-delivery risk prediction
- Late-delivery cause diagnosis
- Recommended operational actions
- Feature importance
- SQL logistics analysis
- Executive business insights report

### Python

See:

`python/ai_freight_delivery.py`

Install:

```bash
pip install -r python/requirements-ai.txt
```

Run:

```bash
python python/ai_freight_delivery.py --data-dir "PATH_TO_OLIST_DATA"
```

### Reports

- [AI Logistics Business Insights Report](reports/AI%20Logistics%20Business%20Insights%20Report.md)
- [AI Logistics Documentation](python/AI_LOGISTICS_AI.md)

### SQL

- [AI Logistics Insights SQL](sql/AI%20Logistics%20Insights.sql)

## Existing dashboard

- Power BI executive dashboard
- SQL analysis
- Python analysis notebook
- E-Commerce Business Intelligence Report


## Automated Logistics Assignment

Run the prediction models first, then run:

```bash
python python/logistics_optimizer.py --data-dir "PATH_TO_OLIST_DATA"
```

The optimizer automatically produces:

- nearest/most suitable eligible seller
- predicted freight
- late-delivery risk
- selected shipping carrier
- estimated carrier cost
- estimated carrier ETA
- decision explanation

Configuration:

`config/carriers.csv`

Optional exact geography:

`--geo-file PATH_TO_GEO.csv`

Results:

`ai_output/automated_logistics_assignments.csv`

`ai_output/carrier_options_by_order.csv`

See `python/AUTOMATED_LOGISTICS.md` for the full workflow.


## Colab — Real Olist Data

Notebook:

`colab/AI_Logistics_Real_Olist.ipynb`

It downloads the official Olist dataset directly from Kaggle, trains the AI models, uses Olist geolocation for seller/customer distance, and generates automated seller/carrier assignments.

[Open this notebook in Google Colab](https://colab.research.google.com/github/maroamratef/Executive-Sales-Analytics-Dashboard/blob/ai-freight-delivery/colab/AI_Logistics_Real_Olist.ipynb)

Note: the notebook can run the analytical assignment stage with the real Olist data. Actual carrier booking requires real carrier API credentials/integration, and the public Olist dataset does not contain historical carrier-company records.
