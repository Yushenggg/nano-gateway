# Setup

`nanogateway` runs as a standalone process. You point any OpenAI-compatible client at it — no SDK or in-process embed needed.

## Start the server

```bash
nanogateway serve
```

Flags:

- `--port` — port to bind (default `9000`)
- `--config` — path to a config file (default: looks for `nano-rules.yaml` then `.nanogateway/config.yaml`)

In your client:

```bash
export OPENAI_BASE_URL="http://localhost:9000/v1"
```

That single env var swap is how every OpenAI SDK talks to the gateway. Once running, every call is logged to a local SQLite DB and visible in the UI at the same port.

## Companion commands

```bash
nanogateway traces --limit 50         # recent calls from the CLI's perspective
nanogateway traces --user alice       # filter by user id
nanogateway config init               # write a starter nano-rules.yaml
```

## Embed as a FastAPI app

If you already have a FastAPI/Starlette/ASGI app and want to mount the gateway under it, use `create_proxy_app`:

```python
from fastapi import FastAPI
from nanogateway import create_proxy_app

app = FastAPI()
app.mount("/v1", create_proxy_app(config_path="nano-rules.yaml"))
```

The proxy can also be served directly with uvicorn:

```python
from nanogateway import create_proxy_app
import uvicorn

uvicorn.run(create_proxy_app(), host="0.0.0.0", port=9000)
```
