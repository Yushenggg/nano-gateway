import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class Storage:
    def __init__(self, db_path: str):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS otel_spans (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT NOT NULL,
                    user_id TEXT,
                    session_id TEXT,
                    model TEXT,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    latency_ms REAL,
                    status_code INTEGER,
                    request_json TEXT,
                    response_json TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_otel_spans_user ON otel_spans(user_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_otel_spans_timestamp ON otel_spans(timestamp)")
            cols = {row[1] for row in conn.execute("PRAGMA table_info(otel_spans)")}
            if "session_id" not in cols:
                conn.execute("ALTER TABLE otel_spans ADD COLUMN session_id TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_otel_spans_session ON otel_spans(session_id)")
            conn.commit()

    def log_span(
        self,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: float = 0.0,
        status_code: int = 200,
        user_id: str | None = None,
        session_id: str | None = None,
        request_json: str | None = None,
        response_json: str | None = None,
    ):
        span_id = f"span-{uuid4().hex[:16]}"
        timestamp = datetime.now(timezone.utc).isoformat()

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO otel_spans
                   (id, timestamp, user_id, session_id, model, input_tokens, output_tokens,
                    latency_ms, status_code, request_json, response_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (span_id, timestamp, user_id, session_id, model, input_tokens, output_tokens,
                 latency_ms, status_code, request_json, response_json),
            )
            conn.commit()

    def get_traces(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
        session_id: str | None = None,
        model_like: str | None = None,
        user_like: str | None = None,
        session_like: str | None = None,
    ) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            where, params = _trace_filters(
                user_id=user_id, session_id=session_id,
                model_like=model_like, user_like=user_like, session_like=session_like,
            )
            params += [limit, offset]
            cursor = conn.execute(
                f"SELECT * FROM otel_spans {where} ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_traces(
        self,
        user_id: str | None = None,
        session_id: str | None = None,
        model_like: str | None = None,
        user_like: str | None = None,
        session_like: str | None = None,
    ) -> int:
        with sqlite3.connect(self.db_path) as conn:
            where, params = _trace_filters(
                user_id=user_id, session_id=session_id,
                model_like=model_like, user_like=user_like, session_like=session_like,
            )
            cursor = conn.execute(f"SELECT COUNT(*) FROM otel_spans {where}", params)
            return cursor.fetchone()[0]

    def get_trace(self, trace_id: str) -> dict | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM otel_spans WHERE id = ?", (trace_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM otel_spans").fetchone()[0]
            models = conn.execute(
                "SELECT COUNT(DISTINCT model) FROM otel_spans WHERE model IS NOT NULL AND model != ''"
            ).fetchone()[0]
            users = conn.execute(
                "SELECT COUNT(DISTINCT user_id) FROM otel_spans WHERE user_id IS NOT NULL AND user_id != ''"
            ).fetchone()[0]
            sessions = conn.execute(
                "SELECT COUNT(DISTINCT session_id) FROM otel_spans WHERE session_id IS NOT NULL AND session_id != ''"
            ).fetchone()[0]
            avg = conn.execute(
                "SELECT AVG(latency_ms) FROM otel_spans WHERE latency_ms IS NOT NULL"
            ).fetchone()[0]
            return {
                "total": total,
                "models": models,
                "users": users,
                "sessions": sessions,
                "avg_latency": avg or 0,
            }

    def get_sessions(self, limit: int = 50, offset: int = 0, query: str | None = None) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            params: list = []
            where = "WHERE session_id IS NOT NULL"
            if query:
                where += " AND session_id LIKE ?"
                params.append(f"%{query}%")
            params += [limit, offset]
            cursor = conn.execute(
                f"""SELECT session_id, COUNT(*) as trace_count, MAX(timestamp) as last_seen
                   FROM otel_spans {where}
                   GROUP BY session_id ORDER BY last_seen DESC LIMIT ? OFFSET ?""",
                params,
            )
            return [dict(row) for row in cursor.fetchall()]

    def count_sessions(self, query: str | None = None) -> int:
        with sqlite3.connect(self.db_path) as conn:
            params: list = []
            where = "WHERE session_id IS NOT NULL"
            if query:
                where += " AND session_id LIKE ?"
                params.append(f"%{query}%")
            cursor = conn.execute(
                f"SELECT COUNT(*) FROM (SELECT session_id FROM otel_spans {where} GROUP BY session_id)",
                params,
            )
            return cursor.fetchone()[0]


def _trace_filters(
    user_id: str | None = None,
    session_id: str | None = None,
    model_like: str | None = None,
    user_like: str | None = None,
    session_like: str | None = None,
) -> tuple[str, list]:
    clauses = []
    params: list = []
    if user_id:
        clauses.append("user_id = ?")
        params.append(user_id)
    if session_id:
        clauses.append("session_id = ?")
        params.append(session_id)
    if model_like:
        clauses.append("model LIKE ?")
        params.append(f"%{model_like}%")
    if user_like:
        clauses.append("user_id LIKE ?")
        params.append(f"%{user_like}%")
    if session_like:
        clauses.append("session_id LIKE ?")
        params.append(f"%{session_like}%")
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    return where, params
