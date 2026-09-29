"""
FastAPI gateway for the Olist Logistics AI.

Endpoints:
GET  /health
GET  /recommendations/{customer_id}
POST /shipping/quote
POST /orders/{order_id}/route
POST /orders/{order_id}/email
POST /orders/{order_id}/automate
POST /routes/matrix

The API uses:
- Olist real data for products/orders/customers/sellers/geolocation
- local ML models for freight + late risk
- Frenet for live Brazilian carrier quotes
- Resend for transactional email
- Google Routes API optionally for road distance/traffic ETA

Secrets are read from environment variables and should never be committed.
"""

from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
import requests
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON_DIR = PROJECT_ROOT / "python"
if str(PYTHON_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_DIR))

from logistics_optimizer import (  # noqa: E402
    add_coordinates,
    item_prediction_features,
    load_data,
    predict_freight,
    predict_late_risk,
    seller_candidates,
    seller_distance,
)


DATA_DIR = Path(os.getenv("DATA_DIR", str(PROJECT_ROOT / "data")))
AI_OUTPUT_DIR = Path(
    os.getenv("AI_OUTPUT_DIR", str(PROJECT_ROOT / "ai_output"))
)
CUSTOMER_EMAILS_FILE = Path(
    os.getenv(
        "CUSTOMER_EMAILS_FILE",
        str(PROJECT_ROOT / "config" / "customer_emails.csv"),
    )
)

APP_API_KEY = os.getenv("APP_API_KEY", "")
FRENET_TOKEN = os.getenv("FRENET_TOKEN", "")
FRENET_PARTNER_TOKEN = os.getenv("FRENET_PARTNER_TOKEN", "")
FRENET_ENDPOINT = os.getenv(
    "FRENET_ENDPOINT",
    "http://api.frenet.com.br/shipping/quote",
)
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "")
GOOGLE_ROUTES_API_KEY = os.getenv("GOOGLE_ROUTES_API_KEY", "")


app = FastAPI(
    title="Olist AI Logistics API",
    version="1.0.0",
    description=(
        "AI routing, live carrier quotation, recommendations and "
        "customer notification for the Olist e-commerce dataset."
    ),
)


class ShippingItem(BaseModel):
    weight_kg: float = Field(gt=0)
    length_cm: float = Field(gt=0)
    height_cm: float = Field(gt=0)
    width_cm: float = Field(gt=0)
    quantity: int = Field(default=1, ge=1)
    sku: str = ""
    category: str = ""
    fragile: bool = False


class ShippingQuoteRequest(BaseModel):
    seller_cep: str
    recipient_cep: str
    invoice_value: float = Field(gt=0)
    items: List[ShippingItem]


class RouteRequest(BaseModel):
    recipient_cep: Optional[str] = None
    seller_cep: Optional[str] = None
    use_google_routes: bool = False


class EmailRequest(BaseModel):
    to_email: Optional[str] = None


class AutomationRequest(BaseModel):
    recipient_cep: Optional[str] = None
    seller_cep: Optional[str] = None
    email: Optional[str] = None
    send_email: bool = False
    use_google_routes: bool = False


class RouteMatrixPoint(BaseModel):
    latitude: float
    longitude: float


class RouteMatrixRequest(BaseModel):
    origins: List[RouteMatrixPoint]
    destinations: List[RouteMatrixPoint]
    traffic_aware: bool = True


def require_api_key(x_api_key: Optional[str]) -> None:
    if APP_API_KEY and x_api_key != APP_API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key.",
        )


@lru_cache(maxsize=1)
def runtime() -> Dict[str, Any]:
    required = [
        DATA_DIR / "olist_orders_dataset.csv",
        DATA_DIR / "olist_order_items_dataset.csv",
        DATA_DIR / "olist_customers_dataset.csv",
        DATA_DIR / "olist_products_dataset.csv",
        DATA_DIR / "olist_sellers_dataset.csv",
        DATA_DIR / "olist_geolocation_dataset.csv",
        AI_OUTPUT_DIR / "freight_cost_model.joblib",
        AI_OUTPUT_DIR / "late_delivery_model.joblib",
    ]

    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise RuntimeError(
            "Runtime files are missing. Train the models and place the "
            "Olist CSV files in DATA_DIR. Missing: " + ", ".join(missing)
        )

    data = load_data(DATA_DIR)
    customers, sellers = add_coordinates(
        data["customers"],
        data["sellers"],
        geolocation=data.get("geolocation"),
        geo_file=None,
    )

    data["customers"] = customers
    data["sellers"] = sellers

    freight_model = joblib.load(
        AI_OUTPUT_DIR / "freight_cost_model.joblib"
    )
    late_model = joblib.load(
        AI_OUTPUT_DIR / "late_delivery_model.joblib"
    )

    return {
        "data": data,
        "freight_model": freight_model,
        "late_model": late_model,
    }


@lru_cache(maxsize=1)
def recommendation_index() -> Dict[str, Any]:
    rt = runtime()
    items = rt["data"]["items"]
    orders = rt["data"]["orders"]

    interactions = (
        items[["order_id", "product_id"]]
        .drop_duplicates()
        .merge(
            orders[["order_id", "customer_id"]],
            on="order_id",
            how="left",
        )
    )

    product_popularity = (
        interactions.groupby("product_id")
        .size()
        .sort_values(ascending=False)
    )

    top_products = set(
        product_popularity.head(1500).index
    )

    pair_counts: Dict[Tuple[str, str], int] = {}

    filtered = interactions[
        interactions["product_id"].isin(top_products)
    ]

    for _, group in filtered.groupby("order_id"):
        products_in_order = sorted(
            group["product_id"].dropna().astype(str).unique()
        )

        for a, b in combinations(products_in_order, 2):
            pair_counts[(a, b)] = (
                pair_counts.get((a, b), 0) + 1
            )

    adjacency: Dict[str, List[Tuple[str, int]]] = {}

    for (a, b), count in pair_counts.items():
        adjacency.setdefault(a, []).append((b, count))
        adjacency.setdefault(b, []).append((a, count))

    return {
        "interactions": interactions,
        "popularity": product_popularity,
        "adjacency": adjacency,
    }


def clean_cep(value: str) -> str:
    digits = re.sub(r"\D", "", str(value))
    if len(digits) != 8:
        raise HTTPException(
            status_code=422,
            detail="Brazilian CEP must contain 8 digits for live carrier quotation.",
        )
    return digits


def build_frenet_items(
    items: pd.DataFrame,
) -> List[Dict[str, Any]]:
    products = items.copy()

    numeric_cols = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]

    for col in numeric_cols:
        products[col] = pd.to_numeric(
            products[col],
            errors="coerce",
        )

    products["product_category_name"] = (
        products["product_category_name"]
        .fillna("UNKNOWN")
        .astype(str)
    )

    grouped = (
        products.groupby(
            [
                "product_id",
                "product_category_name",
                "product_weight_g",
                "product_length_cm",
                "product_height_cm",
                "product_width_cm",
            ],
            dropna=False,
        )
        .size()
        .reset_index(name="quantity")
    )

    output = []

    for _, row in grouped.iterrows():
        def positive(value: Any, minimum: float) -> float:
            try:
                return max(float(value), minimum)
            except (TypeError, ValueError):
                return minimum

        output.append(
            {
                "Weight": positive(
                    row["product_weight_g"],
                    0.001,
                ) / 1000.0,
                "Length": positive(
                    row["product_length_cm"],
                    1.0,
                ),
                "Height": positive(
                    row["product_height_cm"],
                    1.0,
                ),
                "Width": positive(
                    row["product_width_cm"],
                    1.0,
                ),
                "Quantity": int(row["quantity"]),
                "SKU": str(row["product_id"]),
                "Category": str(
                    row["product_category_name"]
                ),
                "isFragile": False,
            }
        )

    return output


def parse_frenet_response(payload: Dict[str, Any]) -> pd.DataFrame:
    services = (
        payload.get("ShippingSevicesArray")
        or payload.get("ShippingServicesArray")
        or payload.get("services")
        or []
    )

    rows = []

    for service in services:
        if service.get("Error") is True:
            continue

        def number(value: Any, default: float = 0.0) -> float:
            try:
                return float(value)
            except (TypeError, ValueError):
                return default

        rows.append(
            {
                "carrier": service.get("Carrier"),
                "carrier_code": service.get("CarrierCode"),
                "service": service.get("ServiceDescription"),
                "service_code": service.get("ServiceCode"),
                "shipping_price": number(
                    service.get("ShippingPrice")
                ),
                "delivery_time_days": number(
                    service.get("DeliveryTime")
                ),
                "allow_buy_label": service.get(
                    "AllowBuyLabel"
                ),
            }
        )

    return pd.DataFrame(rows)


def frenet_quote(
    seller_cep: str,
    recipient_cep: str,
    invoice_value: float,
    items: List[ShippingItem],
) -> pd.DataFrame:
    if not FRENET_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="FRENET_TOKEN is not configured.",
        )

    seller_cep = clean_cep(seller_cep)
    recipient_cep = clean_cep(recipient_cep)

    item_payload = [
        {
            "Weight": item.weight_kg,
            "Length": item.length_cm,
            "Height": item.height_cm,
            "Width": item.width_cm,
            "Quantity": item.quantity,
            "SKU": item.sku,
            "Category": item.category,
            "isFragile": item.fragile,
        }
        for item in items
    ]

    response = requests.post(
        FRENET_ENDPOINT,
        headers={
            "accept": "application/json",
            "Content-Type": "application/json",
            "token": FRENET_TOKEN,
            **(
                {"x-partner-token": FRENET_PARTNER_TOKEN}
                if FRENET_PARTNER_TOKEN
                else {}
            ),
        },
        json={
            "SellerCEP": seller_cep,
            "RecipientCEP": recipient_cep,
            "ShipmentInvoiceValue": float(invoice_value),
            "RecipientCountry": "BR",
            "ShippingServiceCode": None,
            "ShippingItemArray": item_payload,
        },
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail={
                "provider": "frenet",
                "status_code": response.status_code,
                "response": response.text[:2000],
            },
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Frenet returned non-JSON response.",
        ) from exc

    return parse_frenet_response(payload)


def choose_quote(
    quotes: pd.DataFrame,
    late_risk: float,
) -> pd.DataFrame:
    if quotes.empty:
        return quotes

    result = quotes.copy()

    def normalize(series: pd.Series) -> pd.Series:
        low = series.min()
        high = series.max()

        if pd.isna(low) or pd.isna(high) or high == low:
            return pd.Series(
                np.zeros(len(series)),
                index=series.index,
            )

        return (series - low) / (high - low)

    result["price_norm"] = normalize(
        result["shipping_price"]
    )
    result["eta_norm"] = normalize(
        result["delivery_time_days"]
    )

    result["carrier_score"] = (
        0.55 * result["price_norm"]
        + 0.20 * result["eta_norm"]
        + 0.25 * float(late_risk)
    )

    return result.sort_values(
        "carrier_score"
    ).reset_index(drop=True)


def recommendations_for_customer(
    customer_id: str,
    limit: int = 5,
) -> pd.DataFrame:
    rt = runtime()
    idx = recommendation_index()
    interactions = idx["interactions"]
    adjacency = idx["adjacency"]
    popularity = idx["popularity"]

    purchased = set(
        interactions.loc[
            interactions["customer_id"].eq(customer_id),
            "product_id",
        ]
        .dropna()
        .astype(str)
    )

    scores: Dict[str, float] = {}

    for product_id in purchased:
        for candidate, count in adjacency.get(
            product_id,
            [],
        ):
            if candidate not in purchased:
                scores[candidate] = (
                    scores.get(candidate, 0.0)
                    + float(count)
                )

    if not scores:
        for product_id in popularity.index:
            product_id = str(product_id)
            if product_id not in purchased:
                scores[product_id] = float(
                    popularity.loc[product_id]
                )
            if len(scores) >= limit:
                break

    ranked = sorted(
        scores.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:limit]

    if not ranked:
        return pd.DataFrame()

    selected = [product_id for product_id, _ in ranked]

    product_names = rt["data"]["products"][
        [
            "product_id",
            "product_category_name",
        ]
    ].copy()

    selected_df = product_names[
        product_names["product_id"].astype(str).isin(
            selected
        )
    ].copy()

    selected_df["recommendation_score"] = (
        selected_df["product_id"]
        .astype(str)
        .map(dict(ranked))
    )

    return selected_df.sort_values(
        "recommendation_score",
        ascending=False,
    ).reset_index(drop=True)


def rank_sellers(
    order_id: str,
    max_candidates: int = 20,
) -> pd.DataFrame:
    rt = runtime()
    data = rt["data"]

    orders = data["orders"]
    items = data["items"]
    products = data["products"]
    customers = data["customers"]
    sellers = data["sellers"]

    order_match = orders[
        orders["order_id"].eq(order_id)
    ]

    if order_match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Order {order_id} not found.",
        )

    order = order_match.iloc[0]

    customer_match = customers[
        customers["customer_id"].eq(
            order["customer_id"]
        )
    ]

    if customer_match.empty:
        raise HTTPException(
            status_code=404,
            detail="Customer for order not found.",
        )

    customer = customer_match.iloc[0]

    order_items = items[
        items["order_id"].eq(order_id)
    ].copy()

    order_items = order_items.merge(
        products,
        on="product_id",
        how="left",
        suffixes=("", "_product"),
    )

    candidates = seller_candidates(
        order_items,
        items,
        sellers,
    )

    if candidates.empty:
        raise HTTPException(
            status_code=409,
            detail="No seller can be identified for the product basket.",
        )

    rows = []

    for _, seller in candidates.iterrows():
        distance, method = seller_distance(
            customer,
            seller,
        )

        freight_features = item_prediction_features(
            order,
            order_items,
            seller,
            customer,
        )

        predicted_freight = predict_freight(
            rt["freight_model"],
            freight_features,
        )

        late_risk = predict_late_risk(
            rt["late_model"],
            order,
            order_items,
            seller,
            customer,
            predicted_freight=predicted_freight,
        )

        rows.append(
            {
                "seller_id": seller["seller_id"],
                "seller_city": seller.get(
                    "seller_city",
                    "",
                ),
                "seller_state": seller.get(
                    "seller_state",
                    "",
                ),
                "distance_value": float(distance)
                if pd.notna(distance)
                else np.nan,
                "distance_method": method,
                "predicted_freight": float(
                    predicted_freight
                ),
                "late_risk": float(late_risk),
            }
        )

    result = pd.DataFrame(rows)

    result["distance_norm"] = _normalize(
        result["distance_value"]
    )
    result["freight_norm"] = _normalize(
        result["predicted_freight"]
    )
    result["risk_norm"] = _normalize(
        result["late_risk"]
    )

    result["seller_score"] = (
        0.50 * result["distance_norm"]
        + 0.20 * result["freight_norm"]
        + 0.30 * result["risk_norm"]
    )

    return result.sort_values(
        "seller_score"
    ).reset_index(drop=True).head(
        max_candidates
    )


def _normalize(series: pd.Series) -> pd.Series:
    low = series.min()
    high = series.max()

    if pd.isna(low) or pd.isna(high) or high == low:
        return pd.Series(
            np.zeros(len(series)),
            index=series.index,
        )

    return (series - low) / (high - low)


def get_order(order_id: str) -> Tuple[pd.Series, pd.DataFrame, pd.Series]:
    rt = runtime()
    data = rt["data"]

    orders = data["orders"]
    items = data["items"]
    products = data["products"]
    customers = data["customers"]

    order_match = orders[
        orders["order_id"].eq(order_id)
    ]

    if order_match.empty:
        raise HTTPException(
            status_code=404,
            detail=f"Order {order_id} not found.",
        )

    order = order_match.iloc[0]

    customer_match = customers[
        customers["customer_id"].eq(
            order["customer_id"]
        )
    ]

    if customer_match.empty:
        raise HTTPException(
            status_code=404,
            detail="Customer not found.",
        )

    customer = customer_match.iloc[0]

    order_items = items[
        items["order_id"].eq(order_id)
    ].merge(
        products,
        on="product_id",
        how="left",
        suffixes=("", "_product"),
    )

    return order, order_items, customer


def customer_email(customer_id: str) -> Optional[str]:
    if not CUSTOMER_EMAILS_FILE.exists():
        return None

    mapping = pd.read_csv(
        CUSTOMER_EMAILS_FILE
    )

    if not {"customer_id", "email"}.issubset(
        mapping.columns
    ):
        return None

    row = mapping[
        mapping["customer_id"].astype(str).eq(
            str(customer_id)
        )
    ]

    if row.empty:
        return None

    email = str(row.iloc[0]["email"]).strip()
    return email if email else None


def build_email_html(
    assignment: Dict[str, Any],
    recommendations: pd.DataFrame,
) -> str:
    recommendation_html = ""

    for _, row in recommendations.iterrows():
        category = row.get(
            "product_category_name",
            "recommended product",
        )
        recommendation_html += (
            f"<li>{category} "
            f"(product {row['product_id']})</li>"
        )

    return f"""
<html>
<body>
<h2>Your delivery plan</h2>
<p>Order: <strong>{assignment['order_id']}</strong></p>
<p>
Nearest selected seller:
<strong>{assignment['seller_id']}</strong>
({assignment['seller_city']}, {assignment['seller_state']}).
</p>
<p>
Estimated seller distance:
<strong>{assignment['seller_distance_km']:.1f} km</strong>.
</p>
<p>
Selected shipping company:
<strong>{assignment.get('carrier', 'Live quote unavailable')}</strong>
{assignment.get('service', '')}.
</p>
<p>
Shipping price:
<strong>R$ {assignment.get('shipping_price', 0):.2f}</strong>
<br>
Estimated delivery:
<strong>{assignment.get('delivery_time_days', 0):.0f} days</strong>.
</p>
<h3>Recommended products</h3>
<ul>
{recommendation_html}
</ul>
<p>
These recommendations are based on historical Olist
co-purchase patterns. Carrier price and delivery estimates
are subject to provider availability.
</p>
</body>
</html>
"""


def send_resend(
    to_email: str,
    subject: str,
    html: str,
) -> Dict[str, Any]:
    if not RESEND_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="RESEND_API_KEY is not configured.",
        )

    if not EMAIL_FROM:
        raise HTTPException(
            status_code=503,
            detail="EMAIL_FROM is not configured.",
        )

    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": f"Bearer {RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "from": EMAIL_FROM,
            "to": [to_email],
            "subject": subject,
            "html": html,
        },
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail={
                "provider": "resend",
                "status_code": response.status_code,
                "response": response.text[:2000],
            },
        )

    return response.json()


def google_route_matrix(
    request: RouteMatrixRequest,
) -> List[Dict[str, Any]]:
    if not GOOGLE_ROUTES_API_KEY:
        raise HTTPException(
            status_code=503,
            detail="GOOGLE_ROUTES_API_KEY is not configured.",
        )

    if len(request.origins) * len(
        request.destinations
    ) > 100 and request.traffic_aware:
        raise HTTPException(
            status_code=422,
            detail=(
                "Traffic-aware route matrix is limited to "
                "100 origin-destination elements."
            ),
        )

    body = {
        "origins": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {
                            "latitude": point.latitude,
                            "longitude": point.longitude,
                        }
                    }
                }
            }
            for point in request.origins
        ],
        "destinations": [
            {
                "waypoint": {
                    "location": {
                        "latLng": {
                            "latitude": point.latitude,
                            "longitude": point.longitude,
                        }
                    }
                }
            }
            for point in request.destinations
        ],
        "travelMode": "DRIVE",
        "routingPreference": (
            "TRAFFIC_AWARE_OPTIMAL"
            if request.traffic_aware
            else "TRAFFIC_UNAWARE"
        ),
    }

    response = requests.post(
        "https://routes.googleapis.com/"
        "distanceMatrix/v2:computeRouteMatrix",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": GOOGLE_ROUTES_API_KEY,
            "X-Goog-FieldMask": (
                "originIndex,destinationIndex,status,"
                "condition,distanceMeters,duration"
            ),
        },
        json=body,
        timeout=30,
    )

    if not response.ok:
        raise HTTPException(
            status_code=502,
            detail={
                "provider": "google_routes",
                "status_code": response.status_code,
                "response": response.text[:2000],
            },
        )

    results = []

    # REST Route Matrix may return streamed JSON elements.
    for line in response.text.splitlines():
        if not line.strip():
            continue
        try:
            results.append(json.loads(line))
        except json.JSONDecodeError:
            pass

    if not results:
        try:
            payload = response.json()
            if isinstance(payload, list):
                results = payload
            elif isinstance(payload, dict):
                results = [payload]
        except ValueError:
            pass

    return results


@app.get("/health")
def health(
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    return {
        "status": "ok",
        "service": "Olist AI Logistics API",
        "frenet_configured": bool(FRENET_TOKEN),
        "resend_configured": bool(
            RESEND_API_KEY and EMAIL_FROM
        ),
        "google_routes_configured": bool(
            GOOGLE_ROUTES_API_KEY
        ),
    }


@app.get("/recommendations/{customer_id}")
def recommendations_endpoint(
    customer_id: str,
    limit: int = 5,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    if limit < 1 or limit > 20:
        raise HTTPException(
            status_code=422,
            detail="limit must be between 1 and 20.",
        )

    result = recommendations_for_customer(
        customer_id,
        limit,
    )

    return {
        "customer_id": customer_id,
        "recommendations": result.to_dict(
            orient="records"
        ),
    }


@app.post("/shipping/quote")
def shipping_quote_endpoint(
    request: ShippingQuoteRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    quotes = frenet_quote(
        request.seller_cep,
        request.recipient_cep,
        request.invoice_value,
        request.items,
    )

    if quotes.empty:
        return {
            "provider": "frenet",
            "quotes": [],
        }

    ranked = choose_quote(
        quotes,
        late_risk=0.0,
    )

    return {
        "provider": "frenet",
        "quotes": ranked.to_dict(
            orient="records"
        ),
    }


@app.post("/orders/{order_id}/route")
def route_order_endpoint(
    order_id: str,
    request: RouteRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    rt = runtime()

    order, order_items, customer = get_order(
        order_id
    )

    sellers = rank_sellers(order_id)

    if sellers.empty:
        raise HTTPException(
            status_code=409,
            detail="No seller candidate available.",
        )

    selected = sellers.iloc[0]

    recommendations = recommendations_for_customer(
        str(order["customer_id"]),
        limit=5,
    )

    result: Dict[str, Any] = {
        "order_id": order_id,
        "customer_id": str(order["customer_id"]),
        "customer_city": customer["customer_city"],
        "customer_state": customer["customer_state"],
        "seller_id": selected["seller_id"],
        "seller_city": selected["seller_city"],
        "seller_state": selected["seller_state"],
        "seller_distance_km": (
            None
            if pd.isna(
                selected["distance_value"]
            )
            else float(
                selected["distance_value"]
            )
        ),
        "seller_distance_method": selected[
            "distance_method"
        ],
        "predicted_freight": float(
            selected["predicted_freight"]
        ),
        "late_risk_probability": float(
            selected["late_risk"]
        ),
        "recommendations": recommendations.to_dict(
            orient="records"
        ),
    }

    if request.recipient_cep and request.seller_cep:
        seller_row = rt["data"]["sellers"][
            rt["data"]["sellers"]["seller_id"].eq(
                selected["seller_id"]
            )
        ].iloc[0]

        item_models = [
            ShippingItem(
                weight_kg=max(
                    float(
                        pd.to_numeric(
                            row["product_weight_g"],
                            errors="coerce",
                        )
                    ) / 1000.0,
                    0.001,
                ),
                length_cm=max(
                    float(
                        pd.to_numeric(
                            row["product_length_cm"],
                            errors="coerce",
                        )
                    )
                    if pd.notna(
                        row["product_length_cm"]
                    )
                    else 1.0,
                    1.0,
                ),
                height_cm=max(
                    float(
                        pd.to_numeric(
                            row["product_height_cm"],
                            errors="coerce",
                        )
                    )
                    if pd.notna(
                        row["product_height_cm"]
                    )
                    else 1.0,
                    1.0,
                ),
                width_cm=max(
                    float(
                        pd.to_numeric(
                            row["product_width_cm"],
                            errors="coerce",
                        )
                    )
                    if pd.notna(
                        row["product_width_cm"]
                    )
                    else 1.0,
                    1.0,
                ),
                quantity=1,
                sku=str(row["product_id"]),
                category=str(
                    row.get(
                        "product_category_name",
                        "UNKNOWN",
                    )
                ),
            )
            for _, row in order_items.iterrows()
        ]

        invoice_value = float(
            pd.to_numeric(
                order_items["price"],
                errors="coerce",
            ).sum()
        )

        quotes = frenet_quote(
            request.seller_cep,
            request.recipient_cep,
            invoice_value,
            item_models,
        )

        ranked = choose_quote(
            quotes,
            float(selected["late_risk"]),
        )

        result["carrier_quote_status"] = (
            "live"
        )

        result["carrier_options"] = ranked.to_dict(
            orient="records"
        )

        if not ranked.empty:
            best = ranked.iloc[0]
            result["carrier"] = best["carrier"]
            result["service"] = best["service"]
            result["shipping_price"] = float(
                best["shipping_price"]
            )
            result["delivery_time_days"] = float(
                best["delivery_time_days"]
            )
    else:
        result["carrier_quote_status"] = (
            "requires_full_8_digit_ceps"
        )

    if request.use_google_routes:
        result["google_routes_note"] = (
            "Call POST /routes/matrix with the selected "
            "seller and customer coordinates for road distance/traffic."
        )

    return result


@app.post("/orders/{order_id}/email")
def email_order_endpoint(
    order_id: str,
    request: EmailRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    route = route_order_endpoint(
        order_id,
        RouteRequest(),
        x_api_key=x_api_key,
    )

    destination = request.to_email

    if not destination:
        destination = customer_email(
            route["customer_id"]
        )

    if not destination:
        raise HTTPException(
            status_code=422,
            detail=(
                "No email supplied and no authorized "
                "customer_id,email mapping exists."
            ),
        )

    recommendations = pd.DataFrame(
        route.get("recommendations", [])
    )

    html = build_email_html(
        route,
        recommendations,
    )

    message = send_resend(
        destination,
        f"Delivery plan for order {order_id}",
        html,
    )

    return {
        "order_id": order_id,
        "recipient": destination,
        "provider": "resend",
        "message": message,
    }


@app.post("/orders/{order_id}/automate")
def automate_order_endpoint(
    order_id: str,
    request: AutomationRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)

    route = route_order_endpoint(
        order_id,
        RouteRequest(
            recipient_cep=request.recipient_cep,
            seller_cep=request.seller_cep,
            use_google_routes=request.use_google_routes,
        ),
        x_api_key=x_api_key,
    )

    result = {
        "routing": route,
        "email": {
            "enabled": bool(request.send_email),
            "sent": False,
        },
    }

    if request.send_email:
        destination = (
            request.email
            or customer_email(route["customer_id"])
        )

        if not destination:
            raise HTTPException(
                status_code=422,
                detail=(
                    "send_email=true requires an email override "
                    "or an authorized customer email mapping."
                ),
            )

        recommendations = pd.DataFrame(
            route.get("recommendations", [])
        )

        html = build_email_html(
            route,
            recommendations,
        )

        message = send_resend(
            destination,
            f"Delivery plan for order {order_id}",
            html,
        )

        result["email"] = {
            "enabled": True,
            "sent": True,
            "recipient": destination,
            "provider": "resend",
            "message": message,
        }

    return result


@app.post("/routes/matrix")
def routes_matrix_endpoint(
    request: RouteMatrixRequest,
    x_api_key: Optional[str] = Header(default=None),
):
    require_api_key(x_api_key)
    return {
        "provider": "google_routes",
        "routes": google_route_matrix(request),
    }
