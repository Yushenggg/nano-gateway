# Configuration

There's only one config knob on the gateway: `NANOGATEWAY_URL`. Everything else (guardrails, db path) is YAML.

## Gateway env var

| Env var | Default | Purpose |
|---|---|---|
| `NANOGATEWAY_URL` | `https://api.openai.com/v1` | upstream endpoint the gateway forwards to |

Resolution order: `NANOGATEWAY_URL` env var → YAML → default.

The gateway has no API key. Clients pass their own key via the standard OpenAI SDK `Authorization` header; the gateway forwards it upstream.

## Client env vars (where you point OpenAI SDKs at the gateway)

| Env var | Purpose |
|---|---|
| `OPENAI_BASE_URL` | set to `http://<gateway-host>:<port>/v1` |
| `OPENAI_API_KEY` | your real provider key — forwarded through |

`.env` files in the current working directory and `$HOME` are loaded automatically.

## YAML (optional)

Only needed for guardrails or custom DB path. nanogateway checks:

1. path passed to `create_proxy_app(config_path=...)` or `nanogateway serve --config ...`
2. `./nano-rules.yaml`
3. `./.nanogateway/config.yaml`

Starter template (created by `nanogateway config init`):

```yaml
# url: "https://api.openai.com/v1"

guardrails:
  injection:
    enabled: false
    action: block
    block_message: "Request blocked by NanoGateway: potential prompt injection detected"

# db_path: ".nanogateway/data.db"
```

`url:` is overridden by the `NANOGATEWAY_URL` env var when set.
