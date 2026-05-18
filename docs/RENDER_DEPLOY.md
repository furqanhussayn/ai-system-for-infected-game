# Render Deployment Guide

Use this guide to deploy the Team A FastAPI backend on Render Free so the service stays online without your laptop running.

## 1. Push To GitHub

Push the repository to GitHub first. Render deploys from a GitHub repository.

## 2. Create A Web Service

In the Render dashboard, create a new **Web Service** and connect the GitHub repo for this backend.

## 3. Choose The Free Instance

Select the free plan for the web service.

## 4. Configure Build And Start Commands

Use these commands:

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn src.main:app --host 0.0.0.0 --port $PORT
```

You can also keep the same settings in [render.yaml](../render.yaml).

## 5. Set Environment Variables

Add these environment variables in Render:

- `AI_MODE=rules`
- `LLM_PROVIDER=groq`
- `GROQ_API_KEY=`
- `GROQ_MODEL=llama-3.3-70b-versatile`
- `LLM_TIMEOUT_SECONDS=8`

## 6. Verify The Deployment

After deployment, test these endpoints in the Render URL:

- `/health`
- `/`
- `/llm/status`

## 7. Wake The Free Service Before Demo

Render free services sleep after inactivity. Open `/health` before the demo to wake the service up.

## Notes

- Do not commit your local `.env` file.
- Keep `AI_MODE=rules` for the stable free deployment unless you intentionally want agent mode.