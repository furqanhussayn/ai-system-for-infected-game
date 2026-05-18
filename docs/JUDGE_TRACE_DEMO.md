# Judge Trace Demo

## What it is
The trace viewer is a judge-facing page that shows the backend's in-memory agent decisions as readable cards.

## URLs
- JSON trace feed: `GET /trace/{matchId}`
- HTML viewer: `GET /trace_viewer/{matchId}`

## How to use it in the demo
1. Run the backend locally.
2. Trigger a few actions in the game or by Swagger:
   - `POST /register_bot`
   - `POST /decide_action`
   - `POST /respond`
   - `POST /vote`
3. Open the viewer:
   - `http://localhost:8000/trace_viewer/ROOM123`
4. Walk judges through each card:
   - timestamp
   - matchId
   - botId
   - endpoint/action
   - decision
   - trace/reason

## If there are no live logs
- The viewer shows helpful sample cards so the demo still works.
- This is intentional and useful for early demo rehearsals.

## Recommended demo flow
- Start with `GET /health`.
- Show one bot registration.
- Show one decision update.
- Show one meeting response.
- Show one vote.
- Open the trace viewer and explain how the backend is making the bot feel human.

## Notes
- No Firebase is required for the viewer.
- No Gemini/Groq is required for the viewer.
- The viewer is rule-based and free by default.
