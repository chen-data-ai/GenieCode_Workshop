# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 04 · Evaluate, interpret & batch-score
# MAGIC
# MAGIC Load the registered `@prod` model, evaluate it on a held-out sample (classification report,
# MAGIC confusion matrix, macro-F1), interpret the results and limitations, and **batch-score** a
# MAGIC sample into a gold predictions table with readable actual-vs-predicted phases.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt
# MAGIC
# MAGIC ```text
# MAGIC Load serverless_stable_bbecx8_catalog.opensky.flight_phase_model@prod, evaluate it on a
# MAGIC held-out sample with a classification report and confusion matrix (per-class and macro F1),
# MAGIC interpret the results and limitations, and batch-score a sample into
# MAGIC serverless_stable_bbecx8_catalog.opensky.gold_flight_phase_predictions with readable actual
# MAGIC vs predicted phase.
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_bbecx8_catalog", "Catalog")
dbutils.widgets.text("schema", "opensky", "Schema")
dbutils.widgets.text("curated_table", "ml_flight_state_vectors", "Curated table")
dbutils.widgets.text("model_name", "flight_phase_model", "Registered model name")
dbutils.widgets.text("predictions_table", "gold_flight_phase_predictions", "Gold predictions table")
dbutils.widgets.text("eval_rows", "50000", "Rows for evaluation sample")
dbutils.widgets.text("score_rows", "500000", "Rows to batch-score")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CURATED = f"{catalog}.{schema}.{dbutils.widgets.get('curated_table')}"
FULL_NAME = f"{catalog}.{schema}.{dbutils.widgets.get('model_name')}"
PREDICTIONS = f"{catalog}.{schema}.{dbutils.widgets.get('predictions_table')}"
eval_rows = int(dbutils.widgets.get("eval_rows"))
score_rows = int(dbutils.widgets.get("score_rows"))
FEATURES = ["baro_altitude", "geo_altitude", "velocity", "true_track"]
MODEL_URI = f"models:/{FULL_NAME}@prod"

# COMMAND ----------

from pyspark.sql import functions as F

phase_col = (
    F.when(F.col("on_ground"), "Ground")
    .when(F.col("vertical_rate") > 1.5, "Climb")
    .when(F.col("vertical_rate") < -1.5, "Descent")
    .otherwise("Cruise")
)
labeled = spark.table(CURATED).withColumn("flight_phase", phase_col)
total = labeled.count()

# COMMAND ----------

# MAGIC %md
# MAGIC ## Evaluate @prod on a held-out sample

# COMMAND ----------

import mlflow
from sklearn.metrics import classification_report, confusion_matrix, f1_score

eval_pdf = (
    labeled.select(*FEATURES, "flight_phase")
    .sample(min(1.0, eval_rows / total), seed=99).toPandas()
)
model = mlflow.sklearn.load_model(MODEL_URI)
y_true = eval_pdf["flight_phase"]
y_pred = model.predict(eval_pdf[FEATURES])
labels_sorted = sorted(y_true.unique())

macro_f1 = f1_score(y_true, y_pred, average="macro")
report_txt = classification_report(y_true, y_pred, labels=labels_sorted)
cm = confusion_matrix(y_true, y_pred, labels=labels_sorted)
print(f"held-out macro_f1 = {macro_f1:.4f}\n\n{report_txt}")
print("confusion matrix (rows=actual, cols=pred):", labels_sorted)
for lab, row in zip(labels_sorted, cm):
    print(f"  {lab:8s} {row}")

with mlflow.start_run(run_name="holdout_evaluation"):
    mlflow.log_metric("holdout_macro_f1", macro_f1)
    mlflow.log_text(report_txt, "holdout_classification_report.txt")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Batch-score → gold predictions table

# COMMAND ----------

predict_udf = mlflow.pyfunc.spark_udf(spark, model_uri=MODEL_URI, result_type="string", env_manager="local")
gold = (
    labeled.sample(min(1.0, score_rows / total), seed=7)
    .withColumn("flight_phase_pred", predict_udf(*[F.col(c) for c in FEATURES]))
    .withColumnRenamed("flight_phase", "flight_phase_actual")
    .withColumn("scored_at", F.current_timestamp())
    .select("icao24", *FEATURES, "flight_phase_actual", "flight_phase_pred", "scored_at")
)
gold.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(PREDICTIONS)
rows_scored = spark.table(PREDICTIONS).count()
print(f"wrote {rows_scored:,} predictions to {PREDICTIONS}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Interpretation, limitations & next steps
# MAGIC
# MAGIC - **What works:** `Ground` is easy to separate (low altitude + low speed), so it scores high.
# MAGIC - **What's hard:** `Climb`, `Cruise`, and `Descent` overlap heavily in `baro_altitude` /
# MAGIC   `geo_altitude` / `velocity` / `true_track`, because the column that truly distinguishes them
# MAGIC   — `vertical_rate` — is deliberately **excluded to avoid target leakage**. Expect most
# MAGIC   confusion among these three classes; macro-F1 is dominated by that difficulty.
# MAGIC - **Interpretation:** the model mostly learns an altitude/speed proxy; it separates on-ground
# MAGIC   from airborne well and is weak at climb-vs-descent.
# MAGIC - **Limitations:** single 15-min Americas window (not the full day/globe); no temporal
# MAGIC   features; class imbalance (Ground is rare) handled via balanced weights only.
# MAGIC - **Next steps:** add engineered features that carry vertical motion *without* leaking the
# MAGIC   label (e.g. short-horizon altitude deltas per `icao24`), widen the time window/regions,
# MAGIC   try gradient boosting with tuning, and calibrate probabilities.

# COMMAND ----------

import json

dbutils.notebook.exit(json.dumps({
    "model": FULL_NAME, "holdout_macro_f1": round(float(macro_f1), 4),
    "predictions_table": PREDICTIONS, "rows_scored": int(rows_scored),
    "labels": labels_sorted,
}))