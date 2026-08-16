import argparse
from pathlib import Path
from nanogateway.config import load_config
from nanogateway.storage import Storage


DEFAULT_CONFIG = """# NanoGateway Configuration
# url resolution: NANOGATEWAY_URL env var > this file
# The gateway forwards the client's Authorization header upstream; no key is configured here.

# url: "https://api.openai.com/v1"

guardrails:
  injection:
    enabled: false
    action: block
    block_message: "Request blocked by NanoGateway: potential prompt injection detected"

# db_path: ".nanogateway/data.db"
"""


def cmd_config_init():
    path = Path("nano-rules.yaml")
    if path.exists():
        print(f"Config already exists at {path}")
        return
    path.write_text(DEFAULT_CONFIG)
    print(f"Created config at {path}")


def cmd_traces(limit: int, user: str | None):
    try:
        settings = load_config()
    except Exception:
        settings = None

    db_path = settings.db_path if settings else ".nanogateway/data.db"
    storage = Storage(db_path)

    traces = storage.get_traces(limit=limit, user_id=user)

    if not traces:
        print("No traces found.")
        return

    print(f"{'ID':<20} {'Timestamp':<28} {'Model':<20} {'In Tok':<8} {'Out Tok':<8} {'Latency':<10} {'User':<15}")
    print("-" * 110)

    for t in traces:
        span_id = t["id"][:18]
        timestamp = t["timestamp"][:26]
        model = (t["model"] or "-")[:18]
        in_tok = str(t["input_tokens"])
        out_tok = str(t["output_tokens"])
        latency = f"{t['latency_ms']:.1f}ms" if t["latency_ms"] else "-"
        user_id = (t["user_id"] or "-")[:13]
        print(f"{span_id:<20} {timestamp:<28} {model:<20} {in_tok:<8} {out_tok:<8} {latency:<10} {user_id:<15}")


def cmd_serve(port: int, config: str | None):
    try:
        import uvicorn
    except ImportError:
        print("Error: uvicorn not installed. Run: pip install nanogateway[ui]")
        return

    from nanogateway.proxy import create_proxy_app

    app = create_proxy_app(config)
    print(f"NanoGateway proxy running at http://localhost:{port}")
    print(f"Set OPENAI_BASE_URL=http://localhost:{port}/v1 in your agent")
    uvicorn.run(app, host="0.0.0.0", port=port)


def main():
    parser = argparse.ArgumentParser(prog="nanogateway", description="NanoGateway CLI")
    sub = parser.add_subparsers(dest="command")

    serve_cmd = sub.add_parser("serve", help="Start the proxy server")
    serve_cmd.add_argument("--port", type=int, default=9000, help="Port to listen on")
    serve_cmd.add_argument("--config", type=str, default=None, help="Config file path")

    config_cmd = sub.add_parser("config", help="Configuration management")
    config_sub = config_cmd.add_subparsers(dest="config_action")
    config_sub.add_parser("init", help="Create default config file")

    traces_cmd = sub.add_parser("traces", help="View OTel traces")
    traces_cmd.add_argument("--limit", type=int, default=20, help="Number of traces to show")
    traces_cmd.add_argument("--user", type=str, default=None, help="Filter by user ID")

    args = parser.parse_args()

    if args.command == "serve":
        cmd_serve(args.port, args.config)
    elif args.command == "config" and args.config_action == "init":
        cmd_config_init()
    elif args.command == "traces":
        cmd_traces(args.limit, args.user)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
