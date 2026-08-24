# rovo-forge-poc / reports-api

HTTP API that gives the **Triage Agent** the read-only lookups it needs when a customer says *"I never got my report, email, or DXF file."* Given any identifier, it answers three separate questions: is the **delivery configuration** correct, what is the **report status**, and where is the **operations workflow task**.

## Deployed Render endpoints

The project now includes two deployed services:

The Reports API SQL bridge intentionally calls the raw SQL-text endpoint from Human-to-SQL so it can return a single query string to callers.

- Human-to-SQL service (verified live):
  - Base URL: https://reports-human-to-sql-service.onrender.com
  - Health: https://reports-human-to-sql-service.onrender.com/health
  - Generate SQL: https://reports-human-to-sql-service.onrender.com/api/v1/sql/generate
  - Catalog: https://reports-human-to-sql-service.onrender.com/api/v1/catalog/databases
  - Verified health payload:
    ```json
    {"status":"ok","service":"human-to-sql-service","version":"1.0.0","execution":"disabled"}
    ```

- Reports API (verified live):
  - Base URL: https://reports-api-4aux.onrender.com
  - Health: https://reports-api-4aux.onrender.com/health
  - SQL generator bridge: https://reports-api-4aux.onrender.com/api/v1/generatesqlquery
  - Swagger docs: https://reports-api-4aux.onrender.com/docs

> Render free instances spin down after inactivity, so the first request may take a few seconds to wake the service.

### Why this service exists

The triage agent runs in the cloud and cannot reach the on-premise SQL Server, which uses Windows authentication. This service is a stand-in: it exposes the same shapes the agent would get from the `Report`, `ReportDetail`, `ReportFileDeliveryRule`, `CustomerEmailAvailability`, and Operations `Task` / `TaskState` tables, served from a seeded JSON fixture. **There is no database attached.** Responses are deterministic, safe to demo, and contain no customer data.

Every response uses one envelope so the agent can parse uniformly:

```json
{ "ok": true, "source": "seed", "row_count": 2, "data": [], "meta": {} }
```

`row_count` is `0` and `data` is `null` when a record legitimately does not exist. `meta` echoes the identifiers used, plus context such as `current_state_name`.

### Authentication

Send `X-API-Key` on every `/api/v1` call. `/health` stays public so Render can health-check it.

```http
GET /api/v1/reports/44840403
X-API-Key: <your-secret>
```

`Authorization: Bearer <your-secret>` is also accepted. A missing or wrong key returns **401**. Never commit the real key; set `API_SECRET_KEY` in the Render environment and in a local `.env` (gitignored).

| | |
| --- | --- |
| **Live API** | https://reports-api-4aux.onrender.com |
| **Swagger** | https://reports-api-4aux.onrender.com/docs |
| **Health** | https://reports-api-4aux.onrender.com/health |
| **Endpoint catalog** | https://reports-api-4aux.onrender.com/api/v1/metadata/endpoint-catalog |
| **Dashboard** | https://dashboard.render.com/web/srv-da5js3bncjis7395oes0 |
| **Version** | 0.5.0 — 40 routes (39 authenticated, plus public `/health`) |

### Status codes

| Code | When |
| --- | --- |
| 200 | Found, or an empty collection (`row_count: 0`) |
| 401 | Missing or wrong API key on an `/api/v1` route |
| 404 | Unknown ReportID, TaskID, CustomerID, or a report with no such sub-record |
| 422 | Identifier is not a positive whole number (text, `0`, or a Jira key like `PE-658`) |

---

## Valid IDs you can search

Any of these numbers work with `find-by-identifier`, `diagnose-delivery-configuration`, and (for ReportID) the `/reports/{report_id}/...` routes.

| ReportID | OrderID | CustomerID | OrgNodeID | ProfileID | City | Delivery diagnosis | Task current state |
| --- | --- | --- | --- | --- | --- | --- | --- |
| [`44840403`](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) | [`99100234`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=99100234&kind=OrderID) | [`120045`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=120045&kind=CustomerID) | [`88012`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=88012&kind=OrgNodeID) | [`55001`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=55001&kind=ProfileID) | Columbus, OH | `attention` — email OK, DXF rule disabled | Complete |
| [`72391747`](https://reports-api-4aux.onrender.com/api/v1/reports/72391747) | [`100334455`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=100334455&kind=OrderID) | [`220118`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=220118&kind=CustomerID) | [`145002`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=145002&kind=OrgNodeID) | [`66002`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=66002&kind=ProfileID) | Austin, TX | `healthy` — email + DXF enabled | Complete |
| [`50110200`](https://reports-api-4aux.onrender.com/api/v1/reports/50110200) | [`110445566`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=110445566&kind=OrderID) | [`330201`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=330201&kind=CustomerID) | [`200101`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=200101&kind=OrgNodeID) | [`77003`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=77003&kind=ProfileID) | Denver, CO | `issue` — no delivery rules | **Waiting** |
| [`61220311`](https://reports-api-4aux.onrender.com/api/v1/reports/61220311) | [`120556677`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=120556677&kind=OrderID) | [`440312`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=440312&kind=CustomerID) | [`310202`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=310202&kind=OrgNodeID) | [`88004`](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=88004&kind=ProfileID) | Seattle, WA | `issue` — all delivery rules disabled | Complete |

- Inherited org delivery rules: only **OrgNodeID `88012`** has rows.  
- `kind` / `lookup_kind`: `auto`, `ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`.  
- Invalid IDs (text, `0`, Jira keys like `PE-658`) return **422**. Unknown ReportID on `/reports/{id}` returns **404**.

---

## All endpoints (v0.5)

Base URL: `https://reports-api-4aux.onrender.com`

**40** routes (39 under `/api/v1` + public `/health`). Every path spells out what it returns, with no abbreviations or run-together words. Live catalog: [`/api/v1/metadata/endpoint-catalog`](https://reports-api-4aux.onrender.com/api/v1/metadata/endpoint-catalog), which also lists the common triage starting points under `triage_entry_points`.

### Report status and operations workflow

`current-status-with-history` is the customer-visible `ReportStatus` lifecycle. The `operations-workflow-*` paths are the internal `Task` / `TaskState` pipeline. They stay separate because a report can read *Delivered* while its workflow task is stuck.

| Method | Path | Returns | Live example |
| --- | --- | --- | --- |
| GET | `/api/v1/reports/{id}/current-status-with-history` | Current report status plus its full history | [44840403](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/current-status-with-history) |
| GET | `/api/v1/reports/{id}/status-change-history` | Status timeline only, `limit` 1–100 | [history](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/status-change-history) |
| GET | `/api/v1/reports/{id}/operations-workflow-status` | Task plus current, active, and historical states | [50110200 Waiting](https://reports-api-4aux.onrender.com/api/v1/reports/50110200/operations-workflow-status) |
| GET | `/api/v1/reports/{id}/operations-workflow-task` | The `Task` row on its own | [task](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/operations-workflow-task) |
| GET | `/api/v1/reports/{id}/operations-workflow-task-states` | Active and historical `TaskState` rows | [states](https://reports-api-4aux.onrender.com/api/v1/reports/50110200/operations-workflow-task-states) |
| GET | `/api/v1/operations-workflow-tasks/{task_id}` | Same workflow snapshot, keyed by TaskID | [90044840403](https://reports-api-4aux.onrender.com/api/v1/operations-workflow-tasks/90044840403) |
| GET | `/api/v1/operations-workflow-tasks/{task_id}/task-states` | `TaskState` rows keyed by TaskID | [states](https://reports-api-4aux.onrender.com/api/v1/operations-workflow-tasks/90050110200/task-states) |

### Report details, from narrowest to widest payload

| Method | Path | Returns | Live example |
| --- | --- | --- | --- |
| GET | `/api/v1/reports/{id}` | Report header only | [header](https://reports-api-4aux.onrender.com/api/v1/reports/44840403) |
| GET | `/api/v1/reports/{id}/details-with-address-and-measurements` | Header, property address, and `ReportDetail` (facets, area, pitch) | [details](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/details-with-address-and-measurements) |
| GET | `/api/v1/reports/{id}/details-with-ordered-products` | The above plus ordered products | [with products](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/details-with-ordered-products) |
| GET | `/api/v1/reports/{id}/details-with-ordered-products-and-attributes` | The above plus report attributes | [with attributes](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/details-with-ordered-products-and-attributes) |
| GET | `/api/v1/reports/{id}/delivery-configuration-snapshot` | Everything delivery-related in one call | [snapshot](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-configuration-snapshot) |

### Delivery configuration

| Method | Path | Returns | Live example |
| --- | --- | --- | --- |
| GET | `/api/v1/reports/{id}/file-delivery-rules` | `ReportFileDeliveryRule` rows | [rules](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/file-delivery-rules) |
| GET | `/api/v1/reports/{id}/delivery-configuration-diagnosis` | Verdict for a known ReportID | [diagnosis](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-configuration-diagnosis) |
| GET | `/api/v1/reports/{id}/customer-email-notification-settings` | Email availability for the report's organization and profile | [email](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/customer-email-notification-settings) |
| GET | `/api/v1/reports/{id}/deliverable-verification-rules` | `DeliverableVerificationRule` rows | [verification](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/deliverable-verification-rules) |
| GET | `/api/v1/reports/{id}/product-file-generation-capabilities` | Product `CanGenerateDXF` / `CanGenerateXML` / `CanGenerateRXF` | [capabilities](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/product-file-generation-capabilities) |
| GET | `/api/v1/organization-nodes/{id}/inherited-file-delivery-rules` | Organization-level rules (`ReportID` null) | [88012](https://reports-api-4aux.onrender.com/api/v1/organization-nodes/88012/inherited-file-delivery-rules) |
| POST | `/api/v1/triage/diagnose-delivery-configuration` | Verdict from any identifier | use Swagger |

### Report sub-resources

| Method | Path | Returns |
| --- | --- | --- |
| GET | `/api/v1/reports/{id}/ordered-products` | Products ordered on the report |
| GET | `/api/v1/reports/{id}/report-attributes` | Report attributes |
| GET | `/api/v1/reports/{id}/property-address` | `ReportAddress` including latitude, longitude, county |
| GET | `/api/v1/reports/{id}/measurement-values` | `ReportMeasurement` rows |
| GET | `/api/v1/reports/{id}/source-imagery` | `ReportImage` rows |
| GET | `/api/v1/reports/{id}/profile-and-organization-associations` | Profile and organization associations |
| GET | `/api/v1/reports/{id}/related-reports` | Related or duplicate reports |
| GET | `/api/v1/reports/{id}/ordering-application-source` | Ordering channel (Extranet, Partner Web Service, BOSS) |
| GET | `/api/v1/reports/{id}/invoice-status` | Invoice status |

### Customer, organization, profile, order, search, reference data

| Method | Path | Returns | Live example |
| --- | --- | --- | --- |
| GET | `/api/v1/reports/find-by-identifier` | Reports matching any identifier, plus `MatchedAs` | [OrderID](https://reports-api-4aux.onrender.com/api/v1/reports/find-by-identifier?value=99100234) |
| GET | `/api/v1/reports/example-reports-in-seed-data` | Seeded reports plus delivery rule counts | [examples](https://reports-api-4aux.onrender.com/api/v1/reports/example-reports-in-seed-data) |
| GET | `/api/v1/customers/{id}` | Customer | [120045](https://reports-api-4aux.onrender.com/api/v1/customers/120045) |
| GET | `/api/v1/customers/{id}/reports` | Reports for the customer | [reports](https://reports-api-4aux.onrender.com/api/v1/customers/120045/reports) |
| GET | `/api/v1/customers/{id}/email-notification-settings` | `CustomerEmailAvailability` | [email](https://reports-api-4aux.onrender.com/api/v1/customers/120045/email-notification-settings) |
| GET | `/api/v1/organization-nodes/{id}` | Organization node | [88012](https://reports-api-4aux.onrender.com/api/v1/organization-nodes/88012) |
| GET | `/api/v1/organization-nodes/{id}/reports` | Reports under the organization node | [reports](https://reports-api-4aux.onrender.com/api/v1/organization-nodes/88012/reports) |
| GET | `/api/v1/recipient-profiles/{id}` | Recipient profile plus notification flags | [55001](https://reports-api-4aux.onrender.com/api/v1/recipient-profiles/55001) |
| GET | `/api/v1/orders/{id}/reports` | Reports for an OrderID | [99100234](https://reports-api-4aux.onrender.com/api/v1/orders/99100234/reports) |
| GET | `/api/v1/reference-data/{name}` | `delivery-methods`, `file-types`, `email-types`, `workflow-states` | [workflow-states](https://reports-api-4aux.onrender.com/api/v1/reference-data/workflow-states) |
| GET | `/api/v1/metadata/endpoint-catalog` | This catalog, generated from the live router | [catalog](https://reports-api-4aux.onrender.com/api/v1/metadata/endpoint-catalog) |
| GET | `/health` | Health, no authentication | [health](https://reports-api-4aux.onrender.com/health) |

---

## What the delivery-configuration diagnosis does

Two endpoints run the same logic:

- `GET /api/v1/reports/{report_id}/delivery-configuration-diagnosis` — when you already know the ReportID.
- `POST /api/v1/triage/diagnose-delivery-configuration` — when you only have some number (OrderID, CustomerID, OrgNodeID, ProfileID) and want the service to resolve it first.

### The question it answers

*"Was this report ever configured to be delivered the way the customer expected?"*

Every other endpoint hands back raw rows and leaves the interpretation to you. This one reads the report's `ReportFileDeliveryRule` rows and turns them into a verdict, so the agent does not have to hardcode knowledge of `DeliveryMethodID` and `FileTypeID` values. It answers a **configuration** question only. It does **not** check whether a delivery was actually attempted, whether the mail server accepted the message, or whether the workflow task finished — use `operations-workflow-status` for that last one.

### How it decides

Rules are evaluated in order, and the first matching condition wins:

| Condition | Verdict | Confidence | Meaning |
| --- | --- | --- | --- |
| No rule rows at all | `issue` | 92 | Nothing was ever configured to send. Delivery could not have happened. |
| Rules exist, all have `Disabled` set | `issue` | 95 | Someone turned delivery off, or an organization-level `OverrideChildren` rule did. |
| No enabled rule with `DeliveryMethodID = 1` | `issue` | 88 | No active email channel, so no notification email could go out. |
| Email is enabled but no rule has `FileTypeID = 4` | `attention` | 80 | Email works; the neighborhood/DXF file is missing or disabled. |
| Email and DXF rules both enabled | `healthy` | 78 | Configuration is complete, so look downstream for the failure. |
| Identifier matched no report | `info` | 90 | Nothing to diagnose; check the identifier. |

`confidence` is a fixed score per branch reflecting how conclusive that signal is. "All rules disabled" is near-certain (95); "everything looks fine" is the weakest claim (78), because a healthy configuration does not prove the file was delivered.

### Request

```http
POST https://reports-api-4aux.onrender.com/api/v1/triage/diagnose-delivery-configuration
Content-Type: application/json
X-API-Key: <your-secret>

{"lookup": "99100234", "lookup_kind": "auto"}
```

`lookup_kind` is `auto` by default, which tries every identifier column and reports which one matched. Set it explicitly (`ReportID`, `OrderID`, `CustomerID`, `OrgNodeID`, `ProfileID`) to avoid an ambiguous match. If several reports match, the first is diagnosed.

### Response

```json
{
  "ok": true,
  "report_id": 44840403,
  "lookup": "99100234",
  "lookup_kind": "OrderID",
  "verdict": {
    "level": "attention",
    "summary": "Email delivery looks configured; DXF/neighborhood delivery may be missing or disabled.",
    "confidence": 80
  },
  "report": {},
  "delivery_rules": [],
  "products": [],
  "email_availability": [],
  "findings": [
    "1 delivery rule(s) are disabled.",
    "Enabled rules cover FileTypeIDs: [2, 7].",
    "No enabled neighborhood/DXF rule (FileTypeID=4)."
  ],
  "next_checks": [
    "Confirm the customer expected a DXF file.",
    "Check /reports/{report_id}/product-file-generation-capabilities for CanGenerateDXF.",
    "Inspect Partner Web Service or FTP delivery if either applies."
  ]
}
```

`lookup_kind` in the response is the column that actually matched, which may differ from what you sent when using `auto`. `findings` are the observations behind the verdict. `next_checks` name the specific endpoints to call next, so the agent can keep going without a decision tree of its own. The `report`, `delivery_rules`, `products`, and `email_availability` blocks carry the raw evidence, so a human can audit the verdict without a second request.

### Seeded outcomes

| ReportID | Verdict | Why |
| --- | --- | --- |
| [`72391747`](https://reports-api-4aux.onrender.com/api/v1/reports/72391747/delivery-configuration-diagnosis) | `healthy` | Email and DXF rules both enabled |
| [`44840403`](https://reports-api-4aux.onrender.com/api/v1/reports/44840403/delivery-configuration-diagnosis) | `attention` | Email fine, DXF rule disabled |
| [`50110200`](https://reports-api-4aux.onrender.com/api/v1/reports/50110200/delivery-configuration-diagnosis) | `issue` | No delivery rules exist |
| [`61220311`](https://reports-api-4aux.onrender.com/api/v1/reports/61220311/delivery-configuration-diagnosis) | `issue` | Every delivery rule is disabled |

---

## Report status versus operations workflow status

These are two different systems, and confusing them is the most common triage mistake. A report can display *Delivered* to the customer while its internal workflow task is still parked in *Waiting*.

| | Report status | Operations workflow status |
| --- | --- | --- |
| Source | `ReportStatus` table | `Task` / `TaskState` tables |
| Audience | Customer-facing lifecycle | Internal production pipeline |
| Example values | In Production, Delivered | Waiting, InProduction, Complete |
| Endpoints | `/current-status-with-history`, `/status-change-history` | `/operations-workflow-status`, `/operations-workflow-task`, `/operations-workflow-task-states` |

Report `50110200` is seeded to show the mismatch: its report status is *In Production* while its workflow task sits in **Waiting**, which is the shape the Report SLA / activity timeline work needs.

---

## Suggested triage sequence

For "the customer did not receive their report":

1. `GET /api/v1/reports/find-by-identifier?value=<any id>` — turn whatever the ticket contains into a ReportID.
2. `GET /api/v1/reports/{id}/delivery-configuration-diagnosis` — get a verdict before reading raw rows.
3. If the verdict is `healthy`, the configuration is fine, so check `GET /api/v1/reports/{id}/operations-workflow-status` to see whether production ever finished.
4. If the verdict is `issue` or `attention`, follow the `next_checks` paths in the response.
5. `GET /api/v1/reports/{id}/delivery-configuration-snapshot` when you want every delivery-related block in a single call instead of five.

---

## Generate SQL from a natural-language prompt

The Reports API also exposes a prompt-to-SQL bridge to the Human-to-SQL service.

### Endpoint

```http
POST /api/v1/generatesqlquery
Content-Type: application/json
X-API-Key: <your-secret>
```

This bridge calls the upstream Human-to-SQL raw SQL endpoint at `/api/v1/sql/query`, not the structured `/api/v1/sql/generate` route.

### Request body

The endpoint takes exactly one field:

```json
{
  "prompt": "Show the report status timeline for report 45036187"
}
```

This is intentionally limited to `prompt` only. Extra request fields are rejected with **422** to keep the consumer contract simple and explicit.

The upstream Human-to-SQL service handles the default routing internally with:

- `database`: `DB7222`
- `query_mode`: `auto`

### Response body

```json
{
  "ok": true,
  "query": "SELECT TOP (100) ...",
  "params": {
    "ReportID": 45036187
  },
  "mode": "template",
  "source": "human-to-sql",
  "routing": {
    "target": {
      "node": "db01",
      "database": "DB7222"
    }
  },
  "message": "SQL generated successfully."
}
```

This endpoint is useful when a caller already has a user-facing support prompt but does not know which database or query mode to pass. The backend keeps that logic hidden and defaults the upstream call to the static default catalog and automatic routing path.

### Template/generation routing

The Human-to-SQL service uses `auto` mode by default to protect the investment in reviewed templates: it attempts a matching template first and falls back to generated SQL only when no template matches. The response identifies the selected engine under `routing.engine` in the Human-to-SQL service response.

| Mode | Behaviour |
| --- | --- |
| `auto` | Matching template first; generated SQL as fallback |
| `templates_only` | Template required; Gemini is never called |
| `generated_only` | Templates are bypassed completely |

Set a mode per request with `"query_mode": "generated_only"` or `"query_mode": "templates_only"`. Rovo can also express it naturally:

- `prepare query and don't use templates; ...` selects `generated_only`
- `use templates only; ...` selects `templates_only`
- no instruction uses the `QUERY_PLANNER_MODE` feature flag (normally `auto`)

An explicit `query_mode` request field has priority. If the field contradicts a prompt directive, the request is rejected rather than silently choosing one. `POST /api/v1/query/generate-sql` always generates; `POST /api/v1/planner/prepare-query` always uses templates.

Three stages, and the model is only trusted in the middle one.

**1. Retrieve (RAG).** The database has 410 base tables and 2904 columns, far too many for one prompt, so `app/services/schema_index.py` narrows the question to at most `NL2SQL_MAX_TABLES`. Retrieval is BM25 over per-table documents built from table and column names, optionally fused by reciprocal rank with Gemini embeddings when a vector index exists. Three things make it work on real ticket wording:

- Identifiers are indexed camel-split *and* whole, and unknown question words are segmented against the schema vocabulary, so "substatus" reaches `SubStatus`.
- A synonym table maps support language onto internal names: DXF to file/delivery, SKU and billed to product and price, stuck to status.
- Real foreign keys (`foreign_keys.json`, 439 edges) supply a graph prior favouring tables joined to `Report`, and pull in lookup tables so codes come back as names.

Inspect a slice without calling the model via `GET /api/v1/planner/retrieve-schema?prompt=...`.

**2. Generate.** Gemini receives only the retrieved tables, their columns, the declared foreign keys as the sole permitted join paths, and the bound parameters. It returns structured JSON and may answer that the question is not answerable rather than guess.

**3. Validate.** Generated SQL is re-parsed with sqlglot and rejected unless it is a single capped read-only SELECT. The gate blocks writes, DDL, `SELECT INTO`, extra statements, tables outside the retrieved slice, columns absent from the pack, unbound parameters, a missing row cap, a cap above `NL2SQL_ROW_LIMIT`, and inlined literal identifiers. Rejection returns the offending SQL for inspection instead of running it.

Because retrieval spans the whole catalogue, this answers questions the old templates refused, such as billed SKUs (`ProductsOrdered`, `Product`, `Order`) or tax and invoices (`ReportTaxCollected`, `TaxType`).

### Schema pack

Stored at `schema/test/db01/DB7222/`, and only this pack is allowlisted, so request fields cannot reach an arbitrary path.

| File | Contents |
| --- | --- |
| `manifest.json` | Server, database, object and column counts |
| `tables.json` | Every column with type and nullability |
| `foreign_keys.json` | 439 declared foreign key edges |
| `views.json` | The 29 views, labelled as views in the prompt |
| `embeddings.json` | Optional vectors, written by `scripts/build_schema_embeddings.py` |

Refresh foreign keys with `scripts/import_foreign_keys.py` against a read-only `sys.foreign_key_columns` dump. Retrieval works on BM25 alone; building embeddings upgrades it to hybrid.

### Reviewed templates

`POST /api/v1/planner/prepare-query` is the strict template-only endpoint and needs no Gemini key. The template catalogue is intended to grow as common triage questions are reviewed and optimized. It currently maps a prompt to one of six SQL templates and returns `no_match` for unsupported or multi-intent prompts. It requires explicit `ReportID`, `OrderID`, `CustomerID`, `OrganizationNodeID`, or `ProfileID` labels and never guesses the type of an unlabeled number.

Delivery-rule planning includes report, profile, and organization-level candidates and labels each rule's scope. It does not yet calculate the final effective rule after all inheritance/override precedence; that interpretation remains a separate domain service.

### DB01 / DB02 metadata catalog

The planner now has a node registry under `catalog/db01/` and `catalog/db02/`. Cataloging and query activation are separate: all accessible databases can be captured, but generated SQL is allowed only for databases explicitly marked `query_enabled`.

The offline extractor uses Windows integrated authentication and only reads SQL Server `sys.*` catalogs. It captures schemas, tables and columns, constraints, FKs, indexes, views, procedures, functions, parameters, definitions, dependencies, triggers, sequences, extended properties, and statically discoverable first result sets. Procedures and functions are evidence only; the SQL gate still permits only `SELECT` / `WITH...SELECT`.

```powershell
# Complete one-time/local catalog tool setup
pip install -r catalog/requirements.txt

# Capture all accessible DB01 databases, or one database
python scripts/catalog_sqlserver.py --node db01 --continue-on-error
python scripts/catalog_sqlserver.py --node db01 --database DB7222

# DB02 starts with Operations, then the same command without --database
python scripts/catalog_sqlserver.py --node db02 --database Operations

# Publish sanitized planner packs; raw definitions remain git-ignored
python scripts/compile_catalog.py --node db01
python scripts/compile_catalog.py --node db02

# Rebuild reviewed templates as gold question-to-SQL examples
python scripts/compile_gold_examples.py
```

Raw captures live under `.catalog-captures/` and are never committed because module definitions may contain sensitive literals. The compiler redacts secrets, stores definition hashes/excerpts, records drift, and emits catalog packs under `schema/test/{node}/{database}/catalog/`.

Catalog API:

- `GET /api/v1/catalog/databases` — registry, activation, and compiled status
- `GET /api/v1/catalog/search?prompt=...&server=db01&database=DB7222`
- `GET /api/v1/catalog/databases/{server}/{database}`
- `GET /api/v1/catalog/databases/{server}/{database}/objects`

---

## Example calls

```powershell
$base = "https://reports-api-4aux.onrender.com"
$key = $env:API_SECRET_KEY   # do not paste secrets into git

Invoke-RestMethod "$base/api/v1/reports/44840403" -Headers @{ "X-API-Key" = $key }
Invoke-RestMethod "$base/api/v1/reports/find-by-identifier?value=99100234" -Headers @{ "X-API-Key" = $key }
Invoke-RestMethod "$base/api/v1/reports/50110200/operations-workflow-status" -Headers @{ "X-API-Key" = $key }
Invoke-RestMethod "$base/api/v1/reports/44840403/details-with-ordered-products-and-attributes" -Headers @{ "X-API-Key" = $key }
Invoke-RestMethod "$base/api/v1/operations-workflow-tasks/90050110200/task-states" -Headers @{ "X-API-Key" = $key }
Invoke-RestMethod -Method Post "$base/api/v1/triage/diagnose-delivery-configuration" `
  -Headers @{ "X-API-Key" = $key } `
  -ContentType "application/json" `
  -Body '{"lookup":"50110200","lookup_kind":"auto"}'
```

---

## Local run

```powershell
cd reports-api
copy .env.example .env
# Set API_SECRET_KEY in .env to a long random value
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 10000
.\.venv\Scripts\python.exe validate.py
```

`validate.py` runs the whole surface in-process with FastAPI's `TestClient`, so it needs no running server. It sets its own throwaway key before importing the app, then asserts that authentication rejects missing and wrong keys, every endpoint returns the expected status, retired paths return 404, and no path segment has slipped back to an abbreviation.

---

## Project layout

| Path | Role |
| --- | --- |
| `app/main.py` | Route definitions and the generated endpoint catalog |
| `app/repository.py` | All seed lookups, returning the standard envelope |
| `app/services/triage.py` | The delivery-configuration verdict logic |
| `app/services/schema_index.py` | Schema retrieval: BM25, synonyms, word segmentation, foreign-key graph |
| `app/services/nl2sql.py` | Prompt construction and the safety gate over generated SQL |
| `app/services/gemini.py` | Gemini REST client for generation and embeddings |
| `app/services/planner.py` | Legacy intent catalog, SQL templates, and read-only parser validation |
| `app/auth.py` | Constant-time API key comparison, header and bearer |
| `app/validation.py` | Identifier parsing and shared query and path constraints |
| `data/seed.json` | Reports, delivery rules, status timelines, workflow tasks |
| `data/seed_extra.json` | Customers, profiles, addresses, imagery, capabilities |
| `schema/test/db01/DB7222/` | Saved SQL schema pack used by the planner |
| `validate.py` | In-process check of every route |

---

## Render

- Repo: https://github.com/RahulGo8u/rovo-forge-poc  
- Root directory: `reports-api`  
- Build: `pip install -r requirements.txt`  
- Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`  
- Health: `/health` (no API key)  
- Secret: `API_SECRET_KEY` (Render dashboard / env, `sync: false` in `render.yaml`)  

In Swagger (`/docs`), click **Authorize** and paste the key into `X-API-Key`.  

Free instances may sleep when idle.

---

## Renamed paths (v0.5.0)

Every path segment is now a complete, self-describing phrase: no abbreviations (`org`, `meta`, `config`), no run-together words (`withproducts`, `taskstates`), and no bare nouns that send you to the docs. `validate.py` fails if an abbreviated segment reappears.

| Removed | Current |
| --- | --- |
| `GET .../report-status-history` | `GET .../current-status-with-history` and `GET .../status-change-history` |
| `GET .../task-status` | `GET .../operations-workflow-status` |
| `GET .../report-detail` | `GET .../details-with-address-and-measurements` |
| `GET .../report-detail-withproducts` | `GET .../details-with-ordered-products` |
| `GET .../report-detail-withproductsandattributes` | `GET .../details-with-ordered-products-and-attributes` |
| `GET .../task` | `GET .../operations-workflow-task` |
| `GET .../taskstates` | `GET .../operations-workflow-task-states` |
| `GET /api/v1/tasks/{id}` | `GET /api/v1/operations-workflow-tasks/{id}` |
| `GET /api/v1/tasks/{id}/taskstates` | `GET /api/v1/operations-workflow-tasks/{id}/task-states` |
| `GET .../delivery-snapshot` | `GET .../delivery-configuration-snapshot` |
| `GET .../delivery-rules` | `GET .../file-delivery-rules` |
| `GET .../delivery-diagnosis` | `GET .../delivery-configuration-diagnosis` |
| `GET .../customer-email-settings` | `GET .../customer-email-notification-settings` |
| `GET .../deliverable-verification` | `GET .../deliverable-verification-rules` |
| `GET .../product-capabilities` | `GET .../product-file-generation-capabilities` |
| `GET .../products` | `GET .../ordered-products` |
| `GET .../attributes` | `GET .../report-attributes` |
| `GET .../address` | `GET .../property-address` |
| `GET .../measurements` | `GET .../measurement-values` |
| `GET .../images` | `GET .../source-imagery` |
| `GET .../associations` | `GET .../profile-and-organization-associations` |
| `GET .../application-source` | `GET .../ordering-application-source` |
| `GET /api/v1/org-nodes/{id}` | `GET /api/v1/organization-nodes/{id}` |
| `GET /api/v1/profiles/{id}` | `GET /api/v1/recipient-profiles/{id}` |
| `GET /api/v1/reports/lookup-by-identifier` | `GET /api/v1/reports/find-by-identifier` |
| `GET /api/v1/reports/seed-examples` | `GET /api/v1/reports/example-reports-in-seed-data` |
| `GET /api/v1/reference/{name}` | `GET /api/v1/reference-data/{name}` |
| `GET /api/v1/meta/endpoints` | `GET /api/v1/metadata/endpoint-catalog` |
| `POST /api/v1/triage/diagnose-delivery-config` | `POST /api/v1/triage/diagnose-delivery-configuration` |
