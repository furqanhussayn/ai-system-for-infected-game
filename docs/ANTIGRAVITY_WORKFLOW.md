# Antigravity Workflow — THE INFECTED Hackathon

## How Google Antigravity Was Used

**Google Antigravity** served as the AI-assisted development environment for building and iterating on this backend. Antigravity provided:

- **Agentic code generation** — agents, endpoints, and test scaffolding were designed and implemented through Antigravity's planning and execution workflow
- **Multi-turn reasoning** — each component was reasoned through (state → behavior → chat → vote → trace) as a sequential agent pipeline
- **Implementation planning** — the agent architecture was designed top-down, with Antigravity helping identify separation of concerns, failure modes, and safety requirements
- **Test generation** — the complete test suite in `tests/test_api.py` was planned and generated through Antigravity's workflow
- **Documentation** — this file, `AGENT_ARCHITECTURE.md`, `JUDGE_PROOF.md`, and `AI_DIRECTOR_TRACE_EXPLANATION.md` were all authored through Antigravity

Antigravity was used as a **meta-agent** that orchestrated the construction of the domain-level agents that power THE INFECTED's AI Director.

---

## Workplan

| Phase | Goal | Status |
|---|---|---|
| Phase 1 | FastAPI scaffold + health endpoint | ✅ Done |
| Phase 2 | Agent architecture (State, Behavior, Chat, Vote, Referee, Trace) | ✅ Done |
| Phase 3 | Rule-based decision engine (no LLM dependency) | ✅ Done |
| Phase 4 | Groq LLM adapter (optional, gated by AI_MODE=groq) | ✅ Done |
| Phase 5 | Safety filter / prompt hardening for LLM chat | ✅ Done |
| Phase 6 | Trace logger + trace viewer HTML endpoint | ✅ Done |
| Phase 7 | One-click demo endpoint (POST /demo/quick/{matchId}) | ✅ Done |
| Phase 8 | Landing page + judge-facing UI | ✅ Done |
| Phase 9 | Full test suite (pytest) | ✅ Done |
| Phase 10 | Judge-facing docs + Antigravity workflow proof | ✅ Done |

---

## Task Plan

### Task 1: Define Agent Responsibilities

Map each gameplay event to an agent role:

```
Game Event             → Agent
─────────────────────────────────────────────────
Match start            → StateAgent + BehaviorDirector
Wave change / task     → BehaviorDirector
Emergency meeting chat → ChatAgent + RefereeAgent
Voting phase           → VoteAgent
Every decision         → TraceLogger
```

### Task 2: Build Rule-Based Core (AI_MODE=rules)

Implement deterministic, rule-based logic for all agents:
- BehaviorDirector: wave/count heuristics for mode selection
- ChatAgent: personality templates + mention detection
- VoteAgent: accuser counter-vote + random fallback

Ensure: no external calls, works offline, free to run.

### Task 3: Add LLM Adapter (AI_MODE=groq)

Implement `src/services/llm_adapter.py`:
- Calls Groq API only if `AI_MODE=groq` and key is present
- Times out cleanly
- Falls back to rule-based on any failure

Implement `src/utils/prompt_hardening.py`:
- Injects persona constraints into system prompt
- Blocks leaked game state

### Task 4: Add Safety Gate

Implement forbidden-phrase filter in `/respond`:
- Block any LLM output containing: "ai", "model", "prompt", "groq", "backend", "i am infected", etc.
- On violation: fall back to rule-based message

### Task 5: Build Trace System

Implement `src/agents/trace_logger.py`:
- In-memory store keyed by matchId
- Disk persistence to `traces/` directory
- Each entry: timestamp, matchId, botId, action, decision, trace, source

Implement `/trace/{matchId}` → JSON
Implement `/trace_viewer/{matchId}` → HTML cards

### Task 6: One-Click Demo

Implement `POST /demo/quick/{matchId}`:
- Clears match state
- Executes full game lifecycle in sequence:
  1. register_bot
  2. decide_action (early wave, stealth)
  3. respond (meeting accusation)
  4. vote (counter-vote accuser)
  5. decide_action (late wave, aggressive)
  6. decide_action (final hunt)
- Redirects to `/trace_viewer/{matchId}?fresh=...`

### Task 7: Test Suite

Cover:
- All endpoints return 200
- Rule-based mode never calls Groq
- Groq mode falls back on missing key / exception / unsafe output
- Demo populates trace viewer with all 6 action types
- Trace viewer renders cards with data-action attributes
- Quick demo redirects correctly

### Task 8: Antigravity Workflow Endpoint + Docs

Add `GET /antigravity_workflow` → HTML summary page
Add link on landing page
Create all docs/ markdown files

---

## Reasoning Flow

The Antigravity reasoning flow used to design this system:

```
1. UNDERSTAND THE GAME
   └─ Social deduction horror game. Bots need to: hide early, hunt late,
      lie in chat, vote strategically. These are distinct behaviors
      requiring distinct agents.

2. IDENTIFY AGENT BOUNDARIES
   └─ State parsing is separate from decision logic
      Decision logic is separate from chat generation
      Chat generation is separate from safety validation
      All decisions are separate from audit logging

3. DESIGN FOR FAILURE
   └─ LLM might be unavailable → rule-based fallback ALWAYS works
      LLM might produce unsafe output → safety filter catches it
      Rate limiting ensures AI isn't called per frame

4. DESIGN FOR PROOF
   └─ Every decision logged → trace viewer proves agentic reasoning
      Demo covers full game lifecycle → judges can follow decision cards

5. DESIGN FOR EXTENSION
   └─ Groq today → Gemini tomorrow (adapter pattern)
      Rules today → neural policy tomorrow (director pattern)
      Trace today → replay/analysis tool tomorrow
```

---

## Implementation Flow

```
src/
├── agents/
│   ├── state_agent.py          ← Task 1: state parsing
│   ├── behavior_director.py    ← Task 2: core decision logic
│   ├── chat_agent.py           ← Task 3: chat generation (LLM or rules)
│   ├── vote_agent.py           ← Task 2: voting strategy
│   ├── referee_agent.py        ← Task 4: action validation
│   └── trace_logger.py         ← Task 5: audit trail
├── services/
│   ├── llm_adapter.py          ← Task 3: Groq HTTP adapter
│   └── antigravity_workflow.py ← Task 2: event-rate gating
├── api/endpoints/
│   ├── register_bot.py         ← Task 1
│   ├── decide_action.py        ← Task 2
│   ├── respond.py              ← Task 3+4
│   ├── vote.py                 ← Task 2
│   ├── trace.py                ← Task 5
│   ├── demo.py                 ← Task 6
│   └── llm_status.py           ← config inspection
├── main.py                     ← routing + landing page + workflow page
tests/
└── test_api.py                 ← Task 7: full test suite
docs/
├── AGENT_ARCHITECTURE.md       ← Task 8
├── ANTIGRAVITY_WORKFLOW.md     ← Task 8 (this file)
├── JUDGE_PROOF.md              ← Task 8
└── AI_DIRECTOR_TRACE_EXPLANATION.md ← Task 8
```

---

## Testing Flow

### Automated Tests (pytest)

```bash
python -m pytest -q
```

Test coverage:
- `test_health` — /health returns 200
- `test_landing_page` — landing page contains expected elements
- `test_llm_status_hides_api_key` — /llm/status never leaks key
- `test_ai_mode_rules_does_not_call_groq` — rules mode is Groq-free
- `test_groq_missing_key_falls_back_to_rules` — graceful fallback
- `test_groq_exception_falls_back_to_rules` — resilient to API failure
- `test_unsafe_groq_output_falls_back_to_rules` — safety filter works
- `test_valid_groq_output_splits_into_messages` — pipe-split parsing
- `test_demo_run_stays_rule_based_when_ai_mode_is_groq` — demo safety
- `test_direct_vote_logs_and_renders` — vote → trace → viewer chain
- `test_register_and_endpoints_sequence` — full API sequence
- `test_trace_viewer_shows_samples_when_empty` — empty state UX
- `test_demo_run_populates_trace_viewer` — demo populates all 6 cards
- `test_quick_demo_redirects_and_populates_trace_viewer` — one-click works
- `test_antigravity_workflow_page` — new workflow endpoint

### App Import Test

```bash
python -c "from src.main import app; print('APP_IMPORT_OK')"
```

---

## How the One-Click Demo Proves the Workflow

The `POST /demo/quick/DEMO_ROOM` endpoint is the **live proof** of the agentic workflow:

1. **Clears** any previous match state
2. **Calls** all agents in the game lifecycle sequence
3. **Every agent** logs a trace entry with its reasoning
4. **Redirects** to `/trace_viewer/DEMO_ROOM`

The trace viewer shows 6 decision cards in chronological order:
```
register_bot       → personality assigned, initial mode set
decide_action_early → wave 1, stealth mode chosen
respond            → accused in chat, bot defended itself
vote               → voted against accuser
decide_action_late → wave 3, 2 infected vs 2 humans, aggressive
final_hunt         → 3 infected vs 1 human, full hunt mode
```

A judge can:
1. Open the landing page (`/`)
2. Click "Run Fresh Demo"
3. See all 6 decision cards immediately
4. Click "Raw JSON" to inspect the structured trace data
5. See every decision, the reasoning, and the source endpoint

**No Unity client is needed for this proof.** The backend is self-demonstrating.

---

## Alignment with Challenge 4 Requirements

### ✅ AI-Driven NPC Behavior

The BehaviorDirector agent computes a distinct behavior mode for each game phase:
- `stealth_fake_task` (early game, blend in)
- `stalk` (mid game, follow targets)
- `aggressive_chase` (infected majority, apply pressure)
- `final_hunt` (1 human left, full horror mode)

These modes are returned to Unity which executes the corresponding movement and animation logic.

### ✅ Agentic Reasoning

The system uses a 6-agent pipeline:
- Each agent has a distinct role and input/output contract
- Agents are composable — BehaviorDirector builds on StateAgent output
- Agents can be extended independently (e.g., upgrade ChatAgent to use Gemini without touching VoteAgent)
- The `antigravity_workflow.allowed_call()` service enforces event-gated reasoning — decisions are not made on every frame, they are made at meaningful game events

### ✅ State Management

- `src/core/state.py` maintains an in-memory bot registry keyed by `(matchId, botId)`
- Bot personality, behavior mode, and room are persisted across calls within a match
- `clear_match()` allows clean session resets for the demo and testing

### ✅ Referee / Fair Play

- `RefereeAgent.validate()` is the explicit hook for legality checking
- The forbidden-phrase filter in `/respond` prevents bots from revealing game state or breaking immersion
- Prompt hardening in `src/utils/prompt_hardening.py` prevents prompt injection attacks when LLM mode is active
- Rate limiting prevents any bot from acting more than once per event window

### ✅ Visible Trace Logs

- Every agent decision calls `add_trace()` with action + decision + reasoning
- `GET /trace/{matchId}` → full JSON audit trail
- `GET /trace_viewer/{matchId}` → HTML card view for judges
- `GET /trace_debug/{matchId}` → action summary for quick inspection
- Traces persist to disk (`traces/` directory) across server restarts
- The one-click demo produces a complete trace that judges can inspect in real time
