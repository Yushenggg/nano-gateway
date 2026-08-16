import json
import asyncio
from html import escape
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from nanogateway.storage import Storage
from nanogateway.config import load_config
from nanogateway.ui.renderer import render


def create_ui_app(db_path: str | None = None) -> FastAPI:
    if db_path is None:
        try:
            settings = load_config()
            db_path = settings.db_path
        except Exception:
            db_path = ".nanogateway/data.db"

    storage = Storage(db_path)
    app = FastAPI()
    seen_ids: set[str] = set()

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return render(
            "shell.html",
            page_content="",
            initial_page="/ui/page/traces",
            live_cls="", sessions_cls="", traces_cls="active", config_cls="",
        )

    @app.get("/ui/page/traces", response_class=HTMLResponse)
    async def page_traces():
        return f"""<div class="header">
            <h1>Traces</h1>
        </div>
        <div id="stats"
             hx-get="/ui/stats"
             hx-trigger="load"
             hx-swap="innerHTML">
        </div>
        <div class="panel">
            <div class="panel-header"><span class="panel-title">Recent Requests</span></div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Model</th>
                        <th>Tokens</th>
                        <th>TTFT</th>
                        <th>User</th>
                        <th>Status</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody id="trace-body"
                      hx-get="/ui/traces"
                      hx-trigger="load"
                      hx-swap="innerHTML">
                </tbody>
            </table>
        </div>"""

    @app.get("/ui/page/live", response_class=HTMLResponse)
    async def page_live():
        return f"""<div class="header">
            <h1>Live</h1>
            <div class="live-badge"><div class="live-dot"></div> LIVE</div>
        </div>
        <div class="panel">
            <div class="panel-header"><span class="panel-title">Recent Requests</span></div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Model</th>
                        <th>Tokens</th>
                        <th>TTFT</th>
                        <th>User</th>
                        <th>Status</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody id="live-trace-body"
                      hx-get="/ui/traces"
                      hx-trigger="load"
                      hx-swap="innerHTML">
                </tbody>
            </table>
            <div hx-ext="sse" sse-connect="/ui/stream" sse-swap="traces"
                 hx-target="#live-trace-body" hx-swap="afterbegin">
            </div>
        </div>"""

    @app.get("/ui/page/sessions", response_class=HTMLResponse)
    async def page_sessions():
        return """<div class="header"><h1>Sessions</h1></div>
        <div class="panel">
            <div class="panel-header"><span class="panel-title">Conversations</span></div>
            <div class="empty">Sessions view is only available in the NanoGateway proxy dashboard.</div>
        </div>"""

    @app.get("/ui/page/config", response_class=HTMLResponse)
    async def page_config():
        return f"""<div class="header"><h1>Config</h1></div>
        <div class="panel">
            <div class="panel-header"><span class="panel-title">Current Settings</span></div>
            <div class="config-list">
                <div class="config-row"><span class="config-key">db_path</span><code>{escape(str(storage.db_path))}</code></div>
            </div>
        </div>"""

    @app.get("/ui/stats", response_class=HTMLResponse)
    async def stats():
        all_traces = storage.get_traces(limit=1000)
        total = len(all_traces)
        models = len(set(t["model"] for t in all_traces if t["model"]))
        users = len(set(t["user_id"] for t in all_traces if t["user_id"]))
        avg = sum(t["latency_ms"] or 0 for t in all_traces) / total if total else 0
        return f"""
        <div class="stats">
            <div class="stat"><div class="stat-value">{total}</div><div class="stat-label">Traces</div></div>
            <div class="stat"><div class="stat-value">{models}</div><div class="stat-label">Models</div></div>
            <div class="stat"><div class="stat-value">{users}</div><div class="stat-label">Users</div></div>
            <div class="stat"><div class="stat-value">{avg:.0f}ms</div><div class="stat-label">Avg Latency</div></div>
        </div>"""

    @app.get("/ui/traces", response_class=HTMLResponse)
    async def traces():
        rows = storage.get_traces(limit=50)
        if not rows:
            return '<tr><td colspan="7" class="empty">No traces yet</td></tr>'
        html = ""
        for r in rows:
            status_cls = "status-ok" if r["status_code"] == 200 else "status-err"
            html += _trace_row(r, status_cls)
        return html

    @app.get("/ui/traces/{trace_id}", response_class=HTMLResponse)
    async def trace_detail(trace_id: str):
        trace = storage.get_trace(trace_id)
        if not trace:
            return '<div class="empty">Trace not found</div>'

        req = _pretty_json(trace.get("request_json"))
        resp = _pretty_json(trace.get("response_json"))
        return f"""
        <div class="expand-content">
            <div class="detail-grid">
                <div class="detail-block">
                    <div class="detail-label">Request</div>
                    <pre>{escape(req)}</pre>
                </div>
                <div class="detail-block">
                    <div class="detail-label">Response</div>
                    <pre>{escape(resp)}</pre>
                </div>
            </div>
        </div>"""

    @app.get("/ui/stream")
    async def stream():
        async def event_generator():
            for r in storage.get_traces(limit=50):
                seen_ids.add(r["id"])
            while True:
                traces = storage.get_traces(limit=50)
                new_traces = [t for t in traces if t["id"] not in seen_ids]
                for t in new_traces:
                    seen_ids.add(t["id"])
                    status_cls = "status-ok" if t["status_code"] == 200 else "status-err"
                    row = _trace_row(t, status_cls)
                    payload = row.replace("\n", "\ndata: ")
                    yield f"event: traces\ndata: {payload}\n\n"
                await asyncio.sleep(1)

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


def _trace_row(r: dict, status_cls: str) -> str:
    return f"""
    <tr class="new-row expand-row" onclick="toggleExpand('{r['id']}')">
        <td><code>{r['id'][:16]}</code></td>
        <td><span class="model">{escape(str(r['model'] or '-'))}</span></td>
        <td>{r['input_tokens']}→{r['output_tokens']}</td>
        <td>{f"{r['latency_ms']:.0f}ms" if r['latency_ms'] else '-'}</td>
        <td>{escape(str(r['user_id'] or '-'))}</td>
        <td><span class="{status_cls}">{r['status_code']}</span></td>
        <td>{str(r['timestamp'])[11:19]}</td>
    </tr>
    <tr id="expand-{r['id']}" style="display:none">
        <td colspan="7" class="expand-cell" id="detail-{r['id']}"></td>
    </tr>"""


def _pretty_json(raw: str | None) -> str:
    if not raw:
        return "N/A"
    try:
        return json.dumps(json.loads(raw), indent=2, sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        return str(raw)
