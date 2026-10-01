"""
Receive the OpenSky Marketplace data locally with the open Delta Sharing client.

No Spark, no Java — just Python + delta-sharing + pandas. Lists the shared tables,
then pushes a predicate to the sharing server so only matching files cross the
network (baro_altitude < 3000 m), and re-applies the filter in pandas for an exact
result.

Setup (see ./README.md or Step 10):
    uv venv --python 3.12 --seed
    source .venv/bin/activate
    uv pip install delta-sharing pandas

Run:
    python receive_opensky.py

Personalize (optional): edit the constants below, or override without touching
the file via environment variables, e.g.
    SHARE=my_share SCHEMA=my_schema TABLE=my_table python receive_opensky.py
"""

import json
import os

import delta_sharing

# --- Personalize here -------------------------------------------------------
# Point PROFILE at your Delta Sharing profile (.share) file — download it from
# the Databricks Marketplace listing ("Download credential file"). The table
# path is "<profile>#<share>.<schema>.<table>"; run once and list_all_tables()
# below prints the exact share/schema/table names in your credential file.
PROFILE = os.getenv("PROFILE", "opensky.share")
SHARE = os.getenv("SHARE", "opensky_marketplace")
SCHEMA = os.getenv("SCHEMA", "opensky")
TABLE_NAME = os.getenv("TABLE", "state_vectors")
# ----------------------------------------------------------------------------

TABLE = f"{PROFILE}#{SHARE}.{SCHEMA}.{TABLE_NAME}"

client = delta_sharing.SharingClient(PROFILE)
for t in client.list_all_tables():          # what the share exposes
    print(f"{t.share}.{t.schema}.{t.name}")

# Push a predicate down to the server so it skips non-matching files:
# baro_altitude < 3000. It's a file-skipping hint (may return a superset),
# so we re-apply the filter in pandas for an exact result.
low_altitude = {
    "op": "lessThan",
    "children": [
        {"op": "column", "name": "baro_altitude", "valueType": "double"},
        {"op": "literal", "value": "3000", "valueType": "double"},
    ],
}

df = delta_sharing.load_as_pandas(TABLE, jsonPredicateHints=json.dumps(low_altitude), limit=1000)
df = df[df["baro_altitude"] < 3000]
print(df.shape)
print(df[["icao24", "callsign", "time_position", "latitude", "longitude", "baro_altitude"]].head())
