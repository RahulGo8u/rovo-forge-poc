# reports-api

Standalone REST API for the **Triage Agent**. Data is bundled in `data/seed.json` — **no database**.

**Live:** https://reports-api-4aux.onrender.com  
**Swagger:** https://reports-api-4aux.onrender.com/docs  

Auth is not enabled in this POC. Old paths (`/resolve`, `/triage/quick-investigate`, etc.) were renamed in v0.3.0.

---

## Valid IDs (seed data)

Use these with lookup, report routes, delivery diagnosis, or task status.

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | City | Delivery diagnosis | Task current state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `44840403` | `99100234` | `120045` | `88012` | `55001` | Columbus, OH | `attention` (DXF rule disabled) | Complete |
| `72391747` | `100334455` | `220118` | `145002` | `66002` | Austin, TX | `healthy` | Complete |
| `50110200` | `110445566` | `330201` | `200101` | `77003` | Denver, CO | `issue` (no delivery rules) | Waiting |
| `61220311` | `120556677` | `440312` | `310202` | `88004` | Seattle, WA | `issue` (rules disabled) | Complete |

Org-node inherited rules exist for `88012` only.

---

## Endpoints

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Service health |
| GET | `/docs` | Swagger UI |
| GET | `/api/v1/meta/endpoints` | Discovery + sample IDs |
| GET | `/api/v1/reports/seed-examples` | List seeded example reports |
| GET | `/api/v1/reports/lookup-by-identifier?value={id}&kind=auto` | Find a report from ReportID / OrderID / CustomerID / OrgNodeID / ProfileID |
| GET | `/api/v1/reports/{report_id}` | Report header |
| GET | `/api/v1/reports/{report_id}/delivery-snapshot` | Combined delivery + report status + task snapshot |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | File delivery rules |
| GET | `/api/v1/reports/{report_id}/products` | Products on the report |
| GET | `/api/v1/reports/{report_id}/attributes` | Report attributes |
| GET | `/api/v1/reports/{report_id}/report-status-history` | Report lifecycle (`ReportStatus`) — not operations task |
| GET | `/api/v1/reports/{report_id}/task-status` | Operations `Task` + active `TaskState` + history |
| GET | `/api/v1/reports/{report_id}/customer-email-settings` | Customer email availability |
| GET | `/api/v1/reports/{report_id}/delivery-diagnosis` | Diagnose delivery config for a known ReportID |
| GET | `/api/v1/org-nodes/{org_node_id}/inherited-delivery-rules` | Org-node inherited delivery rules |
| GET | `/api/v1/reference/{name}` | `delivery-methods`, `file-types`, `email-types` |
| POST | `/api/v1/triage/diagnose-delivery-config` | Diagnose delivery config from any identifier |

`POST` body:

```json
{"lookup": "44840403", "lookup_kind": "auto"}
```

Live examples:

- [lookup OrderID 99100234](https://reports-api-4aux.onrender.com/api/v1/reports/lookup-by-identifier?value=99100234)
- [task status 50110200](https://reports-api-4aux.onrender.com/api/v1/reports/50110200/task-status)
- [delivery diagnosis 44840403](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-diagnosis)

`diagnose-delivery-config` (formerly quick-investigate) checks **delivery rules only**. It does not inspect operations task status — use `/task-status` for that.

---

## Local run

```powershell
cd reports-api
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10000
.\.venv\Scripts\python.exe validate.py
```
