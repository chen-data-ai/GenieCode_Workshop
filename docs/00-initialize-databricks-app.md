# Initialize the Databricks App (warm-up)

> **Do this before building the app in [Step 9](90-lakebase-apps.md).** Databricks Apps and Model
> Serving endpoints take a few minutes to provision — so deploy an **empty app** and create the
> **serving endpoint** right away, then build the real app while they warm up in the background.

The app is **Streamlit** (Python). It will serve the flight-phase model and use **Lakebase** as its
operational database (prediction log, feedback, app state). Source lives in `code/app/`
(`00_initialize_databricks_app.md` + `opensky-flights/`).

## Prompt (Variant A — let Genie Code plan it)

```text
Create and immediately deploy a minimal Streamlit Databricks App named opensky-flights to begin provisioning its compute. Include only a title and a “Provisioning” message. Do not add the prediction interface or Lakebase integration yet.
```

## CLI (what the prompt runs)

```bash
PROFILE=fevm-serverless-stable-bbecx8

# Empty Streamlit app — create (provisions compute) then deploy the minimal source
databricks apps create opensky-flights --profile $PROFILE
databricks sync ./opensky-flights "/Workspace/Users/<you>/opensky-flights-src" --profile $PROFILE
databricks apps deploy opensky-flights \
  --source-code-path "/Workspace/Users/<you>/opensky-flights-src" --profile $PROFILE
```

## Confirm both are provisioning

```bash
databricks apps get opensky-flights --profile $PROFILE          # app_status.state → STARTING/RUNNING, note the url
databricks serving-endpoints get opensky-flight-phase --profile $PROFILE   # state.ready → READY (a few min)
```

Once both report healthy, continue to **[Step 9: Lakebase and Databricks Apps](90-lakebase-apps.md)**
to build the full UI, wire Lakebase as the operational store, and redeploy over the empty app.

---

### Tutorial navigation

| ← Previous | Overview | Next → |
|:---|:---:|---:|
| [8. AI/BI Dashboards and Genie Agents](80-dashboards.md) | [Table of contents](index.md) | [9. Databricks Apps + ML + Lakebase](90-lakebase-apps.md) |
