from __future__ import annotations

from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse

from .config import settings
from .models import SqlGenerateRequest
from .services.catalog import list_catalog_databases
from .services.query_router import prepare_or_generate_query

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Generates catalog-validated T-SQL. This service never executes SQL.",
)

UI_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Human to SQL</title>
    <style>
        :root {
            --bg: #eef4ff;
            --card: #ffffff;
            --card-soft: #f6f9ff;
            --text: #1f2937;
            --muted: #5e6b85;
            --line: #dfe7f6;
            --primary: #2957d6;
            --primary-strong: #173ebe;
            --primary-soft: #e9f0ff;
            --dark: #0f172a;
            --success: #0d9f6e;
            --danger: #c62828;
            --shadow: 0 18px 45px rgba(37, 62, 126, 0.12);
        }

        * { box-sizing: border-box; }

        body {
            margin: 0;
            min-height: 100vh;
            font-family: "Segoe UI", Arial, sans-serif;
            background: radial-gradient(circle at top, #f8fbff 0%, #edf3ff 45%, #e7efff 100%);
            color: var(--text);
            padding: 32px 20px;
        }

        .container {
            width: min(1200px, 100%);
            margin: 0 auto;
            background: rgba(255, 255, 255, 0.7);
            border: 1px solid rgba(196, 210, 241, 0.9);
            border-radius: 22px;
            box-shadow: var(--shadow);
            backdrop-filter: blur(8px);
            overflow: hidden;
        }

        .header {
            padding: 26px 28px 20px;
            background: linear-gradient(135deg, #f9fbff, #edf3ff);
            border-bottom: 1px solid var(--line);
        }

        .eyebrow {
            display: inline-block;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: var(--primary);
            background: var(--primary-soft);
            border-radius: 999px;
            padding: 7px 10px;
            margin-bottom: 12px;
        }

        .header h1 {
            margin: 0;
            font-size: clamp(2rem, 3vw, 3rem);
            line-height: 1.1;
            color: var(--dark);
        }

        .header p {
            margin: 10px 0 0;
            color: var(--muted);
            font-size: 1rem;
        }

        .content {
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 22px;
            padding: 28px;
        }

        .panel {
            background: var(--card);
            border: 1px solid var(--line);
            border-radius: 18px;
            box-shadow: 0 5px 18px rgba(18, 38, 76, 0.04);
            padding: 20px;
        }

        .panel h2 {
            margin: 0 0 18px;
            font-size: 1.15rem;
            color: var(--dark);
        }

        label {
            display: block;
            font-weight: 600;
            font-size: 0.92rem;
            color: var(--text);
            margin-bottom: 8px;
        }

        textarea,
        input,
        select,
        button {
            width: 100%;
            font: inherit;
        }

        textarea,
        input,
        select {
            border: 1px solid var(--line);
            background: #fbfcff;
            border-radius: 12px;
            color: var(--text);
            padding: 12px 14px;
            transition: border-color 0.2s ease, box-shadow 0.2s ease;
        }

        textarea:focus,
        input:focus,
        select:focus {
            outline: none;
            border-color: rgba(41, 87, 214, 0.6);
            box-shadow: 0 0 0 4px rgba(41, 87, 214, 0.09);
        }

        textarea {
            min-height: 180px;
            resize: vertical;
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 16px;
            margin-top: 16px;
        }

        .primary-button {
            margin-top: 18px;
            padding: 13px 18px;
            border: none;
            border-radius: 12px;
            background: linear-gradient(135deg, var(--primary), var(--primary-strong));
            color: white;
            font-weight: 700;
            cursor: pointer;
            box-shadow: 0 10px 20px rgba(41, 87, 214, 0.2);
            transition: transform 0.15s ease, box-shadow 0.15s ease;
        }

        .primary-button:hover {
            transform: translateY(-1px);
            box-shadow: 0 14px 22px rgba(41, 87, 214, 0.24);
        }

        .primary-button:disabled {
            opacity: 0.7;
            cursor: wait;
            transform: none;
        }

        .status {
            margin-top: 14px;
            min-height: 22px;
            color: var(--muted);
            font-size: 0.92rem;
        }

        .status.error { color: var(--danger); }
        .status.success { color: var(--success); }

        .result-box {
            min-height: 320px;
            background: linear-gradient(180deg, #0f172a, #111827);
            border: 1px solid #1f2d46;
            border-radius: 16px;
            padding: 18px 16px;
            white-space: pre-wrap;
            font-family: "Consolas", "Courier New", monospace;
            line-height: 1.6;
            color: #e2ebff;
            overflow: auto;
        }

        .meta {
            margin-top: 14px;
            color: var(--muted);
            font-size: 0.9rem;
        }

        @media (max-width: 820px) {
            .content { grid-template-columns: 1fr; }
            .row { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="eyebrow">SQL assistant</div>
            <h1>Human to SQL</h1>
            <p>Turn a natural-language prompt into a validated SQL query.</p>
        </div>
        <div class="content">
            <div class="panel">
                <h2>Ask for SQL</h2>
                <form id="sql-form">
                    <label for="prompt">Prompt</label>
                    <textarea id="prompt" placeholder="Example: Show the report status timeline for report 45036187">Show the report status timeline</textarea>

                    <div class="row">
                        <div>
                            <label for="node">Node</label>
                            <select id="node">
                                <option value="">Auto</option>
                                <option value="db01">db01</option>
                                <option value="db02">db02</option>
                            </select>
                        </div>
                        <div>
                            <label for="database">Database</label>
                            <input id="database" type="text" value="DB7222" placeholder="DB7222" />
                        </div>
                    </div>

                    <div class="row">
                        <div>
                            <label for="queryMode">Query mode</label>
                            <select id="queryMode">
                                <option value="auto">auto</option>
                                <option value="templates_only">templates_only</option>
                                <option value="generated_only">generated_only</option>
                            </select>
                        </div>
                    </div>

                    <button id="submitBtn" class="primary-button" type="submit">Generate SQL</button>
                    <div id="status" class="status" aria-live="polite"></div>
                </form>
            </div>

            <div class="panel">
                <h2>Generated SQL</h2>
                <div id="result" class="result-box">Your SQL will appear here.</div>
                <div id="meta" class="meta"></div>
            </div>
        </div>
    </div>

    <script>
        const form = document.getElementById('sql-form');
        const statusEl = document.getElementById('status');
        const resultEl = document.getElementById('result');
        const metaEl = document.getElementById('meta');
        const submitBtn = document.getElementById('submitBtn');

        function renderSqlPreview(sql, params) {
            if (!sql) return 'No SQL returned.';
            if (!params || Object.keys(params).length === 0) return sql;

            let rendered = sql;
            for (const [key, value] of Object.entries(params)) {
                const placeholder = `@${key}`;
                const formatted = typeof value === 'string' ? `'${value.replace(/'/g, "''")}'` : value;
                rendered = rendered.split(placeholder).join(String(formatted));
            }
            return rendered;
        }

        form.addEventListener('submit', async (event) => {
            event.preventDefault();
            const prompt = document.getElementById('prompt').value.trim();
            if (!prompt) {
                statusEl.textContent = 'Please enter a prompt.';
                statusEl.className = 'status error';
                return;
            }

            const payload = {
                prompt,
                environment: 'test',
                node: document.getElementById('node').value || undefined,
                database: document.getElementById('database').value || undefined,
                query_mode: document.getElementById('queryMode').value,
            };

            submitBtn.disabled = true;
            submitBtn.textContent = 'Generating...';
            statusEl.textContent = 'Sending request...';
            statusEl.className = 'status';
            resultEl.textContent = 'Loading...';
            metaEl.textContent = '';

            try {
                const response = await fetch('/api/v1/sql/generate', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();

                if (!response.ok) {
                    throw new Error(data.detail ? JSON.stringify(data.detail) : 'Request failed');
                }

                const renderedSql = renderSqlPreview(data.sql, data.params);
                resultEl.textContent = renderedSql;
                const modeText = data.mode ? `Mode: ${data.mode}` : '';
                const routeText = data.routing ? `Target: ${data.routing.target.node}/${data.routing.target.database}` : '';
                const paramsText = data.params && Object.keys(data.params).length
                    ? `Bound params: ${JSON.stringify(data.params)}`
                    : '';
                metaEl.textContent = [modeText, routeText, paramsText].filter(Boolean).join(' | ');
                statusEl.textContent = 'SQL generated successfully.';
                statusEl.className = 'status success';
            } catch (error) {
                resultEl.textContent = 'Generation failed.';
                statusEl.textContent = error.message || 'A request error occurred.';
                statusEl.className = 'status error';
            } finally {
                submitBtn.disabled = false;
                submitBtn.textContent = 'Generate SQL';
            }
        });
    </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def ui() -> str:
    return UI_HTML


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "execution": "disabled",
    }


@app.get(f"{settings.api_prefix}/catalog/databases")
async def catalog_databases() -> dict[str, Any]:
    databases = list_catalog_databases()
    return {
        "ok": True,
        "row_count": len(databases),
        "data": databases,
        "note": "Registered, query-enabled, and compiled are independent readiness signals.",
    }


@app.post(f"{settings.api_prefix}/sql/generate")
async def generate_sql(payload: SqlGenerateRequest) -> dict[str, Any]:
    result = prepare_or_generate_query(
        prompt=payload.prompt,
        query_mode=payload.query_mode,
        report_id=payload.report_id,
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        organization_node_id=payload.organization_node_id,
        profile_id=payload.profile_id,
        environment=payload.environment,
        server=payload.node_hint,
        database=payload.database,
    )
    if not result.get("ok"):
        status = (
            503
            if result.get("mode")
            in {"catalog_unavailable", "not_configured", "model_error"}
            else 422
        )
        raise HTTPException(status_code=status, detail=result)
    result["execution"] = "not_run"
    return result


@app.post(f"{settings.api_prefix}/sql/query", response_class=PlainTextResponse)
async def generate_sql_only(payload: SqlGenerateRequest) -> str:
    result = prepare_or_generate_query(
        prompt=payload.prompt,
        query_mode=payload.query_mode,
        report_id=payload.report_id,
        order_id=payload.order_id,
        customer_id=payload.customer_id,
        organization_node_id=payload.organization_node_id,
        profile_id=payload.profile_id,
        environment=payload.environment,
        server=payload.node_hint,
        database=payload.database,
    )
    if not result.get("ok"):
        status = (
            503
            if result.get("mode")
            in {"catalog_unavailable", "not_configured", "model_error"}
            else 422
        )
        raise HTTPException(status_code=status, detail=result)
    return result["sql"]
