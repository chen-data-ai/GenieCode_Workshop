# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 05 · Feature Store + Lakebase (variant)
# MAGIC
# MAGIC An **additive** variant on top of the baseline (`01`–`04`). Instead of training on row columns
# MAGIC alone, it enriches each state vector with **per-aircraft features** from a **Unity Catalog
# MAGIC feature table** (`FeatureLookup`), binds that lineage to the model with `fe.log_model`, scores
# MAGIC with `fe.score_batch`, and **publishes the feature table to a Lakebase online store** for
# MAGIC real-time `icao24` lookups.
# MAGIC
# MAGIC Uses the **Feature Store (`FeatureLookup`) API** (GA), not Feature Views. Requires
# MAGIC `databricks-feature-engineering>=0.16.0`. Registers a distinct model `flight_phase_model_fs`
# MAGIC so the plain baseline `flight_phase_model` is untouched.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt
# MAGIC
# MAGIC ```text
# MAGIC On serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors, engineer a per-aircraft
# MAGIC feature table keyed by icao24 (avg velocity, max/min baro_altitude, avg geo_altitude, number
# MAGIC of state vectors) with the Feature Engineering client. Build a training set with a
# MAGIC FeatureLookup that joins those aircraft features onto each row (features: baro_altitude,
# MAGIC geo_altitude, velocity, true_track + the looked-up aircraft features; label = flight phase;
# MAGIC exclude on_ground and vertical_rate). Train a classifier, log it with fe.log_model so feature
# MAGIC lineage is bound, register it in Unity Catalog as
# MAGIC serverless_stable_bbecx8_catalog.opensky.flight_phase_model_fs with a @prod alias, and
# MAGIC batch-score with fe.score_batch. Finally publish the aircraft feature table to a Lakebase
# MAGIC online store (opensky-online-store) for real-time lookups by icao24.
# MAGIC ```

# COMMAND ----------

# MAGIC %md
# MAGIC ## Install the Feature Engineering client
# MAGIC `databricks-feature-engineering` is **not pre-installed** on interactive/serverless notebook
# MAGIC compute, so install it here. (As a serverless *job* the dependency comes from the job
# MAGIC environment; running interactively needs this cell.)

# COMMAND ----------

# MAGIC %pip install -q "databricks-feature-engineering>=0.16.0"

# COMMAND ----------

dbutils.library.restartPython()

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_bbecx8_catalog", "Catalog")
dbutils.widgets.text("schema", "opensky", "Schema")
dbutils.widgets.text("curated_table", "ml_flight_state_vectors", "Curated table")
dbutils.widgets.text("feature_table_name", "aircraft_features", "Feature table")
dbutils.widgets.text("model_name", "flight_phase_model_fs", "Registered model name")
dbutils.widgets.text("online_store_name", "opensky-online-store", "Lakebase online store (DNS name)")
dbutils.widgets.text("sample_rows", "200000", "Sample rows for training")
dbutils.widgets.text("score_rows", "500000", "Rows to batch-score")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CURATED = f"{catalog}.{schema}.{dbutils.widgets.get('curated_table')}"
FEATURE_TABLE = f"{catalog}.{schema}.{dbutils.widgets.get('feature_table_name')}"
FULL_NAME = f"{catalog}.{schema}.{dbutils.widgets.get('model_name')}"
ONLINE_TABLE = f"{catalog}.{schema}.{dbutils.widgets.get('feature_table_name')}_online"
PREDICTIONS = f"{catalog}.{schema}.gold_flight_phase_predictions_fs"
online_store_name = dbutils.widgets.get("online_store_name")
sample_rows = int(dbutils.widgets.get("sample_rows"))
score_rows = int(dbutils.widgets.get("score_rows"))

ROW_FEATURES = ["baro_altitude", "geo_altitude", "velocity", "true_track"]
AIRCRAFT_FEATURES = ["avg_velocity", "max_baro_altitude", "min_baro_altitude", "avg_geo_altitude", "num_state_vectors"]
PHASES = ["Ground", "Climb", "Descent", "Cruise"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Per-aircraft feature table (Unity Catalog)

# COMMAND ----------

from pyspark.sql import functions as F
from databricks.feature_engineering import FeatureEngineeringClient, FeatureLookup

fe = FeatureEngineeringClient(model_registry_uri="databricks-uc")

phase_col = (
    F.when(F.col("on_ground"), "Ground")
    .when(F.col("vertical_rate") > 1.5, "Climb")
    .when(F.col("vertical_rate") < -1.5, "Descent")
    .otherwise("Cruise")
)
curated = spark.table(CURATED).withColumn("flight_phase", phase_col)

aircraft_df = curated.groupBy("icao24").agg(
    F.avg("velocity").alias("avg_velocity"),
    F.max("baro_altitude").alias("max_baro_altitude"),
    F.min("baro_altitude").alias("min_baro_altitude"),
    F.avg("geo_altitude").alias("avg_geo_altitude"),
    F.count("*").cast("double").alias("num_state_vectors"),
)
try:
    fe.create_table(name=FEATURE_TABLE, primary_keys=["icao24"], df=aircraft_df,
                    description="Per-aircraft OpenSky features keyed by icao24.")
except Exception as e:
    if "already exists" in str(e).lower():
        fe.write_table(name=FEATURE_TABLE, df=aircraft_df, mode="overwrite")
    else:
        raise
print(f"feature table ready: {FEATURE_TABLE}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Training set via FeatureLookup (row features + looked-up aircraft features)

# COMMAND ----------

total = curated.count()
fraction = min(1.0, sample_rows / total) if total else 1.0
labels_df = curated.sampleBy("flight_phase", {c: fraction for c in PHASES}, seed=42).select(
    "icao24", *ROW_FEATURES, "flight_phase"
)

training_set = fe.create_training_set(
    df=labels_df,
    feature_lookups=[FeatureLookup(table_name=FEATURE_TABLE, lookup_key="icao24", feature_names=AIRCRAFT_FEATURES)],
    label="flight_phase",
    exclude_columns=["icao24"],
)
training_pd = training_set.load_df().toPandas().dropna()
print(f"training rows={len(training_pd):,}  columns={list(training_pd.columns)}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train + register with feature lineage (`fe.log_model`)

# COMMAND ----------

import mlflow
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import train_test_split

mlflow.set_registry_uri("databricks-uc")
username = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{username}/opensky_flight_phase")
mlflow.sklearn.autolog(log_models=False, silent=True)

FEATURE_COLS = ROW_FEATURES + AIRCRAFT_FEATURES
X = training_pd[FEATURE_COLS]
y = training_pd["flight_phase"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

with mlflow.start_run(run_name="feature_store_rf") as run:
    model = RandomForestClassifier(n_estimators=200, max_depth=16, class_weight="balanced", random_state=42, n_jobs=-1)
    model.fit(X_train, y_train)
    macro_f1 = f1_score(y_test, model.predict(X_test), average="macro")
    mlflow.log_metric("macro_f1", macro_f1)
    print(classification_report(y_test, model.predict(X_test), labels=sorted(y.unique())))
    fe.log_model(
        model=model, artifact_path="model", flavor=mlflow.sklearn,
        training_set=training_set, registered_model_name=FULL_NAME,
    )

client = MlflowClient(registry_uri="databricks-uc")
latest = max(client.search_model_versions(f"name='{FULL_NAME}'"), key=lambda v: int(v.version))
client.set_registered_model_alias(FULL_NAME, "prod", version=latest.version)
print(f"registered {FULL_NAME} v{latest.version} -> @prod  (macro_f1={macro_f1:.4f})")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Batch score with `fe.score_batch` (features auto-joined by lineage)

# COMMAND ----------

to_score = curated.sample(min(1.0, score_rows / total), seed=7).select("icao24", *ROW_FEATURES, "flight_phase")
scored = fe.score_batch(model_uri=f"models:/{FULL_NAME}@prod", df=to_score, result_type="string")

gold = (
    scored
    .withColumnRenamed("flight_phase", "flight_phase_actual")
    .withColumnRenamed("prediction", "flight_phase_pred")
    .withColumn("scored_at", F.current_timestamp())
    .select("icao24", *ROW_FEATURES, "flight_phase_actual", "flight_phase_pred", "scored_at")
)
gold.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(PREDICTIONS)
rows_scored = spark.table(PREDICTIONS).count()
print(f"wrote {rows_scored:,} predictions to {PREDICTIONS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Publish the feature table to a Lakebase online store
# MAGIC
# MAGIC Syncs `aircraft_features` into a Lakebase-backed online store so a serving endpoint can look
# MAGIC features up by `icao24` in real time. First creation provisions Lakebase (~5 min). Guarded so
# MAGIC a provisioning issue doesn't fail the run — status is reported.

# COMMAND ----------

import time

online_status = {"store": online_store_name, "online_table": ONLINE_TABLE}
try:
    store = fe.get_online_store(name=online_store_name)   # returns None (not raise) if absent
    if store is None:
        print(f"creating Lakebase online store {online_store_name} (~5 min)...")
        fe.create_online_store(name=online_store_name, capacity="CU_1")
        time.sleep(300)
        store = fe.get_online_store(name=online_store_name)
    try:
        fe.publish_table(
            online_store=store, source_table_name=FEATURE_TABLE,
            online_table_name=ONLINE_TABLE, publish_mode="SNAPSHOT",
        )
        online_status["state"] = "PUBLISHED"
        print(f"published {FEATURE_TABLE} -> {ONLINE_TABLE}")
    except Exception as pe:
        # Idempotent re-run: an existing online table / store is fine.
        if "exist" in str(pe).lower() or "already" in str(pe).lower():
            online_status["state"] = "ALREADY_PUBLISHED"
            print(f"online table already published: {ONLINE_TABLE}")
        else:
            raise
except Exception as e:
    online_status["state"] = "FAILED"
    online_status["error"] = str(e)[:500]
    print(f"online publish skipped/failed: {e}")

# COMMAND ----------

import json

dbutils.notebook.exit(json.dumps({
    "model": FULL_NAME, "model_version": latest.version, "macro_f1": round(float(macro_f1), 4),
    "feature_table": FEATURE_TABLE, "rows_scored": int(rows_scored),
    "predictions_table": PREDICTIONS, "online_store": online_status,
}))