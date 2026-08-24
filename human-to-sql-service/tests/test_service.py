from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.nl2sql import repair_literal_identifiers, validate_generated_sql
from app.services.nl2sql import generate_sql as generate_model_sql
from app.services.planner import load_schema_pack
from app.services.query_router import prepare_or_generate_query
from app.services.target_router import resolve_target


class TargetRoutingTests(unittest.TestCase):
    def test_report_language_routes_db01(self) -> None:
        result = resolve_target("show report order delivery status")
        self.assertTrue(result["ok"])
        self.assertEqual(result["target"].node, "db01")
        self.assertEqual(result["target"].database, "DB7222")
        self.assertGreater(result["routing"]["confidence"], 0)
        self.assertTrue(result["routing"]["evidence"])

    def test_operations_language_selects_db02_but_catalog_is_unavailable(self) -> None:
        result = resolve_target("show operations workflow task queue")
        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "catalog_unavailable")
        self.assertEqual(result["routing"]["node"], "db02")
        self.assertEqual(result["routing"]["database"], "Operations")

    def test_registered_explicit_hint_overrides_prompt(self) -> None:
        result = resolve_target("show workflow tasks", node="db01")
        self.assertTrue(result["ok"])
        self.assertEqual(result["target"].database, "DB7222")
        self.assertEqual(result["routing"]["source"], "explicit_hint")

    def test_conflicting_explicit_hints_fail_closed(self) -> None:
        result = resolve_target(
            "show reports", node="db01", database="Operations"
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "routing_error")

    def test_ambiguous_prompt_fails_closed(self) -> None:
        result = resolve_target("show useful information")
        self.assertFalse(result["ok"])
        self.assertEqual(result["mode"], "routing_error")


class TemplateTests(unittest.TestCase):
    def test_auto_uses_db7222_template_and_keeps_routing_layers_separate(self) -> None:
        result = prepare_or_generate_query(
            prompt="show report status timeline",
            report_id=45036187,
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "template")
        self.assertEqual(result["routing"]["target"]["database"], "DB7222")
        self.assertEqual(result["routing"]["engine"]["selected_engine"], "template")
        self.assertEqual(result["execution"], "not_run")

    def test_templates_only_generates_template(self) -> None:
        result = prepare_or_generate_query(
            prompt="show ordered report products",
            query_mode="templates_only",
            report_id=45036187,
        )
        self.assertTrue(result["ok"])
        self.assertIn("SELECT TOP", result["sql"])

    def test_prompt_identifier_is_inferred_without_request_id(self) -> None:
        result = prepare_or_generate_query(
            prompt="show report status for report 45036187",
            query_mode="templates_only",
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["mode"], "template")
        self.assertIn("@ReportID", result["sql"])


class GeminiGenerationTests(unittest.TestCase):
    @patch("app.services.nl2sql.gemini.generate_json")
    def test_one_deterministic_repair_attempt(self, generate_json) -> None:
        generate_json.side_effect = [
            (
                {
                    "answerable": True,
                    "sql": "SELECT r.ReportID FROM dbo.Report AS r",
                    "notes": "first draft",
                },
                {"model": "mock"},
            ),
            (
                {
                    "answerable": True,
                    "sql": "SELECT TOP (10) r.ReportID FROM dbo.Report AS r",
                    "notes": "repaired",
                },
                {"model": "mock"},
            ),
        ]
        result = generate_model_sql(prompt="show report summary")
        self.assertTrue(result["ok"])
        self.assertTrue(result["repaired"])
        self.assertEqual(generate_json.call_count, 2)
        self.assertEqual(
            [attempt["kind"] for attempt in result["model_attempts"]],
            ["generate", "repair"],
        )


class SqlGuardrailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        pack = load_schema_pack()
        cls.tables = pack["tables"]
        cls.report_columns = {"Report": cls.tables["Report"]}
        cls.relationships = [
            {
                "parent_table": "ReportStatus",
                "parent_column": "ReportID",
                "referenced_table": "Report",
                "referenced_column": "ReportID",
            }
        ]

    def validate(
        self,
        sql: str,
        *,
        tables: list[str] | None = None,
        relationships: list[dict[str, str]] | None = None,
        params: dict[str, int] | None = None,
    ) -> None:
        validate_generated_sql(
            sql,
            allowed_tables=tables or ["Report"],
            allowed_relationships=relationships or [],
            pack_tables=self.tables,
            params=params or {},
            row_limit=200,
        )

    def assert_rejected(self, sql: str, text: str, **kwargs: object) -> None:
        with self.assertRaisesRegex(ValueError, text):
            self.validate(sql, **kwargs)

    def test_rejects_write(self) -> None:
        self.assert_rejected("UPDATE dbo.Report SET City = 'x';", "Only SELECT")

    def test_rejects_hallucinated_column(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) r.NotARealColumn FROM dbo.Report AS r;",
            "do not exist",
        )

    def test_rejects_unreviewed_join(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) r.ReportID FROM dbo.Report AS r "
            "JOIN dbo.ReportStatus AS rs ON rs.StatusID = r.ReportID;",
            "unreviewed join",
            tables=["Report", "ReportStatus"],
            relationships=self.relationships,
        )

    def test_repair_rewrites_literal_identifier_to_parameter(self) -> None:
        sql = (
            "SELECT TOP (10) r.ReportID FROM dbo.Report AS r "
            "WHERE r.ReportID = 45036187 ORDER BY r.ReportID;"
        )
        repaired = repair_literal_identifiers(sql, {"ReportID": 45036187})
        self.assertIn("= @ReportID", repaired)
        self.assertNotIn("= 45036187", repaired)
        self.validate(
            repaired,
            tables=["Report"],
            params={"ReportID": 45036187},
        )

    def test_rejects_inline_long_identifier(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) r.ReportID FROM dbo.Report AS r "
            "WHERE r.ReportID = 45036187;",
            "inlines a literal identifier",
        )

    def test_rejects_missing_top(self) -> None:
        self.assert_rejected(
            "SELECT r.ReportID FROM dbo.Report AS r;",
            "row limit|TOP",
        )

    def test_rejects_cross_database_name(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) r.ReportID FROM DB7222.dbo.Report AS r;",
            "Cross-database",
        )

    def test_rejects_select_star(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) * FROM dbo.Report;",
            r"SELECT \*",
        )

    def test_rejects_unsupplied_parameter(self) -> None:
        self.assert_rejected(
            "SELECT TOP (10) r.ReportID FROM dbo.Report AS r "
            "WHERE r.ReportID = @ReportID;",
            "not supplied",
        )


class ApiContractTests(unittest.TestCase):
    client = TestClient(app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["execution"], "disabled")

    def test_root_ui_serves_prompt_form(self) -> None:
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Human to SQL", response.text)
        self.assertIn("Generate SQL", response.text)
        self.assertNotIn("Report ID", response.text)

    def test_generate_without_manual_report_id_uses_prompt_value(self) -> None:
        response = self.client.post(
            "/api/v1/sql/generate",
            json={
                "prompt": "show report status timeline for report 45036187",
                "environment": "test",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertIn("45036187", body["sql"])
        self.assertNotIn("@ReportID", body["sql"])

    def test_defaults_database_and_query_mode_when_not_provided(self) -> None:
        response = self.client.post(
            "/api/v1/sql/generate",
            json={
                "prompt": "show report status timeline for report 45036187",
                "environment": "test",
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["routing"]["target"]["database"], "DB7222")
        self.assertIn(body["mode"], ["auto", "template", "templates_only"])

    def test_catalog_endpoint_exposes_readiness(self) -> None:
        response = self.client.get("/api/v1/catalog/databases")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["data"]
        db7222 = next(
            row for row in rows
            if row["node"] == "db01" and row["database"] == "DB7222"
        )
        operations = next(
            row for row in rows
            if row["node"] == "db02" and row["database"] == "Operations"
        )
        self.assertTrue(db7222["compiled"])
        self.assertFalse(operations["compiled"])

    def test_generate_contract(self) -> None:
        response = self.client.post(
            "/api/v1/sql/generate",
            json={
                "prompt": "show report status timeline",
                "report_id": 45036187,
            },
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["execution"], "not_run")
        self.assertIn("target", body["routing"])
        self.assertIn("engine", body["routing"])

    def test_sql_only_endpoint_returns_raw_sql(self) -> None:
        response = self.client.post(
            "/api/v1/sql/query",
            json={
                "prompt": "show report status timeline for report 45036187",
                "environment": "test",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("SELECT", response.text)
        self.assertNotIn("\"sql\"", response.text)
        self.assertNotIn("\"ok\"", response.text)
        self.assertIn("45036187", response.text)
        self.assertNotIn("@ReportID", response.text)

    def test_omitted_database_uses_semantic_target_when_present(self) -> None:
        response = self.client.post(
            "/api/v1/sql/generate",
            json={"prompt": "show operations workflow queue tasks"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            response.json()["routing"]["target"]["database"],
            ["DB7222", "Operations"],
        )

    def test_conflicting_node_aliases_are_invalid(self) -> None:
        response = self.client.post(
            "/api/v1/sql/generate",
            json={
                "prompt": "show reports",
                "node": "db01",
                "server": "db02",
            },
        )
        self.assertEqual(response.status_code, 422)


if __name__ == "__main__":
    unittest.main()
