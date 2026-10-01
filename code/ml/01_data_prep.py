# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "6"
# ///
# MAGIC %md
# MAGIC # 01 · Data prep & quality
# MAGIC
# MAGIC First step of the flight-phase ML workflow. Filters the raw OpenSky state vectors to **one
# MAGIC region and a short time window**, runs **data-quality checks**, applies **cleaning rules
# MAGIC equivalent to the SDP silver expectations** (independently — no dependency on the pipeline),
# MAGIC and writes a small **curated Delta table** the rest of the workflow reads.
# MAGIC
# MAGIC See [`docs/70-ml-models.md`](../../docs/70-ml-models.md) for the full write-up.

# COMMAND ----------

# MAGIC %md
# MAGIC ## Prompt
# MAGIC
# MAGIC ```text
# MAGIC Using @state_vectors_raw, filter to the Americas region (longitude between -170 and -30)
# MAGIC for 2026-03-01 18:00-18:15 UTC. Run data-quality checks (null counts and out-of-range
# MAGIC values for latitude, longitude, geo_altitude, true_track), then clean using rules
# MAGIC equivalent to the SDP silver expectations: drop rows with null latitude/longitude,
# MAGIC latitude outside -90..90, longitude outside -180..180, geo_altitude outside -500..50000,
# MAGIC or true_track outside 0..360; also require baro_altitude, geo_altitude, velocity,
# MAGIC true_track, vertical_rate and on_ground to be non-null. Write the result to
# MAGIC serverless_stable_bbecx8_catalog.opensky.ml_flight_state_vectors and report rows kept vs
# MAGIC dropped per rule.
# MAGIC ```

# COMMAND ----------

dbutils.widgets.text("catalog", "serverless_stable_bbecx8_catalog", "Catalog")
dbutils.widgets.text("schema", "opensky", "Schema")
dbutils.widgets.text("source_table", "state_vectors_raw", "Source table")
dbutils.widgets.text("curated_table", "ml_flight_state_vectors", "Curated output table")
dbutils.widgets.dropdown("region", "Americas", ["Americas", "EMEA", "APAC"], "Region")
dbutils.widgets.text("window_start", "2026-03-01T18:00:00", "Window start (UTC)")
dbutils.widgets.text("window_end", "2026-03-01T18:15:00", "Window end (UTC)")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
SOURCE = f"{catalog}.{schema}.{dbutils.widgets.get('source_table')}"
CURATED = f"{catalog}.{schema}.{dbutils.widgets.get('curated_table')}"
region = dbutils.widgets.get("region")
window_start = dbutils.widgets.get("window_start")
window_end = dbutils.widgets.get("window_end")

REGION_BANDS = {
    "Americas": "longitude BETWEEN -170 AND -30",
    "EMEA": "longitude BETWEEN -30 AND 75",
    "APAC": "(longitude >= 60 OR longitude <= -120)",
}
region_filter = REGION_BANDS[region]
print(f"source={SOURCE}\ncurated={CURATED}\nregion={region} ({region_filter})\nwindow={window_start}..{window_end} UTC")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Scope filter (region + time) — applied first

# COMMAND ----------

from pyspark.sql import functions as F

scoped = spark.table(SOURCE).where(
    F.expr(region_filter)
    & (F.col("time_position") >= F.to_timestamp(F.lit(window_start)))
    & (F.col("time_position") < F.to_timestamp(F.lit(window_end)))
)
scoped_rows = scoped.count()
print(f"rows in scope: {scoped_rows:,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ## Data-quality checks (before cleaning)
# MAGIC
# MAGIC Null counts and out-of-range counts for the columns the model and label depend on.

# COMMAND ----------

check_cols = ["latitude", "longitude", "baro_altitude", "geo_altitude", "velocity", "true_track", "vertical_rate", "on_ground"]
null_counts = scoped.select([F.sum(F.col(c).isNull().cast("int")).alias(c) for c in check_cols]).collect()[0].asDict()
range_issues = scoped.select(
    F.sum((~F.col("latitude").between(-90, 90)).cast("int")).alias("latitude_out_of_range"),
    F.sum((~F.col("longitude").between(-180, 180)).cast("int")).alias("longitude_out_of_range"),
    F.sum((~F.col("geo_altitude").between(-500, 50000) & F.col("geo_altitude").isNotNull()).cast("int")).alias("geo_altitude_out_of_range"),
    F.sum(((F.col("true_track") < 0) | (F.col("true_track") >= 360)).cast("int")).alias("true_track_out_of_range"),
).collect()[0].asDict()
print("null counts:", null_counts)
print("range issues:", range_issues)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Cleaning — SDP silver expectations (reimplemented independently)
# MAGIC
# MAGIC Same intent as the pipeline's silver layer, applied here as hard drops so the ML step gets
# MAGIC complete, in-range rows. Each rule's drop count is reported.

# COMMAND ----------

rules = {
    "null_position": "latitude IS NOT NULL AND longitude IS NOT NULL",
    "latitude_range": "latitude BETWEEN -90 AND 90",
    "longitude_range": "longitude BETWEEN -180 AND 180",
    "geo_altitude_range": "geo_altitude BETWEEN -500 AND 50000",
    "true_track_range": "true_track >= 0 AND true_track < 360",
    "features_not_null": "baro_altitude IS NOT NULL AND geo_altitude IS NOT NULL AND velocity IS NOT NULL AND true_track IS NOT NULL",
    "label_cols_not_null": "vertical_rate IS NOT NULL AND on_ground IS NOT NULL",
}
keep_expr = " AND ".join(f"({r})" for r in rules.values())

clean = scoped.where(keep_expr)
clean_rows = clean.count()

# Per-rule drop attribution (how many scoped rows each rule alone would remove).
report = {"scoped_rows": scoped_rows, "clean_rows": clean_rows, "dropped_total": scoped_rows - clean_rows}
for name, expr in rules.items():
    report[f"fail_{name}"] = scoped.where(f"NOT ({expr})").count()
print(report)

# COMMAND ----------

# MAGIC %md
# MAGIC ## Write curated table

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
(
    clean.select(
        "icao24", "callsign", "time_position", "latitude", "longitude",
        "baro_altitude", "geo_altitude", "velocity", "true_track",
        "vertical_rate", "on_ground",
    )
    .write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(CURATED)
)
print(f"wrote {clean_rows:,} curated rows to {CURATED}")

# COMMAND ----------

import json

dbutils.notebook.exit(json.dumps({
    "region": region, "window": f"{window_start}..{window_end}",
    "curated_table": CURATED, "scoped_rows": scoped_rows, "clean_rows": clean_rows,
    "dropped_total": scoped_rows - clean_rows,
}))