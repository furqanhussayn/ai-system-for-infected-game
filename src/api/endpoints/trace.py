from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, JSONResponse
from src.models.schemas import TraceResponse
from src.agents.trace_logger import get_traces, clear_traces

router = APIRouter()
viewer_router = APIRouter()
debug_router = APIRouter()

def _sample_traces(match_id: str) -> list[dict]:
    return [
        {
            "timestamp": "2026-05-18T12:00:00Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "register_bot",
            "decision": "personality=deflector, behaviorMode=stealth_fake_task",
            "reason": "Registered bot with personality deflector and early stealth behavior.",
            "trace": "Registered bot with personality deflector and early stealth behavior.",
            "source": "/demo/sample",
        },
        {
            "timestamp": "2026-05-18T12:00:20Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "decide_action_early",
            "decision": "stealth_fake_task",
            "reason": "Early wave. Bot should fake tasks and avoid obvious aggression.",
            "trace": "Early wave. Bot should fake tasks and avoid obvious aggression.",
            "source": "/demo/sample",
        },
        {
            "timestamp": "2026-05-18T12:01:00Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "respond",
            "decision": "bro what?? | i was literally doing wires",
            "reason": "Bot was directly accused, so it denied and defended itself.",
            "trace": "Bot was directly accused, so it denied and defended itself.",
            "source": "/demo/sample",
        },
        {
            "timestamp": "2026-05-18T12:01:20Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "vote",
            "decision": "player_1",
            "reason": "Player 1 accused the bot, so bot voted against them.",
            "trace": "Player 1 accused the bot, so bot voted against them.",
            "source": "/demo/sample",
        },
        {
            "timestamp": "2026-05-18T12:02:00Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "decide_action_late",
            "decision": "aggressive_chase",
            "reason": "Infected majority approaching. Increase pressure.",
            "trace": "Infected majority approaching. Increase pressure.",
            "source": "/demo/sample",
        },
        {
            "timestamp": "2026-05-18T12:03:00Z",
            "matchId": match_id,
            "botId": "player_2",
            "action": "final_hunt",
            "decision": "final_hunt",
            "reason": "3 infected vs 1 human. Full horror survival mode.",
            "trace": "3 infected vs 1 human. Full horror survival mode.",
            "source": "/demo/sample",
        },
    ]


def _normalize_trace(trace_item: dict) -> dict:
    if {
        "ts",
        "eventType",
        "matchId",
        "botId",
        "input",
        "output",
        "trace",
    }.issubset(trace_item.keys()):
        return trace_item

    output = trace_item.get("output", {}) if isinstance(trace_item.get("output", {}), dict) else {}
    action = trace_item.get("action") or trace_item.get("event", "unknown")
    decision = trace_item.get("decision") or output.get("behaviorMode") or output.get("voteTarget") or output.get("messages") or ""
    if isinstance(decision, list):
        decision = " | ".join(decision)
    if not decision:
        decision = str(output)
    trace_text = trace_item.get("trace") or output.get("trace") or output.get("reason") or ""
    return {
        "timestamp": trace_item.get("timestamp") or trace_item.get("ts", "unknown"),
        "ts": trace_item.get("ts") or trace_item.get("timestamp", "unknown"),
        "matchId": trace_item.get("matchId", "unknown"),
        "botId": trace_item.get("botId") or trace_item.get("input", {}).get("botId") or "unknown",
        "action": action,
        "eventType": trace_item.get("eventType") or action,
        "decision": decision,
        "input": trace_item.get("input") or "",
        "output": trace_item.get("output") or "",
        "trace": trace_text,
        "source": trace_item.get("source") or f"/{action}",
    }


def _render_cards(trace_items: list[dict], empty: bool = False) -> tuple[str, str, int]:
    if empty:
        trace_items = _sample_traces("ROOM123")
        header = "No live traces yet. Showing sample logs for demo readiness."
    else:
        header = f"Showing {len(trace_items)} trace events for {{matchId}}"

    cards = []
    for item in trace_items:
        action = item.get("action", "unknown")
        timestamp = item.get("timestamp", "unknown")
        match_id = item.get("matchId", "unknown")
        bot_id = item.get("botId", "unknown")
        decision = item.get("decision", "")
        trace_text = item.get("trace", "")
        source = item.get("source", "")
        cards.append(
            f"""
            <article class=\"trace-card card\" data-action=\"{escape(str(action))}\">
              <div class=\"meta\">{escape(str(timestamp))}</div>
              <h3>{escape(str(action))}</h3>
              <div><strong>matchId:</strong> {escape(str(match_id))}</div>
              <div><strong>botId:</strong> {escape(str(bot_id))}</div>
              <div><strong>decision:</strong> {escape(str(decision))}</div>
              <div><strong>trace:</strong> {escape(str(trace_text))}</div>
              <div><strong>source:</strong> {escape(str(source))}</div>
            </article>
            """
        )

    return "\n".join(cards), header, len(trace_items)

@router.get('/{matchId}', response_model=TraceResponse)
async def get_trace(matchId: str):
    traces = [_normalize_trace(trace) for trace in get_traces(matchId)]
    return {"matchId": matchId, "count": len(traces), "traces": traces}


@debug_router.get('/trace_debug/{matchId}')
async def trace_debug(matchId: str):
    traces = [_normalize_trace(trace) for trace in get_traces(matchId)]
    actions = [trace["eventType"] for trace in traces]
    return {"matchId": matchId, "count": len(traces), "actions": actions, "traces": traces}


@viewer_router.get('/trace_viewer/{matchId}', response_class=HTMLResponse)
async def trace_viewer(matchId: str):
    traces = [_normalize_trace(trace) for trace in get_traces(matchId)]
    cards_html, header, count = _render_cards(traces, empty=(len(traces) == 0))
    header_text = header.format(matchId=matchId)
    html = f"""
    <!doctype html>
    <html lang=\"en\">
    <head>
      <meta charset=\"utf-8\" />
      <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
      <title>Antigravity Agent Trace - {escape(matchId)}</title>
            <style>
                :root {{ color-scheme: dark; }}
                body {{ margin: 0; font-family: Arial, sans-serif; background: #0a0a0f; color: #e8e8f0; }}
                .wrap {{ max-width: 1100px; margin: 0 auto; padding: 24px; }}
                .hero {{ background: linear-gradient(135deg, #1a1a2e, #2d3561); border: 1px solid #313d74; padding: 20px; border-radius: 16px; margin-bottom: 18px; }}
                h1 {{ margin: 0 0 8px; font-size: 28px; }}
                .sub {{ color: #bfc4e6; }}
                .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
                .card {{ background: rgba(26, 26, 46, 0.92); border: 1px solid #2d3561; border-radius: 14px; padding: 16px; box-shadow: 0 10px 24px rgba(0,0,0,0.28); }}
                .card h3 {{ margin: 8px 0 10px; text-transform: uppercase; letter-spacing: 0.06em; color: #00ff9c; }}
                .meta {{ font-size: 12px; color: #f5a623; }}
                .hint {{ margin-top: 16px; color: #b8b8ca; font-size: 14px; }}
                strong {{ color: #f5a623; }}
                .top-links {{ margin-top: 16px; display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }}
                .top-links a {{ color: #0a0a0f; background: #00ff9c; padding: 8px 12px; border-radius: 10px; text-decoration: none; font-weight: 700; }}
            </style>
        </head>
        <body>
            <div class=\"wrap\">
                <section class=\"hero\">
                    <h1>Antigravity Agent Trace</h1>
                    <div class=\"sub\">Match: {escape(matchId)}</div>
                    <p class=\"sub\">{escape(header_text)}</p>
                    <div class=\"top-links\">
                        <a href=\"/trace/{escape(matchId)}\">Raw JSON</a>
                    </div>
                </section>
                <section class=\"grid\">{cards_html}</section>
                <p class=\"hint\">Tip: use this page during the demo so judges can see every major AI decision without needing Unity connected yet.</p>
            </div>
        </body>
        </html>
        """
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0", "Pragma": "no-cache", "Expires": "0"})
