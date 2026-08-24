# Human-to-SQL Service

Standalone FastAPI and CLI service that converts natural-language questions into
validated Microsoft SQL Server `SELECT` statements. It generates SQL only and
has no query execution path or runtime dependency on `reports-api`.

## Deployed Render endpoint

The Human-to-SQL service is live on Render at:

- Base URL: https://reports-human-to-sql-service.onrender.com
- Health: https://reports-human-to-sql-service.onrender.com/health
- SQL generation: https://reports-human-to-sql-service.onrender.com/api/v1/sql/generate
- SQL-only output: https://reports-human-to-sql-service.onrender.com/api/v1/sql/generate-sql-only
- Catalog list: https://reports-human-to-sql-service.onrender.com/api/v1/catalog/databases

Verified health response:

```json
{"status":"ok","service":"human-to-sql-service","version":"1.0.0","execution":"disabled"}
```

Render free instances sleep after inactivity, so the first request may take a few seconds to wake.

## Request contract

The public request contract is intentionally simple:

- prompt is required
- environment defaults to test when omitted
- database is optional and defaults to DB7222 when omitted
- query_mode is optional and defaults to auto when omitted
- report_id is optional; if supplied, the SQL generation step substitutes it into the final query when a prompt references it

Example:

```powershell
$body = @{
  prompt = "Show the report status timeline for report 45036187"
  environment = "test"
  database = "DB7222"
  query_mode = "auto"
  report_id = 45036187
} | ConvertTo-Json

Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri https://reports-human-to-sql-service.onrender.com/api/v1/sql/generate -Body $body
```

The raw SQL-only variant responds with just the generated SQL string:

```powershell
Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri https://reports-human-to-sql-service.onrender.com/api/v1/sql/generate-sql-only `
  -Body (@{ prompt = "Show the report status timeline for report 45036187" } | ConvertTo-Json)
```

## Setup and local run

```powershell
cd C:\git1\triage-agent\rovo-forge-poc\human-to-sql-service
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload --port 10001
```

`GEMINI_API_KEY` is optional for reviewed DB7222 templates. It is required when
`generated_only` is selected or `auto` cannot match a template.

## API

```powershell
Invoke-RestMethod http://localhost:10001/health
Invoke-RestMethod http://localhost:10001/api/v1/catalog/databases

$body = @{
  prompt = "Show the report status timeline"
  report_id = 45036187
  query_mode = "auto"
} | ConvertTo-Json
Invoke-RestMethod -Method Post -ContentType application/json `
  -Uri http://localhost:10001/api/v1/sql/generate -Body $body
```

Node and database are optional. The router scores registered targets using the
prompt and semantic catalog terms. Explicit registered hints win; conflicting or
unknown pairs fail closed. Target routing and template/generated engine routing
are reported separately.

## CLI

```powershell
python -m app.cli "Show the report status timeline" --report-id 45036187
python -m app.cli "Show workflow queue tasks" --node db02 --database Operations
python -m app.cli "Show report products" --report-id 45036187 --query-mode templates_only
```

## Readiness matrix

| Node | Database | Routing | Catalog | SQL generation |
|---|---|---|---|---|
| db01 | DB7222 | Enabled | Compiled legacy pack included | Ready; templates and optional Gemini |
| db02 | Operations | Enabled | Not captured/compiled | Returns `catalog_unavailable` until capture and review |

The service never silently falls back to another database when the selected
target has no compiled catalog.

## Guardrails

Every returned query is parsed and must be one `SELECT`/CTE with a `TOP` cap.
Only retrieved catalog objects and columns are accepted. Joins require reviewed
relationships. Cross-database names, `SELECT *`, writes, DDL, execution,
unbound parameters, and long inline identifier literals are rejected.
Procedures, functions, triggers, and dependencies are evidence only.

## Catalog maintenance

Offline tools are self-contained under `scripts/` and use this project's
`catalog/`, `schema/`, and `.catalog-captures/` paths:

```powershell
pip install pyodbc
python scripts/catalog_sqlserver.py --node db02 --database Operations
python scripts/compile_catalog.py --node db02 --database Operations
python scripts/build_schema_embeddings.py --server db01 --database DB7222
python scripts/compile_gold_examples.py --node db01 --database DB7222
python scripts/import_foreign_keys.py foreign-keys.json
```

Raw captures may include protected metadata and are ignored by git. Review
compiled relationships and catalog policy before enabling a new target.

## Tests

```powershell
python -m unittest discover -s tests -v
python -m compileall -q app scripts tests
```
