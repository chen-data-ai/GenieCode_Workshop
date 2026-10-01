# ML — flight-phase classification

End-to-end ML workflow built with **Genie Code** on the OpenSky state vectors. Full write-up,
business/ML problem, scope, and both reproducible prompt variants are in the principal doc:
**[`docs/70-ml-models.md`](../../docs/70-ml-models.md)**.

Run the notebooks in order (each carries its own `## Prompt` cell):

| # | Notebook | Lifecycle phase |
|---|----------|-----------------|
| 01 | `01_data_prep.py` | Scope filter (region + time) → data-quality checks → cleaning → curated table |
| 02 | `02_eda.py` | ML-focused EDA (class balance, distributions, coverage, feature↔label) |
| 03 | `03_train_register.py` | Label → stratified sample → compare models (MLflow autolog) → register `@prod` |
| 04 | `04_evaluate.py` | Evaluate `@prod`, interpret, batch-score → gold predictions table |
| 05 | `05_feature_store_lakebase.py` *(optional)* | Feature Store (`FeatureLookup`) + Lakebase online store; registers `flight_phase_model_fs` |

Defaults target `serverless_stable_bbecx8_catalog.opensky` (source table `state_vectors_raw`);
all catalog/schema/table names are notebook widgets. Register target:
`serverless_stable_bbecx8_catalog.opensky.flight_phase_model` (swap the catalog/schema widgets to
reuse elsewhere — pick a **writable** catalog, not a read-only Marketplace share).
