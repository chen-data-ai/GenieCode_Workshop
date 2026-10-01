# 9. Databricks Apps + ML + Lakebase

The capstone: a governed **Databricks App** (Streamlit) that turns the [ML model](70-ml-models.md)
into an interactive product, with **Lakebase** as its operational database. It predicts an
aircraft's **flight phase** from a Model Serving endpoint and logs every prediction and piece of
feedback to Lakebase.

> ⚠️ **Warm up the compute first — don't wait on spin-up.**
> Databricks Apps and Model Serving endpoints take a few minutes to provision. So **before** you
> build anything, run **[Initialize the Databricks App (warm-up)](00-initialize-databricks-app.md)**:
> it deploys an *empty* app and creates the serving endpoint so both provision in the background
> while you build the real app. By the time the code is ready, the compute is already running.

## What you'll build

**OpenSky Flights** — a Streamlit app (`code/app/opensky-flights/`) that:

1. Takes an aircraft state (`icao24` + `baro_altitude`, `geo_altitude`, `velocity`, `true_track`).
2. Calls the **`opensky-flight-phase`** Model Serving endpoint (serving `flight_phase_model_fs@prod`),
   which **auto-joins per-aircraft features from the Lakebase online store** by `icao24`.
3. Shows the predicted phase (Ground / Climb / Descent / Cruise) and **logs it to Lakebase**.
4. Captures 👍/👎 **feedback** and shows **recent predictions** — all from Lakebase.

## Lakebase plays two roles here

| Role | Table | Written by |
|------|-------|-----------|
| **Online feature store** | `aircraft_features_online` (in `opensky-online-store`) | [Step 7](70-ml-models.md) `fe.publish_table` — serves features to the model endpoint |
| **Operational database** | `app.prediction_log`, `app.feedback` (app-owned schema) | the app's service principal, on every prediction/feedback |

## Architecture & data flow

```
User → Streamlit app (opensky-flights)
         │  /predict
         ▼
   Model Serving endpoint  opensky-flight-phase  (flight_phase_model_fs@prod)
         │  auto-joins aircraft features by icao24
         ▼  ◄──────────────  Lakebase online store (aircraft_features_online)
   predicted phase
         │
         ├─► shown in the UI (phase-colored card)
         └─► INSERT into Lakebase  app.prediction_log      (operational store)
 feedback 👍/👎 ─────────────────► app.feedback
 recent view / KPIs ◄───────────── app.*
```

## Build it with Genie Code

The warm-up prompt lives in **[Initialize the Databricks App (warm-up)](00-initialize-databricks-app.md)**.
Once the empty app + endpoint are provisioning, build the real app with this prompt:

```text
Build the OpenSky Flights Streamlit app on Databricks Apps. It should:
- Take an aircraft state: icao24 + baro_altitude, geo_altitude, velocity, true_track.
- Predict flight phase by calling the opensky-flight-phase Model Serving endpoint
  (serving serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs@prod), which auto-joins
  the aircraft_features from the Lakebase online store by icao24.
- Use Lakebase as the operational database: on each prediction INSERT into an app-owned schema
  (app.prediction_log); capture thumbs-up/down feedback into app.feedback; show recent predictions.
- Authenticate as the app service principal (databricks-sdk Config), connect to Lakebase with an
  OAuth token from w.postgres.generate_database_credential(endpoint=LAKEBASE_ENDPOINT), and handle
  errors gracefully.
Wire the serving endpoint and Lakebase as app resources, and give it a clean phase-colored UI.
```

## How to run, test & deploy

```bash
PROFILE=fevm-serverless-stable-bbecx8
SRC=/Workspace/Users/<you>/opensky-flights-src

# Attach resources once (serving endpoint + Lakebase operational DB)
databricks apps create-update opensky-flights --profile $PROFILE --json '{
  "update_mask": "resources",
  "app": {"resources": [
    {"name": "serving-endpoint", "serving_endpoint": {"name": "opensky-flight-phase", "permission": "CAN_QUERY"}},
    {"name": "database", "postgres": {
      "branch":   "projects/opensky-online-store/branches/production",
      "database": "projects/opensky-online-store/branches/production/databases/databricks-postgres",
      "permission": "CAN_CONNECT_AND_CREATE"}}
  ]}
}'

# Deploy (deploy BEFORE running locally so the SP owns the Lakebase schema)
databricks sync ./opensky-flights "$SRC" --profile $PROFILE
databricks apps deploy opensky-flights --source-code-path "$SRC" --profile $PROFILE

# Verify
databricks apps get opensky-flights --profile $PROFILE                      # app_status.state=RUNNING, note url
databricks serving-endpoints get opensky-flight-phase --profile $PROFILE    # state.ready=READY
databricks apps logs opensky-flights --profile $PROFILE                     # startup / schema init
```

> **Gotchas we hit (and fixed):** Lakebase auth is a **short-lived OAuth token**, not a static
> password — mint it with `w.postgres.generate_database_credential(endpoint=LAKEBASE_ENDPOINT)`.
> And **pin `databricks-sdk>=0.144.0`** in `requirements.txt`, or the runtime's older preinstalled
> SDK (without the Beta `w.postgres` API) silently breaks the Lakebase connection.

## Databricks Apps — Beyond the Basics

- **[Governed app resources](https://docs.databricks.com/aws/en/dev-tools/databricks-apps/resources)** —
  declare the serving endpoint (`CAN_QUERY`) and Lakebase (`CAN_CONNECT_AND_CREATE`) as resources so
  the app's service principal gets scoped, auditable access.
- **[Lakebase online store](https://docs.databricks.com/aws/en/oltp/)** — the same Postgres layer
  serves model features (online) *and* app state (operational), with scale-to-zero.
- **Model version swaps** — repoint the `@prod` alias and `update-config` the endpoint for
  zero-downtime model updates behind the running app.

## Recap

You shipped a governed, end-to-end product: a Streamlit **Databricks App** that serves the
**flight-phase model** (with features from the **Lakebase** online store) and uses **Lakebase** as
its **operational database** for predictions and feedback — warmed up ahead of time so there's no
spin-up wait.

---

### Tutorial navigation

| ← Previous | Overview | Next → |
|:---|:---:|---:|
| [Initialize the Databricks App (warm-up)](00-initialize-databricks-app.md) | [Table of contents](index.md) | [Bonus — Databricks Apps gallery (Flight DNA)](90-apps.md) |
