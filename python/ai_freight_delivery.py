"""
AI Freight & Delivery Intelligence for the Olist/E-Commerce dataset.

What this script does:
1. Predicts item-level freight cost.
2. Predicts order-level late-delivery risk using only information available
   before final delivery.
3. Diagnoses likely late-delivery drivers from observed process times.
4. Produces recommended operational actions.
5. Writes predictions, causes, recommendations, feature importance and model metrics.

Expected files in --data-dir:
- olist_orders_dataset.csv
- olist_order_items_dataset.csv
- olist_customers_dataset.csv
- olist_products_dataset.csv
- olist_sellers_dataset.csv
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesClassifier, ExtraTreesRegressor
from sklearn.inspection import permutation_importance
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


RANDOM_STATE = 42


def read_csv(data_dir: Path, name: str) -> pd.DataFrame:
    path = data_dir / name
    if not path.exists():
        raise FileNotFoundError(f"Missing dataset: {path}")
    return pd.read_csv(path)


def to_datetime(df: pd.DataFrame, columns: List[str]) -> None:
    for col in columns:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce")


def add_shared_features(orders: pd.DataFrame) -> pd.DataFrame:
    o = orders.copy()
    date_cols = [
        "order_purchase_timestamp",
        "order_approved_at",
        "order_delivered_carrier_date",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
    ]
    to_datetime(o, date_cols)

    o["purchase_year"] = o["order_purchase_timestamp"].dt.year
    o["purchase_month"] = o["order_purchase_timestamp"].dt.month
    o["purchase_dayofweek"] = o["order_purchase_timestamp"].dt.dayofweek
    o["purchase_hour"] = o["order_purchase_timestamp"].dt.hour

    o["approval_delay_hours"] = (
        o["order_approved_at"] - o["order_purchase_timestamp"]
    ).dt.total_seconds() / 3600.0

    o["estimated_lead_days"] = (
        o["order_estimated_delivery_date"] - o["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400.0

    o["seller_handoff_days"] = (
        o["order_delivered_carrier_date"] - o["order_approved_at"]
    ).dt.total_seconds() / 86400.0

    o["carrier_to_customer_days"] = (
        o["order_delivered_customer_date"] - o["order_delivered_carrier_date"]
    ).dt.total_seconds() / 86400.0

    o["actual_delivery_days"] = (
        o["order_delivered_customer_date"] - o["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400.0

    o["days_late"] = (
        o["order_delivered_customer_date"] - o["order_estimated_delivery_date"]
    ).dt.total_seconds() / 86400.0

    o["late_delivery"] = (
        o["order_delivered_customer_date"] > o["order_estimated_delivery_date"]
    ).astype("Int64")

    return o


def aggregate_items(
    items: pd.DataFrame, products: pd.DataFrame
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    i = items.copy()
    p = products.copy()

    numeric_product_cols = [
        "product_weight_g",
        "product_length_cm",
        "product_height_cm",
        "product_width_cm",
        "product_photos_qty",
        "product_name_lenght",
        "product_description_lenght",
    ]

    for col in numeric_product_cols:
        if col in p.columns:
            p[col] = pd.to_numeric(p[col], errors="coerce")

    if "shipping_limit_date" in i.columns:
        i["shipping_limit_date"] = pd.to_datetime(
            i["shipping_limit_date"], errors="coerce"
        )

    i = i.merge(
        p[
            [
                "product_id",
                "product_category_name",
                *[c for c in numeric_product_cols if c in p.columns],
            ]
        ],
        on="product_id",
        how="left",
    )

    for col in ["price", "freight_value"]:
        i[col] = pd.to_numeric(i[col], errors="coerce")

    i["product_volume_cm3"] = (
        i["product_length_cm"].fillna(0)
        * i["product_height_cm"].fillna(0)
        * i["product_width_cm"].fillna(0)
    )

    i["freight_to_price_ratio"] = i["freight_value"] / i["price"].replace(0, np.nan)

    order_agg = (
        i.groupby("order_id", as_index=False)
        .agg(
            item_count=("order_item_id", "count"),
            unique_products=("product_id", "nunique"),
            unique_sellers=("seller_id", "nunique"),
            total_price=("price", "sum"),
            total_freight=("freight_value", "sum"),
            avg_item_price=("price", "mean"),
            avg_freight=("freight_value", "mean"),
            avg_weight_g=("product_weight_g", "mean"),
            max_weight_g=("product_weight_g", "max"),
            avg_volume_cm3=("product_volume_cm3", "mean"),
            max_volume_cm3=("product_volume_cm3", "max"),
            avg_length_cm=("product_length_cm", "mean"),
            avg_height_cm=("product_height_cm", "mean"),
            avg_width_cm=("product_width_cm", "mean"),
            category_count=("product_category_name", "nunique"),
        )
    )

    return i, order_agg


def build_item_model_data(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    sellers: pd.DataFrame,
) -> pd.DataFrame:
    i, _ = aggregate_items(items, products)

    o = orders[
        [
            "order_id",
            "customer_id",
            "order_purchase_timestamp",
            "order_approved_at",
            "order_estimated_delivery_date",
        ]
    ].copy()

    c = customers[["customer_id", "customer_state", "customer_city"]].copy()
    s = sellers[["seller_id", "seller_state", "seller_city"]].copy()

    df = i.merge(o, on="order_id", how="left")
    df = df.merge(c, on="customer_id", how="left")
    df = df.merge(s, on="seller_id", how="left")

    to_datetime(
        df,
        [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_estimated_delivery_date",
            "shipping_limit_date",
        ],
    )

    df["purchase_year"] = df["order_purchase_timestamp"].dt.year
    df["purchase_month"] = df["order_purchase_timestamp"].dt.month
    df["purchase_dayofweek"] = df["order_purchase_timestamp"].dt.dayofweek
    df["purchase_hour"] = df["order_purchase_timestamp"].dt.hour

    df["customer_seller_same_state"] = (
        df["customer_state"].fillna("") == df["seller_state"].fillna("")
    ).astype(int)

    df["days_to_shipping_limit"] = (
        df["shipping_limit_date"] - df["order_purchase_timestamp"]
    ).dt.total_seconds() / 86400.0

    df["freight_value"] = pd.to_numeric(df["freight_value"], errors="coerce")
    return df


def build_order_dataset(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    products: pd.DataFrame,
    customers: pd.DataFrame,
    sellers: pd.DataFrame,
) -> pd.DataFrame:
    o = add_shared_features(orders)
    i, order_agg = aggregate_items(items, products)

    c = customers[["customer_id", "customer_state", "customer_city"]].copy()

    df = o.merge(order_agg, on="order_id", how="left")
    df = df.merge(c, on="customer_id", how="left")

    seller_state = (
        i[["order_id", "seller_id"]]
        .merge(
            sellers[["seller_id", "seller_state"]],
            on="seller_id",
            how="left",
        )
        .groupby("order_id", as_index=False)
        .agg(
            seller_state_nunique=("seller_state", "nunique"),
            primary_seller_state=(
                "seller_state",
                lambda s: s.dropna().mode().iloc[0]
                if not s.dropna().empty
                else np.nan,
            ),
        )
    )

    df = df.merge(seller_state, on="order_id", how="left")

    df["cross_state"] = (
        df["customer_state"].fillna("")
        != df["primary_seller_state"].fillna("")
    ).astype(int)

    # Train only on delivered orders because the target depends on final delivery.
    df = df[df["late_delivery"].notna()].copy()
    df["late_delivery"] = df["late_delivery"].astype(int)

    # Avoid target leakage in the predictive feature set. These fields remain in
    # the dataframe because the diagnostic layer uses them after delivery.
    return df


def make_preprocessor(
    numeric_features: List[str],
    categorical_features: List[str],
) -> ColumnTransformer:
    return ColumnTransformer(
        transformers=[
            (
                "num",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="median")),
                    ]
                ),
                [c for c in numeric_features if c],
            ),
            (
                "cat",
                Pipeline(
                    steps=[
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        (
                            "onehot",
                            OneHotEncoder(
                                handle_unknown="ignore",
                                min_frequency=10,
                            ),
                        ),
                    ]
                ),
                [c for c in categorical_features if c],
            ),
        ],
        remainder="drop",
    )


def feature_importance_table(
    pipeline: Pipeline,
    X_test: pd.DataFrame,
    y_test: pd.Series,
    task: str,
) -> pd.DataFrame:
    scoring = "roc_auc" if task == "classification" else "neg_mean_absolute_error"

    result = permutation_importance(
        pipeline,
        X_test,
        y_test,
        n_repeats=5,
        random_state=RANDOM_STATE,
        scoring=scoring,
        n_jobs=-1,
    )

    return (
        pd.DataFrame(
            {
                "feature": X_test.columns,
                "importance_mean": result.importances_mean,
                "importance_std": result.importances_std,
            }
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )


def train_freight_model(df: pd.DataFrame, out_dir: Path) -> Dict:
    target = "freight_value"

    numeric = [
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
    ]

    categorical = [
        "product_category_name",
        "seller_state",
        "customer_state",
        "customer_seller_same_state",
    ]

    features = [c for c in numeric + categorical if c in df.columns]
    model_df = df[features + [target]].dropna(subset=[target]).copy()

    X = model_df[features]
    y = model_df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
    )

    preprocessor = make_preprocessor(numeric, categorical)

    model = ExtraTreesRegressor(
        n_estimators=350,
        min_samples_leaf=3,
        max_features=0.8,
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )

    pipeline.fit(X_train, y_train)

    pred = pipeline.predict(X_test)

    metrics = {
        "mae": float(mean_absolute_error(y_test, pred)),
        "rmse": float(np.sqrt(mean_squared_error(y_test, pred))),
        "test_rows": int(len(y_test)),
        "target_mean": float(y_test.mean()),
    }

    importance = feature_importance_table(
        pipeline,
        X_test,
        y_test,
        "regression",
    )
    importance.to_csv(
        out_dir / "freight_feature_importance.csv",
        index=False,
    )

    freight_predictions = X_test.copy()
    freight_predictions["actual_freight_value"] = y_test.to_numpy()
    freight_predictions["predicted_freight_value"] = pred
    freight_predictions["absolute_error"] = np.abs(
        freight_predictions["actual_freight_value"]
        - freight_predictions["predicted_freight_value"]
    )

    freight_predictions.to_csv(
        out_dir / "freight_predictions.csv",
        index=False,
    )

    joblib.dump(
        pipeline,
        out_dir / "freight_cost_model.joblib",
    )

    return metrics


def train_late_model(df: pd.DataFrame, out_dir: Path) -> Dict:
    target = "late_delivery"

    numeric = [
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
    ]

    categorical = [
        "customer_state",
        "primary_seller_state",
        "order_status",
    ]

    # Notice what is intentionally NOT present:
    # order_delivered_customer_date, days_late, actual_delivery_days,
    # seller_handoff_days, and carrier_to_customer_days.
    # These would leak the final outcome or post-delivery information.
    features = [c for c in numeric + categorical if c in df.columns]

    model_df = df[features + [target]].dropna(subset=[target]).copy()

    X = model_df[features]
    y = model_df[target]

    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.20,
        random_state=RANDOM_STATE,
        stratify=y,
    )

    preprocessor = make_preprocessor(numeric, categorical)

    model = ExtraTreesClassifier(
        n_estimators=400,
        min_samples_leaf=4,
        max_features=0.8,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        n_jobs=-1,
    )

    pipeline = Pipeline(
        [
            ("preprocessor", preprocessor),
            ("model", model),
        ]
    )

    pipeline.fit(X_train, y_train)

    prob = pipeline.predict_proba(X_test)[:, 1]
    pred = (prob >= 0.50).astype(int)

    precision, recall, f1, _ = precision_recall_fscore_support(
        y_test,
        pred,
        average="binary",
        zero_division=0,
    )

    metrics = {
        "roc_auc": float(roc_auc_score(y_test, prob)),
        "accuracy": float(accuracy_score(y_test, pred)),
        "precision": float(precision),
        "recall": float(recall),
        "f1": float(f1),
        "late_rate": float(y_test.mean()),
        "test_rows": int(len(y_test)),
    }

    importance = feature_importance_table(
        pipeline,
        X_test,
        y_test,
        "classification",
    )
    importance.to_csv(
        out_dir / "late_delivery_feature_importance.csv",
        index=False,
    )

    late_predictions = X_test.copy()
    late_predictions["actual_late_delivery"] = y_test.to_numpy()
    late_predictions["late_risk_probability"] = prob
    late_predictions["predicted_late_delivery"] = pred

    late_predictions.to_csv(
        out_dir / "late_delivery_predictions.csv",
        index=False,
    )

    with open(
        out_dir / "late_classification_report.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            classification_report(
                y_test,
                pred,
                output_dict=True,
                zero_division=0,
            ),
            f,
            indent=2,
        )

    joblib.dump(
        pipeline,
        out_dir / "late_delivery_model.joblib",
    )

    return metrics


def cause_score(
    row: pd.Series,
    thresholds: Dict[str, float],
) -> Tuple[str, float]:
    scores = {
        "Seller processing delay": 0.0,
        "Carrier transit delay": 0.0,
        "Tight delivery estimate": 0.0,
        "Geographic complexity": 0.0,
        "Heavy / bulky shipment": 0.0,
        "High freight burden": 0.0,
    }

    if (
        pd.notna(row.get("seller_handoff_days"))
        and row["seller_handoff_days"] > thresholds["seller_handoff_days"]
    ):
        scores["Seller processing delay"] += 3.0

    if (
        pd.notna(row.get("carrier_to_customer_days"))
        and row["carrier_to_customer_days"]
        > thresholds["carrier_to_customer_days"]
    ):
        scores["Carrier transit delay"] += 3.0

    if (
        pd.notna(row.get("estimated_lead_days"))
        and row["estimated_lead_days"] < thresholds["estimated_lead_days"]
    ):
        scores["Tight delivery estimate"] += 2.0

    if row.get("cross_state", 0) == 1:
        scores["Geographic complexity"] += 2.0

    if (
        pd.notna(row.get("max_weight_g"))
        and row["max_weight_g"] > thresholds["max_weight_g"]
    ):
        scores["Heavy / bulky shipment"] += 2.0

    if (
        pd.notna(row.get("freight_ratio"))
        and row["freight_ratio"] > thresholds["freight_ratio"]
    ):
        scores["High freight burden"] += 2.0

    cause, score = max(
        scores.items(),
        key=lambda x: x[1],
    )
    return cause, float(score)


def diagnose_and_recommend(
    df: pd.DataFrame,
    out_dir: Path,
) -> None:
    d = df.copy()

    d["freight_ratio"] = (
        d["total_freight"]
        / d["total_price"].replace(0, np.nan)
    )

    thresholds = {
        "seller_handoff_days": float(
            d["seller_handoff_days"].quantile(0.75)
        ),
        "carrier_to_customer_days": float(
            d["carrier_to_customer_days"].quantile(0.75)
        ),
        "estimated_lead_days": float(
            d["estimated_lead_days"].quantile(0.25)
        ),
        "max_weight_g": float(
            d["max_weight_g"].quantile(0.75)
        ),
        "freight_ratio": float(
            d["freight_ratio"].quantile(0.75)
        ),
    }

    late = d[d["late_delivery"] == 1].copy()

    recommendations = {
        "Seller processing delay": (
            "Tighten seller shipping SLA; monitor approval-to-handoff time; "
            "prioritize high-risk sellers; add seller-level alerts."
        ),
        "Carrier transit delay": (
            "Review carrier and route performance; allocate faster service "
            "on high-risk lanes; trigger exception management before SLA breach."
        ),
        "Tight delivery estimate": (
            "Increase estimated-delivery buffer using historical lane "
            "performance instead of a single global promise."
        ),
        "Geographic complexity": (
            "Segment lanes by origin and destination state; pre-position "
            "fast-moving inventory or use regional fulfillment for expensive/slow lanes."
        ),
        "Heavy / bulky shipment": (
            "Re-evaluate packaging dimensions; negotiate dimensional-weight "
            "rates; compare carriers for bulky SKUs."
        ),
        "High freight burden": (
            "Review freight pricing by SKU and lane; consolidate shipments; "
            "negotiate carrier contracts where freight-to-item-price is persistently high."
        ),
    }

    if late.empty:
        pd.DataFrame(
            columns=[
                "order_id",
                "primary_cause",
                "cause_score",
                "recommended_action",
            ]
        ).to_csv(
            out_dir / "late_delivery_causes.csv",
            index=False,
        )
        return

    causes = late.apply(
        lambda row: cause_score(row, thresholds),
        axis=1,
        result_type="expand",
    )
    causes.columns = [
        "primary_cause",
        "cause_score",
    ]

    late = pd.concat(
        [
            late.reset_index(drop=True),
            causes.reset_index(drop=True),
        ],
        axis=1,
    )

    late["recommended_action"] = late["primary_cause"].map(
        recommendations
    )

    late[
        [
            "order_id",
            "primary_cause",
            "cause_score",
            "days_late",
            "seller_handoff_days",
            "carrier_to_customer_days",
            "total_freight",
            "freight_ratio",
            "cross_state",
            "recommended_action",
        ]
    ].to_csv(
        out_dir / "late_delivery_causes.csv",
        index=False,
    )

    cause_summary = (
        late.groupby(
            "primary_cause",
            as_index=False,
        )
        .agg(
            late_orders=("order_id", "count"),
            avg_days_late=("days_late", "mean"),
            avg_freight=("total_freight", "mean"),
        )
        .sort_values(
            "late_orders",
            ascending=False,
        )
    )

    cause_summary.to_csv(
        out_dir / "late_cause_summary.csv",
        index=False,
    )

    with open(
        out_dir / "recommended_actions.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            recommendations,
            f,
            indent=2,
        )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--data-dir",
        type=Path,
        required=True,
        help="Folder containing the five Olist CSV files.",
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ai_output"),
    )

    args = parser.parse_args()
    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    orders = read_csv(
        args.data_dir,
        "olist_orders_dataset.csv",
    )
    items = read_csv(
        args.data_dir,
        "olist_order_items_dataset.csv",
    )
    customers = read_csv(
        args.data_dir,
        "olist_customers_dataset.csv",
    )
    products = read_csv(
        args.data_dir,
        "olist_products_dataset.csv",
    )
    sellers = read_csv(
        args.data_dir,
        "olist_sellers_dataset.csv",
    )

    item_df = build_item_model_data(
        orders,
        items,
        products,
        customers,
        sellers,
    )

    order_df = build_order_dataset(
        orders,
        items,
        products,
        customers,
        sellers,
    )

    freight_metrics = train_freight_model(
        item_df,
        args.output_dir,
    )

    late_metrics = train_late_model(
        order_df,
        args.output_dir,
    )

    diagnose_and_recommend(
        order_df,
        args.output_dir,
    )

    summary = {
        "project": "AI Freight & Delivery Intelligence",
        "freight_model": freight_metrics,
        "late_delivery_model": late_metrics,
        "outputs": [
            "freight_cost_model.joblib",
            "late_delivery_model.joblib",
            "freight_predictions.csv",
            "late_delivery_predictions.csv",
            "freight_feature_importance.csv",
            "late_delivery_feature_importance.csv",
            "late_delivery_causes.csv",
            "late_cause_summary.csv",
            "recommended_actions.json",
        ],
    }

    with open(
        args.output_dir / "model_summary.json",
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            summary,
            f,
            indent=2,
        )

    print("\nAI Freight & Delivery Intelligence complete.")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
