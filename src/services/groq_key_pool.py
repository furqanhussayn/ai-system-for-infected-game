from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import time

from src.core import config


@dataclass
class GroqKeySlot:
    key_id: str
    key_value: str
    is_available: bool = False
    cooldown_until: float = 0.0
    last_error: str = ""
    last_success_at: float = 0.0
    last_failed_at: float = 0.0
    metadata: dict[str, object] = field(default_factory=dict)


_KEY_ORDER = ("groq_key_1", "groq_key_2", "groq_key_3")
_KEY_ENV_NAMES = {
    "groq_key_1": "GROQ_API_KEY",
    "groq_key_2": "GROQ_API_KEY_2",
    "groq_key_3": "GROQ_API_KEY_3",
}
_KEY_POOL: dict[str, GroqKeySlot] = {}


def _now() -> float:
    return time.time()


def _iso_from_ts(value: float) -> str:
    if not value:
        return ""
    return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()


def _cooldown_expired(slot: GroqKeySlot, now: float | None = None) -> bool:
    current_time = _now() if now is None else now
    return slot.cooldown_until <= current_time


def _build_slot(key_id: str, key_value: str, existing: GroqKeySlot | None = None) -> GroqKeySlot:
    slot = existing or GroqKeySlot(key_id=key_id, key_value=key_value)
    slot.key_value = key_value
    slot.is_available = bool(key_value.strip()) and _cooldown_expired(slot)
    if not key_value.strip():
        slot.cooldown_until = 0.0
        slot.last_error = ""
    return slot


def load_groq_keys() -> list[GroqKeySlot]:
    now = _now()
    slots: list[GroqKeySlot] = []
    for key_id in _KEY_ORDER:
        env_name = _KEY_ENV_NAMES[key_id]
        key_value = str(getattr(config, env_name, "") or "").strip()
        slot = _build_slot(key_id, key_value, _KEY_POOL.get(key_id))
        slot.is_available = bool(key_value) and _cooldown_expired(slot, now)
        _KEY_POOL[key_id] = slot
        if key_value:
            slots.append(slot)
    return list(slots)


def get_available_groq_keys() -> list[GroqKeySlot]:
    load_groq_keys()
    now = _now()
    available: list[GroqKeySlot] = []
    for key_id in _KEY_ORDER:
        slot = _KEY_POOL.get(key_id)
        if slot is None or not slot.key_value.strip():
            continue
        slot.is_available = _cooldown_expired(slot, now)
        if slot.is_available:
            available.append(slot)
    return available


def get_groq_key_slot(key_id: str) -> GroqKeySlot | None:
    load_groq_keys()
    slot = _KEY_POOL.get(key_id)
    if slot is None or not slot.key_value.strip():
        return None
    slot.is_available = _cooldown_expired(slot)
    return slot


def mark_key_success(key_id: str) -> None:
    load_groq_keys()
    slot = _KEY_POOL.get(key_id)
    if slot is None:
        return
    now = _now()
    slot.last_success_at = now
    slot.last_error = ""
    slot.last_failed_at = 0.0
    slot.cooldown_until = 0.0
    slot.is_available = True


def mark_key_failed(key_id: str, reason: str, cooldown_seconds: int) -> None:
    load_groq_keys()
    slot = _KEY_POOL.get(key_id)
    if slot is None:
        return
    now = _now()
    cooldown = max(0, int(cooldown_seconds or 0))
    slot.last_failed_at = now
    slot.last_error = str(reason or "")
    slot.cooldown_until = now + cooldown if cooldown else now
    slot.is_available = bool(slot.key_value.strip()) and cooldown == 0


def mark_key_rate_limited(key_id: str, cooldown_seconds: int) -> None:
    mark_key_failed(key_id, "rate_limited", cooldown_seconds)


def get_key_pool_status() -> dict:
    load_groq_keys()
    now = _now()
    keys: list[dict[str, object]] = []
    available = 0
    cooldown_count = 0
    for key_id in _KEY_ORDER:
        slot = _KEY_POOL.get(key_id)
        if slot is None:
            continue
        is_available = bool(slot.key_value.strip()) and _cooldown_expired(slot, now)
        slot.is_available = is_available
        if slot.key_value.strip():
            if is_available:
                available += 1
            if slot.cooldown_until > now:
                cooldown_count += 1
        keys.append(
            {
                "keyId": slot.key_id,
                "available": is_available,
                "cooldownUntil": _iso_from_ts(slot.cooldown_until),
                "lastError": slot.last_error,
                "lastSuccessAt": _iso_from_ts(slot.last_success_at),
                "lastFailedAt": _iso_from_ts(slot.last_failed_at),
            }
        )
    return {
        "keyCount": len([slot for slot in _KEY_POOL.values() if slot.key_value.strip()]),
        "availableKeys": available,
        "cooldownKeys": cooldown_count,
        "keys": keys,
    }