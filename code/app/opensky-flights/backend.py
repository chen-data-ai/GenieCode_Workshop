"""Backend for the OpenSky Flights app: Model Serving + Lakebase operational store.

- Predictions come from the `opensky-flight-phase` Model Serving endpoint (serves
  `flight_phase_model_fs@prod`, which auto-joins per-aircraft features from the Lakebase
  online store by `icao24`).
- Operational data (prediction log, feedback) is persisted in a Lakebase (Postgres) schema the
  app owns. Connection env vars (PGHOST/PGDATABASE/PGUSER/PGPASSWORD/PGPORT) are auto-injected
  when the Lakebase database resource is attached to the app.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import psycopg2
import streamlit as st
from databricks.sdk import WorkspaceClient

APP_SCHEMA = os.getenv("APP_SCHEMA", "app")
SERVING_ENDPOINT = os.getenv("SERVING_ENDPOINT", "opensky-flight-phase")
FEATURES = ["baro_altitude", "geo_altitude", "velocity", "true_track"]


# --- Model Serving ---------------------------------------------------------

@st.cache_resource
def _workspace_client() -> WorkspaceClient:
    return WorkspaceClient()


def predict_phase(icao24: str, features: dict) -> str:
    """Call the serving endpoint. The feature-store model auto-joins aircraft features by icao24."""
    record = {"icao24": icao24, **{f: features[f] for f in FEATURES}}
    resp = _workspace_client().serving_endpoints.query(
        name=SERVING_ENDPOINT, dataframe_records=[record]
    )
    preds = resp.predictions
    return str(preds[0]) if preds else "unknown"


# --- Lakebase (operational store) ------------------------------------------
# Lakebase auth is a short-lived OAuth token (NOT a static PGPASSWORD): the platform injects
# PGHOST/PGUSER/PGDATABASE/LAKEBASE_ENDPOINT, and we mint the token with
# w.postgres.generate_database_credential(endpoint=LAKEBASE_ENDPOINT). Tokens expire ~1h, so we
# open a short-lived connection with a fresh token per operation (fine for this low-traffic app).

LAKEBASE_ENDPOINT = os.getenv(
    "LAKEBASE_ENDPOINT", "projects/opensky-online-store/branches/production/endpoints/primary"
)


def lakebase_configured() -> bool:
    return bool(os.getenv("PGHOST") and LAKEBASE_ENDPOINT)


def _connect():
    token = _workspace_client().postgres.generate_database_credential(endpoint=LAKEBASE_ENDPOINT).token
    conn = psycopg2.connect(
        host=os.getenv("PGHOST"),
        dbname=os.getenv("PGDATABASE"),
        user=os.getenv("PGUSER"),
        password=token,
        port=os.getenv("PGPORT", "5432"),
        sslmode="require",
    )
    conn.autocommit = True
    return conn


@contextmanager
def _cursor():
    conn = _connect()
    try:
        with conn.cursor() as cur:
            yield cur
    finally:
        conn.close()


def init_schema() -> None:
    """Create the app-owned schema and operational tables (idempotent). SP owns them."""
    with _cursor() as cur:
        cur.execute(f"CREATE SCHEMA IF NOT EXISTS {APP_SCHEMA}")
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {APP_SCHEMA}.prediction_log (
                id             BIGSERIAL PRIMARY KEY,
                icao24         TEXT,
                baro_altitude  DOUBLE PRECISION,
                geo_altitude   DOUBLE PRECISION,
                velocity       DOUBLE PRECISION,
                true_track     DOUBLE PRECISION,
                predicted_phase TEXT,
                created_by     TEXT,
                created_at     TIMESTAMPTZ DEFAULT now()
            )
            """
        )
        cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {APP_SCHEMA}.feedback (
                id            BIGSERIAL PRIMARY KEY,
                prediction_id BIGINT REFERENCES {APP_SCHEMA}.prediction_log(id),
                is_correct    BOOLEAN,
                correct_phase TEXT,
                created_at    TIMESTAMPTZ DEFAULT now()
            )
            """
        )


def log_prediction(icao24: str, features: dict, phase: str, user: str) -> int:
    with _cursor() as cur:
        cur.execute(
            f"""INSERT INTO {APP_SCHEMA}.prediction_log
                (icao24, baro_altitude, geo_altitude, velocity, true_track, predicted_phase, created_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (icao24, features["baro_altitude"], features["geo_altitude"], features["velocity"],
             features["true_track"], phase, user),
        )
        return cur.fetchone()[0]


def log_feedback(prediction_id: int, is_correct: bool, correct_phase: str | None) -> None:
    with _cursor() as cur:
        cur.execute(
            f"""INSERT INTO {APP_SCHEMA}.feedback (prediction_id, is_correct, correct_phase)
                VALUES (%s,%s,%s)""",
            (prediction_id, is_correct, correct_phase),
        )


def recent_predictions(limit: int = 10):
    with _cursor() as cur:
        cur.execute(
            f"""SELECT icao24, predicted_phase, velocity, baro_altitude, created_by, created_at
                FROM {APP_SCHEMA}.prediction_log ORDER BY created_at DESC LIMIT %s""",
            (limit,),
        )
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
