# AI-powered Analytics of 700 Million OpenSky Network Avionics Records 

## [Tutorial: How to get started with Databricks Genie as a Data Scientist or Data Engineer on Databricks Free Edition](https://community.databricks.com/t5/technical-blog/tutorial-databricks-genie-for-data-engineers-and-data-scientists/ba-p/168969)


Welcome to this hands-on tutorial for data scientists and data engineers that runs start to finish on Databricks Free Edition, with real data from real planes instead of an AI generated toy dataset.

You begin with raw flight data from the **[OpenSky Network](https://opensky-network.org/)** on Databricks Marketplace: 696 million records — one full day of telemetry data in 2026, every aircraft that was in the air.

From there you track down the anomalies, explore it with natural language, build a Spark Declarative Pipeline to clean it, and finish with a live app. Genie handles the analysis and writes the SQL, pipeline and web app code as you go.

If you are interested in OSS and data sharing, you can read the same data straight from your own laptop with [open sharing](docs/100-opensharing.md) and take it from there.

<p align="center">
  <img src="docs/assets/00-intro2-anim.gif" alt="Intro animation showing the OpenSky flight-data workshop" width="75%" />
</p>

<p align="center"><em>The animation above is built from the Marketplace dataset: a space-time prism of flights over the US, followed by aircraft trajectories across Australia and holding patterns over Sydney Airport. It runs as a Databricks App</em></p>


## What you'll build

1. **[Databricks Marketplace](docs/10-marketplace.md)** — get the data as a read-only Unity Catalog table.
2. **[Genie Agents - EDA](docs/20-genie-eda.md)** — find data anomalies.
3. **[Genie Agents - explore & visualize](docs/30-genie-explore.md)** — explore and visualize the data.
4. **[Genie Code - Spark Declarative Pipeline](docs/40-pipeline.md)** — ingest and clean the data into per-region gold tables.
5. **[Genie Code - Lakeflow Job](docs/50-job.md)** — schedule and orchestrate the pipeline as a multi-task job.
6. **[Declarative Automation Bundles (DABs)](docs/60-dabs.md)** — package and deploy the project as code.
7. **[ML Models](docs/70-ml-models.md)** — train and register a flight-phase model, and serve features from Lakebase.
8. **[AI/BI Dashboards and Genie Agents](docs/80-dashboards.md)** — build governed dashboards and a curated Genie Agent.
9. **[Lakebase and Databricks Apps](docs/90-lakebase-apps.md)** — build a governed app on a gold table and visualize APAC flight routes on a zoomable map.
10. **[Open Sharing](docs/100-opensharing.md)** — receive the shared data locally with the open-source client and VSCode.
11. **[Wrap-up & next steps](docs/110-wrap-up.md)** — clean up and where to go from here.

```text
TL;DR what this tutorial shows: Marketplace → Genie Agents & Genie Code (EDA) → Genie Agents (explore & visualize) 
→ Genie Code for Declarative Pipeline → Genie Code for a Lakeflow Job → Declarative Automation Bundles 
→ ML Models → AI/BI Dashboards & Genie Agents → Lakebase & Databricks Apps → Open Sharing with OSS
```

## Personalize this workshop

The tutorial defaults to the dataset `marketplace.opensky.state_vectors`. If you named your
catalog, schema, or table differently, set them once in [`config.yml`](config.yml):

```yaml
catalog: marketplace
schema: opensky
table: state_vectors
```

Those values flow into every page, SQL snippet, and Genie prompt via
[mkdocs-macros](https://mkdocs-macros-plugin.readthedocs.io/) (rendered as `{{ catalog }}.{{ schema }}.{{ table }}`),
so `mkdocs serve` / `mkdocs build` regenerates the whole site with your names. The local
[Open Sharing client](code/opensharing/receive_opensky.py) reads the same values from
constants (or `SHARE` / `SCHEMA` / `TABLE` environment variables).

## How to use this tutorial

This is a guided overview, not a click-by-click manual. Each page sketches the path and highlights the prompts that matter, rather than documenting every button and menu. It's suitable for a workshop: an instructor demos each step live while the audience follows along. Working on your own is fine too. Then treat each page as the map, explore, and let Genie do the AI-powered driving.

## Before you begin

- A **Databricks account** — the free [Databricks Free Edition](https://login.databricks.com/signup?provider=DB_FREE_TIER&dbx_source=lf_fm1)
  is enough to follow along. 
- **Unity Catalog** enabled (default on Free Edition).
- **Serverless compute** available (default on Free Edition).
- The **`USE MARKETPLACE ASSETS`** privilege on the metastore (default unless your admin revoked it).
