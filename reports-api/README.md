# rovo-forge-poc / reports-api

PoC HTTP API for the **Triage Agent**: look up a report by ID and inspect **delivery configuration**, **report status**, and **operations task status**.

Data is **seeded** (`data/seed.json`). There is no SQL connection. No auth.

| | |
| --- | --- |
| **Live API** | https://reports-api-4aux.onrender.com |
| **Swagger** | https://reports-api-4aux.onrender.com/docs |
| **Health** | https://reports-api-4aux.onrender.com/health |
| **Endpoint catalog** | https://reports-api-4aux.onrender.com/api/v1/meta/endpoints |
| **Dashboard** | https://dashboard.render.com/web/srv-da5js3bncjis7395oes0 |
| **Repo** | https://github.com/RahulGo8u/rovo-forge-poc |

---

## Valid IDs you can search

Any of these numbers work with `lookup-by-identifier`, `diagnose-delivery-config`, and (for ReportID) the `/reports/{report_id}/...` routes.

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | City | Delivery diagnosis | Task current state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`44840403`](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) | [`99100234`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=99100234&kind=OrderID) | [`120045`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=120045&kind=CustomerID) | [`88012`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=88012&kind=OrgNodeID) | [`55001`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=55001&kind=ProfileID) | Columbus, OH | `attention` — email OK, DXF rule disabled | Complete |
| [`72391747`](https://reports-api-4aux.onrender.com/api/v1/reports/72391747) | [`100334455`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=100334455&kind=OrderID) | [`220118`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=220118&kind=CustomerID) | [`145002`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=145002&kind=OrgNodeID) | [`66002`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=66002&kind=ProfileID) | Austin, TX | `healthy` — email + DXF enabled | Complete |
| [`50110200`](https://reports-api-4aux.onrender.com/api/v1/reports/50110200) | [`110445566`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=110445566&kind=OrderID) | [`330201`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=330201&kind=CustomerID) | [`200101`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=200101&kind=OrgNodeID) | [`77003`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=77003&kind=ProfileID) | Denver, CO | `issue` — no delivery rules | **Waiting** |
| [`61220311`](https://reports-api-4aux.onrender.com/api/v1/reports/61220311) | [`120556677`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=120556677&kind=OrderID) | [`440312`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=440312&kind=CustomerID) | [`310202`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=310202&kind=OrgNodeID) | [`88004`](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=88004&kind=ProfileID) | Seattle, WA | `issue` — all delivery rules disabled | Complete |

- Inherited org delivery rules: only **OrgNodeID `88012`** has rows.  
- `kind` / `lookup_kind`: `auto`, `ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`.  
- Invalid IDs (text, `0`, Jira keys like `PE-658`) return **422**. Unknown ReportID on `/reports/{id}` returns **404**.

---

## All endpoints

Base URL: `https://reports-api-4aux.onrender.com`

| Method | Path | Query / body | Returns | Live example |
| --- | --- | --- | --- | --- |
| GET | `/health` | — | `{ status, service, version, data_source, auth }` | [open](https://reports-api-4aux.onrender.com/health) |
| GET | `/docs` | — | Swagger UI | [open](https://reports-api-4aux.onrender.com/docs) |
| GET | `/api/v1/meta/endpoints` | — | Full path list + sample IDs | [open](https://reports-api-4aux.onrender.com/api/v1/meta/endpoints) |
| GET | `/api/v1/reports/seed-examples` | `limit` (1–50, default 10) | Seeded reports + delivery rule counts | [open](https://reports-api-4aux.onrender.com/api/v1/reports/seed-examples) |
| GET | `/api/v1/reports/lookup-by-identifier` | **`value`** (required), `kind` (default `auto`), `limit` (1–50) | Matching report(s) + `MatchedAs` | [OrderID 99100234](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=99100234) |
| GET | `/api/v1/reports/{report_id}` | — | Report header (IDs, dates, city/state/zip) | [44840403](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) |
| GET | `/api/v1/reports/{report_id}/delivery-snapshot` | — | Report + products + attributes + delivery rules + report status history + **task status** + email settings | [snapshot](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-snapshot) |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | — | `ReportFileDeliveryRule` rows | [rules](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-rules) |
| GET | `/api/v1/reports/{report_id}/products` | — | Products on the report | [products](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/products) |
| GET | `/api/v1/reports/{report_id}/attributes` | — | Report attributes | [attributes](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/attributes) |
| GET | `/api/v1/reports/{report_id}/report-status-history` | `limit` (1–100, default 25) | Report lifecycle (`ReportStatus`: Delivered / In Production / …) | [history](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/report-status-history) |
| GET | `/api/v1/reports/{report_id}/task-status` | — | Operations `Task` + `current_state` + `active_states` + `state_history` | [50110200 Waiting](https://reports-api-4aux.onrender.com/api/v1/reports/50110200/task-status) |
| GET | `/api/v1/reports/{report_id}/customer-email-settings` | — | Customer email availability for the org/profile | [email](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/customer-email-settings) |
| GET | `/api/v1/reports/{report_id}/delivery-diagnosis` | — | Same diagnosis as POST, but ReportID only | [diagnosis](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-diagnosis) |
| GET | `/api/v1/org-nodes/{org_node_id}/inherited-delivery-rules` | — | Org-level rules (`ReportID` null) | [org 88012](https://reports-api-4aux.onrender.com/api/v1/org-nodes/88012/inherited-delivery-rules) |
| GET | `/api/v1/reference/{name}` | `name` = `delivery-methods` \| `file-types` \| `email-types` | ID catalogs | [file-types](https://reports-api-4aux.onrender.com/api/v1/reference/file-types) |
| POST | `/api/v1/triage/diagnose-delivery-config` | JSON body (below) | Delivery-config verdict for any identifier | use Swagger or example below |

### POST `diagnose-delivery-config`

Looks up the identifier, loads delivery rules / products / email settings, and scores **delivery configuration only** (not task status).

```http
POST https://reports-api-4aux.onrender.com/api/v1/triage/diagnose-delivery-config
Content-Type: application/json

{"lookup": "44840403", "lookup_kind": "auto"}
```

Response includes: `ok`, `report_id`, `lookup`, `lookup_kind`, `verdict` (`level`, `summary`, `confidence`), `report`, `delivery_rules`, `products`, `email_availability`, `findings`, `next_checks`.

Verdict levels: `issue` | `attention` | `healthy` | `info`.

### Report status vs task status

| Endpoint | Meaning |
| --- | --- |
| `/report-status-history` | Report lifecycle (e.g. In Production → Delivered) |
| `/task-status` | Operations pipeline Task / TaskState (e.g. Waiting vs Complete) |

---

## Example calls

```powershell
$base = "https://reports-api-4aux.onrender.com"

Invoke-RestMethod "$base/api/v1/reports/44840403"
Invoke-RestMethod "$base/api/v1/reports/lookup-by-identifier?value=99100234"
Invoke-RestMethod "$base/api/v1/reports/50110200/task-status"
Invoke-RestMethod "$base/api/v1/reports/44840403/delivery-diagnosis"
Invoke-RestMethod -Method Post "$base/api/v1/triage/diagnose-delivery-config" `
  -ContentType "application/json" `
  -Body '{"lookup":"50110200","lookup_kind":"auto"}'
```

---

## Local run

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10000
.\.venv\Scripts\python.exe validate.py
```

---

## Render

- Repo: https://github.com/RahulGo8u/rovo-forge-poc  
- Root directory: `reports-api`  
- Build: `pip install -r requirements.txt`  
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
- Health: `/health`  

Free instances may sleep when idle.

---

## Renamed paths (v0.3.0)

| Removed | Current |
| --- | --- |
| `POST /api/v1/triage/quick-investigate` | `POST /api/v1/triage/diagnose-delivery-config` |
| `GET .../delivery-analysis` | `GET .../delivery-diagnosis` |
| `GET /api/v1/resolve` | `GET /api/v1/reports/lookup-by-identifier` |
| `GET .../overview` | `GET .../delivery-snapshot` |
| `GET .../status-timeline` | `GET .../report-status-history` |
| `GET .../email-availability` | `GET .../customer-email-settings` |
| `GET /api/v1/catalog/{name}` | `GET /api/v1/reference/{name}` |
| `GET /api/v1/samples/reports` | `GET /api/v1/reports/seed-examples` |
| `GET .../org-nodes/{id}/delivery-rules` | `GET .../inherited-delivery-rules` |
