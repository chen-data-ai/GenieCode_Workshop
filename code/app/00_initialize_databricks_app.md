# 00 · Initialize the Databricks App (warm-up)

**Do this first.** Databricks Apps and Model Serving endpoints take a few minutes to provision, so
deploy an **empty app** and create the **serving endpoint** right away — they warm up in the
background while you build the real app ([Step 9: Lakebase and Databricks Apps](../../docs/90-lakebase-apps.md)).

This app is **Streamlit** (Python). It will serve the flight-phase model and use **Lakebase** as its
operational database (prediction log, feedback, app state).

## Prompt

```text
Warm up the app infrastructure first. (1) Create a Model Serving endpoint named
opensky-flight-phase for serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs@prod so it
provisions in parallel. (2) Scaffold a minimal empty Streamlit Databricks App named opensky-flights
(just a title + "provisioning" message — no real UI yet), create it, and deploy it immediately so
its compute starts provisioning. Don't build the prediction UI or Lakebase wiring yet — that's the
next step; the goal here is only to get the empty app and the endpoint warming up.
```

## CLI (what the prompt runs)

```bash
PROFILE=fevm-serverless-stable-bbecx8

# 1. Serving endpoint (feature-store model; auto-joins aircraft_features from the Lakebase online store)
databricks serving-endpoints create --no-wait --profile $PROFILE --json '{
  "name": "opensky-flight-phase",
  "config": {"served_entities": [{
    "entity_name": "serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs",
    "entity_version": "3", "workload_size": "Small", "scale_to_zero_enabled": true}]}
}'

# 2. Empty Streamlit app — create (provisions compute) then deploy the minimal source
databricks apps create opensky-flights --profile $PROFILE
databricks sync ./opensky-flights "/Workspace/Users/<you>/opensky-flights-src" --profile $PROFILE
databricks apps deploy opensky-flights \
  --source-code-path "/Workspace/Users/<you>/opensky-flights-src" --profile $PROFILE
```

## Confirm it's provisioning

```bash
databricks apps get opensky-flights --profile $PROFILE          # app_status.state → STARTING/RUNNING, note the url
databricks serving-endpoints get opensky-flight-phase --profile $PROFILE   # state.ready → READY (a few min)
```

Once both report healthy, continue to the full build (Lakebase schema, prediction + feedback, UI).
