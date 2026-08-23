# rovo-forge-poc

Personal PoC for the **Triage Agent** reports API (`reports-api/`). Seed data only — no database.

**Live:** https://reports-api-4aux.onrender.com  
**Swagger:** https://reports-api-4aux.onrender.com/docs  
**Full docs:** [reports-api/README.md](reports-api/README.md)

## Valid IDs

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | Delivery diagnosis | Task state |
| --- | --- | --- | --- | --- | --- | --- |
| `44840403` | `99100234` | `120045` | `88012` | `55001` | `attention` | Complete |
| `72391747` | `100334455` | `220118` | `145002` | `66002` | `healthy` | Complete |
| `50110200` | `110445566` | `330201` | `200101` | `77003` | `issue` (no rules) | Waiting |
| `61220311` | `120556677` | `440312` | `310202` | `88004` | `issue` (disabled) | Complete |

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health |
| GET | `/api/v1/meta/endpoints` | Discovery |
| GET | `/api/v1/reports/seed-examples` | Example reports |
| GET | `/api/v1/reports/lookup-by-identifier?value={id}` | Find report by any ID |
| GET | `/api/v1/reports/{report_id}` | Report header |
| GET | `/api/v1/reports/{report_id}/delivery-snapshot` | Full snapshot |
| GET | `/api/v1/reports/{report_id}/delivery-rules` | Delivery rules |
| GET | `/api/v1/reports/{report_id}/products` | Products |
| GET | `/api/v1/reports/{report_id}/attributes` | Attributes |
| GET | `/api/v1/reports/{report_id}/report-status-history` | Report lifecycle status |
| GET | `/api/v1/reports/{report_id}/task-status` | Operations task status |
| GET | `/api/v1/reports/{report_id}/customer-email-settings` | Email settings |
| GET | `/api/v1/reports/{report_id}/delivery-diagnosis` | Delivery-config diagnosis for ReportID |
| GET | `/api/v1/org-nodes/{org_node_id}/inherited-delivery-rules` | Org inherited rules |
| GET | `/api/v1/reference/{name}` | Reference catalogs |
| POST | `/api/v1/triage/diagnose-delivery-config` | Delivery-config diagnosis from any identifier |
