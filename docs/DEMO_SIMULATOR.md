# Demo Simulator

This backend includes a zero-cost judge demo simulator that creates a believable mini-match without Unity.

## What it does
The demo runner simulates:
- bot registration
- early exploration decision making
- meeting accusation response
- voting
- late-game aggression
- final hunt behavior

It writes real in-memory trace logs, which show up in:
- `GET /trace/{matchId}`
- `GET /trace_viewer/{matchId}`

## How to run it
1. Start the backend.
2. Open `http://localhost:8000/docs`.
3. Call:
   - `POST /demo/run/DEMO_ROOM`
4. Open:
   - `http://localhost:8000/trace_viewer/DEMO_ROOM`

## During judging
Use the demo to show the judge:
- the bot starts in stealth mode
- the bot responds when accused
- the bot votes against an accuser when legal
- the bot becomes aggressive in late game
- the bot enters final hunt when only one human remains

## Clear and rerun
If you want to reset the demo match:
- `POST /demo/clear/DEMO_ROOM`
- then run the demo again

## Notes
- No Firebase is required.
- No Gemini or Groq keys are required.
- All behavior is rule-based and free by default.
