# One-Click Demo

This is the fastest judge flow.

## Steps
1. Run the backend.
2. Open `http://localhost:8000/`.
3. Click **Run Fresh Demo**.
4. The backend clears `DEMO_ROOM`, runs the demo simulator, and redirects to the trace viewer.
5. The browser lands on `/trace_viewer/DEMO_ROOM?fresh=<timestamp>`.
6. Walk the judges through the cards:
   - register_bot
   - decide_action_early
   - respond
   - vote
   - decide_action_late
   - final_hunt

## Why it works
- The demo is rule-based and zero-cost.
- The trace viewer shows every major bot decision as a separate card.
- The redirect uses a cache-busting query string so the browser does not show stale HTML.

## What to point at during judging
- The big **Run Fresh Demo** button on the landing page.
- The trace count at the top of the viewer.
- The vote card and final hunt card.
