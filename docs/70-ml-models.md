# 7. Machine learning: flight-phase classification with Genie Code

This is the principal document for the ML workflow. It states the problem, the data scope, every
step of the ML lifecycle, the exact **Genie Code** prompts to reproduce it (two ways), how to run
the notebooks in order, and the results. The notebooks live in `code/ml/`
(`01_data_prep` → `02_eda` → `03_train_register` → `04_evaluate`), each carrying its own `## Prompt`
cell.

## MLOps architecture & lifecycle

These notebooks are the **experimentation** half of a bigger picture. On Databricks the same work
hardens into production with the **"deploy code, not models"** approach: tested *code* is promoted
**dev → staging → prod**, and each environment runs the same pipelines against its own Unity Catalog
assets (rather than copying model artifacts between environments).

![Databricks production MLOps architecture — feature engineering, model training with MLflow, evaluation, registration in Unity Catalog, Champion/Challenger deployment and serving, monitoring and scheduled retraining, orchestrated by Lakeflow Jobs.](https://docs.databricks.com/aws/en/assets/images/mlops-prod-diagram-8033cbb4ce8746883c46e8dc4101faed.png)

*Databricks MLOps production architecture. Source: [MLOps workflow on Databricks](https://docs.databricks.com/aws/en/machine-learning/mlops/mlops-workflow).*

### The lifecycle, end to end

1. **Data preparation** — scope, data-quality checks, cleaning → a curated Delta table.
2. **Feature engineering** — reusable features in Unity Catalog (offline for training, online for serving).
3. **Experimentation (EDA)** — interactive exploration of distributions, class balance, feature signal.
4. **Model training** — fit/compare models with hyperparameters; every run logged to MLflow.
5. **Evaluation** — metrics on held-out data (classification report, confusion matrix, macro-F1).
6. **Registration** — the best model becomes a governed object in Unity Catalog with a `@prod` alias.
7. **Deployment / serving** — batch inference to a gold table, or a Model Serving REST endpoint; online features from Lakebase.
8. **Monitoring** — track input drift and prediction quality once in production.
9. **Retraining** — re-run the pipeline on a schedule or when drift/new data triggers it.

### Platform building blocks

- **MLflow** — experiment tracking (params, metrics, artifacts) and the model flavor logged for every run; the comparison that picks the best model.
- **Unity Catalog (Models in UC)** — governance, versioning, lineage, and the movable `@prod` / `@challenger` aliases models are loaded by.
- **Lakeflow Jobs** — orchestration: runs the notebooks as a scheduled, multi-task workflow with retries (dev → staging → prod).
- **Model Serving** — serverless REST endpoints (scale-to-zero, A/B traffic) for real-time inference when batch isn't enough.
- **CI/CD** — promotes code through branches (dev → main → release) with automated unit/integration tests; the engine behind "deploy code, not models."

### How this repo maps to the architecture

| Lifecycle stage | In this repo |
|-----------------|--------------|
| Data preparation & quality | `01_data_prep.py` → `ml_flight_state_vectors` |
| Experimentation / EDA | `02_eda.py` |
| Feature engineering | `05_feature_store_lakebase.py` → `aircraft_features` (FeatureLookup) |
| Model training + tracking | `03_train_register.py` (MLflow autolog, model comparison) |
| Evaluation | `04_evaluate.py` (classification report, confusion matrix, macro-F1) |
| Registration (UC) | `03`/`05` → `…opensky.flight_phase_model` / `…flight_phase_model_fs` `@prod` |
| Deployment / serving | Batch → `gold_flight_phase_predictions`; online features → Lakebase `opensky-online-store`; (Model Serving endpoint = next step) |
| Orchestration | the serverless multi-task **Lakeflow Job** running `01 → 02 → 03 → 04` |
| Monitoring / retraining | *not yet implemented* — schedule the job + add Lakehouse Monitoring (next step) |

### Dev / staging / prod

| Environment | Access model | Purpose |
|-------------|--------------|---------|
| **Dev** | read-write dev catalog; read-only prod | Experimentation and temporary assets — **this workshop runs here** |
| **Staging** | isolated staging catalog | CI/CD integration tests on the promoted code |
| **Prod** | write-restricted to ML engineers; read-only for data scientists | Scheduled pipelines and production inference/serving |

This workshop runs entirely in a single dev-style workspace; in a real deployment the *same*
notebooks run unchanged as code promoted through dev → staging → prod.

## Feature engineering & online serving

Feature Store notebook `05` builds a per-aircraft feature table and serves it from Lakebase. That
pattern is evolving on Databricks into **[Feature Views](https://www.databricks.com/blog/introducing-feature-views)**
— the recommended way to keep training and serving features identical.

- **Define once, no skew.** You declare the feature logic once (source, entity, time-series column,
  computation); Databricks generates both the training data and the production serving pipeline from
  that single definition — eliminating the "computed differently at train vs. serve" failure mode.
- **Offline + online materialization.** Features materialize **offline to Delta** (point-in-time-correct
  training sets) and **online to Lakebase** (low-latency inference) from the same spec.
- **Managed pipelines.** Backfills, streaming aggregations (e.g. `RollingWindow` over Kafka), and
  infrastructure are managed — you call `materialize_features()`; real-time paths reach ~200 ms p99.
- **Governed in Unity Catalog.** Features become discoverable, lineage-tracked UC objects, shareable
  across models and teams.

**In this repo:** `05_feature_store_lakebase.py` uses the GA **`FeatureLookup` API** today — it
computes `aircraft_features` (keyed by `icao24`), binds the lineage to the model with
`fe.log_model`, and **publishes to the Lakebase online store `opensky-online-store`**
(`aircraft_features_online`) for real-time `icao24` lookups. Feature Views (declarative, Public
Preview) are the forward-looking evolution of the same idea — see the blog above.

## Business problem

Air-traffic and airspace-analytics teams need to know **what each aircraft is doing** at any
moment — sitting on the ground, climbing out, cruising, or descending — to power situational
dashboards, capacity analysis, and anomaly detection. The raw OpenSky feed doesn't carry a clean
"phase" label, so we learn one from the telemetry.

## ML problem & expected outcome

A **multiclass classification** model that labels each state-vector record as one of four **flight
phases**, from a handful of kinematic features:

- `Ground` — `on_ground = true`
- `Climb` — `on_ground = false` and `vertical_rate > 1.5`
- `Descent` — `on_ground = false` and `vertical_rate < -1.5`
- `Cruise` — otherwise

**Features:** `baro_altitude`, `geo_altitude`, `velocity`, `true_track`.
**Deliberately excluded:** `on_ground` and `vertical_rate` — they *define* the label, so using them
as features would be **target leakage**. That makes this an honest, non-trivial problem: `Ground` is
easy, but `Climb` / `Cruise` / `Descent` overlap without the vertical-rate signal.

## Data source & selected scope

- **Source:** `serverless_stable_bbecx8_catalog.opensky.state_vectors_raw` (raw OpenSky state
  vectors, one full UTC day, ~696M rows).
- **Scope (applied first):** **Americas** region (`longitude BETWEEN -170 AND -30`) for
  **2026-03-01 18:00–18:15 UTC** — a small, clearly-defined slice (~7M rows) that keeps the
  workflow fast and reproducible.
- **Curated output:** `serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors`.
- The workflow is **independent from the SDP pipeline** but **reuses its silver data-quality
  rules** (valid lat/lon, ranges for latitude/longitude/geo_altitude/true_track) — see
  [Spark Declarative Pipeline](40-pipeline.md).

## The ML lifecycle, step by step

| Notebook | Lifecycle phase | What it does |
|----------|-----------------|--------------|
| `01_data_prep` | Data prep & quality | Filter region + time first; null/range data-quality checks; clean with SDP-equivalent rules; write the curated Delta table. |
| `02_eda` | Exploratory analysis | Class balance, missing values, feature distributions & outliers, geographic coverage, per-minute time pattern, feature-vs-phase signal. |
| `03_train_register` | Train + track + govern | Derive label; stratified sample preserving class proportions; compare 3 models with **MLflow autologging**; register best to **Unity Catalog** as `flight_phase_model`, alias `@prod`. |
| `04_evaluate` | Evaluate + score | Evaluate `@prod` (classification report, confusion matrix, macro-F1); interpret + limitations; batch-score to `gold_flight_phase_predictions`. |
| `05_feature_store_lakebase` *(optional)* | Feature Store + Lakebase | Per-aircraft feature table + `FeatureLookup` lineage (`fe.log_model` / `fe.score_batch`); registers `flight_phase_model_fs`; publishes features to a **Lakebase** online store. |

**MLflow** tracks every experiment, parameter, metric, artifact (classification report + confusion
matrix), and model version; the best model is governed in **Unity Catalog** with a movable `@prod`
alias.

## Reproduce with Genie Code

The whole workflow was authored with **Genie Code**'s
[Data Science Agent](https://docs.databricks.com/aws/en/notebooks/ds-agent). Two ways to reproduce it.

### Variant A — let Genie Code plan it

One prompt that hands Genie Code the objective and constraints and lets the agent plan and build
the notebooks:

```text
You are my data science agent. Build an end-to-end flight-phase classification workflow on
serverless_stable_bbecx8_catalog.opensky.state_vectors_raw, and plan the steps yourself.

Scope (apply first): Americas region (longitude between -170 and -30), 2026-03-01 18:00-18:15 UTC.
Create a small curated table.

Label: Ground when on_ground; Climb when not on_ground and vertical_rate > 1.5; Descent when not
on_ground and vertical_rate < -1.5; otherwise Cruise.
Features: baro_altitude, geo_altitude, velocity, true_track ONLY. Do NOT use on_ground or
vertical_rate as features (target leakage).

Plan and build notebooks that: (1) filter + run data-quality checks + clean with rules equivalent
to the pipeline silver expectations (valid lat/lon, lat -90..90, lon -180..180, geo_altitude
-500..50000, true_track 0..360) + write a curated Delta table; (2) run an ML-focused EDA;
(3) take a stratified sample preserving class balance, compare Logistic Regression, Random Forest
and Histogram Gradient Boosting with MLflow autologging, evaluate with classification report,
confusion matrix and macro F1; (4) register the best model in Unity Catalog as
serverless_stable_bbecx8_catalog.opensky.flight_phase_model with a @prod alias, then evaluate it and
batch-score a sample into a gold predictions table; (5) as a Feature Store variant, engineer a
per-aircraft feature table keyed by icao24 (avg velocity, max/min baro_altitude, avg geo_altitude,
number of state vectors), build a training set with a FeatureLookup, train and log the model with
fe.log_model (feature lineage) registering serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs
with a @prod alias, batch-score with fe.score_batch, and publish the feature table to a Lakebase
online store (opensky-online-store) for real-time icao24 lookups. Track everything in MLflow. Keep
it independent from the SDP pipeline.
```

### Variant B — step by step

One prompt per notebook (also embedded in each notebook's `## Prompt` cell).

**Step 1 — data prep & quality (`01_data_prep`)**

```text
Using @state_vectors_raw, filter to the Americas region (longitude between -170 and -30) for
2026-03-01 18:00-18:15 UTC. Run data-quality checks (null counts and out-of-range values for
latitude, longitude, geo_altitude, true_track), then clean using rules equivalent to the SDP silver
expectations: drop rows with null latitude/longitude, latitude outside -90..90, longitude outside
-180..180, geo_altitude outside -500..50000, or true_track outside 0..360; also require
baro_altitude, geo_altitude, velocity, true_track, vertical_rate and on_ground to be non-null. Write
the result to serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors and report rows kept
vs dropped per rule.
```

**Step 2 — ML-focused EDA (`02_eda`)**

```text
On serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors, run an ML-focused EDA: derive
the flight_phase label (Ground/Climb/Descent/Cruise) and show class balance; report missing values;
show distributions and outliers for baro_altitude, geo_altitude, velocity, true_track; summarize
geographic coverage and the per-minute time pattern; and show how each feature relates to
flight_phase. Note that on_ground and vertical_rate are excluded from features to avoid target
leakage.
```

**Step 3 — train, compare & register (`03_train_register`)**

```text
On the curated table, derive the flight_phase label, take a stratified sample (~200k rows) that
preserves the class distribution, and split into train/test. Using features baro_altitude,
geo_altitude, velocity, true_track only, compare Logistic Regression, Random Forest and Histogram
Gradient Boosting with MLflow autologging. Evaluate each with macro F1, register the best model in
Unity Catalog as serverless_stable_bbecx8_catalog.opensky.flight_phase_model, and set its @prod alias.
```

**Step 4 — evaluate, interpret & batch-score (`04_evaluate`)**

```text
Load serverless_stable_bbecx8_catalog.opensky.flight_phase_model@prod, evaluate it on a held-out
sample with a classification report and confusion matrix (per-class and macro F1), interpret the
results and limitations, and batch-score a sample into
serverless_stable_bbecx8_catalog.opensky.gold_flight_phase_predictions with readable actual vs
predicted phase.
```

**Step 5 — Feature Store + Lakebase (`05_feature_store_lakebase`)** — *optional variant (see the
"Optional variant — Feature Store + Lakebase" section below for when to use it).*

```text
On serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors, engineer a per-aircraft
feature table keyed by icao24 (avg velocity, max/min baro_altitude, avg geo_altitude, number of
state vectors). Build a training set with a FeatureLookup that joins those aircraft features onto
each row (features: baro_altitude, geo_altitude, velocity, true_track + the looked-up aircraft
features; label = flight phase; exclude on_ground and vertical_rate). Train a classifier, log it
with fe.log_model so feature lineage is bound, register it in Unity Catalog as
serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs with a @prod alias, batch-score with
fe.score_batch, and publish the aircraft feature table to a Lakebase online store
(opensky-online-store) for real-time lookups by icao24.
```

## How to run

1. Import the notebooks from `code/ml/` into the workspace.
2. Run in order: **`01_data_prep` → `02_eda` → `03_train_register` → `04_evaluate`** (each
   reads/writes Unity Catalog tables, so order matters). On serverless, set the catalog/schema
   widgets to a **writable** catalog if you change the defaults.
3. The registered model lands at `serverless_stable_bbecx8_catalog.opensky.flight_phase_model` with
   the `@prod` alias; predictions land in `gold_flight_phase_predictions`.
4. *(Optional)* run **`05_feature_store_lakebase`** after `01` for the Feature Store + Lakebase
   variant (see below).

## Optional variant — Feature Store + Lakebase (`05`)

The baseline above uses plain Unity Catalog tables — the right default for this batch problem.
Notebook `05` adds a **Feature Store + Lakebase** path when you want feature reuse, model-bound
feature lineage, or **real-time online lookups**.

**Feature Store vs. Feature Views** — two flavors of Databricks Feature Engineering:

| | Feature Store (`FeatureLookup`) | Feature Views |
|---|---|---|
| Status | **GA** | Public Preview |
| Who computes features | **You** (`fe.create_table` / `write_table`) | Databricks, from a declarative spec |
| Materialization | You control | Databricks auto-materializes offline + online |
| Online store | Publish explicitly to Lakebase | Materialized to Lakebase automatically |

`05` uses the **`FeatureLookup` API (GA)**: it builds a per-aircraft `aircraft_features` table
(keyed by `icao24`), joins it onto each row via `FeatureLookup`, binds the lineage to the model
with `fe.log_model`, scores with `fe.score_batch`, registers `flight_phase_model_fs`, and
**publishes `aircraft_features` to a Lakebase online store** (`opensky-online-store`) for
sub-millisecond `icao24` lookups. Requires `databricks-feature-engineering>=0.16.0`.

The Genie Code prompt for this variant is **Step 5** in the step-by-step prompts above.

> Naming pattern: register as `<catalog>.<schema>.flight_phase_model`. Here `<catalog>` is this
> workspace's writable catalog; don't register into a read-only Marketplace catalog.

## Results

_Populated from the end-to-end run on `fevm-serverless-stable-bbecx8`:_

| Metric | Value |
|--------|-------|
| Scope | Americas · 2026-03-01 18:00–18:15 UTC |
| Curated rows | 6,447,418 |
| Class balance | Cruise 62.6% · Descent 21.7% · Climb 15.7% · **Ground 0.007%** (429 rows) |
| Models compared (macro-F1) | logistic_regression 0.349 · **random_forest 0.798** · hist_gradient_boosting 0.748 |
| Best model | `random_forest` |
| Registered model | `serverless_stable_bbecx8_catalog.opensky.flight_phase_model` v1 `@prod` |
| Held-out macro-F1 | 0.651 |
| Batch-scored | 500,300 rows → `gold_flight_phase_predictions` |

**Finding — Ground is nearly absent (429 rows, 0.007%)** in this daytime Americas window, so the
4-class task is effectively Cruise/Descent/Climb. Random Forest clearly beats the linear baseline
(0.798 vs 0.349 test macro-F1); the lower held-out score (0.651) reflects genuine Climb↔Cruise↔Descent
overlap once `vertical_rate` is excluded (no leakage), plus the thin Ground class. To improve:
engineer non-leaking vertical-motion features (short-horizon altitude deltas per `icao24`), pick a
window with more ground traffic, or rebalance the rare class.

**Reading the results:** `Ground` is well separated by altitude/speed; `Climb` / `Cruise` /
`Descent` are hard to distinguish once `vertical_rate` is removed, so most error concentrates among
those three. See `04_evaluate`'s interpretation cell for limitations and next steps.

---

### Tutorial navigation

| ← Previous | Overview | Next → |
|:---|:---:|---:|
| [6. Declarative Automation Bundles (DABs)](60-dabs.md) | [Table of contents](index.md) | [8. AI/BI Dashboards and Genie Agents](80-dashboards.md) |
