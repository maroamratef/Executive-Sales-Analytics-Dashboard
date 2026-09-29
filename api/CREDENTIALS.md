# API Credentials Checklist

## Colab Secrets

Create these in Google Colab under **Secrets**.

| Secret | Required | Provider | Purpose |
|---|---|---|---|
| `FRENET_TOKEN` | For live carrier quotes | Frenet | Client authentication token |
| `FRENET_PARTNER_TOKEN` | For Frenet platform/production integrations | Frenet | Partner/platform authentication |
| `RESEND_API_KEY` | For email sending | Resend | Transactional email authentication |
| `EMAIL_FROM` | For email sending | Resend | Verified sender address |
| `GOOGLE_ROUTES_API_KEY` | Optional | Google Maps Platform | Road distance / traffic ETA |
| `APP_API_KEY` | Recommended | Your app | Protect your own FastAPI endpoints |

Never put these values into GitHub.

## 1. Frenet

Official authentication docs:

https://docs.frenet.com.br/docs/autenticacao

Official shipping quote:

https://docs.frenet.com.br/reference/calculateshippingquote

Frenet states that the client token is available in the account's access keys / registration data, or can be returned by the onboarding API. Its authentication documentation also describes the Partner Token; the production Partner Token is provided after the integration/homologation process. citeturn761329search1turn417159search2turn761329search0

Set:

`FRENET_TOKEN=<client token>`

`FRENET_PARTNER_TOKEN=<partner token>`

For a production integration, complete the Frenet homologation process required for the specific integration. citeturn761329search0

## 2. Resend

Start:

https://resend.com/

API/key management:

https://resend.com/api-keys

Domains:

https://resend.com/domains

Resend supports scoped API keys, including sending-only access, and recommends verifying the sending domain for production. citeturn761329search4turn761329search5

Set:

`RESEND_API_KEY=re_xxxxxxxxx`

`EMAIL_FROM=Your Store <orders@yourdomain.com>`

The sender domain must be verified in Resend before using it for production sending. Resend's current free tier includes up to three verified domains per team. citeturn738427search8

## 3. Google Routes API (optional)

Setup:

https://developers.google.com/maps/documentation/routes/get-api-key

Google Cloud credentials:

https://console.cloud.google.com/apis/credentials

Routes API:

https://console.cloud.google.com/apis/library/routes.googleapis.com

Enable the Routes API in the Google Cloud project and create an API key. Google documents API-key authentication for Routes API and recommends restricting keys. citeturn470746search3

Set:

`GOOGLE_ROUTES_API_KEY=AIza...`

The notebook uses `ComputeRouteMatrix` when enabled. The API returns route distance/duration and can use traffic-aware routing. citeturn470746search5turn470746search8

## 4. Your own FastAPI protection key

Generate a random secret locally:

```python
import secrets
print(secrets.token_urlsafe(32))
```

Put the result in:

`APP_API_KEY=<random value>`

The notebook sends it as:

`X-API-Key: <APP_API_KEY>`

## 5. Private data that is not an API credential

The public Olist archive does not contain customer email addresses or full eight-digit CEPs for customers/sellers, so the production system needs those values from your authorized CRM/OMS.

Recommended private mappings:

`config/customer_emails.csv`

```text
customer_id,email
```

`config/seller_full_ceps.csv`

```text
seller_id,seller_cep
```

Do not commit those private files to the public repository.

## Minimum setup

1. Upload `archive.zip` to Colab.
2. Train the AI.
3. Obtain the Frenet client token and required Partner Token.
4. Create the Resend API key and verify the sending domain.
5. Supply full eight-digit CEPs from your OMS/CRM for live shipping quotes.
6. Supply an authorized customer email for the test.
7. Add Google Routes only when road/traffic routing is needed.
8. Keep email sending disabled until the route/quote/recommendation preview is verified.