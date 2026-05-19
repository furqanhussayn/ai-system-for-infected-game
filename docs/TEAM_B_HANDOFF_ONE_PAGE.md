# Team B Handoff One Page

Backend URL for local dev:

- `http://127.0.0.1:8000`

Backend URL for phone or APK testing:

- `http://<YOUR-LAN-IP>:8000`

Unity baseUrl note:

- A phone or APK cannot use `localhost` for the PC backend.
- Use the machine LAN IP or public tunnel URL instead.

Endpoint order for gameplay:

1. `GET /health`
2. `POST /register_bot` after infection
3. `POST /decide_action` every 20-30 seconds per bot
4. `POST /respond` during meetings
5. `POST /vote` during `AntidoteVote`
6. `POST /unregister_bot` after cure

Firebase files Team B needs:

- `firebase/realtime-database-rules.json`
- `firebase/sample_match_ROOM123.json`
- `firebase/unity_config/android/google-services.json` during integration

Fallback behavior if backend is down:

- Unity should fall back to local rules or no-op behavior.
- Do not block the game loop waiting on HTTP retries.

Final checklist Team B should test:

- `GET /health` returns V4 shape.
- Register and unregister work for `player_2`.
- `decide_action` returns `nextDecisionInSeconds`.
- `respond` returns `typingDelaySeconds` and `secondMessageDelaySeconds`.
- `vote` prefers a human target.
- `trace/{matchId}` shows the full interaction history.