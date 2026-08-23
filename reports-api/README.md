# reports-api

Standalone REST API for the **Triage Agent**. Data is bundled in `data/seed.json` — **no database**. Look up a report by **ReportID**, **OrderID**, **CustomerID**, **OrgNodeID**, or **ProfileID**.

**Live (Render):** https://reports-api-4aux.onrender.com  
**Swagger:** https://reports-api-4aux.onrender.com/docs  
**GitHub:** https://github.com/RahulGo8u/rovo-forge-poc  
**Dashboard:** https://dashboard.render.com/web/srv-da5js3bncjis7395oes0

Auth is not enabled in this POC.

---

## Valid IDs (seed data)

Use any of these values with `/api/v1/resolve`, `/api/v1/reports/{report_id}`, or `POST /api/v1/triage/quick-investigate`.

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | City | Triage verdict |
| --- | --- | --- | --- | --- | --- | --- |
| `44840403` | `99100234` | `120045` | `88012` | `55001` | Columbus, OH | `attention` — email OK, DXF rule disabled |
| `72391747` | `100334455` | `220118` | `145002` | `66002` | Austin, TX | `healthy` — email + DXF enabled |
| `50110200` | `110445566` | `330201` | `200101` | `77003` | Denver, CO | `issue` — no delivery rules |
| `61220311` | `120556677` | `440312` | `310202` | `88004` | Seattle, WA | `issue` — all rules disabled |

**Org-node rules:** only `88012` has inherited org-level delivery rules. `145002`, `200101`, and `310202` return an empty list.

**Catalog names:** `delivery-methods`, `file-types`, `email-types`

---

## Endpoints

Base URL (live): `https://reports-api-4aux.onrender.com`

| Method | Path | Query / body | Description | Example |
| --- | --- | --- | --- | --- |
| GET | `/health` | — | Health check (Render) | [/health](https://reports-api-4aux.onrender.com/health) |
| GET | `/docs` | — | OpenAPI / Swagger UI | [/docs](https://reports-api-4aux.onrender.com/docs) |
| GET | `/api/v1/meta/endpoints` | — | Lists all API paths + sample IDs | [/api/v1/meta/endpoints](https://reports-api-4aux.onrender.com/api/v1/meta/endpoints) |
| GET | `/api/v1/samples/reports` | `limit` (1–50, default 10) | Seeded reports you can search | [/api/v1/samples/reports](https://reports-api-4aux.onrender.com/api/v1/samples/reports) |
| GET | `/api/v1/reports/{report_id}` | — | Get report by ReportID | [/api/v1/reports/44840403](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) |
| GET | `/api/v1/reports/{report_id}/overview` | — | Report + products + rules + timeline + email | [/api/v1/reports/44840403/overview](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/overview) |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | — | Delivery rules for the report | [/api/v1/reports/44840403/delivery-rules](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-rules) |
| GET | `/api/v1/reports/{report_id}/products` | — | Products on the report | [/api/v1/reports/44840403/products](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/products) |
| GET | `/api/v1/reports/{report_id}/attributes` | — | Report attributes | [/api/v1/reports/44840403/attributes](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/attributes) |
| GET | `/api/v1/reports/{report_id}/status-timeline` | `limit` (1–100, default 25) | Status history | [/api/v1/reports/44840403/status-timeline](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/status-timeline) |
| GET | `/api/v1/reports/{report_id}/email-availability` | — | Email availability from org/profile | [/api/v1/reports/44840403/email-availability](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/email-availability) |
| GET | `/api/v1/reports/{report_id}/delivery-analysis` | — | Triage verdict for that ReportID | [/api/v1/reports/44840403/delivery-analysis](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-analysis) |
| GET | `/api/v1/resolve` | `value` (required), `kind` (`auto` \| `ReportID` \| `OrderID` \| `CustomerID` \| `OrgNodeID` \| `ProfileID`), `limit` (1–50) | Resolve any identifier to report(s) | [/api/v1/resolve?value=99100234](https://reports-api-4aux.onrender.com/api/v1/resolve?value=99100234) |
| GET | `/api/v1/org-nodes/{org_node_id}/delivery-rules` | — | Org-node inherited delivery rules | [/api/v1/org-nodes/88012/delivery-rules](https://reports-api-4aux.onrender.com/api/v1/org-nodes/88012/delivery-rules) |
| GET | `/api/v1/catalog/{catalog_name}` | `catalog_name`: `delivery-methods`, `file-types`, `email-types` | Reference catalogs | [/api/v1/catalog/file-types](https://reports-api-4aux.onrender.com/api/v1/catalog/file-types) |
| POST | `/api/v1/triage/quick-investigate` | JSON body `{"lookup":"<id>","lookup_kind":"auto"}` | Default triage flow (resolve + verdict) | see examples below |

`/api/v1/reports/{report_id}` returns **404** if the ReportID is not in seed data. Invalid IDs (zero, text, Jira keys like `PE-658`) return **422**.

---

## Example searches

Resolve by OrderID:

```
GET https://reports-api-4aux.onrender.com/api/v1/resolve?value=99100234&kind=OrderID
```

Resolve by CustomerID (auto-detect):

```
GET https://reports-api-4aux.onrender.com/api/v1/resolve?value=220118
```

Quick investigate (JSON body):

```json
POST https://reports-api-4aux.onrender.com/api/v1/triage/quick-investigate
{"lookup": "44840403", "lookup_kind": "auto"}
```

PowerShell:

```powershell
Invoke-RestMethod https://reports-api-4aux.onrender.com/api/v1/reports/44840403
Invoke-RestMethod "https://reports-api-4aux.onrender.com/api/v1/resolve?value=99100234"
Invoke-RestMethod "https://reports-api-4aux.onrender.com/api/v1/resolve?value=55001&kind=ProfileID"
Invoke-RestMethod -Method Post https://reports-api-4aux.onrender.com/api/v1/triage/quick-investigate `
  -ContentType "application/json" `
  -Body '{"lookup":"50110200","lookup_kind":"auto"}'
```

---

## Local run

```powershell
cd reports-api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10000
```

Open http://127.0.0.1:10000/docs

Validation suite (no auth):

```powershell
.\.venv\Scripts\python.exe validate.py
```

Identifier rules:

- Path IDs and `lookup` / `value` must be a positive whole number
- Jira keys are rejected (`422`)
- `kind` / `lookup_kind` must be one of: `auto`, `ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`

---

## Render

Service **reports-api** is already deployed (free plan, Python, root directory `reports-api`).

To recreate:

- Repo: `https://github.com/RahulGo8u/rovo-forge-poc`
- Root directory: `reports-api`
- Build: `pip install -r requirements.txt`
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`

Or use the Blueprint at repo-root `render.yaml`.

The free instance may sleep when idle; the first request after sleep can take a few seconds.
