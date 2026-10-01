# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 03 · Train, compare & register
# MAGIC
# MAGIC Derive the flight-phase label, take a **stratified sample that preserves the class
# MAGIC distribution**, and compare three classifiers with **MLflow autologging**. Evaluate by
# MAGIC **macro-F1**, then register the best model to **Unity Catalog** as `flight_phase_model` and
# MAGIC point the `@prod` alias at it.
# MAGIC
# MAGIC Features: `baro_altitude, geo_altitude, velocity, true_track` only — `on_ground` and
# MAGIC `vertical_rate` are **excluded** (they derive the label → target leakage).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt
# MAGIC
# MAGIC ```text
# MAGIC On the curated table, derive the flight_phase label, take a stratified sample (~200k rows)
# MAGIC that preserves the class distribution, and split into train/test. Using features
# MAGIC baro_altitude, geo_altitude, velocity, true_track only, compare Logistic Regression, Random
# MAGIC Forest and Histogram Gradient Boosting with MLflow autologging. Evaluate each with macro F1,
# MAGIC register the best model in Unity Catalog as
# MAGIC serverless_stable_bbecx8_catalog.opensky.flight_phase_model, and set its @prod alias.
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_bbecx8_catalog", "Catalog")
dbutils.widgets.text("schema", "opensky", "Schema")
dbutils.widgets.text("curated_table", "ml_flight_state_vectors", "Curated table")
dbutils.widgets.text("model_name", "flight_phase_model", "Registered model name")
dbutils.widgets.text("sample_rows", "200000", "Sample rows for training")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CURATED = f"{catalog}.{schema}.{dbutils.widgets.get('curated_table')}"
FULL_NAME = f"{catalog}.{schema}.{dbutils.widgets.get('model_name')}"
sample_rows = int(dbutils.widgets.get("sample_rows"))
FEATURES = ["baro_altitude", "geo_altitude", "velocity", "true_track"]

# COMMAND ----------

# MAGIC %md
# MAGIC ## Label + stratified sample (preserves class proportions)

# COMMAND ----------

from pyspark.sql import functions as F

phase_col = (
    F.when(F.col("on_ground"), "Ground")
    .when(F.col("vertical_rate") > 1.5, "Climb")
    .when(F.col("vertical_rate") < -1.5, "Descent")
    .otherwise("Cruise")
)
labeled = spark.table(CURATED).withColumn("flight_phase", phase_col).select(*FEATURES, "flight_phase")
total = labeled.count()

# Same fraction per class = proportional sample → preserves the class distribution.
fraction = min(1.0, sample_rows / total) if total else 1.0
classes = [r["flight_phase"] for r in labeled.select("flight_phase").distinct().collect()]
pdf = labeled.sampleBy("flight_phase", {c: fraction for c in classes}, seed=42).toPandas()
print(f"{total:,} labeled rows -> sampled {len(pdf):,}")
print(pdf["flight_phase"].value_counts(normalize=True).round(4).to_dict())

# COMMAND ----------

# MAGIC %md
# MAGIC ## Train/test split + model comparison (MLflow autolog)

# COMMAND ----------

import mlflow
from mlflow.tracking import MlflowClient
from sklearn.ensemble import RandomForestClassifier, HistGradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

mlflow.set_registry_uri("databricks-uc")
username = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{username}/opensky_flight_phase")
mlflow.sklearn.autolog(log_models=False, silent=True)

X = pdf[FEATURES]
y = pdf["flight_phase"]
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42, stratify=y)

candidates = {
    "logistic_regression": make_pipeline(
        StandardScaler(), LogisticRegression(max_iter=1000, class_weight="balanced")
    ),
    "random_forest": RandomForestClassifier(
        n_estimators=200, max_depth=16, class_weight="balanced", random_state=42, n_jobs=-1
    ),
    "hist_gradient_boosting": HistGradientBoostingClassifier(max_iter=200, random_state=42),
}

results = {}
for name, est in candidates.items():
    with mlflow.start_run(run_name=name):
        if name == "hist_gradient_boosting":
            est.fit(X_train, y_train, sample_weight=compute_sample_weight("balanced", y_train))
        else:
            est.fit(X_train, y_train)
        macro_f1 = f1_score(y_test, est.predict(X_test), average="macro")
        mlflow.log_metric("macro_f1", macro_f1)
        results[name] = {"model": est, "macro_f1": macro_f1}
        print(f"{name}: macro_f1={macro_f1:.4f}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Register the best model to Unity Catalog

# COMMAND ----------

best_name = max(results, key=lambda k: results[k]["macro_f1"])
best_model = results[best_name]["model"]
best_f1 = results[best_name]["macro_f1"]
labels_sorted = sorted(y.unique())
report_txt = classification_report(y_test, best_model.predict(X_test), labels=labels_sorted)
print(f"BEST = {best_name} (macro_f1={best_f1:.4f})\n\n{report_txt}")

with mlflow.start_run(run_name=f"best__{best_name}"):
    mlflow.log_metric("macro_f1", best_f1)
    mlflow.log_param("best_model", best_name)
    mlflow.log_text(report_txt, "classification_report.txt")
    cm = confusion_matrix(y_test, best_model.predict(X_test), labels=labels_sorted)
    mlflow.log_text(
        "labels: " + ",".join(labels_sorted) + "\n" + "\n".join(",".join(map(str, row)) for row in cm),
        "confusion_matrix.csv",
    )
    info = mlflow.sklearn.log_model(
        best_model, artifact_path="model", input_example=X_train.head(5), registered_model_name=FULL_NAME
    )

client = MlflowClient(registry_uri="databricks-uc")
client.set_registered_model_alias(FULL_NAME, "prod", info.registered_model_version)
print(f"registered {FULL_NAME} v{info.registered_model_version} -> @prod")

# COMMAND ----------

import json

dbutils.notebook.exit(json.dumps({
    "model": FULL_NAME, "model_version": info.registered_model_version,
    "best_model": best_name, "best_macro_f1": round(float(best_f1), 4),
    "all_macro_f1": {k: round(float(v["macro_f1"]), 4) for k, v in results.items()},
}))