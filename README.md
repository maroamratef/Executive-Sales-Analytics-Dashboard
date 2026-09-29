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


## Real Olist automation — no Kaggle API

New Colab:

[Open AI Logistics Automation in Google Colab](https://colab.research.google.com/github/maroamratef/Executive-Sales-Analytics-Dashboard/blob/ai-freight-delivery/colab/AI_Logistics_Automation_Real_Olist_No_Kaggle_API.ipynb)

The notebook asks you to upload the Olist `archive.zip` directly. It then:

- trains freight and late-delivery AI on the real data
- finds the nearest eligible seller using Olist geolocation
- requests live Brazilian carrier quotes from Frenet when `FRENET_TOKEN` is configured
- ranks shipping services by cost, ETA, and late risk
- recommends products based on purchased items
- generates a customer email containing the selected seller, carrier, quote/ETA, and recommendations
- sends email only when `RESEND_API_KEY`, `EMAIL_FROM`, and an authorized `customer_id,email` mapping are supplied

Carrier API and email credentials are intentionally not stored in the repository.

## Production API layer

The project now includes a FastAPI gateway in `api/main.py`.

### Endpoints

```text
GET  /health
GET  /recommendations/{customer_id}
POST /shipping/quote
POST /orders/{order_id}/route
POST /orders/{order_id}/email
POST /orders/{order_id}/automate
POST /routes/matrix
```

Run:

```bash
pip install -r api/requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Swagger UI:

`http://localhost:8000/docs`

### External integrations

- Frenet: live Brazilian freight/carrier quotation. The documented quote API requires a client token and accepts origin CEP, destination CEP, invoice value and shipment items. citeturn362449view0turn799717search8
- Resend: transactional customer email. citeturn629030search0
- Google Routes API: optional road distance and traffic-aware route matrix. citeturn618215search1turn618215search2

### Private data required for live automation

The public Olist dataset provides ZIP prefixes, not full 8-digit CEPs, and it does not contain customer email addresses or historical carrier-account data.

For live operation, provide:

`config/customer_emails.csv`
`config/seller_ceps.csv`

and the corresponding Frenet/Resend/Google credentials through environment variables.

The API will not invent missing email addresses, full CEPs, carrier credentials, or private customer data.