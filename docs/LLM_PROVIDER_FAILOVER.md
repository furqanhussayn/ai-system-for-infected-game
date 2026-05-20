# LLM Provider Failover

The backend now uses a strict provider order for normal chat:

1. Gemini Flash-Lite
2. Groq key 1
3. Groq key 2
4. Groq key 3
5. Local rules fallback

## Environment

Set these variables in `.env` or your deployment environment:

```env
AI_MODE=agent
CHAT_PROVIDER_ORDER=gemini,groq_key_1,groq_key_2,groq_key_3,rules
GEMINI_API_KEY=
GEMINI_CHAT_MODEL=gemini-3.1-flash-lite
GEMINI_BACKUP_CHAT_MODEL=gemini-2.5-flash-lite
GROQ_API_KEY=
GROQ_API_KEY_2=
GROQ_API_KEY_3=
GROQ_CHAT_MODEL=llama-3.1-8b-instant
GROQ_MODEL=llama-3.3-70b-versatile
LLM_PROVIDER_FAILOVER_ENABLED=true
LLM_GROQ_KEY_FAILOVER_ENABLED=true
LLM_MAX_PROVIDER_ATTEMPTS=4
LLM_GROQ_MAX_KEY_ATTEMPTS=3
LLM_KEY_COOLDOWN_SECONDS=600
LLM_RATE_LIMIT_COOLDOWN_SECONDS=600
LLM_TIMEOUT_SECONDS=8
LLM_MAX_OUTPUT_TOKENS=80
LLM_MAX_PROMPT_CHARS=2200
LLM_RECENT_CHAT_LIMIT=6
LLM_CHAT_MAX_BOTS_PER_EVENT=1
LLM_ENABLE_CACHE=true
LLM_CACHE_TTL_SECONDS=120
```

## How It Works

- Gemini is tried first when a Gemini API key is configured.
- If the primary Gemini model reports `model_unavailable`, the backup Gemini model is tried once.
- If Gemini fails or is unavailable, Groq key 1 is tried.
- Groq key 2 and key 3 are backup-only.
- Keys and providers are never tried in parallel.
- The request stops immediately when one provider succeeds.
- If everything fails, the existing local rules fallback still runs.

## Safety

- No API keys are written to traces, logs, status output, or responses.
- `/llm/status` only shows safe availability and cooldown metadata.
- `/llm/ping` only returns safe status fields and short error details.

## Status

Check `GET /llm/status` to see the safe provider order and availability snapshot.

## Ping

Use `GET /llm/ping` to test the full provider order.

Use these query forms for provider-specific checks:

- `GET /llm/ping?provider=gemini`
- `GET /llm/ping?provider=groq&key=1`
- `GET /llm/ping?provider=groq&key=2`
- `GET /llm/ping?provider=groq&key=3`

## Disabling

- Disable Gemini by clearing `GEMINI_API_KEY`.
- Disable Groq key failover by setting `LLM_GROQ_KEY_FAILOVER_ENABLED=false`.
- Disable provider failover entirely by setting `LLM_PROVIDER_FAILOVER_ENABLED=false`.