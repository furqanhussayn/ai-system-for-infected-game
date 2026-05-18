# Groq Testing

The default mode is free and local:

AI_MODE=rules

That keeps the backend zero-cost unless you explicitly switch it on.

## Create `.env`

Copy `.env.example` to `.env` and edit the values you want to test.

## Enable Groq

Set:

AI_MODE=groq

Keep:

LLM_PROVIDER=groq

Paste your Groq key into:

GROQ_API_KEY=

## Restart the backend

After changing `.env`, restart the FastAPI server so the new values load.

## Test `POST /respond`

Call `/respond` with a meeting message that directly mentions a bot. If Groq is enabled and the key is valid, the endpoint can return up to two short chat messages.

## Switch back to rules

Set:

AI_MODE=rules

Then restart the backend again.

## Do not commit secrets

Never commit `.env`.