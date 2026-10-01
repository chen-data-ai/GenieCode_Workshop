# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 02 · ML-focused EDA
# MAGIC
# MAGIC Understand the curated dataset before modeling: class balance of the derived label, missing
# MAGIC values, feature distributions and outliers, geographic coverage, time pattern, and how each
# MAGIC candidate feature relates to the flight phase. Explicitly excludes `on_ground` / `vertical_rate`
# MAGIC from features (they define the label → target leakage).

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt
# MAGIC
# MAGIC ```text
# MAGIC On serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors, run an ML-focused EDA:
# MAGIC derive the flight_phase label (Ground/Climb/Descent/Cruise) and show class balance; report
# MAGIC missing values; show distributions and outliers for baro_altitude, geo_altitude, velocity,
# MAGIC true_track; summarize geographic coverage and the per-minute time pattern; and show how each
# MAGIC feature relates to flight_phase. Note that on_ground and vertical_rate are excluded from the
# MAGIC features to avoid target leakage.
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_bbecx8_catalog", "Catalog")
dbutils.widgets.text("schema", "opensky", "Schema")
dbutils.widgets.text("curated_table", "ml_flight_state_vectors", "Curated table")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
CURATED = f"{catalog}.{schema}.{dbutils.widgets.get('curated_table')}"
FEATURES = ["baro_altitude", "geo_altitude", "velocity", "true_track"]

# COMMAND ----------

from pyspark.sql import functions as F

phase_col = (
    F.when(F.col("on_ground"), "Ground")
    .when(F.col("vertical_rate") > 1.5, "Climb")
    .when(F.col("vertical_rate") < -1.5, "Descent")
    .otherwise("Cruise")
)
df = spark.table(CURATED).withColumn("flight_phase", phase_col)
n = df.count()
print(f"{n:,} curated rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Class balance (the target)

# COMMAND ----------

class_balance = (
    df.groupBy("flight_phase").count()
    .withColumn("pct", F.round(100 * F.col("count") / F.lit(n), 3))
    .orderBy(F.desc("count"))
)
display(class_balance)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Missing values (post-cleaning sanity check)

# COMMAND ----------

display(df.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in FEATURES]))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Feature distributions & outliers
# MAGIC
# MAGIC Summary stats plus 1st/50th/99th percentiles to spot outliers.

# COMMAND ----------

display(df.select(*FEATURES).summary("count", "mean", "stddev", "min", "1%", "50%", "99%", "max"))

# COMMAND ----------

# MAGIC %md
# MAGIC ## Geographic coverage & time pattern

# COMMAND ----------

display(df.select(
    F.min("latitude").alias("lat_min"), F.max("latitude").alias("lat_max"),
    F.min("longitude").alias("lon_min"), F.max("longitude").alias("lon_max"),
    F.min("time_position").alias("ts_min"), F.max("time_position").alias("ts_max"),
))
display(
    df.groupBy(F.date_format(F.date_trunc("MINUTE", "time_position"), "HH:mm").alias("minute"))
    .count().orderBy("minute")
)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Feature vs. flight phase
# MAGIC
# MAGIC Mean feature values per phase — shows the signal the model has to work with (altitude
# MAGIC separates Ground well; Climb vs Cruise vs Descent overlap since `vertical_rate` is excluded).

# COMMAND ----------

display(
    df.groupBy("flight_phase").agg(
        F.round(F.avg("baro_altitude"), 1).alias("avg_baro_altitude"),
        F.round(F.avg("geo_altitude"), 1).alias("avg_geo_altitude"),
        F.round(F.avg("velocity"), 1).alias("avg_velocity"),
        F.round(F.avg("true_track"), 1).alias("avg_true_track"),
    ).orderBy("flight_phase")
)

# COMMAND ----------

import json

cb = {r["flight_phase"]: {"count": r["count"], "pct": r["pct"]} for r in class_balance.collect()}
dbutils.notebook.exit(json.dumps({"curated_table": CURATED, "rows": n, "class_balance": cb}))