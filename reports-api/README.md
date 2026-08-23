# reports-api

Standalone REST API for the **Triage Agent**. It ships with seeded report data and returns results by identifier. **No database connection.**

Designed for [Render](https://render.com).

## How it works

All report, delivery-rule, product, and catalog data lives in `data/seed.json`.  
Pass a **ReportID**, **OrderID**, **CustomerID**, **OrgNodeID**, or **ProfileID** — the API looks it up and returns the matching record(s).

## Sample identifiers

| Kind | Values |
| --- | --- |
| ReportID | `44840403`, `72391747`, `50110200`, `61220311` |
| OrderID | `99100234`, `100334455`, `110445566`, `120556677` |
| CustomerID | `120045`, `220118`, `330201`, `440312` |
| OrgNodeID | `88012`, `145002`, `200101`, `310202` |
| ProfileID | `55001`, `66002`, `77003`, `88004` |

Expected triage shapes in the seed:

- `44840403` — email OK, DXF rule disabled (`attention`)
- `72391747` — email + DXF enabled (`healthy`)
- `50110200` — no delivery rules (`issue`)
- `61220311` — all rules disabled (`issue`)

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Render health check |
| GET | `/api/v1/reports/{report_id}` | Get report by ID |
| GET | `/api/v1/reports/{report_id}/overview` | Full report overview |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | Delivery rules |
| GET | `/api/v1/reports/{report_id}/products` | Products on report |
| GET | `/api/v1/reports/{report_id}/attributes` | Report attributes |
| GET | `/api/v1/reports/{report_id}/status-timeline` | Status history |
| GET | `/api/v1/reports/{report_id}/email-availability` | Email availability |
| GET | `/api/v1/reports/{report_id}/delivery-analysis` | Triage verdict for report |
| GET | `/api/v1/resolve?value={id}&kind=auto` | Resolve any identifier |
| GET | `/api/v1/org-nodes/{org_node_id}/delivery-rules` | Org-node rules |
| GET | `/api/v1/catalog/{name}` | `delivery-methods`, `file-types`, `email-types` |
| GET | `/api/v1/samples/reports` | List seeded reports |
| POST | `/api/v1/triage/quick-investigate` | Quick investigate (`{"lookup":"...","lookup_kind":"auto"}`) |
| GET | `/api/v1/meta/endpoints` | Discovery + sample IDs |

## Local run

```powershell
cd C:\git1\triage-agent\rovo-forge-poc\reports-api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10000
```

Open http://127.0.0.1:10000/docs

```powershell
Invoke-RestMethod http://127.0.0.1:10000/api/v1/reports/44840403
Invoke-RestMethod "http://127.0.0.1:10000/api/v1/resolve?value=99100234"
Invoke-RestMethod -Method Post http://127.0.0.1:10000/api/v1/triage/quick-investigate `
  -ContentType "application/json" `
  -Body '{"lookup":"44840403","lookup_kind":"auto"}'
```

## Validation

No auth in this POC. Requests are validated for identifier shape:

- Path IDs must be integers `>= 1`
- `lookup` / `value` must be a positive whole number (Jira keys like `PE-658` return `422`)
- `kind` must be one of `auto`, `ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`
- Catalog names and `limit` ranges are checked

Run the suite:

```powershell
.\.venv\Scripts\python.exe validate.py
```

## Deploy on Render

1. Push this folder (or parent repo) to GitHub
2. In Render: **New → Blueprint** using `rovo-forge-poc/render.yaml`  
   or create a **Web Service**:
   - Root directory: `reports-api`
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - Health check: `/health`

No SQL drivers, secrets, or network access to EagleView databases are required.
