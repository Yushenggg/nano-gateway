import json
import time
import asyncio
from html import escape
from uuid import uuid4
from pathlib import Path
from urllib.parse import quote
import httpx
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, JSONResponse, HTMLResponse, RedirectResponse
from nanogateway.config import load_config, Settings
from nanogateway.storage import Storage
from nanogateway.guardrails import GuardrailRegistry
from nanogateway.guardrails.injection import InjectionGuardrail
from nanogateway.ui.renderer import render


def create_proxy_app(config_path: str | None = None) -> FastAPI:
    settings = load_config(config_path)
    storage = Storage(settings.db_path)
    guardrails = _build_guardrails(settings)
    http_client = httpx.AsyncClient(base_url=settings.url, timeout=120.0)

    app = FastAPI(title="NanoGateway Proxy")

    # ── API Routes ──

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request):
        body = await request.json()
        messages = body.get("messages", [])
        model = body.get("model")
        stream = body.get("stream", False)
        user = body.get("user")
        session_id = _extract_session_id(request, body)

        from nanogateway.models import ChatMessage
        chat_messages = [ChatMessage(**m) for m in messages]
        result = guardrails.check_all(chat_messages)

        if not result.passed:
            block_msg = settings.guardrails.injection.block_message
            return JSONResponse(
                content={
                    "id": f"nanogw-blocked-{uuid4().hex[:8]}",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{"index": 0, "message": {"role": "assistant", "content": block_msg}, "finish_reason": "content_filter"}],
                    "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
                }
            )

        start_time = time.monotonic()
        upstream_headers = _upstream_headers(request)

        body.pop("session_id", None)
        body.pop("thread_id", None)
        body.pop("conversation_id", None)

        if stream:
            body["stream"] = True
            provider_request = http_client.build_request("POST", "/chat/completions", json=body, headers=upstream_headers)
            provider_response = await http_client.send(provider_request, stream=True)

            async def stream_generator():
                input_tokens = 0
                output_tokens = 0
                content_parts: list[str] = []
                first_token_at: float | None = None
                async for raw_line in provider_response.aiter_lines():
                    if not raw_line:
                        yield "\n"
                        continue
                    yield raw_line + "\n"
                    if raw_line.startswith("data: ") and raw_line.strip() != "data: [DONE]":
                        try:
                            chunk = json.loads(raw_line[6:])
                            usage = chunk.get("usage")
                            if usage:
                                input_tokens = usage.get("prompt_tokens", input_tokens)
                                output_tokens = usage.get("completion_tokens", output_tokens)
                            for choice in chunk.get("choices", []):
                                delta = choice.get("delta") or {}
                                content = delta.get("content")
                                if content:
                                    if first_token_at is None:
                                        first_token_at = time.monotonic()
                                    content_parts.append(content)
                        except json.JSONDecodeError:
                            pass
                await provider_response.aclose()
                ttft_ms = (first_token_at - start_time) * 1000 if first_token_at else (time.monotonic() - start_time) * 1000
                response_snapshot = {
                    "id": f"nanogw-stream-{uuid4().hex[:8]}",
                    "object": "chat.completion",
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": "".join(content_parts)},
                        "finish_reason": "stop",
                    }],
                    "usage": {
                        "prompt_tokens": input_tokens,
                        "completion_tokens": output_tokens,
                        "total_tokens": input_tokens + output_tokens,
                    },
                }
                storage.log_span(model=model, input_tokens=input_tokens, output_tokens=output_tokens,
                    latency_ms=ttft_ms, status_code=200, user_id=user,
                    session_id=session_id, request_json=json.dumps(body),
                    response_json=json.dumps(response_snapshot))

            return StreamingResponse(stream_generator(), media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        else:
            response = await http_client.post("/chat/completions", json=body, headers=upstream_headers)
            data = response.json()
            storage.log_span(model=model,
                input_tokens=data.get("usage", {}).get("prompt_tokens", 0),
                output_tokens=data.get("usage", {}).get("completion_tokens", 0),
                latency_ms=(time.monotonic() - start_time) * 1000, status_code=response.status_code,
                user_id=user, session_id=session_id,
                request_json=json.dumps(body), response_json=json.dumps(data))
            return JSONResponse(content=data, status_code=response.status_code)

    @app.get("/v1/models")
    async def list_models(request: Request):
        response = await http_client.get("/models", headers=_upstream_headers(request))
        return JSONResponse(content=response.json(), status_code=response.status_code)

    # ── UI Routes ──

    PAGE_SIZE = 50
    PAGE_SIZES = (10, 25, 50, 100)
    LIVE_INITIAL = 10

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return RedirectResponse("/live")

    @app.get("/live", response_class=HTMLResponse)
    async def live_route():
        return _render_shell("live", await live_page())

    @app.get("/sessions", response_class=HTMLResponse)
    async def sessions_route():
        return _render_shell("sessions", await sessions_page())

    @app.get("/traces", response_class=HTMLResponse)
    async def traces_route(session: str = ""):
        query = f"?session={quote(session)}" if session else ""
        return _render_shell("traces", await traces_page(session), query=query)

    @app.get("/config", response_class=HTMLResponse)
    async def config_route():
        return _render_shell("config", await config_page())

    @app.get("/ui/page/live", response_class=HTMLResponse)
    async def live_page():
        return f"""<div class="header">
            <h1>Live</h1>
            <div class="live-badge"><div class="live-dot"></div> LIVE</div>
        </div>
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Recent Requests</span>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Model</th>
                        <th>Session</th>
                        <th>Tokens</th>
                        <th>TTFT</th>
                        <th>User</th>
                        <th>Status</th>
                        <th>Time</th>
                    </tr>
                </thead>
                <tbody id="live-trace-body"
                      hx-get="/ui/traces?view=live&limit={LIVE_INITIAL}"
                      hx-trigger="load"
                      hx-swap="innerHTML">
                </tbody>
            </table>
            <div hx-ext="sse" sse-connect="/ui/stream" sse-swap="traces"
                 hx-target="#live-trace-body" hx-swap="afterbegin">
            </div>
        </div>"""

    @app.get("/ui/page/sessions", response_class=HTMLResponse)
    async def sessions_page():
        return f"""<div class="header">
            <h1>Sessions</h1>
        </div>
        <div id="stats"
             hx-get="/ui/stats"
             hx-trigger="load"
             hx-swap="innerHTML">
        </div>
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Conversations</span>
                <div class="filters">
                    <input class="filter-input" type="text" name="q" placeholder="filter sessions…"
                           hx-get="/ui/sessions" hx-target="#sessions-list" hx-trigger="keyup changed delay:400ms"
                           hx-vals='js:{{...sessionsVals(0)}}'>
                    {_page_size_select("sessions", "/ui/sessions", "#sessions-list")}
                </div>
            </div>
            <div id="sessions-list"
                 hx-get="/ui/sessions"
                 hx-trigger="load"
                 hx-vals='js:{{...sessionsVals(0)}}'
                 hx-swap="innerHTML">
            </div>
            <div id="sessions-pagination"></div>
            <div id="session-detail"></div>
        </div>"""

    @app.get("/ui/page/traces", response_class=HTMLResponse)
    async def traces_page(session: str = ""):
        filter_html = ""
        if session:
            filter_html = f"""<span class="filter-note">
                session: {escape(session[:16])}
                <button onclick="goToTraces('')">clear</button>
            </span>"""
        return f"""<div class="header">
            <h1>Traces</h1>
            <div style="display:flex; gap:12px; align-items:center;">
                {filter_html}
            </div>
        </div>
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Recent Requests</span>
                <div class="filters">
                    <input class="filter-input" type="text" name="f_session" placeholder="session…"
                           hx-get="/ui/traces" hx-target="#trace-body" hx-trigger="keyup changed delay:400ms"
                           hx-vals='js:{{...traceVals(0)}}'>
                    <input class="filter-input" type="text" name="f_model" placeholder="model…"
                           hx-get="/ui/traces" hx-target="#trace-body" hx-trigger="keyup changed delay:400ms"
                           hx-vals='js:{{...traceVals(0)}}'>
                    <input class="filter-input" type="text" name="f_user" placeholder="user…"
                           hx-get="/ui/traces" hx-target="#trace-body" hx-trigger="keyup changed delay:400ms"
                           hx-vals='js:{{...traceVals(0)}}'>
                    {_page_size_select("traces", "/ui/traces", "#trace-body")}
                </div>
            </div>
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Model</th>
                        <th>Session</th>
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
                      hx-vals='js:{{...traceVals(0)}}'
                      hx-swap="innerHTML">
                </tbody>
            </table>
            <div id="trace-pagination"></div>
        </div>"""

    @app.get("/ui/page/config", response_class=HTMLResponse)
    async def config_page():
        g = settings.guardrails.injection
        guardrail_status = "enabled" if g.enabled else "disabled"
        rows = f"""
            <div class="config-row"><span class="config-key">upstream url</span><code>{escape(settings.url)}</code></div>
            <div class="config-row"><span class="config-key">db_path</span><code>{escape(settings.db_path)}</code></div>
            <div class="config-row"><span class="config-key">injection guardrail</span><code>{guardrail_status}</code></div>"""
        if g.enabled:
            rows += f"""
            <div class="config-row"><span class="config-key">injection action</span><code>{escape(g.action)}</code></div>
            <div class="config-row"><span class="config-key">block message</span><code>{escape(g.block_message)}</code></div>"""
        return f"""<div class="header">
            <h1>Config</h1>
        </div>
        <div class="panel">
            <div class="panel-header">
                <span class="panel-title">Current Settings</span>
            </div>
            <div class="config-list">{rows}
            </div>
        </div>"""

    @app.get("/ui/stats", response_class=HTMLResponse)
    async def stats():
        s = storage.get_stats()
        return f"""<div class="stats">
            <div class="stat"><div class="stat-value">{s['total']}</div><div class="stat-label">Traces</div></div>
            <div class="stat"><div class="stat-value">{s['models']}</div><div class="stat-label">Models</div></div>
            <div class="stat"><div class="stat-value">{s['users']}</div><div class="stat-label">Users</div></div>
            <div class="stat"><div class="stat-value">{s['sessions']}</div><div class="stat-label">Sessions</div></div>
            <div class="stat"><div class="stat-value">{s['avg_latency']:.0f}ms</div><div class="stat-label">Avg TTFT</div></div>
        </div>"""

    @app.get("/ui/traces", response_class=HTMLResponse)
    async def traces(
        session: str = "", view: str = "",
        f_session: str = "", f_model: str = "", f_user: str = "",
        page: int = 0, page_size: int = 0, limit: int = 0,
    ):
        filters = dict(
            session_id=session or None,
            session_like=f_session.strip() or None,
            model_like=f_model.strip() or None,
            user_like=f_user.strip() or None,
        )
        if view == "live":
            n = min(max(limit, 1), 500) if limit > 0 else LIVE_INITIAL
            rows = storage.get_traces(limit=n, **filters)
            if not rows:
                return '<tr><td colspan="8" class="empty">No traces yet</td></tr>'
            return "".join(_trace_row(r) for r in rows)

        page = max(page, 0)
        page_size = page_size if page_size in PAGE_SIZES else PAGE_SIZE
        rows = storage.get_traces(limit=page_size + 1, offset=page * page_size, **filters)
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        total = storage.count_traces(**filters)
        pag = _pagination(
            container_id="session-trace-pagination" if view == "detail" else "trace-pagination",
            list_id="trace-body",
            endpoint="/ui/traces",
            page=page,
            total=total,
            has_prev=page > 0,
            has_next=has_more,
            url_params=f"session={quote(session)}&view={view}" if view == "detail" else f"view={view}",
            vals_template='js:{{...sessionsVals({p})}}' if view == "detail" else 'js:{{...traceVals({p})}}',
        )
        if not rows:
            cols = 7 if view == "detail" else 8
            return f'<tr><td colspan="{cols}" class="empty">No traces yet</td></tr>' + pag
        return "".join(_trace_row(r, show_session=view != "detail") for r in rows) + pag

    @app.get("/ui/sessions", response_class=HTMLResponse)
    async def sessions(q: str = "", page: int = 0, page_size: int = 0):
        page = max(page, 0)
        page_size = page_size if page_size in PAGE_SIZES else PAGE_SIZE
        query = q.strip() or None
        rows = storage.get_sessions(limit=page_size + 1, offset=page * page_size, query=query)
        has_more = len(rows) > page_size
        rows = rows[:page_size]
        total = storage.count_sessions(query=query)
        pag = _pagination(
            container_id="sessions-pagination",
            list_id="sessions-list",
            endpoint="/ui/sessions",
            page=page,
            total=total,
            has_prev=page > 0,
            has_next=has_more,
            url_params=f"q={quote(query)}" if query else "",
            vals_template="js:{{...sessionsVals({p})}}",
        )
        if not rows:
            return '<div class="sessions-empty">No sessions yet. Start a conversation to see it here.</div>' + pag
        return "".join(_session_row(r) for r in rows) + pag

    @app.get("/ui/sessions/{session_id}/traces", response_class=HTMLResponse)
    async def session_traces(session_id: str):
        if storage.count_traces(session_id=session_id) == 0:
            return f"""<div class="session-detail">
                <div class="detail-head">
                    <span class="panel-title">{escape(session_id[:24])}</span>
                    <button class="link-btn" onclick="goToTraces('{escape(session_id)}')">Open in Traces →</button>
                </div>
                <div class="empty">No traces in this session</div>
            </div>"""
        return f"""<div class="session-detail">
            <div class="detail-head">
                <span class="panel-title">{escape(session_id[:24])}</span>
                <button class="link-btn" onclick="goToTraces('{escape(session_id)}')">Open in Traces →</button>
            </div>
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
                <tbody id="trace-body" hx-get="/ui/traces?session={quote(session_id)}&view=detail"
                       hx-trigger="load" hx-vals='js:{{...sessionsVals(0)}}' hx-swap="innerHTML">
                </tbody>
            </table>
            <div id="session-trace-pagination"></div>
        </div>"""

    @app.get("/ui/traces/{trace_id}", response_class=HTMLResponse)
    async def trace_detail(trace_id: str):
        trace = storage.get_trace(trace_id)
        if not trace:
            return '<div class="empty">Trace not found</div>'
        req = _pretty_json(trace.get("request_json"))
        resp = _pretty_json(trace.get("response_json"))
        return f"""<div class="expand-content"><div class="detail-grid">
            <div class="detail-block"><div class="detail-label">Request</div><pre>{escape(req)}</pre></div>
            <div class="detail-block"><div class="detail-label">Response</div><pre>{escape(resp)}</pre></div>
        </div></div>"""

    @app.get("/ui/stream")
    async def stream(session: str = ""):
        async def event_generator():
            seen: set[str] = set()
            for r in storage.get_traces(limit=50, session_id=session or None):
                seen.add(r["id"])
            while True:
                traces = storage.get_traces(limit=50, session_id=session or None)
                for t in traces:
                    if t["id"] not in seen:
                        seen.add(t["id"])
                        payload = _trace_row(t).replace("\n", "\ndata: ")
                        yield f"event: traces\ndata: {payload}\n\n"
                await asyncio.sleep(1)
        return StreamingResponse(event_generator(), media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return app


def _extract_session_id(request: Request, body: dict) -> str | None:
    for header in ("x-session-id", "x-thread-id", "x-conversation-id"):
        value = request.headers.get(header)
        if value:
            return value
    metadata = body.get("metadata")
    if isinstance(metadata, dict):
        for key in ("session_id", "thread_id", "conversation_id"):
            value = metadata.get(key)
            if value:
                return str(value)
    for key in ("session_id", "thread_id", "conversation_id"):
        value = body.get(key)
        if value:
            return str(value)
    return None


def _upstream_headers(request: Request) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    auth = request.headers.get("authorization")
    if auth:
        headers["Authorization"] = auth
    return headers


def _trace_row(r: dict, show_session: bool = True) -> str:
    status_cls = "status-ok" if r["status_code"] == 200 else "status-err"
    session_cell = ""
    if show_session:
        session = r.get("session_id")
        session_cell = (
            f'<td><button class="session-chip" data-session="{escape(str(session))}" '
            f'onclick="event.stopPropagation(); goToTraces(\'{escape(str(session))}\')">{escape(str(session)[:16])}</button></td>'
            if session
            else "<td>-</td>"
        )
    return f"""<tr class="new-row expand-row" onclick="toggleExpand('{r['id']}')">
        <td><code>{r['id'][:16]}</code></td>
        <td><span class="model">{escape(str(r['model'] or '-'))}</span></td>
        {session_cell}
        <td>{r['input_tokens']}→{r['output_tokens']}</td>
        <td>{f"{r['latency_ms']:.0f}ms" if r['latency_ms'] else '-'}</td>
        <td>{escape(str(r['user_id'] or '-'))}</td>
        <td><span class="{status_cls}">{r['status_code']}</span></td>
        <td>{str(r['timestamp'])[11:19]}</td>
    </tr>
    <tr id="expand-{r['id']}" style="display:none">
        <td colspan="{8 if show_session else 7}" class="expand-cell" id="detail-{r['id']}"></td>
    </tr>"""


def _session_row(s: dict) -> str:
    sid = s["session_id"] or ""
    short = sid[:24] if len(sid) > 24 else sid
    last = str(s["last_seen"])[11:19]
    return f"""<button class="session-row" data-session="{escape(sid)}" onclick="expandSession('{escape(sid)}', this)">
        <div class="session-id" title="{escape(sid)}">{escape(short)}</div>
        <div class="session-meta">{s['trace_count']} traces · last {last}</div>
    </button>"""


def _pagination(
    container_id: str,
    list_id: str,
    endpoint: str,
    page: int,
    total: int,
    has_prev: bool,
    has_next: bool,
    url_params: str = "",
    vals_template: str = "",
) -> str:
    def page_btn(step: int, label: str, disabled: bool) -> str:
        if disabled:
            return f'<button class="page-btn" disabled>{label}</button>'
        params = f"page={page + step}"
        if url_params:
            params += f"&{url_params}"
        attrs = f' hx-get="{endpoint}?{params}" hx-target="#{list_id}" hx-swap="innerHTML"'
        if vals_template:
            attrs += f' hx-vals="{vals_template.format(p=page + step)}"'
        return f'<button class="page-btn"{attrs}>{label}</button>'

    return f"""<div class="pagination" id="{container_id}" hx-swap-oob="outerHTML" data-page="{page}">
        <span class="page-info">Page {page + 1} · {total} total</span>
        <div class="page-btns">
            {page_btn(-1, "← Prev", not has_prev)}
            {page_btn(1, "Next →", not has_next)}
        </div>
    </div>"""


def _page_size_select(page: str, endpoint: str, target: str) -> str:
    options = "".join(
        f'<option value="{s}"{" selected" if s == 50 else ""}>{s}</option>' for s in (10, 25, 50, 100)
    )
    vals_fn = "sessionsVals(0)" if page == "sessions" else "traceVals(0)"
    return f"""<select class="page-size-select" data-page="{page}"
            hx-get="{endpoint}" hx-target="{target}" hx-swap="innerHTML"
            hx-trigger="change" hx-vals='js:{{...{vals_fn}}}'>{options}</select>"""


def _render_shell(page: str, content: str, query: str = "") -> str:
    nav = {p: ("active" if p == page else "") for p in ("live", "sessions", "traces", "config")}
    shell = render(
        "shell.html",
        page_content="__PAGE_CONTENT__",
        initial_page=f"/ui/page/{page}{query}",
        live_cls=nav["live"],
        sessions_cls=nav["sessions"],
        traces_cls=nav["traces"],
        config_cls=nav["config"],
    )
    return shell.replace("__PAGE_CONTENT__", content)


def _pretty_json(raw: str | None) -> str:
    if not raw:
        return "N/A"
    try:
        return json.dumps(json.loads(raw), indent=2, sort_keys=True)
    except (json.JSONDecodeError, TypeError):
        return str(raw)


def _build_guardrails(settings: Settings) -> GuardrailRegistry:
    registry = GuardrailRegistry()
    if settings.guardrails.injection.enabled:
        registry.register(InjectionGuardrail())
    return registry
