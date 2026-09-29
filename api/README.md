# Olist AI Logistics API

This FastAPI service turns the Colab/model workflow into callable APIs.

## Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| GET | /health | Service/configuration health |
| GET | /recommendations/{customer_id} | Product recommendations from purchase patterns |
| POST | /shipping/quote | Live Frenet carrier/service quotation |
| POST | /orders/{order_id}/route | Select nearest/most suitable seller + live carrier options |
| POST | /orders/{order_id}/email | Send personalized customer email |
| POST | /orders/{order_id}/automate | Run routing + recommendations + optional email |
| POST | /routes/matrix | Optional Google road-distance/traffic matrix |

## Run locally

Create a virtual environment and install:

```bash
pip install -r api/requirements.txt
```

Set environment variables from:

`api/.env.example`

Then run:

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Open:

`http://localhost:8000/docs`

## Real data

Set `DATA_DIR` to the folder containing:

- olist_orders_dataset.csv
- olist_order_items_dataset.csv
- olist_customers_dataset.csv
- olist_products_dataset.csv
- olist_sellers_dataset.csv
- olist_geolocation_dataset.csv

Set `AI_OUTPUT_DIR` to the directory containing:

- freight_cost_model.joblib
- late_delivery_model.joblib

## Frenet

The live quote endpoint is the documented Frenet shipping quote service. Frenet requires a client token; current platform integrations may also require a partner token depending on endpoint/account setup. The documented quote request contains SellerCEP, RecipientCEP, ShipmentInvoiceValue and ShippingItemArray. citeturn362449view0turn799717search8

The Olist public data only has five-digit ZIP prefixes, while a live Brazilian CEP quote requires an eight-digit CEP. Therefore production routing should obtain the full seller/customer CEP from the seller/order-management/CRM system instead of padding the Olist prefix with zeros.

## Resend

The email endpoint calls the Resend REST API. Keep `RESEND_API_KEY` and `EMAIL_FROM` in environment variables. Resend's current API supports sending transactional messages through its REST endpoint. citeturn629030search0

The public Olist customer dataset does not contain email addresses. Provide an authorized `customer_id,email` mapping in:

`config/customer_emails.csv`

## Google Routes

The optional `/routes/matrix` endpoint calls:

`POST https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix`

It can return distance and duration, with traffic-aware routing when enabled. Google documents a 100-element maximum for traffic-aware matrices and requires a response field mask. citeturn618215search2turn618215search5

## Production sequence

`new order -> /orders/{order_id}/automate -> seller ranking -> Frenet quote -> carrier ranking -> recommendation engine -> Resend email -> OMS/carrier booking -> tracking`

The last booking/tracking step requires the organization's order-management/carrier integration and credentials.
