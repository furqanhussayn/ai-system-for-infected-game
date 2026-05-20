from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from src.api.endpoints import register_bot, unregister_bot, decide_action, respond, vote, trace, demo, llm_status, chat_lab
from src.core import config

app = FastAPI(title="Infected - Team A Antigravity API")

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(register_bot.router, prefix="/register_bot", tags=["register"])
app.include_router(unregister_bot.router, prefix="/unregister_bot", tags=["unregister"])
app.include_router(decide_action.router, prefix="/decide_action", tags=["decide"])
app.include_router(respond.router, prefix="/respond", tags=["respond"])
app.include_router(vote.router, prefix="/vote", tags=["vote"])
app.include_router(trace.router, prefix="/trace", tags=["trace"])
app.include_router(trace.viewer_router, tags=["trace-viewer"])
app.include_router(trace.debug_router, tags=["trace-debug"])
app.include_router(llm_status.router)
app.include_router(demo.router, tags=["demo"])
app.include_router(chat_lab.router, tags=["chat-lab"])


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "infected-ai-backend",
        "contractVersion": "v4",
        "aiMode": config.AI_MODE,
        "llmProvider": config.LLM_PROVIDER,
        "firebaseConfigured": config.FIREBASE_CONFIGURED,
    }


@app.get("/", response_class=HTMLResponse)
async def landing_page():
        html = """
        <!doctype html>
        <html lang="en">
        <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>THE INFECTED — Agentic AI Backend</title>
            <style>
                :root { color-scheme: dark; }
                body {
                    margin: 0;
                    font-family: Arial, sans-serif;
                    background: radial-gradient(circle at top, #1a1a2e 0%, #0a0a0f 55%);
                    color: #e8e8f0;
                }
                .wrap { max-width: 1080px; margin: 0 auto; padding: 28px; }
                .hero {
                    background: linear-gradient(135deg, rgba(45,53,97,0.92), rgba(26,26,46,0.96));
                    border: 1px solid #313d74;
                    border-radius: 20px;
                    padding: 28px;
                    box-shadow: 0 24px 48px rgba(0,0,0,0.35);
                }
                h1 { margin: 0 0 10px; font-size: 38px; letter-spacing: 0.02em; }
                .status {
                    display: inline-block;
                    padding: 8px 14px;
                    border-radius: 999px;
                    background: rgba(0, 255, 156, 0.12);
                    border: 1px solid rgba(0, 255, 156, 0.45);
                    color: #00ff9c;
                    font-weight: 700;
                    margin-bottom: 16px;
                }
                .demo-form { margin-top: 18px; }
                .demo-button {
                    display: inline-block;
                    appearance: none;
                    border: 0;
                    cursor: pointer;
                    padding: 16px 22px;
                    border-radius: 14px;
                    text-decoration: none;
                    color: #0a0a0f;
                    background: linear-gradient(135deg, #00ff9c, #f5a623);
                    font-weight: 900;
                    font-size: 18px;
                    box-shadow: 0 12px 28px rgba(0,0,0,0.32);
                }
                .links { margin-top: 16px; }
                .links a {
                    display: inline-block;
                    margin: 8px 10px 0 0;
                    padding: 10px 14px;
                    border-radius: 10px;
                    text-decoration: none;
                    color: #0a0a0f;
                    background: #f5a623;
                    font-weight: 700;
                }
                .links a.secondary { background: #00ff9c; }
                .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-top: 18px; }
                .card {
                    background: rgba(10,10,15,0.68);
                    border: 1px solid #2d3561;
                    border-radius: 16px;
                    padding: 18px;
                }
                ol { padding-left: 20px; }
                li { margin: 8px 0; }
                .muted { color: #bfc4e6; line-height: 1.6; }
                .mini { font-size: 14px; color: #bfc4e6; }
                code { color: #f5a623; }
            </style>
        </head>
        <body>
            <div class="wrap">
                <section class="hero">
                    <div class="status">Backend Status: Online</div>
                    <h1>THE INFECTED — Agentic AI Backend</h1>
                    <p class="muted">Unity executes gameplay. This backend acts as the Antigravity-style AI Director for infected bot behavior, chat, voting, and trace logs.</p>
                    <form class="demo-form" method="post" action="/demo/quick/DEMO_ROOM">
                        <button class="demo-button" type="submit">▶ Run Fresh Demo</button>
                    </form>
                    <form class="demo-form" method="post" action="/demo/agent_quick/AGENT_ROOM">
                        <button class="demo-button" type="submit">▶ Run Agent Demo</button>
                    </form>
                    <div class="links">
                        <a href="/chat_lab">🎭 Chat Lab</a>
                        <a href="/trace_viewer/DEMO_ROOM">View Current Trace</a>
                        <a href="/trace/DEMO_ROOM">Raw Trace JSON</a>
                        <a href="/docs">Swagger Docs</a>
                        <a href="/health">Health Check</a>
                        <a class="secondary" href="/antigravity_workflow">Antigravity Workflow</a>
                    </div>
                </section>

                <div class="grid">
                    <section class="card">
                        <h2>Judge Demo Flow</h2>
                        <ol>
                            <li>Open <code>/docs</code></li>
                            <li>Click <strong>Run Fresh Demo</strong></li>
                            <li>Browser redirects to <code>/trace_viewer/DEMO_ROOM?fresh=...</code></li>
                            <li>Explain the trace cards to judges</li>
                        </ol>
                    </section>
                    <section class="card">
                        <h2>Quick Links</h2>
                        <p class="mini">Use the trace viewer during the demo so judges can see each bot decision card without needing Unity connected yet.</p>
                        <p class="mini">Recommended match ID: <code>DEMO_ROOM</code></p>
                    </section>
                </div>
            </div>
        </body>
        </html>
        """
        return HTMLResponse(content=html)


@app.get("/antigravity_workflow", response_class=HTMLResponse)
async def antigravity_workflow():
    html = """
    <!doctype html>
    <html lang="en">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Antigravity Workflow — THE INFECTED AI Director</title>
        <style>
            :root { color-scheme: dark; }
            body {
                margin: 0;
                font-family: Arial, sans-serif;
                background: radial-gradient(circle at top, #0d0f1e 0%, #0a0a0f 60%);
                color: #e8e8f0;
            }
            .wrap { max-width: 1100px; margin: 0 auto; padding: 28px; }
            .hero {
                background: linear-gradient(135deg, rgba(30,20,60,0.95), rgba(26,26,46,0.97));
                border: 1px solid #4b3fa0;
                border-radius: 20px;
                padding: 30px;
                box-shadow: 0 24px 48px rgba(0,0,0,0.45);
                margin-bottom: 24px;
            }
            .badge {
                display: inline-block;
                padding: 6px 14px;
                border-radius: 999px;
                background: rgba(120, 80, 255, 0.15);
                border: 1px solid rgba(120, 80, 255, 0.5);
                color: #a78bfa;
                font-weight: 700;
                font-size: 13px;
                margin-bottom: 14px;
            }
            h1 { margin: 0 0 10px; font-size: 34px; letter-spacing: 0.02em; }
            h2 { color: #a78bfa; margin: 0 0 12px; font-size: 16px; text-transform: uppercase; letter-spacing: 0.08em; }
            h3 { color: #00ff9c; margin: 0 0 8px; }
            .sub { color: #bfc4e6; line-height: 1.6; max-width: 780px; }
            .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; margin-bottom: 24px; }
            .card {
                background: rgba(10,10,20,0.80);
                border: 1px solid #2d3561;
                border-radius: 16px;
                padding: 20px;
                box-shadow: 0 8px 24px rgba(0,0,0,0.3);
            }
            .card ul { padding-left: 18px; margin: 0; }
            .card li { margin: 6px 0; color: #bfc4e6; font-size: 14px; }
            .flow {
                background: rgba(10,10,20,0.80);
                border: 1px solid #2d3561;
                border-radius: 16px;
                padding: 20px 24px;
                margin-bottom: 24px;
                font-family: monospace;
                font-size: 13px;
                color: #f5a623;
                white-space: pre-wrap;
                overflow-x: auto;
            }
            .links-bar { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 8px; }
            .links-bar a {
                display: inline-block;
                padding: 10px 16px;
                border-radius: 10px;
                text-decoration: none;
                font-weight: 700;
                font-size: 14px;
                color: #0a0a0f;
                background: #a78bfa;
            }
            .links-bar a.green { background: #00ff9c; }
            .links-bar a.amber { background: #f5a623; }
            .section-label {
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                color: #6366f1;
                margin-bottom: 10px;
            }
            table { width: 100%; border-collapse: collapse; font-size: 14px; }
            th { text-align: left; padding: 10px 12px; background: rgba(75,63,160,0.25); color: #a78bfa; border-bottom: 1px solid #2d3561; }
            td { padding: 9px 12px; border-bottom: 1px solid #1e2040; color: #d0d4f0; vertical-align: top; }
            tr:last-child td { border-bottom: none; }
            .tbl-wrap { background: rgba(10,10,20,0.80); border: 1px solid #2d3561; border-radius: 16px; overflow: hidden; margin-bottom: 24px; }
        </style>
    </head>
    <body>
        <div class="wrap">
            <section class="hero">
                <div class="badge">Google Antigravity · Workflow Proof</div>
                <h1>Antigravity AI Director</h1>
                <p class="sub">
                    This backend is the agentic brain for <strong>THE INFECTED</strong> — a Unity mobile social deduction horror game.
                    Built and iterated through Google Antigravity, it coordinates 6 specialised agents to drive infected NPC
                    behavior, chat, voting, and full decision tracing.
                </p>
                <div class="links-bar" style="margin-top:20px;">
                    <a class="green" href="/">Home</a>
                    <a class="amber" href="/docs">Swagger Docs</a>
                    <a href="/demo/quick/DEMO_ROOM">▶ Run Demo</a>
                    <a href="/trace_viewer/DEMO_ROOM">Trace Viewer</a>
                    <a href="/llm/status">LLM Status</a>
                </div>
            </section>

            <div class="section-label">Agent Pipeline</div>
            <div class="grid">
                <div class="card">
                    <h3>State Agent</h3>
                    <ul>
                        <li>Parses raw Unity payloads</li>
                        <li>Normalises wave, phase, alive list</li>
                        <li>Feeds all downstream agents</li>
                        <li>Triggered by: <code>/register_bot</code></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>Behavior Director Agent</h3>
                    <ul>
                        <li>Rule engine: wave × ratio → mode</li>
                        <li>Modes: stealth → stalk → chase → hunt</li>
                        <li>Event-gated via antigravity_workflow</li>
                        <li>Triggered by: <code>/decide_action</code></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>Chat Agent</h3>
                    <ul>
                        <li>Personality-matched templates (rules)</li>
                        <li>Groq LLM optional (AI_MODE=groq)</li>
                        <li>Mention detection → forced reply</li>
                        <li>Triggered by: <code>/respond</code></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>Vote Agent</h3>
                    <ul>
                        <li>Reads recent chat for accusers</li>
                        <li>Counter-votes accuser strategically</li>
                        <li>Falls back to random human pick</li>
                        <li>Triggered by: <code>/vote</code></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>Referee / Safety Agent</h3>
                    <ul>
                        <li>Validates action legality</li>
                        <li>Forbidden-phrase filter for chat</li>
                        <li>Prompt hardening against injection</li>
                        <li>Active in: <code>/respond</code></li>
                    </ul>
                </div>
                <div class="card">
                    <h3>Trace Logger Agent</h3>
                    <ul>
                        <li>Logs every decision with reasoning</li>
                        <li>In-memory + disk persistence</li>
                        <li>Powers trace_viewer HTML cards</li>
                        <li>Called by: all endpoints</li>
                    </ul>
                </div>
            </div>

            <div class="section-label">Decision Flow</div>
            <div class="flow">Unity Event  →  HTTP POST  →  State Agent  →  Behavior Director
                                                                  ↓
                                                         Chat Agent  +  Vote Agent
                                                                  ↓
                                                        Referee / Safety Gate
                                                                  ↓
                                                        Trace Logger  →  /trace_viewer
                                                                  ↓
                                                         JSON Response  →  Unity Acts</div>

            <div class="section-label">Endpoint → Agent Mapping</div>
            <div class="tbl-wrap">
                <table>
                    <thead>
                        <tr><th>Endpoint</th><th>Agents Invoked</th><th>Trace Action</th></tr>
                    </thead>
                    <tbody>
                        <tr><td>POST /register_bot</td><td>StateAgent → BehaviorDirector → TraceLogger</td><td>register_bot</td></tr>
                        <tr><td>POST /decide_action</td><td>BehaviorDirector → TraceLogger</td><td>decide_action_early / late / final_hunt</td></tr>
                        <tr><td>POST /respond</td><td>ChatAgent → RefereeAgent → TraceLogger</td><td>respond</td></tr>
                        <tr><td>POST /vote</td><td>VoteAgent → TraceLogger</td><td>vote</td></tr>
                        <tr><td>GET /trace/{matchId}</td><td>TraceLogger (read)</td><td>—</td></tr>
                        <tr><td>GET /trace_viewer/{matchId}</td><td>TraceLogger (read) → HTML</td><td>—</td></tr>
                        <tr><td>POST /demo/quick/{matchId}</td><td>All agents in sequence</td><td>All 6 types</td></tr>
                    </tbody>
                </table>
            </div>

            <div class="section-label">AI Mode</div>
            <div class="tbl-wrap">
                <table>
                    <thead>
                        <tr><th>Mode</th><th>Chat Source</th><th>Cost</th><th>Offline</th></tr>
                    </thead>
                    <tbody>
                        <tr><td><strong>rules</strong> (default)</td><td>Personality templates</td><td>Free</td><td>✅ Yes</td></tr>
                        <tr><td><strong>groq</strong></td><td>Llama-3.3-70b via Groq API</td><td>API credits</td><td>❌ No</td></tr>
                    </tbody>
                </table>
            </div>

            <p class="sub" style="font-size:13px; margin-top:0;">
                AI calls are <strong>event-driven, not frame-driven</strong>.
                The <code>antigravity_workflow.allowed_call()</code> service enforces a minimum interval between
                agent calls per bot per event type — preventing runaway LLM costs and ensuring predictable timing.
            </p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# trace endpoint registered above
