# Judge Proof — THE INFECTED AI Director Demo

## Pre-Demo Checklist

Before sitting down with the judges, confirm:

- [ ] Backend server is running (`uvicorn src.main:app --reload` or equivalent)
- [ ] Browser open to `http://localhost:8000` (or deployed URL)
- [ ] `/health` returns `{"status": "ok"}`
- [ ] No `.env` API key required — rule-based mode runs with zero configuration

---

## Exact Demo Script

### Step 1 — Open the Landing Page

**URL:** `http://localhost:8000/`

**Say to judges:**
> "This is the Team A backend landing page. This FastAPI server is the AI Director for THE INFECTED — a Unity mobile social deduction horror game. The backend decides every infected bot's behavior: what they do, what they say, and who they vote to eliminate."

**Point out:**
- The "Backend Status: Online" badge
- The "Run Fresh Demo" button
- The quick links to trace viewer, raw JSON, and Swagger

---

### Step 2 — Run the One-Click Demo

**Click:** The **"▶ Run Fresh Demo"** button on the landing page.

This sends `POST /demo/quick/DEMO_ROOM` to the server.

**Say to judges:**
> "I just triggered the full game lifecycle in one click. The backend executed: bot registration, an early-game stealth decision, a meeting chat response, a voting decision, a mid-game aggressive behavior switch, and a final hunt mode. All of this happened in under a second — and every decision was logged."

**Browser will redirect to:** `/trace_viewer/DEMO_ROOM`

---

### Step 3 — Explain the Trace Viewer

**URL:** `/trace_viewer/DEMO_ROOM`

You will see **6 decision cards** in a grid. Walk through them left to right:

#### Card 1: `register_bot`
> "When a match starts, Unity calls our backend with the bot's ID, the wave number, and the list of alive players. Our State Agent parses this and our Behavior Director assigns the bot a personality — in this case 'deflector' — and sets an initial stealth behavior mode."

#### Card 2: `decide_action_early`
> "At wave 1, the infected count is low. Our rule engine determines: stealth mode. The bot should fake tasks and blend in. Unity receives `behaviorMode: stealth_fake_task` and `targetRoom: Electrical`. No aggression yet."

#### Card 3: `respond`
> "An emergency meeting was called. Player 1 accused Player 2 — our bot — in chat. The Chat Agent detected the direct accusation and generated a defensive response matching the 'deflector' personality. The response went through a safety filter before being returned."

#### Card 4: `vote`
> "During the vote phase, our Vote Agent read the recent chat history, detected that Player 1 accused the bot, and counter-voted Player 1. This is context-driven strategic reasoning — not random."

#### Card 5: `decide_action_late`
> "By wave 3, there are 2 infected and 2 humans. The infected now outnumber humans. The Behavior Director switches mode to `aggressive_chase`. Unity will change the bot's movement behavior accordingly."

#### Card 6: `final_hunt`
> "Three infected versus one human. The bot enters `final_hunt` mode. Maximum aggression. The horror endgame begins. Every bot decision escalated naturally based on game state — that's agentic gameplay logic."

---

### Step 4 — Show the Raw JSON Trace

**Click:** "Raw JSON" link on the trace viewer page, or go to `/trace/DEMO_ROOM`

**Say to judges:**
> "Every card maps to a structured JSON entry. This is the audit trail. You can see the exact timestamp, the bot ID, the action type, the decision value, the human-readable reasoning, and the source endpoint. This proves the backend made real decisions — not hardcoded outputs."

---

### Step 5 — Show the Swagger Docs (Optional)

**URL:** `/docs`

**Say to judges:**
> "Here are all the endpoints. Judges can call `/register_bot`, `/decide_action`, `/respond`, and `/vote` directly with custom payloads using the Swagger UI. Every call will appear in the trace viewer."

---

### Step 6 — Show the LLM Status

**URL:** `/llm/status`

**Say to judges:**
> "This shows the current AI mode. Right now it's `rules` — fully offline, no API key needed. If we set `AI_MODE=groq` in the environment, the Chat Agent will start using Groq's Llama-3.3-70b model for more natural-sounding chat. The behavior logic, voting, and traces remain the same either way."

---

### Step 7 — Show the Antigravity Workflow Page

**URL:** `/antigravity_workflow`

**Say to judges:**
> "This page summarizes the entire agentic architecture — all 6 agents, the data flow, and the design rationale. It was generated as part of our Antigravity workflow proof."

---

## Screenshots to Capture Before Presentation

1. `screenshot_landing_page.png` — `http://localhost:8000/`
2. `screenshot_trace_viewer.png` — `/trace_viewer/DEMO_ROOM` with all 6 cards visible
3. `screenshot_raw_json.png` — `/trace/DEMO_ROOM` showing JSON array
4. `screenshot_swagger.png` — `/docs` showing all endpoints
5. `screenshot_llm_status.png` — `/llm/status` response
6. `screenshot_antigravity_workflow.png` — `/antigravity_workflow` page

---

## Backup Explanation if Unity Integration is Incomplete

If the Unity client is not connected or the mobile build is not ready, use this explanation:

> "Unity is responsible for rendering gameplay, movement, and Firebase sync. Our backend is the AI brain. We've built a complete self-demonstrating backend that doesn't require Unity to be running. The one-click demo at `/demo/quick/DEMO_ROOM` simulates the full game lifecycle and proves every AI decision. When Unity is integrated, it will call these same endpoints at the same game events — registration, decision, meeting, vote — and act on our responses."

**Key points to stress:**
- The API contract is documented in `docs/TEAM_B_API_CONTRACT.md`
- Unity example integration code is in `docs/UNITY_AI_CLIENT_EXAMPLE.cs`
- The backend is fully functional independently — Unity is just the renderer
- Every response from this backend is directly actionable by Unity (behavior mode → animation, targetRoom → navigation, voteTarget → UI highlight)

---

## Rule-Based Mode vs Groq Mode

| Feature | Rule-Based (default) | Groq Mode |
|---|---|---|
| Activation | `AI_MODE=rules` (default) | `AI_MODE=groq` + `GROQ_API_KEY` |
| Cost | Free, no API calls | Groq API credits |
| Behavior logic | Identical | Identical |
| Voting logic | Identical | Identical |
| Chat generation | Personality templates | Llama-3.3-70b LLM |
| Offline | ✅ Yes | ❌ Requires internet |
| Demo safe | ✅ Yes | ✅ Yes (demo forces rules mode) |
| Safety filter | ✅ Applied | ✅ Applied (extra important) |
| Trace logging | ✅ Identical | ✅ Identical |

**Key message:** Groq mode only affects chat text quality. All game logic, decision tracing, and behavior modes are identical in both modes.

---

## AI Calls Are Event-Based, Not Frame-Based

This is a critical point for the technical judges:

> "Unlike a traditional game AI loop that runs every frame (60fps = 60 decisions/second), our AI Director is called at discrete game events:
> - Match start → `/register_bot` (once per bot per match)
> - Wave change or task completion → `/decide_action` (triggered by game event)
> - Emergency meeting → `/respond` and `/vote` (once per meeting)
>
> Additionally, `src/services/antigravity_workflow.py` enforces a minimum interval (`AI_CALL_MIN_INTERVAL`, default 20 seconds) between AI calls per bot per event type. This prevents LLM costs from scaling with frame rate and makes the system safe and predictable."

**Why this matters:**
- No wasted API calls
- Deterministic timing
- Compatible with Unity's coroutine/async integration
- Cost-predictable in production
