# 8. Build AI/BI Dashboards and Genie Agents

## What you'll do

The [explore step](30-genie-explore.md) answered one-off questions with Genie Agents. Now you make
that self-service and persistent: a shareable **AI/BI Dashboard** on the same OpenSky **state
vectors** table (`serverless_stable_bbecx8_catalog.opensky.state_vectors_raw`), plus a curated **Genie Agent** wired into it so anyone can keep
asking questions in plain English.

As before, you don't hand-build charts or write SQL. You describe the dashboard you want and Genie
does the work — proposing datasets, picking chart types, and laying out the page.

## How do AI/BI Dashboards and Genie Agents fit together?

- **[AI/BI Dashboards](https://docs.databricks.com/aws/en/dashboards/)** are governed dashboards
  that read live from Unity Catalog through a SQL warehouse. You author them from plain-English
  prompts, and every viewer sees data filtered by their own permissions.
- **[Genie Agents](https://docs.databricks.com/aws/en/genie-agents/)** turn a set of tables into a
  conversational agent: ask a question, get the SQL, the result, and a chart. You can **embed a
  Genie Agent in a dashboard** as an "Ask Genie" surface, so the dashboard answers the questions
  you didn't think to chart.

Together: the dashboard shows the metrics you know matter; the Genie Agent handles everything else.

## Step-by-step guide

> **Step 1: Build the dashboard from a prompt**
>
> Open a new **AI/BI Dashboard** and describe the overview you want on the state vectors table.
> Genie proposes the datasets and widgets:
>
> ```text
> Build a dashboard named "OpenSky Flights" on serverless_stable_bbecx8_catalog.opensky.state_vectors_raw. Put three KPI tiles across the top — total
> state vectors, distinct aircraft (distinct icao24), and average velocity — then
> a histogram of baro_altitude and a bar chart of record count by hour of
> time_position. Add a filter on on_ground.
> ```
>
> **Step 2: Add a map and refine**
>
> Follow up in plain English to add or change widgets. Genie edits the dashboard in place:
>
> ```text
> Add a point map of the most recent position per aircraft, colored by velocity.
> Format the KPI tiles with compact numbers, and order the hourly bar chart by hour.
> ```
>
> **Step 3: Create a Genie Agent on the same data**
>
> Create a **Genie Agent** over the state vectors table so users can ask free-form questions:
>
> ```text
> Create a Genie Agent named "OpenSky Genie" on serverless_stable_bbecx8_catalog.opensky.state_vectors_raw. Add instructions that "flight phase" is
> Ground when on_ground, Climb when vertical_rate > 1.5, Descent when
> vertical_rate < -1.5, otherwise Cruise, and add example questions about the
> busiest hours and the altitude distribution.
> ```
>
> **Step 4: Link the Genie Agent into the dashboard**
>
> In the dashboard settings, enable **Ask Genie** and point it at the Genie Agent you just built.
> Now the dashboard carries both the curated views and a conversational way to go beyond them.

## What you'll see

- A published dashboard with **KPI tiles, an altitude histogram, an hourly-volume bar chart, and a
  map**, all filterable and refreshing live from `serverless_stable_bbecx8_catalog.opensky.state_vectors_raw`.
- A **Genie Agent** that answers plain-English questions with SQL, results, and charts — reachable
  from the dashboard's **Ask Genie** button.

## AI/BI Dashboards and Genie Agents — Beyond the Basics

A few things worth knowing once the basics work:

- **[Choose the right visualization](https://docs.databricks.com/aws/en/dashboards/manage/visualizations/types)** —
  AI/BI offers ~20 chart types (point and choropleth maps, heatmaps, histograms, combo charts,
  funnels, Sankey). Use it when a default chart doesn't tell the story; just ask Genie to switch it.
- **Cross-filtering** — clicking a bar or map point filters every other widget backed by the same
  dataset. Use it to drill from an overview into a slice without building extra filters.
- **[Curate the Genie Agent](https://docs.databricks.com/aws/en/genie-agents/best-practices)** —
  add instructions, metric definitions, and verified example SQL so the agent answers domain
  questions your way every time. Use it when you keep re-explaining the same joins or filters.
- **Scheduled refresh and alerts** — publish the dashboard on a refresh schedule and set alerts on
  a metric threshold. Use it when stakeholders should see fresh numbers without opening the tool.

## Recap

You built a governed **AI/BI Dashboard** on `serverless_stable_bbecx8_catalog.opensky.state_vectors_raw` and a curated **Genie Agent**, then linked
them so the dashboard both shows the key metrics and answers open-ended questions — all from
plain-English prompts. Next you serve this same governed data through a Databricks App.

---

### Tutorial navigation

| ← Previous | Overview | Next → |
|:---|:---:|---:|
| [7. ML Models](70-ml-models.md) | [Table of contents](index.md) | [Initialize the Databricks App (warm-up)](00-initialize-databricks-app.md) |
