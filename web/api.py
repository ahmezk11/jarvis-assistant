"""FastAPI bridge for the EDITH web HUD.

Wraps the existing Python backend (Claude brain + tools + integrations) behind a
small JSON API the React front-end talks to. Nothing about the assistant logic
lives here — this module only translates HTTP <-> the modules EDITH already had:
claude_client, agent_tools, task_manager, tools, briefing, and the Google/Notion
integrations.

Side-effectful tools (send email, calendar/Drive/Notion writes) stay
confirmation-gated: execute_tool() blocks on a threading.Event that the front-end
resolves via POST /api/confirms/{id}. Fail-closed — an unanswered prompt times out
and is treated as declined, exactly like the old Tkinter dialog.
"""

import os
import sys
import re
import time
import json as _json
import threading
import uuid
import requests
from datetime import datetime, timedelta

# The assistant modules live one directory up; make them importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_ROOT, ".env"))
except ImportError:
    pass

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import config
import claude_client
import ollama_client
import agents as agent_net
import elevenlabs_client as tts
import memory_manager
import agent_tools
import task_manager
import briefing
from tools import (
    get_weather, format_weather, get_news,
    get_system_stats, format_system_stats,
)
import google_integration as google
import notion_integration as notion

memory = memory_manager.load()

app = FastAPI(title="EDITH HUD API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # single-user local app
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Confirmation bridge (side-effect tools) ───────────────────────────────
# execute_tool() runs on a worker thread and blocks here until the browser
# answers. Mirrors the old thread-safe Tkinter modal.

_pending: dict = {}
_pending_lock = threading.Lock()
_reminders: list = []


def _web_confirm(title: str, detail: str) -> bool:
    cid = uuid.uuid4().hex[:12]
    entry = {"id": cid, "title": title, "detail": detail,
             "event": threading.Event(), "ok": False,
             "created": datetime.now().isoformat()}
    with _pending_lock:
        _pending[cid] = entry
    # Fail-closed: if nobody answers within two minutes, treat as declined.
    answered = entry["event"].wait(timeout=120)
    with _pending_lock:
        _pending.pop(cid, None)
    return bool(answered and entry["ok"])


def _web_reminder(text: str):
    _reminders.append({"text": text, "at": datetime.now().isoformat()})


def _retry(fn, attempts: int = 3):
    """Call fn(), retrying on transient errors. The first Google API call after
    a cold start occasionally fails a TLS handshake (SSL WRONG_VERSION_NUMBER);
    one quick retry warms it so the panels never flash empty on load."""
    last = None
    for _ in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 — surface the last error to caller
            last = exc
    raise last


agent_tools.set_context(memory, reminder_callback=_web_reminder,
                        confirm_callback=_web_confirm)


# ── Models ────────────────────────────────────────────────────────────────

class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    backend: str = "claude"  # "claude" (paid) or "local" (free, Ollama)


class NewTask(BaseModel):
    text: str
    priority: str = "normal"


class ConfirmDecision(BaseModel):
    approve: bool


# ── Status / config ───────────────────────────────────────────────────────

@app.get("/api/status")
def status():
    return {
        "name": memory.get("preferred_name") or memory.get("user_name") or "Ahmed",
        "city": memory.get("city") or "Dubai",
        "claude": claude_client.is_configured(),
        "local": ollama_client.is_available(),
        "google": google.is_available(),
        "notion": notion.is_available(),
        "tavily": bool(os.getenv("TAVILY_API_KEY")),
        "news": bool(os.getenv("NEWS_API_KEY")),
    }


# ── Chat (Claude brain + tools) ───────────────────────────────────────────

@app.post("/api/chat")
def chat(req: ChatRequest):
    """Run one turn through the selected brain with full tool use. Sync def →
    FastAPI runs it on a worker thread, so /api/confirms polling stays responsive
    while a side-effect tool waits for approval."""
    convo = [{"role": m.role, "content": m.content} for m in req.messages
             if m.role in ("user", "assistant") and m.content]
    system = memory_manager.build_claude_system_prompt(memory)
    agent_tools.set_backend(req.backend)  # delegated agents inherit this brain
    try:
        if req.backend == "local":
            if not ollama_client.is_available():
                raise HTTPException(503, "Local model unavailable — is Ollama running?")
            reply = ollama_client.call_ollama(convo, system=system)
        else:
            if not claude_client.is_configured():
                raise HTTPException(503, "Claude isn't configured — set ANTHROPIC_API_KEY.")
            reply = claude_client.call_claude(convo, system=system)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(500, str(exc))
    return {"reply": reply}


# ── Pending confirmations ─────────────────────────────────────────────────

@app.get("/api/confirms")
def list_confirms():
    with _pending_lock:
        return [{"id": e["id"], "title": e["title"], "detail": e["detail"]}
                for e in _pending.values()]


@app.post("/api/confirms/{cid}")
def resolve_confirm(cid: str, decision: ConfirmDecision):
    with _pending_lock:
        entry = _pending.get(cid)
    if not entry:
        raise HTTPException(404, "No such pending confirmation.")
    entry["ok"] = decision.approve
    entry["event"].set()
    return {"ok": True}


@app.get("/api/reminders")
def reminders():
    return _reminders[-20:]


# ── Briefing ──────────────────────────────────────────────────────────────

@app.get("/api/briefing")
def get_briefing(polish: bool = False):
    raw = briefing.build_briefing(memory, config)
    if polish and claude_client.is_configured():
        try:
            raw = claude_client.call_claude(
                [{"role": "user", "content": (
                    "Here is my raw morning briefing data:\n\n" + raw +
                    "\n\nRewrite this as a tight, natural morning briefing in your "
                    "voice. Keep every fact; don't invent anything.")}],
                system=memory_manager.build_claude_system_prompt(memory),
                use_tools=False,
            )
        except Exception:
            pass
    return {"text": raw}


# ── System stats ──────────────────────────────────────────────────────────

@app.get("/api/system")
def system():
    stats = get_system_stats()
    stats["summary"] = format_system_stats(stats)
    return stats


# ── Weather ───────────────────────────────────────────────────────────────

@app.get("/api/weather")
def weather(city: str | None = None):
    city = city or memory.get("city") or "Dubai"
    w = get_weather(city)
    if not w:
        return {"city": city, "available": False}
    return {"city": city, "available": True, "summary": format_weather(w), **w}


# ── News ──────────────────────────────────────────────────────────────────

@app.get("/api/news")
def news(count: int = 5):
    return {"headlines": get_news(config.NEWS_CATEGORY, count)}


# ── Tasks ─────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
def tasks():
    return {
        "tasks": task_manager.list_tasks(include_done=True),
        "pending": len(task_manager.list_tasks()),
        "done_today": len(task_manager.done_today()),
    }


@app.post("/api/tasks")
def add_task(body: NewTask):
    return task_manager.add_task(body.text, body.priority)


@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int):
    t = task_manager.complete_task(task_id=task_id)
    if not t:
        raise HTTPException(404, "No matching pending task.")
    return t


@app.delete("/api/tasks/{task_id}")
def delete_task(task_id: int):
    t = task_manager.delete_task(task_id)
    if not t:
        raise HTTPException(404, "No task with that id.")
    return t


# ── Calendar (Google) ─────────────────────────────────────────────────────

@app.get("/api/calendar")
def calendar():
    if not google.is_available():
        return {"connected": False, "events": []}
    now = datetime.now().astimezone()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    end = now.replace(hour=23, minute=59, second=59, microsecond=0).isoformat()
    try:
        events = _retry(lambda: google.list_events(start, end))
    except Exception as exc:
        return {"connected": True, "error": str(exc), "events": []}
    return {"connected": True, "events": events}


# ── Inbox (Google) ────────────────────────────────────────────────────────

@app.get("/api/inbox")
def inbox(max_results: int = 8):
    if not google.is_available():
        return {"connected": False, "unread": 0, "emails": []}
    try:
        count = _retry(google.unread_count)
        emails = _retry(lambda: google.list_unread(max_results))
    except Exception as exc:
        return {"connected": True, "error": str(exc), "unread": 0, "emails": []}
    return {"connected": True, "unread": count, "emails": emails}


# ── Football (Premier League + World Cup) ─────────────────────────────────
# No free structured API covers the live 2026 World Cup, so we let Claude pull
# it via web_search and return structured JSON. Cached with stale-while-
# revalidate so the widget is instant and we only hit Claude every ~15 min.

_football = {"data": None, "at": 0.0, "error": None, "error_at": 0.0}
_football_lock = threading.Lock()
_football_refreshing = threading.Event()
FOOTBALL_TTL = 900  # seconds
FOOTBALL_BACKOFF = 300  # after an error, wait this long before retrying


def _parse_json_block(text: str):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return _json.loads(m.group(0))
    except Exception:
        return None


# Premier League comes from TheSportsDB (free, no API key, no Claude) — only the
# live World Cup needs Claude + web search, so the widget keeps working (PL at
# least) even when Claude credits are out.
_TSDB = "https://www.thesportsdb.com/api/v1/json/3"
_PL_LEAGUE_ID = "4328"
_TEAM_ALIASES = {
    "Manchester United": "Man Utd", "Manchester City": "Man City",
    "Tottenham Hotspur": "Tottenham", "Wolverhampton Wanderers": "Wolves",
    "Nottingham Forest": "Nott'm Forest", "Brighton and Hove Albion": "Brighton",
    "West Ham United": "West Ham", "Newcastle United": "Newcastle",
    "Sheffield United": "Sheffield Utd", "Leeds United": "Leeds",
}


def _short_team(name: str) -> str:
    name = (name or "").replace(" FC", "").strip()
    return _TEAM_ALIASES.get(name, name)


def _fmt_fixture(date_s: str, time_s: str) -> str:
    try:
        d = datetime.strptime(date_s, "%Y-%m-%d")
        out = d.strftime("%a %-d %b")
        if time_s and time_s[:5] not in ("00:00", ""):
            out += " " + time_s[:5]
        return out
    except Exception:
        return date_s or ""


def _fetch_pl():
    """Premier League fixtures/results from TheSportsDB. Returns a competition
    dict or None on failure."""
    try:
        nxt = requests.get(f"{_TSDB}/eventsnextleague.php?id={_PL_LEAGUE_ID}", timeout=8).json().get("events") or []
        past = requests.get(f"{_TSDB}/eventspastleague.php?id={_PL_LEAGUE_ID}", timeout=8).json().get("events") or []
    except Exception:
        return None

    off_season = False
    resumes = ""
    if nxt:
        try:
            nd = datetime.strptime(nxt[0]["dateEvent"], "%Y-%m-%d")
            off_season = (nd - datetime.now()).days > 25
            resumes = nd.strftime("%-d %b")
        except Exception:
            pass

    matches = []
    if not off_season:  # in season → show a couple of recent results too
        for e in past[:2]:
            hs, a = e.get("intHomeScore"), e.get("intAwayScore")
            detail = f"{hs}-{a} FT" if hs not in (None, "") else _fmt_fixture(e.get("dateEvent"), e.get("strTime"))
            matches.append({"home": _short_team(e.get("strHomeTeam")), "away": _short_team(e.get("strAwayTeam")),
                            "detail": detail, "state": "finished"})
    for e in nxt[:5]:
        matches.append({"home": _short_team(e.get("strHomeTeam")), "away": _short_team(e.get("strAwayTeam")),
                        "detail": _fmt_fixture(e.get("dateEvent"), e.get("strTime")), "state": "upcoming"})

    status = f"Off-season · resumes {resumes}" if off_season else ("Fixtures" if matches else "No data")
    return {"status": status, "matches": matches[:6]}


def _fetch_football():
    """Premier League only, from TheSportsDB — free, no API key, no Claude."""
    err = None
    try:
        pl = _fetch_pl()
        if pl is None:
            err = "unavailable"
        data = {"premier_league": pl or {"status": "unavailable", "matches": []}}
        with _football_lock:
            _football["data"] = data
            _football["at"] = time.time()
    except Exception as exc:
        err = "unavailable"
        print(f"[football] fetch error: {type(exc).__name__}: {exc}", flush=True)
    finally:
        with _football_lock:
            _football["error"] = err
            _football["error_at"] = time.time() if err else 0.0
        _football_refreshing.clear()


@app.get("/api/football")
def football():
    now = time.time()
    with _football_lock:
        data = _football["data"]
        age = now - _football["at"]
        error = _football["error"]
        err_age = now - _football["error_at"]
    stale = data is None or age > FOOTBALL_TTL
    backing_off = error is not None and err_age < FOOTBALL_BACKOFF
    if stale and not backing_off and not _football_refreshing.is_set():
        _football_refreshing.set()
        threading.Thread(target=_fetch_football, daemon=True).start()
    return {"data": data, "loading": data is None and error is None, "error": error}


# Warm the football cache at boot so the widget is ready by first page load
# (the fetch takes ~40s via web search). Runs once per server process.
_football_refreshing.set()
threading.Thread(target=_fetch_football, daemon=True).start()


# ── Scheduled jobs (auto briefing, end-of-day, calendar alerts) ───────────
# These used to run only inside the Tkinter app's event loop, so they never
# fired for the web HUD. A thread-driven scheduler now pushes each event onto
# an announcement queue that the front-end polls, speaks and notifies on.

import scheduler as scheduler_mod  # noqa: E402 — after sys.path setup above

_announcements: list = []
_ann_lock = threading.Lock()


def _announce(kind: str, text: str) -> None:
    with _ann_lock:
        _announcements.append({
            "id": uuid.uuid4().hex[:12],
            "kind": kind,
            "text": text,
            "at": datetime.now().isoformat(timespec="seconds"),
        })
        del _announcements[:-20]  # keep the queue bounded


def _sched_briefing() -> None:
    memory["last_briefing_date"] = datetime.now().date().isoformat()
    memory_manager.save(memory)
    _announce("briefing", briefing.build_briefing(memory, config))


def _sched_end_of_day() -> None:
    """Write the daily log and announce a short summary."""
    memory["last_eod_date"] = datetime.now().date().isoformat()
    memory_manager.save(memory)
    done = task_manager.done_today()
    pending = task_manager.list_tasks()
    lines = [f"Good evening, Ahmed. Here's your day."]
    lines.append(f"You completed {len(done)} task{'s' if len(done) != 1 else ''} today."
                 if done else "No tasks completed today.")
    if pending:
        lines.append(f"{len(pending)} still pending.")
    summary = " ".join(lines)

    log_dir = os.path.join(_ROOT, "daily_log")
    try:
        os.makedirs(log_dir, exist_ok=True)
        today = datetime.now().strftime("%Y-%m-%d")
        with open(os.path.join(log_dir, f"{today}.md"), "w") as f:
            f.write(f"# Daily Log — {today}\n\n## Summary\n{summary}\n\n## Completed\n")
            for t in done:
                f.write(f"- {t['text']}\n")
            f.write("\n## Still pending\n")
            for t in pending:
                f.write(f"- {t['text']}\n")
    except Exception as exc:
        print(f"[scheduler] daily log failed: {exc}", flush=True)
    _announce("end_of_day", summary)


_scheduler = scheduler_mod.BackgroundScheduler(
    config, memory,
    on_morning_briefing=_sched_briefing,
    on_end_of_day=_sched_end_of_day,
    on_calendar_alert=lambda msg: _announce("alert", msg),
    get_upcoming_events=lambda mins: scheduler_mod.upcoming_events_within(google, mins),
)
if getattr(config, "ENABLE_SCHEDULED_JOBS", True):
    _scheduler.start()


@app.get("/api/announcements")
def announcements(since: str | None = None):
    """Scheduled events the HUD hasn't shown yet. Pass the last id seen."""
    with _ann_lock:
        items = list(_announcements)
    if since:
        ids = [a["id"] for a in items]
        if since in ids:
            items = items[ids.index(since) + 1:]
    return {"announcements": items}


# ── Voice (ElevenLabs) ────────────────────────────────────────────────────

class SpeakRequest(BaseModel):
    text: str


@app.get("/api/voice")
def voice_status():
    """Whether the ElevenLabs voice is usable, plus remaining quota."""
    s = tts.status()
    s["quota"] = tts.subscription()
    return s


@app.post("/api/voice/speak")
def voice_speak(req: SpeakRequest):
    """MP3 for the given text. 204 means 'unavailable' — the front-end then
    falls back to the browser's built-in speech synthesis."""
    audio = tts.synthesize(req.text)
    if not audio:
        return Response(status_code=204)
    return Response(content=audio, media_type="audio/mpeg",
                    headers={"Cache-Control": "no-store"})


# ── Agent network ─────────────────────────────────────────────────────────

class DispatchRequest(BaseModel):
    request: str
    backend: str = "local"


@app.get("/api/agents")
def list_agents():
    """The specialist roster plus live per-agent status for the HUD graph."""
    return {"agents": agent_net.roster(), "activity": agent_net.activity()}


@app.get("/api/agents/activity")
def agents_activity():
    return agent_net.activity()


@app.post("/api/agents/dispatch")
def agents_dispatch(req: DispatchRequest):
    """Route a request to specialists, run them in parallel, synthesise."""
    try:
        return agent_net.dispatch(req.request, req.backend)
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ── Prayer times (Aladhan — free, no API key) ─────────────────────────────

_prayer = {"data": None, "day": None}
_prayer_lock = threading.Lock()
_PRAYER_ORDER = ["Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]


@app.get("/api/prayer")
def prayer():
    """Today's prayer times for the user's city, with the next one flagged.
    Cached per calendar day — the timings only change once a day."""
    today = datetime.now().date().isoformat()
    with _prayer_lock:
        cached = _prayer["data"] if _prayer["day"] == today else None

    if cached is None:
        try:
            r = requests.get(
                "https://api.aladhan.com/v1/timings",
                params={"latitude": 25.2048, "longitude": 55.2708, "method": 8},
                timeout=8, allow_redirects=True,
            )
            timings = r.json()["data"]["timings"]
            cached = [{"name": k, "time": timings[k][:5]} for k in _PRAYER_ORDER if k in timings]
            with _prayer_lock:
                _prayer["data"] = cached
                _prayer["day"] = today
        except Exception as exc:
            return {"available": False, "error": str(exc), "times": []}

    # Flag the next upcoming prayer so the widget can highlight it.
    now = datetime.now().strftime("%H:%M")
    next_name = next((p["name"] for p in cached if p["time"] > now), None)
    times = [{**p, "next": p["name"] == next_name} for p in cached]
    return {"available": True, "city": memory.get("city") or "Dubai", "times": times}


# ── Static front-end (production build) ───────────────────────────────────
# In dev the Vite server proxies /api here; in production FastAPI serves the
# built SPA. Mounted last so it never shadows /api routes.

_DIST = os.path.join(_HERE, "frontend", "dist")
if os.path.isdir(_DIST):
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="static")
