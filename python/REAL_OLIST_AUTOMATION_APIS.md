# Real Olist Logistics Automation — API Setup

## Data source

The Colab notebook uses the uploaded `archive.zip` directly. It does not require a Kaggle API key.

The archive should contain the nine Olist CSV files, including `olist_geolocation_dataset.csv`.

## What is automated

### Seller

For each order, the AI:

1. finds sellers that stock the purchased product(s)
2. calculates customer-to-seller distance from Olist ZIP centroids
3. predicts freight value for each candidate seller
4. predicts late-delivery probability for each candidate seller
5. ranks the candidates and selects the lowest routing score

Default seller score:

`0.50 * normalized distance + 0.20 * normalized predicted freight + 0.30 * normalized late risk`

### Shipping company

For Brazilian shipping quotes the notebook can call Frenet's quote endpoint:

`https://api.frenet.com.br/shipping/quote`

The official Frenet documentation specifies `SellerCEP`, `RecipientCEP`, `ShipmentInvoiceValue`, `ShippingItemArray`, and a `token` header for the quote request. citeturn582621view0

The API returns shipping services including carrier/service, price, and delivery time. citeturn435815search3

The AI ranks returned services by:

`55% price + 20% delivery-time + 25% late-risk penalty`

### Recommendations

Recommendations are learned locally from item-to-item co-purchase patterns in the Olist order history. No recommendation API is required.

### Email

The public Olist customer table does not include a customer email field. Therefore `config/customer_emails_template.csv` is intentionally empty apart from its headers.

Fill it from an authorized CRM/customer system:

`customer_id,email`

For transactional email, the Colab supports Resend. Resend's REST API sends mail through `POST https://api.resend.com/emails` using a Bearer API key and `from`, `to`, `subject`, and `html` fields. citeturn252276search0turn252276search2

Gmail is an alternative; Google's Gmail API sends messages with `users.messages.send` and a base64URL-encoded MIME message. citeturn976459search0

## APIs needed for a production deployment

| Capability | API | Required? |
| --- | --- | --- |
| ZIP-centroid nearest seller | Olist geolocation | No external API |
| Road distance / traffic ETA | Google Routes API | Optional |
| Live carrier quote | Frenet | Yes for live carrier selection |
| Label / tracking | Frenet or direct carrier APIs | Yes for actual shipping execution |
| Customer email | Resend or Gmail API | Yes for automatic email |
| Recommendations | Local ML | No external API |

Google's current Routes API provides `ComputeRouteMatrix` for origin/destination distance and duration, and requires response field masks. citeturn976459search1turn976459search2

## Secrets in Colab

Create Colab Secrets named:

`FRENET_TOKEN`

`RESEND_API_KEY`

`EMAIL_FROM`

Do not hard-code these values in a notebook or commit them to GitHub.

## Email safety

The notebook defaults to `SEND_EMAILS = False` and `EMAIL_LIMIT = 1`.

Use one verified test address first, then increase the limit only after checking the generated seller, carrier, price, ETA, and recommendation content.

## Validation on the uploaded real archive

Data checks:

- 99,441 orders
- 112,650 order-item rows
- 96,096 unique customers
- 1,000,163 geolocation observations

Corrected order-level business metrics:

- product revenue: 13.59M
- freight: 2.25M
- freight / product revenue: 16.57%
- average delivery: 12.56 days
- late delivery: 8.11%

Lightweight full-data model validation:

- freight MAE: about 4.04
- late-delivery ROC-AUC: about 0.78

These are development validation results for this dataset. They are not guarantees of production performance.