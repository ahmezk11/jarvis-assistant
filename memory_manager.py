import json
import os
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
    _DUBAI = ZoneInfo("Asia/Dubai")
except Exception:
    _DUBAI = None

MEMORY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "memory.json")

_DEFAULTS = {
    "user_name":            None,
    "preferred_name":       None,
    "city":                 None,
    "first_launch":         True,
    "preferences": {
        "response_style": "concise",
        "format":         "conversational",
    },
    "last_session_summary": None,
    # Long-term facts EDITH has learned about Ahmed. Each is
    # {"id": int, "text": str, "created": iso}. Injected into the system prompt
    # so they persist across sessions.
    "facts": [],
}


# ── Long-term facts ───────────────────────────────────────────

def add_fact(text: str) -> dict:
    """Remember a durable fact. Skips near-duplicates."""
    mem = load()
    facts = mem.setdefault("facts", [])
    norm = text.strip()
    for f in facts:
        if f["text"].strip().lower() == norm.lower():
            return f
    fact = {
        "id": max((f.get("id", 0) for f in facts), default=0) + 1,
        "text": norm,
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    facts.append(fact)
    save(mem)
    return fact


def list_facts() -> list[dict]:
    return load().get("facts", [])


def forget_fact(fact_id: int = None, text_fragment: str = None) -> dict | None:
    """Delete a fact by id or by matching text. Returns the removed fact."""
    mem = load()
    facts = mem.setdefault("facts", [])
    for i, f in enumerate(facts):
        match = (fact_id is not None and f.get("id") == fact_id) or (
            text_fragment and text_fragment.lower() in f["text"].lower()
        )
        if match:
            removed = facts.pop(i)
            save(mem)
            return removed
    return None


def load() -> dict:
    if os.path.exists(MEMORY_FILE):
        try:
            with open(MEMORY_FILE) as f:
                data = json.load(f)
            # fill in any keys added after first launch
            for key, val in _DEFAULTS.items():
                if key not in data:
                    data[key] = val
            return data
        except Exception:
            pass
    return dict(_DEFAULTS)


def save(memory: dict) -> None:
    with open(MEMORY_FILE, "w") as f:
        json.dump(memory, f, indent=2)


def build_claude_system_prompt(memory: dict) -> str:
    """System prompt for the Claude backend — identity/voice/rules from CLAUDE.md."""
    name = memory.get("preferred_name") or memory.get("user_name") or "Ahmed"
    city = memory.get("city") or "Dubai"

    now = datetime.now(_DUBAI) if _DUBAI else datetime.now()
    now_str = now.strftime("%A, %B %-d, %Y at %-I:%M %p")

    prompt = (
        f"You are EDITH, {name}'s proactive personal AI assistant — a chief of staff "
        f"who manages {name}'s day, tracks tasks, and keeps him informed.\n\n"
        f"User context:\n"
        f"- Name: {name} — address him as '{name}', never 'sir', never 'user'\n"
        f"- Location: {city}. For local queries (weather, time, services), default to {city} context.\n"
        f"- Current date & time: {now_str} (Asia/Dubai). This is authoritative for "
        f"'now', 'today', and 'current' — your training knowledge is older than this, "
        f"so don't assume dated events are still in the future.\n\n"
        f"Voice and tone:\n"
        f"- Direct and confident — never hedge or waffle\n"
        f"- Empathetic but not sycophantic — no 'Great question!' or 'Absolutely!'\n"
        f"- Occasionally dry humor, never forced\n"
        f"- Explain things plainly — no jargon\n"
        f"- Never say 'I'm an AI' or 'as a language model' — you are simply EDITH\n"
        f"- Keep responses short unless {name} asks for detail; brevity respects his time\n"
        f"- You are spoken aloud through a voice interface. Reply in plain conversational "
        f"prose — no markdown, asterisks, bold, bullet characters, headers, or emoji. "
        f"Write the way you would say it out loud.\n\n"
        f"Rules:\n"
        f"- Never fabricate data — calendar events, emails, tasks, weather, anything. "
        f"If you don't have access to a data source, say so briefly and move on.\n"
        f"- For live or time-sensitive facts — sports fixtures and scores, news, prices, "
        f"standings, elections, or anything 'latest'/'current'/'today' — call the "
        f"web_search tool instead of answering from memory. Never state that a dated "
        f"event is upcoming or hasn't happened without checking against the current date.\n"
        f"- When uncertain, say so plainly.\n"
        f"- Always confirm before sending emails or modifying calendar events.\n"
        f"- When drafting communications, be professional but warm."
    )

    facts = memory.get("facts") or []
    if facts:
        lines = "\n".join(f"- {f['text']}" for f in facts[-40:])
        prompt += (
            f"\n\nWhat you know about {name} (remembered from earlier conversations — "
            f"use it naturally, don't recite it back):\n{lines}"
        )

    last = memory.get("last_session_summary")
    if last:
        prompt += f"\n\nContext from your last conversation: {last}"

    return prompt


def build_system_prompt(memory: dict) -> str:
    name = memory.get("preferred_name") or memory.get("user_name")
    title = name if name else "Ahmed"

    prompt = (
        f"You are EDITH, a highly intelligent, witty, and efficient AI assistant. "
        f"You are concise but never cold. You address the user as '{title}'. "
        f"You are proactive, anticipate needs, and occasionally make dry observations. "
        f"You never say you are an AI model — you are simply EDITH."
    )

    last = memory.get("last_session_summary")
    if last:
        prompt += f"\n\nContext from your last conversation: {last}"

    return prompt
