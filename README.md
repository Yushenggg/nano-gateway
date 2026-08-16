> **Status: in testing (alpha, v0.1.0).** The CLI and proxy API may change between minor versions. Pin a version and expect to update.

# nanogateway

Ultra-lightweight AI Gateway proxy server.

`nanogateway` is a drop-in proxy for any OpenAI-compatible LLM endpoint. It forwards every request, logs it to a local SQLite DB, and shows you a web UI to inspect traffic. No SDK, no credentials stored — it just passes your existing OpenAI key through.

## Two settings, two contexts

There is exactly one env var for the gateway process and one for the client.

**On the client / app** (your existing OpenAI SDK env vars still work — just point them at the gateway):

```bash
export OPENAI_BASE_URL="http://localhost:9000/v1"   # gateway instead of api.openai.com
export OPENAI_API_KEY="sk-..."                       # real key, forwarded through nanogateway
```

**On the gateway process:**

```bash
export NANOGATEWAY_URL="https://api.openai.com/v1"   # upstream — defaults to OpenAI
```

The gateway has no API key config. It forwards whatever `Authorization` header your client sends. Each client uses their own key; the gateway never sees it stored.

## Start the proxy

```bash
nanogateway serve
```

The proxy listens on `http://localhost:9000`. The trace UI is at the same address.

That's the whole flow. If your client SDK supports `OPENAI_BASE_URL`, it just works — no code changes.

## Embed as a FastAPI app

If you already have an ASGI app and want to mount the gateway under it:

```python
from nanogateway import create_proxy_app

app = create_proxy_app(config_path="nano-rules.yaml")
```

## What's next

- [Docs index](docs/) — configuration, guardrails, Docker patterns, full API reference

## License

MIT
