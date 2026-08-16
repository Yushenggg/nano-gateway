# Quickstart

Two env vars. Two contexts. Pick one.

## 1. OpenAI

**Client env** (your app / OpenAI SDK):

```bash
export OPENAI_BASE_URL="http://localhost:9000/v1"
export OPENAI_API_KEY="sk-..."
```

**Gateway env:**

```bash
# optional — defaults to https://api.openai.com/v1
export NANOGATEWAY_URL="https://api.openai.com/v1"
```

## 2. Any other OpenAI-compatible provider

**Client env** — same as above. The gateway forwards your key through; the upstream is decided by `NANOGATEWAY_URL`, not by the SDK env vars.

```bash
export OPENAI_BASE_URL="http://localhost:9000/v1"
export OPENAI_API_KEY="sk-..."
```

**Gateway env:**

```bash
export NANOGATEWAY_URL="https://api.together.xyz/v1"   # any OpenAI-compatible endpoint
```

## Run

```bash
nanogateway serve
```

Proxy listens on `http://localhost:9000`. Trace UI is at the same address.

The gateway has no API key — your client supplies it through the standard OpenAI SDK, and nanogateway forwards the `Authorization` header upstream.

## What's next

- All env vars and YAML knobs: [Config](config.md)
- Prompt-injection blocking: [Guardrails](guardrails.md)
- Reference: [API](api.md)
