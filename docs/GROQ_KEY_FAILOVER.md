# Groq Key Failover

This backend supports three Groq API keys in a strict priority order.

## Environment

Set these variables in your environment or `.env` file:

```env
GROQ_API_KEY=
GROQ_API_KEY_2=
GROQ_API_KEY_3=
GROQ_CHAT_MODEL=llama-3.1-8b-instant
GROQ_MODEL=llama-3.3-70b-versatile
LLM_GROQ_KEY_FAILOVER_ENABLED=true
LLM_GROQ_MAX_KEY_ATTEMPTS=3
LLM_GROQ_KEY_COOLDOWN_SECONDS=600
LLM_RATE_LIMIT_COOLDOWN_SECONDS=600
LLM_TIMEOUT_SECONDS=8
LLM_MAX_OUTPUT_TOKENS=80
LLM_MAX_PROMPT_CHARS=2200
```

Only `GROQ_API_KEY` is required for normal operation. `GROQ_API_KEY_2` and `GROQ_API_KEY_3` are optional backups and are ignored when empty.

## How Failover Works

- Key 1 is tried first.
- Key 2 is only tried if Key 1 fails or is on cooldown.
- Key 3 is only tried if Key 1 and Key 2 fail or are on cooldown.
- Keys are never called in parallel.
- The request stops as soon as one key succeeds.
- If all configured keys fail, the existing local fallback is used.

## Safety

- API keys are never written to traces, logs, status output, or responses.
- `/llm/status` only shows safe metadata about availability and cooldown state.
- `/llm/ping` only returns safe execution details and a short error summary.

## Checking Status

Open `GET /llm/status` to inspect the safe pool view.

Example:

```json
{
  "aiMode": "agent",
  "provider": "groq",
  "model": "llama-3.1-8b-instant",
  "hasGroqKey": true,
  "groqKeyFailoverEnabled": true,
  "groqKeyPool": {
    "keyCount": 3,
    "availableKeys": 2,
    "cooldownKeys": 1,
    "keys": [
      {"keyId": "groq_key_1", "available": false, "lastError": "rate_limited"},
      {"keyId": "groq_key_2", "available": true, "lastError": ""},
      {"keyId": "groq_key_3", "available": true, "lastError": ""}
    ]
  }
}
```

## Ping Checks

Use `GET /llm/ping` to test the normal failover path.

Use a query parameter to test one key at a time:

- `GET /llm/ping?key=1`
- `GET /llm/ping?key=2`
- `GET /llm/ping?key=3`

If `LLM_GROQ_KEY_FAILOVER_ENABLED=false`, the backend only uses the primary configured key and does not try backups.