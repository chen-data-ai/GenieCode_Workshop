# App code (Step 9) — OpenSky Flights

A **Streamlit** Databricks App that predicts an aircraft's **flight phase** from the
`opensky-flight-phase` Model Serving endpoint (serving `flight_phase_model_fs@prod`, which
auto-joins per-aircraft features from the Lakebase online store by `icao24`) and uses **Lakebase**
as its **operational database** (prediction log + feedback).

## Two-stage build

**Stage 1 — warm up first** (see [`00_initialize_databricks_app.md`](00_initialize_databricks_app.md)):
deploy an empty app and create the serving endpoint immediately so both provision in the
background (a few minutes each).

**Stage 2 — the real app** (`opensky-flights/`):

| File | Role |
|------|------|
| `app.py` | Streamlit UI: input form → predict → feedback → recent predictions |
| `backend.py` | Model Serving call (`WorkspaceClient`) + Lakebase connection, schema init, CRUD |
| `app.yaml` | `streamlit run app.py`; `SERVING_ENDPOINT` via `valueFrom`; `APP_SCHEMA=app` |
| `requirements.txt` | `streamlit`, `databricks-sdk`, `psycopg2-binary` |

Resources attached to the app: the **serving endpoint** (`CAN_QUERY`) and a **Lakebase database**
(`CAN_CONNECT_AND_CREATE`); Lakebase connection env vars (`PGHOST/PGDATABASE/PGUSER/PGPASSWORD/PGPORT`)
are auto-injected. The app's service principal creates and owns the `app` schema on first deploy.

## Run / test / deploy

```bash
PROFILE=fevm-serverless-stable-bbecx8
SRC=/Workspace/Users/<you>/opensky-flights-src

# Deploy (deploy BEFORE running locally so the SP owns the Lakebase schema)
databricks sync ./opensky-flights "$SRC" --profile $PROFILE
databricks apps deploy opensky-flights --source-code-path "$SRC" --profile $PROFILE

# Verify
databricks apps get opensky-flights --profile $PROFILE        # app_status.state=RUNNING, note url
databricks apps logs opensky-flights --profile $PROFILE        # check startup / schema init (OAuth required)
databricks serving-endpoints get opensky-flight-phase --profile $PROFILE   # state.ready=READY

# Smoke-test the model endpoint directly (use an icao24 present in aircraft_features)
databricks serving-endpoints query opensky-flight-phase --profile $PROFILE \
  --json '{"dataframe_records":[{"icao24":"<ID>","baro_altitude":5000,"geo_altitude":5200,"velocity":200,"true_track":90}]}'
```

> **Note:** the feature-store model looks features up by `icao24`, so the app predicts for aircraft
> present in `aircraft_features`. Unknown ids get null features. Local dev needs the SP to have
> created the schema first (deploy once before running locally).
