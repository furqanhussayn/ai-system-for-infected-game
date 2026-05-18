# Final Demo Flow

This is the exact judge-facing demo sequence for the backend-only stage.

## 1. Run the backend
Use the local dev script or run Uvicorn directly.

## 2. Open the landing page
Open `http://localhost:8000/`.
You should see:
- backend status online
- links to health, Swagger, demo guide, trace viewer, and trace JSON
- the exact demo instructions

## 3. Open Swagger
Open `http://localhost:8000/docs`.
Use the Swagger UI to call:
- `POST /demo/clear/DEMO_ROOM`
- `POST /demo/run/DEMO_ROOM`

## 4. Run the demo simulator
Call `POST /demo/run/DEMO_ROOM`.
This generates real rule-based logs for:
- register_bot
- stealth_fake_task
- respond/chat
- vote
- aggressive_chase
- final_hunt

## 5. Open the trace viewer
Open `http://localhost:8000/trace_viewer/DEMO_ROOM`.
The viewer shows each trace as a judge-friendly card.

## 6. Explain the logs
Walk the judge through:
- when the bot was registered
- why it stayed stealthy early
- how it responded to accusation
- how it voted
- how it escalated late game
- how it entered final hunt

## Notes
- No Unity integration is required for this backend-only demo.
- No Firebase or Gemini/Groq is required.
- The demo is rule-based and free by default.
