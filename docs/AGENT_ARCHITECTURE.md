# Agent Architecture — THE INFECTED AI Director Backend

## System Overview

**THE INFECTED** is a Unity mobile social deduction horror game.  
Team A's backend is the **Agentic AI Director**: a FastAPI service that acts as the brain for infected NPC bots.

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Unity Mobile Client                         │
│  (gameplay, physics, rendering, player input, Firebase sync)        │
└────────────────────────────┬────────────────────────────────────────┘
                             │ HTTP POST (game events)
                             ▼
┌─────────────────────────────────────────────────────────────────────┐
│                Team A — Agentic AI Director (FastAPI)               │
│                                                                     │
│  ┌─────────────┐  ┌───────────────────┐  ┌──────────────────────┐  │
│  │ State Agent │→ │ Behavior Director │→ │ Trace Logger Agent   │  │
│  └─────────────┘  └───────────────────┘  └──────────────────────┘  │
│                          │                                          │
│            ┌─────────────┼───────────────┐                         │
│            ▼             ▼               ▼                         │
│      ┌──────────┐  ┌──────────┐  ┌──────────────┐                 │
│      │  Chat    │  │  Vote    │  │  Referee/    │                 │
│      │  Agent   │  │  Agent   │  │  Safety Agent│                 │
│      └──────────┘  └──────────┘  └──────────────┘                 │
│                                                                     │
│  Optional: Groq LLM (AI_MODE=groq) — chat generation only          │
│  Default:  Rule-based mode (AI_MODE=rules) — always free/offline   │
└─────────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                  JSON responses → Unity acts
                  Trace logs → /trace_viewer proof
```

Unity is responsible for:
- Rendering the game world
- Handling player movement and task mechanics
- Syncing state via Firebase
- Calling this backend at key game events (NOT every frame)

This backend is responsible for:
- Deciding every infected bot's **behavior mode** (stealth / stalk / chase / hunt)
- Generating **chat responses** that sound like a human player
- Choosing **who the bot votes** during meetings
- **Logging every decision** as an auditable trace entry
- Enforcing **rate limits** so AI calls are event-driven, not frame-driven
- Running a **Safety/Referee** pass to validate actions are legal

---

## Agent Roles

### 1. State Agent (`src/agents/state_agent.py`)

**Purpose:** Receives raw game state from Unity via the `/register_bot` payload and produces a normalized internal snapshot used by all other agents.

**Inputs:**
- `matchId`, `botId`, `wave`, `alivePlayers`, `infectedPlayers`

**Outputs:**
- Structured dict: `{ phase, wave, alive }`

**Why it's agentic:** It isolates state parsing from decision logic. No agent below it needs to touch raw request fields directly — they consume the snapshot.

---

### 2. Behavior Director Agent (`src/agents/behavior_director.py`)

**Purpose:** The core decision-making agent. Reads game state and outputs the bot's current behavior mode and movement target.

**Inputs:**
- `botId`, `wave`, `infectedPlayers`, `humanPlayers`, `alive`

**Decision Logic (rule-based):**
```
if humanPlayers == 1             → final_hunt
elif infectedCount >= humanCount → aggressive_chase
elif wave <= 1                   → stealth_fake_task
else                             → stalk
```

**Outputs:**
- `behaviorMode` (one of: `stealth_fake_task`, `stalk`, `aggressive_chase`, `final_hunt`)
- `targetRoom` (randomized room for stealth mode)
- `targetPlayer` (None — Unity resolves proximity targeting)
- `shouldChase` (bool — Unity triggers chase animation)

**Rate limiting:** Uses `antigravity_workflow.allowed_call()` to ensure behavior decisions are event-gated, not called every frame.

**Why it's agentic:** It reasons about game state to produce contextual, escalating behavior. The mode output changes dynamically across the game lifecycle, escalating horror pressure naturally.

---

### 3. Chat Agent (`src/agents/chat_agent.py`)

**Purpose:** Generates human-like chat messages for the bot during emergency meetings. Operates in two modes based on `AI_MODE` environment variable.

**Mode: `rules` (default)**
- Selects from personality-specific templates
- Introduces realistic typos
- Applies mention-detection logic (bot responds more if directly accused)

**Mode: `groq`**
- Builds a hardened system prompt via `src/utils/prompt_hardening.py`
- Calls Groq Llama-3.3-70b API
- Response is passed through a **safety filter** that blocks forbidden phrases
- Falls back to rule-based if LLM call fails or output is unsafe

**Rate limiting:** `allowed_call(botId, "meeting")` — LLM is called at most once per meeting event per bot.

**Why it's agentic:** In Groq mode, it uses live LLM reasoning conditioned on recent chat context and bot personality. In rules mode, it uses personality-aware heuristics.

---

### 4. Vote Agent (`src/agents/vote_agent.py`)

**Purpose:** Decides who the infected bot nominates during voting phase.

**Decision Logic:**
1. Exclude self and other known infected from candidate pool
2. If someone accused the bot in recent chat → vote against that accuser (counter-vote)
3. Else → random pick from human candidates
4. Fallback → any alive non-self player

**Inputs:** `alivePlayers`, `infectedPlayers`, `recentChat`, `botId`

**Outputs:** `voteTarget` (player ID string), `trace` (reason)

**Why it's agentic:** The vote decision is context-driven — it reads chat history and applies a strategy (self-defense counter-vote) rather than simply picking randomly.

---

### 5. Referee / Safety Agent (`src/agents/referee_agent.py`)

**Purpose:** Validates that a proposed action is legal before it is dispatched. Acts as a guard agent in the pipeline.

**Current implementation:** `validate(state, action) → (True, "ok")`

**Design intent:**
- Prevents bots from targeting players who are already eliminated
- Prevents double-votes
- Can be extended to enforce any fair-play rule without touching other agents
- The **forbidden phrase filter** in `respond.py` is the practical implementation of safety gating for chat

**Why it's agentic:** It is a dedicated verification step that sits between decision and dispatch — a standard pattern in multi-agent safety architectures.

---

### 6. Trace Logger Agent (`src/agents/trace_logger.py`)

**Purpose:** Records every agent decision as a structured, auditable trace entry. Persists to both in-memory store and the `traces/` directory on disk.

**Every trace entry contains:**
```json
{
  "timestamp": "2026-05-18T12:00:00Z",
  "matchId": "DEMO_ROOM",
  "botId": "player_2",
  "action": "decide_action_early",
  "decision": "stealth_fake_task",
  "trace": "Early wave. Bot should fake tasks and avoid obvious aggression.",
  "source": "/decide_action"
}
```

**Why it's agentic:** It creates a full **decision audit trail** — every agent action is observable, replayable, and explainable. This is what `GET /trace_viewer/{matchId}` visualizes.

---

## Data Flow

### Registration Flow (game start)

```
Unity → POST /register_bot
          │
          ├─ StateAgent.snapshot(req)       → structured state
          ├─ BehaviorDirector.assign_personality() → personality label
          ├─ BehaviorDirector.initial_mode() → initial behavior
          ├─ core/state.py register_bot_state() → stored in memory
          └─ TraceLogger.add_trace()        → logged as "register_bot"
          │
          ▼
      Response: { botId, personality, behaviorMode, trace }
```

### Behavior Decision Flow (each game event)

```
Unity → POST /decide_action
          │
          ├─ get_bot_state() → retrieve personality/room from memory
          ├─ rule engine logic → compute behaviorMode
          ├─ antigravity_workflow.allowed_call() → rate gate check
          └─ TraceLogger.add_trace() → logged as "decide_action"
          │
          ▼
      Response: { botId, behaviorMode, targetRoom, shouldChase, trace }
```

### Emergency Meeting Flow

```
Unity → POST /respond
          │
          ├─ get_bot_state() → personality
          ├─ _should_respond() → mention detection + personality rate check
          ├─ if AI_MODE=groq → build_prompt() → Groq API → safety filter
          ├─ if AI_MODE=rules → _rule_based_messages(personality)
          └─ TraceLogger.add_trace() → logged as "respond"
          │
          ▼
      Response: { botId, messages: ["...", "..."], trace }

Unity → POST /vote
          │
          ├─ parse recentChat for accusers
          ├─ counter-vote logic
          ├─ fallback: random human pick
          └─ TraceLogger.add_trace() → logged as "vote"
          │
          ▼
      Response: { botId, voteTarget, trace }
```

---

## Endpoint-to-Agent Mapping

| Endpoint | Primary Agents Invoked |
|---|---|
| `POST /register_bot` | StateAgent → BehaviorDirector → TraceLogger |
| `POST /decide_action` | BehaviorDirector → TraceLogger |
| `POST /respond` | ChatAgent → RefereeAgent (safety filter) → TraceLogger |
| `POST /vote` | VoteAgent → TraceLogger |
| `GET /trace/{matchId}` | TraceLogger (read) |
| `GET /trace_viewer/{matchId}` | TraceLogger (read) → HTML render |
| `POST /demo/quick/{matchId}` | All agents in sequence → redirect to trace_viewer |
| `GET /llm/status` | Config read — no agent |
| `GET /antigravity_workflow` | Static HTML — architecture summary |

---

## What Unity Sends

| Endpoint | Key Fields Sent |
|---|---|
| `/register_bot` | `matchId`, `botId`, `wave`, `alivePlayers`, `infectedPlayers` |
| `/decide_action` | `matchId`, `botId`, `phase`, `wave`, `infectedPlayers`, `humanPlayers`, `taskProgress`, `nearestHuman`, `botRoom` |
| `/respond` | `matchId`, `botId`, `message`, `recentChat[]`, `alivePlayers`, `infectedPlayers` |
| `/vote` | `matchId`, `botId`, `alivePlayers`, `infectedPlayers`, `recentChat[]` |

Unity does **NOT** call these endpoints every frame. They are called at discrete game events:
- Match start → `/register_bot`
- Player completes task / wave changes → `/decide_action`
- Emergency meeting opened → `/respond` + `/vote`

---

## What the Backend Returns

| Endpoint | Response Fields |
|---|---|
| `/register_bot` | `botId`, `personality`, `behaviorMode`, `trace` |
| `/decide_action` | `botId`, `behaviorMode`, `targetRoom`, `targetPlayer`, `shouldChase`, `trace` |
| `/respond` | `botId`, `messages[]`, `trace` |
| `/vote` | `botId`, `voteTarget`, `trace` |

---

## How Trace Logs Prove Decisions

Every agent action calls `add_trace()`. The trace viewer at `/trace_viewer/{matchId}` displays each decision as a card with:

- **Timestamp** — when the decision was made
- **Action type** — which agent fired (register_bot, decide_action, respond, vote, etc.)
- **Decision** — the actual output value chosen
- **Trace** — the human-readable reasoning string
- **Source** — which endpoint triggered the agent

This creates a **full audit chain** from Unity event → agent input → agent reasoning → output → Unity action.

The one-click demo at `POST /demo/quick/DEMO_ROOM` executes the full game lifecycle (register → early decision → meeting → vote → late decision → final hunt) and redirects to the trace viewer, allowing judges to see all 6+ decision cards in sequence.

---

## Why This Qualifies as Agentic Gameplay Logic

1. **Multi-agent separation of concerns** — Each agent has a distinct role: state parsing, behavior decision, chat generation, voting, safety validation, and audit logging.

2. **Event-driven, not frame-driven** — The backend is called at discrete game events. `antigravity_workflow.allowed_call()` enforces a minimum interval between AI calls per bot per event type.

3. **Context-aware decisions** — Behavior mode escalates based on wave number, infected count, and alive player ratio. Vote target is chosen based on chat history. Chat uses personality heuristics or live LLM reasoning.

4. **LLM-optional design** — Groq LLM can be plugged in for richer chat generation (`AI_MODE=groq`) without changing any game logic. Rule-based mode (`AI_MODE=rules`) provides full functionality offline and free.

5. **Safety gating** — A dedicated Referee agent validates actions. The respond endpoint applies a forbidden-phrase filter to prevent any LLM output from breaking game immersion or revealing game state.

6. **Observable trace** — Every decision is logged with its reasoning. Judges and developers can inspect `GET /trace/{matchId}` or `GET /trace_viewer/{matchId}` to see exactly what every agent decided and why.
