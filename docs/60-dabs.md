# 6. Package the Project as a Declarative Automation Bundle with Genie Code

So far you built the [pipeline](40-pipeline.md) and wrapped it in a [job](50-job.md) by clicking
through the workspace. That works for one person in one workspace, but it isn't repeatable: there's
no version-controlled source of truth, and no clean way to promote the same pipeline from dev to
prod. **Declarative Automation Bundles (DABs)** fix that — they describe your resources as code in YAML,
so the whole project deploys the same way every time, to any workspace. And Genie Code generates the
bundle for you from the pipeline you already have.

## What is a Declarative Automation Bundle?

A **[Declarative Automation Bundle](https://docs.databricks.com/aws/en/dev-tools/bundles/)** packages your
resources — pipelines, jobs, notebooks, dashboards — as declarative YAML next to the source code they
run. One `databricks.yml` defines the bundle and its **targets** (for example `dev` and `prod`), each
resource gets a file under `resources/`, and `databricks bundle deploy` provisions everything. The
payoff: your pipeline lives in Git, deploys identically to every workspace, and promotes from dev to
prod by switching one flag.

Here you don't write that YAML by hand. You point **Genie Code** at the `opensky_pipeline` from
[Step 4](40-pipeline.md) and ask it to convert the pipeline into a bundle.

## Step-by-step guide: generate a bundle with Genie Code { #step-by-step-guide }

1. **Open the Genie Code interface.** Use the same Genie Code panel you used to build the
   [pipeline](40-pipeline.md) and [job](50-job.md).

2. **Prompt Genie Code to build the bundle.** Reference your `opensky_pipeline` and spell out the
   DAB-specific field names up front — these are the parts Genie most often gets wrong:

   ```text
   Convert my opensky_pipeline into a Declarative Automation Bundle. Follow the SDP
   pipeline resource pattern from the DABs docs: use glob: include: for libraries
   (not file:), target: for the schema field, and set root_path. Create
   databricks.yml, resources/opensky_pipeline.pipeline.yml, and src/, with dev and
   prod targets and variables for catalog, schema, and workspace host. Show me the
   planned YAML before writing any files. Do not deploy.
   ```

   > [!TIP]
   > Being explicit about the field names saves a round-trip. Two common Genie slip-ups: using
   > `file:` instead of `glob: include:` for the pipeline libraries, and `schema:` instead of
   > `target:` for the pipeline's schema field. Naming them in the prompt heads both off, and
   > *"show me the planned YAML before writing any files"* gives you a checkpoint to catch anything
   > else before it lands on disk.

3. **Review the proposed YAML.** Genie Code shows the planned `databricks.yml` and resource files
   before writing them. Confirm the structure matches the layout below, and that the pipeline keeps
   its original configuration (the libraries glob, catalog, and target).

4. **Write the files, then validate in the workspace.** Approve the plan so Genie creates the bundle
   files. Then open the **Bundles** section in your workspace, select the generated bundle, and
   validate it there — fix anything it flags before moving on. The project is now described as
   code, and nothing is deployed yet.

## Results

Genie Code generates a bundle with this layout:

```text
opensky_bundle/
├── databricks.yml                      # bundle name, variables, dev/prod targets
├── resources/
│   └── opensky_pipeline.pipeline.yml   # the SDP pipeline as a resource
└── src/
    └── ...                             # pipeline transformation code
```

**`databricks.yml`** — the bundle definition, with variables for catalog and schema and two targets.
`mode: development` isolates your dev deploy (it prefixes resource names and pauses schedules);
`mode: production` deploys the shared, production copy:

```yaml
bundle:
  name: opensky_bundle

include:
  - resources/*.yml

variables:
  catalog:
    default: {{ catalog }}
  schema:
    default: {{ schema }}

targets:
  dev:
    default: true
    mode: development
    variables:
      catalog: dev_catalog
      schema: opensky_dev
  prod:
    mode: production
    variables:
      catalog: prod_catalog
      schema: opensky
```

**`resources/opensky_pipeline.pipeline.yml`** — the pipeline from Step 4 as a resource. Note the two
fields called out in the prompt: `target:` (not `schema:`) for the schema, and `glob: include:` (not
`file:`) for the libraries:

```yaml
resources:
  pipelines:
    opensky_pipeline:
      name: opensky_pipeline
      catalog: ${var.catalog}
      target: ${var.schema}
      libraries:
        - glob:
            include: ../src/transformations/**
      root_path: ../src
      serverless: true
```

_(Names shown are illustrative — confirm the exact values in the YAML Genie generates.)_ With the
bundle validated, deploy it whenever you're ready:

```bash
databricks bundle deploy --target dev
```

Switch `--target prod` to deploy the production copy from the same code.

## Declarative Automation Bundles — Beyond the Basics

A few things worth knowing once the basics work:

- **[Deployment modes: dev vs prod](https://docs.databricks.com/aws/en/dev-tools/bundles/deployment-modes)** — `mode: development` prefixes resource names with your username and pauses schedules so your deploy never collides with a teammate's or with production; `mode: production` deploys the real, shared copy. Use it when the same bundle has to serve both a personal sandbox and the production workspace.
- **[Variables and target overrides](https://docs.databricks.com/aws/en/dev-tools/bundles/variables)** — declare `catalog`, `schema`, or a warehouse once and override them per target, so one bundle points at dev data in dev and prod data in prod with no code changes. Use it when the only difference between environments is names and IDs.
- **[Generate a bundle from existing resources](https://docs.databricks.com/aws/en/dev-tools/bundles/resources)** — `databricks bundle generate pipeline <pipeline-id>` (or `job`, `dashboard`, `app`) reverse-engineers YAML from a resource you already built in the UI. Use it when you want to bring a hand-built pipeline or job under source control without rewriting it.
- **[Bundles in CI/CD](https://docs.databricks.com/aws/en/dev-tools/bundles/ci-cd/)** — run `bundle validate` and `bundle deploy` from GitHub Actions or Azure DevOps so every merge promotes the project automatically. Use it when more than one person works on the project and deploys need to be repeatable and reviewed.

## Recap

You turned the clicked-together pipeline into a **Declarative Automation Bundle**: a `databricks.yml`,
a pipeline resource file, and `src/`, all under version control, validated with
`databricks bundle validate`, and ready to deploy to `dev` or `prod` with a single command. The
project is now reproducible code, not a one-off you built by hand.

Next, you [train and register an ML model](70-ml-models.md) on the cleaned gold data and serve its
features from Lakebase.

---

### Tutorial navigation

| ← Previous | Overview | Next → |
|:---|:---:|---:|
| [5. Lakeflow Job](50-job.md) | [Table of contents](index.md) | [7. ML Models](70-ml-models.md) |
