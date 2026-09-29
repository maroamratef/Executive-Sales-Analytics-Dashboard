# API Examples

Base URL:

`http://localhost:8000`

Optional authentication header:

`X-API-Key: YOUR_APP_API_KEY`

## Health

```bash
curl http://localhost:8000/health
```

## Recommendations

```bash
curl "http://localhost:8000/recommendations/YOUR_CUSTOMER_ID?limit=5"
```

## Live Frenet quote

Frenet requires full 8-digit Brazilian CEPs.

```bash
curl -X POST "http://localhost:8000/shipping/quote" ^
  -H "Content-Type: application/json" ^
  -d "{
    \"seller_cep\": \"06473000\",
    \"recipient_cep\": \"05132000\",
    \"invoice_value\": 499.90,
    \"items\": [{
      \"weight_kg\": 0.20,
      \"length_cm\": 28,
      \"height_cm\": 5.5,
      \"width_cm\": 22,
      \"quantity\": 1,
      \"sku\": \"PRODUCT-001\",
      \"category\": \"electronics\",
      \"fragile\": false
    }]
  }"
```

## Route an order

The API selects a seller from the Olist seller/product history and Olist geolocation. Provide full CEPs to activate live Frenet quotes.

```bash
curl -X POST "http://localhost:8000/orders/YOUR_ORDER_ID/route" ^
  -H "Content-Type: application/json" ^
  -d "{
    \"seller_cep\": \"06473000\",
    \"recipient_cep\": \"05132000\"
  }"
```

## Full automation

```bash
curl -X POST "http://localhost:8000/orders/YOUR_ORDER_ID/automate" ^
  -H "Content-Type: application/json" ^
  -d "{
    \"seller_cep\": \"06473000\",
    \"recipient_cep\": \"05132000\",
    \"email\": \"customer@example.com\",
    \"send_email\": false
  }"
```

Set `send_email` to true only after Resend is configured and the destination is authorized.

## Send email

```bash
curl -X POST "http://localhost:8000/orders/YOUR_ORDER_ID/email" ^
  -H "Content-Type: application/json" ^
  -d "{\"to_email\":\"customer@example.com\"}"
```

## Google road matrix

```bash
curl -X POST "http://localhost:8000/routes/matrix" ^
  -H "Content-Type: application/json" ^
  -d "{
    \"origins\": [
      {\"latitude\": -23.56, \"longitude\": -46.64}
    ],
    \"destinations\": [
      {\"latitude\": -23.55, \"longitude\": -46.63}
    ],
    \"traffic_aware\": true
  }"
```

## Production flow

`Order -> /orders/{id}/automate -> seller selection -> live Frenet quote -> carrier selection -> recommendation -> Resend email -> OMS/carrier booking`
