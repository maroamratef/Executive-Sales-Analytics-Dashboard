"""
Automated Seller + Shipping Carrier Assignment.

For each order, this engine:
1. Builds a seller candidate pool from sellers that historically sold the
   products in the order.
2. Computes seller-to-customer distance when latitude/longitude are available.
3. Otherwise uses a transparent Brazilian postal/city/state proximity proxy.
4. Scores sellers using distance, predicted freight and predicted late risk.
5. Selects a shipping carrier from a configurable carrier table.
6. Produces an explainable automated assignment.

Important:
- The Olist dataset does not contain actual carrier/shipping-company history.
  Carrier choices therefore come from the external/configurable carriers CSV.
- Exact "nearest seller" requires coordinates. With the raw Olist data the
  customer and seller files only provide ZIP prefixes, cities and states, so
  the fallback is an approximation.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd


DEFAULT_CARRIER_PATH = Path("config/carriers.csv")


def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    radius_km = 6371.0088
    p1 = np.radians(lat1)
    p2 = np.radians(lat2)
    dp = np.radians(lat2 - lat1)
    dl = np.radians(lon2 - lon1)

    a = (
        np.sin(dp / 2) ** 2
        + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    )
    return float(
        radius_km
        * 2
        * np.arctan2(np.sqrt(a), np.sqrt(1 - a))
    )


def load_data(data_dir: Path) -> Dict[str, pd.DataFrame]:
    names = {
        "orders": "olist_orders_dataset.csv",
        "items": "olist_order_items_dataset.csv",
        "customers": "olist_customers_dataset.csv",
        "products": "olist_products_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
    }

    out = {}
    for key, filename in names.items():
        path = data_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"Missing dataset: {path}")
        out[key] = pd.read_csv(path)

    return out


def load_carriers(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"Carrier configuration not found: {path}. "
            "Copy config/carriers_template.csv to config/carriers.csv "
            "and enter your real carrier contracts/performance."
        )

    carriers = pd.read_csv(path)

    required = [
        "carrier_id",
        "carrier_name",
        "base_fee",
        "per_km",
        "per_kg",
        "max_weight_kg",
        "base_days",
        "days_per_500km",
    ]

    missing = [c for c in required if c not in carriers.columns]
    if missing:
        raise ValueError(
            f"Carrier CSV missing columns: {missing}"
        )

    numeric = [
        "base_fee",
        "per_km",
        "per_kg",
        "max_weight_kg",
        "base_days",
        "days_per_500km",
    ]

    for col in numeric:
        carriers[col] = pd.to_numeric(
            carriers[col],
            errors="coerce",
        )

    carriers = carriers.dropna(subset=numeric).copy()
    carriers["enabled"] = carriers.get(
        "enabled",
        True,
    )

    return carriers[carriers["enabled"].astype(bool)].copy()


def add_coordinates(
    customers: pd.DataFrame,
    sellers: pd.DataFrame,
    geo_file: Path | None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    customers = customers.copy()
    sellers = sellers.copy()

    # Optional geo file:
    # entity_type,entity_id,lat,lon
    if geo_file is not None and geo_file.exists():
        geo = pd.read_csv(geo_file)

        required = {"entity_type", "entity_id", "lat", "lon"}
        missing = required - set(geo.columns)

        if missing:
            raise ValueError(
                f"Geo file missing columns: {sorted(missing)}"
            )

        customer_geo = (
            geo[geo["entity_type"].eq("customer")]
            [["entity_id", "lat", "lon"]]
            .drop_duplicates("entity_id")
            .rename(
                columns={
                    "entity_id": "customer_id",
                    "lat": "customer_lat",
                    "lon": "customer_lon",
                }
            )
        )

        seller_geo = (
            geo[geo["entity_type"].eq("seller")]
            [["entity_id", "lat", "lon"]]
            .drop_duplicates("entity_id")
            .rename(
                columns={
                    "entity_id": "seller_id",
                    "lat": "seller_lat",
                    "lon": "seller_lon",
                }
            )
        )

        customers = customers.merge(
            customer_geo,
            on="customer_id",
            how="left",
        )

        sellers = sellers.merge(
            seller_geo,
            on="seller_id",
            how="left",
        )

    return customers, sellers


def proximity_proxy(
    customer_state: str,
    customer_city: str,
    customer_zip: str,
    seller_state: str,
    seller_city: str,
    seller_zip: str,
) -> Tuple[float, str]:
    state_equal = (
        str(customer_state).strip().upper()
        == str(seller_state).strip().upper()
    )

    city_equal = (
        str(customer_city).strip().lower()
        == str(seller_city).strip().lower()
        and str(customer_city).strip() != ""
        and str(seller_city).strip() != ""
    )

    try:
        customer_prefix = int(str(customer_zip)[:5])
        seller_prefix = int(str(seller_zip)[:5])
        prefix_gap = abs(customer_prefix - seller_prefix)
    except (ValueError, TypeError):
        prefix_gap = 999999

    # Lower is better. This is a ranking proxy, not a physical distance.
    score = prefix_gap / 1000.0
    if not state_equal:
        score += 20.0
    if city_equal:
        score = max(0.0, score - 5.0)

    return float(score), "postal/city/state proximity proxy"


def build_order_context(
    order_id: str,
    orders: pd.DataFrame,
    items: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
) -> Tuple[pd.Series, pd.DataFrame, pd.Series]:
    order = orders.loc[
        orders["order_id"].eq(order_id)
    ].iloc[0]

    customer = customers.loc[
        customers["customer_id"].eq(order["customer_id"])
    ].iloc[0]

    order_items = items.loc[
        items["order_id"].eq(order_id)
    ].copy()

    order_items = order_items.merge(
        products,
        on="product_id",
        how="left",
        suffixes=("", "_product"),
    )

    return order, order_items, customer


def build_seller_product_index(
    items: pd.DataFrame,
) -> Dict[str, set]:
    return (
        items.groupby("seller_id")["product_id"]
        .apply(set)
        .to_dict()
    )


def seller_candidates(
    order_items: pd.DataFrame,
    items: pd.DataFrame,
    sellers: pd.DataFrame,
) -> pd.DataFrame:
    required_products = set(
        order_items["product_id"]
        .dropna()
        .astype(str)
    )

    seller_products = build_seller_product_index(items)

    exact = []
    coverage = []

    for seller_id, product_set in seller_products.items():
        covered = len(required_products.intersection(product_set))

        if covered == len(required_products):
            exact.append(seller_id)

        coverage.append(
            (seller_id, covered)
        )

    candidate_ids = exact

    if not candidate_ids:
        coverage.sort(
            key=lambda x: x[1],
            reverse=True,
        )
        candidate_ids = [
            seller_id
            for seller_id, covered in coverage[:50]
            if covered > 0
        ]

    return sellers[
        sellers["seller_id"].isin(candidate_ids)
    ].copy()


def seller_distance(
    customer: pd.Series,
    seller: pd.Series,
) -> Tuple[float, str]:
    customer_lat = customer.get("customer_lat")
    customer_lon = customer.get("customer_lon")
    seller_lat = seller.get("seller_lat")
    seller_lon = seller.get("seller_lon")

    coordinates_available = all(
        pd.notna(x)
        for x in [
            customer_lat,
            customer_lon,
            seller_lat,
            seller_lon,
        ]
    )

    if coordinates_available:
        return (
            haversine_km(
                float(customer_lat),
                float(customer_lon),
                float(seller_lat),
                float(seller_lon),
            ),
            "Haversine distance from coordinates",
        )

    return proximity_proxy(
        customer.get("customer_state", ""),
        customer.get("customer_city", ""),
        customer.get("customer_zip_code_prefix", ""),
        seller.get("seller_state", ""),
        seller.get("seller_city", ""),
        seller.get("seller_zip_code_prefix", ""),
    )


def item_prediction_features(
    order: pd.Series,
    order_items: pd.DataFrame,
    seller: pd.Series,
    customer: pd.Series,
) -> pd.DataFrame:
    rows = order_items.copy()

    numeric_product_cols = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
    ]

    for col in numeric_product_cols:
        rows[col] = pd.to_numeric(
            rows[col],
            errors="coerce",
        )

    rows["price"] = pd.to_numeric(
        rows["price"],
        errors="coerce",
    )

    if "shipping_limit_date" in rows.columns:
        rows["shipping_limit_date"] = pd.to_datetime(
            rows["shipping_limit_date"],
            errors="coerce",
        )

    purchase_dt = pd.to_datetime(
        order["order_purchase_timestamp"],
        errors="coerce",
    )

    rows["product_volume_cm3"] = (
        rows["product_length_cm"].fillna(0)
        * rows["product_height_cm"].fillna(0)
        * rows["product_width_cm"].fillna(0)
    )

    rows["purchase_year"] = purchase_dt.year
    rows["purchase_month"] = purchase_dt.month
    rows["purchase_dayofweek"] = purchase_dt.dayofweek
    rows["purchase_hour"] = purchase_dt.hour

    rows["customer_state"] = customer.get(
        "customer_state",
        np.nan,
    )
    rows["seller_state"] = seller.get(
        "seller_state",
        np.nan,
    )
    rows["product_category_name"] = rows.get(
        "product_category_name",
        np.nan,
    )

    rows["customer_seller_same_state"] = (
        str(customer.get("customer_state", "")).upper()
        == str(seller.get("seller_state", "")).upper()
    )

    rows["days_to_shipping_limit"] = (
        rows["shipping_limit_date"] - purchase_dt
    ).dt.total_seconds() / 86400.0

    # Match the freight model's feature columns exactly.
    wanted = [
        "price",
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
        "product_volume_cm3",
        "purchase_month",
        "purchase_dayofweek",
        "purchase_hour",
        "days_to_shipping_limit",
        "product_category_name",
        "seller_state",
        "customer_state",
        "customer_seller_same_state",
    ]

    for col in wanted:
        if col not in rows.columns:
            rows[col] = np.nan

    return rows[wanted]


def predict_freight(
    model,
    order_features: pd.DataFrame,
) -> float:
    predictions = model.predict(order_features)
    return float(
        np.clip(
            np.nansum(predictions),
            a_min=0,
            a_max=None,
        )
    )


def predict_late_risk(
    model,
    order: pd.Series,
    order_items: pd.DataFrame,
    seller: pd.Series,
    customer: pd.Series,
) -> float:
    product_weights = pd.to_numeric(
        order_items["product_weight_g"],
        errors="coerce",
    )
    lengths = pd.to_numeric(
        order_items["product_length_cm"],
        errors="coerce",
    )
    heights = pd.to_numeric(
        order_items["product_height_cm"],
        errors="coerce",
    )
    widths = pd.to_numeric(
        order_items["product_width_cm"],
        errors="coerce",
    )
    prices = pd.to_numeric(
        order_items["price"],
        errors="coerce",
    )
    freight_values = pd.to_numeric(
        order_items.get("freight_value", 0),
        errors="coerce",
    )

    purchase_dt = pd.to_datetime(
        order["order_purchase_timestamp"],
        errors="coerce",
    )
    approved_dt = pd.to_datetime(
        order["order_approved_at"],
        errors="coerce",
    )
    estimated_dt = pd.to_datetime(
        order["order_estimated_delivery_date"],
        errors="coerce",
    )

    volume = (
        lengths.fillna(0)
        * heights.fillna(0)
        * widths.fillna(0)
    )

    candidate = pd.DataFrame(
        [
            {
                "item_count": len(order_items),
                "unique_products": order_items["product_id"].nunique(),
                "unique_sellers": 1,
                "total_price": prices.sum(),
                "total_freight": freight_values.sum(),
                "avg_item_price": prices.mean(),
                "avg_freight": freight_values.mean(),
                "avg_weight_g": product_weights.mean(),
                "max_weight_g": product_weights.max(),
                "avg_volume_cm3": volume.mean(),
                "max_volume_cm3": volume.max(),
                "category_count": order_items["product_category_name"].nunique(),
                "purchase_year": purchase_dt.year,
                "purchase_month": purchase_dt.month,
                "purchase_dayofweek": purchase_dt.dayofweek,
                "purchase_hour": purchase_dt.hour,
                "approval_delay_hours": (
                    (approved_dt - purchase_dt).total_seconds()
                    / 3600.0
                    if pd.notna(approved_dt)
                    else np.nan
                ),
                "estimated_lead_days": (
                    (estimated_dt - purchase_dt).total_seconds()
                    / 86400.0
                    if pd.notna(estimated_dt)
                    else np.nan
                ),
                "cross_state": int(
                    str(customer.get("customer_state", "")).upper()
                    != str(seller.get("seller_state", "")).upper()
                ),
                "seller_state_nunique": 1,
                "customer_state": customer.get("customer_state", np.nan),
                "primary_seller_state": seller.get("seller_state", np.nan),
                "order_status": order.get("order_status", "created"),
            }
        ]
    )

    model_features = [
        "item_count",
        "unique_products",
        "unique_sellers",
        "total_price",
        "total_freight",
        "avg_item_price",
        "avg_freight",
        "avg_weight_g",
        "max_weight_g",
        "avg_volume_cm3",
        "max_volume_cm3",
        "category_count",
        "purchase_year",
        "purchase_month",
        "purchase_dayofweek",
        "purchase_hour",
        "approval_delay_hours",
        "estimated_lead_days",
        "cross_state",
        "seller_state_nunique",
        "customer_state",
        "primary_seller_state",
        "order_status",
    ]

    probabilities = model.predict_proba(
        candidate[model_features]
    )[:, 1]

    return float(probabilities[0])


def choose_carrier(
    carriers: pd.DataFrame,
    distance_km: float,
    weight_kg: float,
    late_risk: float,
    risk_weight: float = 20.0,
) -> Tuple[pd.Series, pd.DataFrame]:
    rows = carriers[
        carriers["max_weight_kg"] >= weight_kg
    ].copy()

    if rows.empty:
        raise ValueError(
            f"No carrier can accept estimated weight {weight_kg:.2f} kg."
        )

    rows["estimated_cost"] = (
        rows["base_fee"]
        + rows["per_km"] * distance_km
        + rows["per_kg"] * weight_kg
    )

    rows["estimated_eta_days"] = (
        rows["base_days"]
        + rows["days_per_500km"]
        * (distance_km / 500.0)
    )

    # Expected operational score:
    # cost + late-risk penalty + transit-time penalty.
    rows["carrier_score"] = (
        rows["estimated_cost"]
        + risk_weight * late_risk
        + 2.0 * rows["estimated_eta_days"]
    )

    rows = rows.sort_values(
        "carrier_score"
    ).reset_index(drop=True)

    return rows.iloc[0], rows


def assign_order(
    order_id: str,
    data: Dict[str, pd.DataFrame],
    freight_model,
    late_model,
    carriers: pd.DataFrame,
    seller_weight: float = 0.50,
    freight_weight: float = 0.20,
    risk_weight: float = 0.30,
) -> Tuple[Dict, pd.DataFrame]:
    orders = data["orders"]
    items = data["items"]
    products = data["products"]
    customers = data["customers"]
    sellers = data["sellers"]

    order, order_items, customer = build_order_context(
        order_id,
        orders,
        items,
        products,
        customers,
    )

    candidates = seller_candidates(
        order_items,
        items,
        sellers,
    )

    if candidates.empty:
        raise ValueError(
            f"No seller candidate found for order {order_id}."
        )

    candidate_rows = []

    for _, seller in candidates.iterrows():
        distance, distance_method = seller_distance(
            customer,
            seller,
        )

        features = item_prediction_features(
            order,
            order_items,
            seller,
            customer,
        )

        predicted_freight = predict_freight(
            freight_model,
            features,
        )

        late_risk = predict_late_risk(
            late_model,
            order,
            order_items,
            seller,
            customer,
        )

        candidate_rows.append(
            {
                "order_id": order_id,
                "seller_id": seller["seller_id"],
                "seller_city": seller.get("seller_city", ""),
                "seller_state": seller.get("seller_state", ""),
                "customer_city": customer.get("customer_city", ""),
                "customer_state": customer.get("customer_state", ""),
                "distance_km_or_proxy": distance,
                "distance_method": distance_method,
                "predicted_freight": predicted_freight,
                "late_risk": late_risk,
            }
        )

    candidate_df = pd.DataFrame(candidate_rows)

    def normalize(series: pd.Series) -> pd.Series:
        lo = series.min()
        hi = series.max()

        if pd.isna(lo) or pd.isna(hi) or hi == lo:
            return pd.Series(
                np.zeros(len(series)),
                index=series.index,
            )

        return (series - lo) / (hi - lo)

    candidate_df["distance_norm"] = normalize(
        candidate_df["distance_km_or_proxy"]
    )
    candidate_df["freight_norm"] = normalize(
        candidate_df["predicted_freight"]
    )
    candidate_df["risk_norm"] = normalize(
        candidate_df["late_risk"]
    )

    candidate_df["seller_score"] = (
        seller_weight * candidate_df["distance_norm"]
        + freight_weight * candidate_df["freight_norm"]
        + risk_weight * candidate_df["risk_norm"]
    )

    selected = candidate_df.sort_values(
        "seller_score"
    ).iloc[0]

    selected_seller = candidates.loc[
        candidates["seller_id"].eq(selected["seller_id"])
    ].iloc[0]

    weight_kg = (
        pd.to_numeric(
            order_items["product_weight_g"],
            errors="coerce",
        )
        .fillna(0)
        .sum()
        / 1000.0
    )

    carrier, carrier_options = choose_carrier(
        carriers=carriers,
        distance_km=float(selected["distance_km_or_proxy"]),
        weight_kg=float(weight_kg),
        late_risk=float(selected["late_risk"]),
    )

    assignment = {
        "order_id": order_id,
        "customer_id": order["customer_id"],
        "customer_city": customer.get("customer_city", ""),
        "customer_state": customer.get("customer_state", ""),
        "selected_seller_id": selected_seller["seller_id"],
        "selected_seller_city": selected_seller.get(
            "seller_city",
            "",
        ),
        "selected_seller_state": selected_seller.get(
            "seller_state",
            "",
        ),
        "seller_distance_km_or_proxy": selected[
            "distance_km_or_proxy"
        ],
        "seller_distance_method": selected[
            "distance_method"
        ],
        "predicted_freight": selected[
            "predicted_freight"
        ],
        "late_risk_probability": selected[
            "late_risk"
        ],
        "carrier_id": carrier["carrier_id"],
        "carrier_name": carrier["carrier_name"],
        "carrier_estimated_cost": carrier[
            "estimated_cost"
        ],
        "carrier_estimated_eta_days": carrier[
            "estimated_eta_days"
        ],
        "carrier_score": carrier[
            "carrier_score"
        ],
        "seller_score": selected["seller_score"],
        "decision_reason": (
            "Seller selected by configurable distance/freight/risk score; "
            "carrier selected by estimated cost + risk + ETA score."
        ),
    }

    return assignment, carrier_options


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated seller and carrier assignment."
    )

    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--models-dir",
        type=Path,
        default=Path("ai_output"),
    )

    parser.add_argument(
        "--carriers",
        type=Path,
        default=DEFAULT_CARRIER_PATH,
    )

    parser.add_argument(
        "--geo-file",
        type=Path,
        default=None,
        help=(
            "Optional CSV with entity_type,entity_id,lat,lon "
            "for exact Haversine distances."
        ),
    )

    parser.add_argument(
        "--order-id",
        type=str,
        default=None,
        help="Assign one order. Default: first 100 orders.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=100,
    )

    args = parser.parse_args()

    data = load_data(
        args.data_dir
    )

    customers, sellers = add_coordinates(
        data["customers"],
        data["sellers"],
        args.geo_file,
    )

    data["customers"] = customers
    data["sellers"] = sellers

    freight_model_path = (
        args.models_dir
        / "freight_cost_model.joblib"
    )
    late_model_path = (
        args.models_dir
        / "late_delivery_model.joblib"
    )

    if not freight_model_path.exists():
        raise FileNotFoundError(
            f"Missing model: {freight_model_path}. "
            "Run ai_freight_delivery.py first."
        )

    if not late_model_path.exists():
        raise FileNotFoundError(
            f"Missing model: {late_model_path}. "
            "Run ai_freight_delivery.py first."
        )

    freight_model = joblib.load(
        freight_model_path
    )
    late_model = joblib.load(
        late_model_path
    )

    carriers = load_carriers(
        args.carriers
    )

    if args.order_id:
        order_ids = [args.order_id]
    else:
        order_ids = (
            data["orders"]["order_id"]
            .dropna()
            .astype(str)
            .head(args.limit)
            .tolist()
        )

    assignments = []
    carrier_rankings = []

    for order_id in order_ids:
        try:
            assignment, options = assign_order(
                order_id,
                data,
                freight_model,
                late_model,
                carriers,
            )

            assignments.append(
                assignment
            )

            options["order_id"] = order_id
            carrier_rankings.append(
                options
            )

        except Exception as exc:
            assignments.append(
                {
                    "order_id": order_id,
                    "assignment_error": str(exc),
                }
            )

    output_dir = args.models_dir
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    pd.DataFrame(
        assignments
    ).to_csv(
        output_dir / "automated_logistics_assignments.csv",
        index=False,
    )

    if carrier_rankings:
        pd.concat(
            carrier_rankings,
            ignore_index=True,
        ).to_csv(
            output_dir / "carrier_options_by_order.csv",
            index=False,
        )

    print(
        f"Automated assignments written to: "
        f"{output_dir / 'automated_logistics_assignments.csv'}"
    )


if __name__ == "__main__":
    main()
