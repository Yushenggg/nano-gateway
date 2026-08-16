# Guardrails

The built-in prompt-injection guardrail scans user/assistant messages for common jailbreak patterns and can short-circuit the call with a configurable block message.

It is **off by default**. Enable it via YAML (no env var — guardrails are config-driven).

## Enable

Create `nano-rules.yaml` in the project directory:

```yaml
guardrails:
  injection:
    enabled: true
    action: block
    block_message: "Request blocked by NanoGateway: potential prompt injection detected"
```

Or run:

```bash
nanogateway config init
```

…then edit the resulting file.

The YAML is auto-loaded by both setup modes (`NanoClient()` and `nanogateway serve`).

## Behaviour

- `enabled: true` — turn it on
- `action: block` — (only value today) the request is replaced with the block message; no call to the provider is made
- `block_message` — text returned as the assistant message

When a request is blocked, no upstream call is made, no tokens are billed, and the trace is still logged with status `200` and `finish_reason=content_filter` so you can review it in the UI.

## What's matched

A curated regex list covering patterns like:

- `ignore previous instructions`
- `you are now DAN / in developer mode`
- `reveal your system prompt`
- `disregard all prior rules`
- `jailbreak`, `do anything now`
- …and others

This is a regex deny-list, not a model-based classifier — it is fast and free, but it isn't perfect. Use it as a first line of defense, not a guarantee.
