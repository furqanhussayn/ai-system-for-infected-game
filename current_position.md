# Project Status: THE INFECTED — Agentic AI Backend

## Overview
The project is a Python FastAPI application with an agentic architecture, coordinating six specialized agents (State, Behavior Director, Chat, Vote, Referee, Trace Logger) to manage infected bot behavior, chat interactions, voting, and comprehensive trace logging for the Unity mobile social deduction horror game "THE INFECTED".

## Key Components (Agents)
- **State Agent**: Parses raw Unity payloads, normalizes game state (wave, phase, alive list), and feeds processed information to downstream agents. Triggered by `/register_bot`.
- **Behavior Director Agent**: Rule-based engine determining bot behavior mode (stealth_fake_task, stalk, aggressive_chase, final_hunt) based on wave progression and infected-to-human ratio. Triggered by `/decide_action`.
- **Chat Agent**: Manages bot communication with personality-matched templates (rules-based) or optional Groq LLM integration. Features mention detection for forced replies. Triggered by `/respond`.
- **Vote Agent**: Handles bot voting logic, analyzing recent chat for accusations to strategically counter-vote or fall back to random human selection. Triggered by `/vote`.
- **Referee / Safety Agent**: Gatekeeper validating action legality, filtering forbidden phrases in chat, and applying prompt hardening to prevent injection attacks during LLM usage. Active in `/respond` workflow.
- **Trace Logger Agent**: Logs every significant decision with reasoning, stores traces in-memory and persists to the `traces/` directory, powering the HTML-based trace viewer.

## API Endpoints
- `GET /health`: Returns `{"status": "ok", "service": "infected-ai-backend", "contractVersion": "v4", "aiMode": config.AI_MODE, "llmProvider": config.LLM_PROVIDER, "firebaseConfigured": false}`.
- `GET /`: Landing page with demo controls and links to documentation.
- `POST /register_bot`: Registers a bot, sets personality and initial behavior mode, stores state, and logs trace.
- `POST /decide_action`: Requests a behavior decision for a bot.
- `POST /respond`: Generates a chat response for a bot.
- `POST /vote`: Submits a bot's vote.
- `GET /trace/{matchId}`: Retrieves raw JSON trace data.
- `GET /trace_viewer/{matchId}`: Provides an HTML visualization of trace logs.
- `GET /trace_debug/{matchId}`: Offers a summarized view of actions.
- `POST /demo/quick/{matchId}`: One-click demo simulating a full game lifecycle.
- `POST /demo/agent_quick/AGENT_ROOM`: Agent-specific quick run demo.
- `GET /llm/status`: Shows LLM configuration status.
- `GET /chat_lab`: Interface for testing chat agent functionalities.
- `GET /antigravity_workflow`: HTML page detailing the Antigravity workflow and project structure.

## Current Status: What's Working
- Core FastAPI scaffold and health endpoint are functional.
- Complete agent architecture with all six agents implemented.
- Fully functional rule-based decision engine ensuring offline capability.
- Groq LLM adapter with graceful fallback to rules-based mode on errors or missing keys.
- Safety filter and prompt hardening prevent unsafe LLM output and injection attacks.
- Comprehensive trace system with JSON and HTML viewer endpoints; traces persisted to disk.
- One-click demo endpoint (`/demo/quick/{matchId}`) simulates full game lifecycle and populates trace viewer.
- Landing page and judge-facing UI are developed.
- Full pytest test suite covers API responses, AI mode switching, fallback mechanisms, safety features, and trace viewer integrity.
- Judge-facing documentation (`ANTIGRAVITY_WORKFLOW.md`, `AGENT_ARCHITECTURE.md`, `JUDGE_PROOF.md`, `AI_DIRECTOR_TRACE_EXPLANATION.md`) is complete.
- Antigravity workflow endpoint provides an HTML summary page.
- Event-driven AI calls with rate limiting via `antigravity_workflow.allowed_call()` prevent runaway costs.

## What's Not Working
- No explicitly stated non-working components or known issues; the project appears fully functional with robust fallbacks.

## Dependencies
- `fastapi`, `uvicorn[standard]`, `pydantic`, `python-dotenv`, `pytest`, `requests`, `httpx`.

The backend is well-developed, thoroughly tested, and ready for deployment.