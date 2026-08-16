# API reference

`nanogateway` ships a single FastAPI app and a CLI. The CLI is the recommended entry point; the app is exposed for embedding.

## CLI

```bash
nanogateway serve [--port 9000] [--config PATH]
nanogateway traces [--limit 20] [--user USER]
nanogateway config init
```

`serve` starts uvicorn with `create_proxy_app()` and blocks until Ctrl-C. `traces` prints recent calls from the SQLite DB. `config init` writes a starter `nano-rules.yaml`.

## `create_proxy_app(config_path=None) -> FastAPI`

Returns the fully-wired proxy app. Mount it under your own ASGI server, or run it directly with uvicorn.

| Arg | Default | Purpose |
|---|---|---|
| `config_path` | `None` | path to `nano-rules.yaml`; `None` auto-discovers |

### Exposed routes

API:

- `POST /v1/chat/completions` — OpenAI-compatible passthrough (streams supported)
- `GET  /v1/models` — model list from the upstream provider

UI pages:

- `GET /`, `/live`, `/sessions`, `/traces`, `/config`

UI JSON:

- `GET /ui/stats`, `/ui/traces`, `/ui/sessions`, `/ui/stream`

The UI mounts on the same port as the API — there is no separate web server.

## Version

```python
import nanogateway
nanogateway.__version__
```
