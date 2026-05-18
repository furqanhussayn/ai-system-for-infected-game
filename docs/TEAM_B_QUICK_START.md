# Team B Quick Start

1. Run the backend.
2. Open `http://localhost:8000/docs`.
3. Test `GET /health`.
4. Set `baseUrl` in `AIDirectorClient`.
5. Call `RegisterBot()` when a bot becomes infected.
6. Call `DecideAction()` every 20-30 seconds or on major events.
7. Call `SendChatToBot()` when a meeting message mentions a bot.
8. Call `RequestBotVote()` at voting start.

Tip: Use the LAN IP or ngrok URL for mobile devices. Do not use `localhost` on a phone.
