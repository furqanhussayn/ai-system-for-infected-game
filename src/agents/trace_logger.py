import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

LOG_DIR = Path(__file__).parent.parent.parent / "traces"
LOG_DIR.mkdir(parents=True, exist_ok=True)

_TRACE_STORE: dict[str, list[dict]] = {}
_LOCK = Lock()


def _write_trace_file(entry: dict) -> None:
    source = entry.get("source", "unknown").strip("/").replace("/", "_") or "trace"
    timestamp_suffix = entry["timestamp"].replace(":", "-")
    fp = LOG_DIR / f"{source}_{timestamp_suffix}.json"
    fp.parent.mkdir(parents=True, exist_ok=True)
    fp.write_text(json.dumps(entry, default=str))


def _to_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        return str(value)


def add_trace(match_id: str, bot_id: str, action: str, decision, trace, source: str, input_data=None, output_data=None):
    input_text = _to_text(input_data if input_data is not None else decision)
    output_text = _to_text(output_data if output_data is not None else trace)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ts": datetime.now(timezone.utc).isoformat(),
        "matchId": match_id,
        "botId": bot_id,
        "action": action,
        "eventType": action,
        "decision": decision,
        "trace": trace,
        "input": input_text,
        "output": output_text,
        "source": source,
    }
    with _LOCK:
        _TRACE_STORE.setdefault(match_id, []).append(entry)
    _write_trace_file(entry)
    return entry


def get_traces(match_id: str):
    with _LOCK:
        return list(_TRACE_STORE.get(match_id, []))


def clear_traces(match_id: str):
    with _LOCK:
        _TRACE_STORE.pop(match_id, None)
