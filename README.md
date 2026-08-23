# rovo-forge-poc

Personal PoC repo for the **Triage Agent** reports API.

The API lives in [`reports-api/`](reports-api/). It is hosted on Render and uses bundled seed data (no database).

**Live:** https://reports-api-4aux.onrender.com  
**Swagger:** https://reports-api-4aux.onrender.com/docs  
**Dashboard:** https://dashboard.render.com/web/srv-da5js3bncjis7395oes0

Full endpoint list, example calls, and local/Render notes: [`reports-api/README.md`](reports-api/README.md)

---

## Valid IDs you can search

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | City | Expected triage |
| --- | --- | --- | --- | --- | --- | --- |
| `44840403` | `99100234` | `120045` | `88012` | `55001` | Columbus, OH | `attention` |
| `72391747` | `100334455` | `220118` | `145002` | `66002` | Austin, TX | `healthy` |
| `50110200` | `110445566` | `330201` | `200101` | `77003` | Denver, CO | `issue` (no rules) |
| `61220311` | `120556677` | `440312` | `310202` | `88004` | Seattle, WA | `issue` (rules disabled) |

Org-node delivery rules exist for `88012` only.

---

## Endpoints

| Method | Path | Description | Live example |
| --- | --- | --- | --- |
| GET | `/health` | Health check | [open](https://reports-api-4aux.onrender.com/health) |
| GET | `/docs` | Swagger UI | [open](https://reports-api-4aux.onrender.com/docs) |
| GET | `/api/v1/meta/endpoints` | Discovery + sample IDs | [open](https://reports-api-4aux.onrender.com/api/v1/meta/endpoints) |
| GET | `/api/v1/samples/reports` | List seeded reports | [open](https://reports-api-4aux.onrender.com/api/v1/samples/reports) |
| GET | `/api/v1/reports/{report_id}` | Get report by ID | [44840403](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) |
| GET | `/api/v1/reports/{report_id}/overview` | Full overview | [overview](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/overview) |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | Delivery rules | [rules](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-rules) |
| GET | `/api/v1/reports/{report_id}/products` | Products | [products](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/products) |
| GET | `/api/v1/reports/{report_id}/attributes` | Attributes | [attributes](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/attributes) |
| GET | `/api/v1/reports/{report_id}/status-timeline` | Status history | [timeline](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/status-timeline) |
| GET | `/api/v1/reports/{report_id}/email-availability` | Email availability | [email](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/email-availability) |
| GET | `/api/v1/reports/{report_id}/delivery-analysis` | Triage verdict | [analysis](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-analysis) |
| GET | `/api/v1/resolve?value={id}&kind=auto` | Resolve OrderID / CustomerID / OrgNodeID / ProfileID / ReportID | [OrderID 99100234](https://reports-api-4aux.onrender.com/api/v1/resolve?value=99100234) |
| GET | `/api/v1/org-nodes/{org_node_id}/delivery-rules` | Org-node rules | [org 88012](https://reports-api-4aux.onrender.com/api/v1/org-nodes/88012/delivery-rules) |
| GET | `/api/v1/catalog/{name}` | `delivery-methods`, `file-types`, `email-types` | [file-types](https://reports-api-4aux.onrender.com/api/v1/catalog/file-types) |
| POST | `/api/v1/triage/quick-investigate` | Body: `{"lookup":"44840403","lookup_kind":"auto"}` | use Swagger or curl |

`kind` / `lookup_kind`: `auto`, `ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`.
