# EDITH — Personal AI Assistant

A personal-assistant app for Ahmed. EDITH manages your day, triages your
inbox, tracks your tasks, and keeps you informed — from a dark-themed Tkinter GUI
with voice, a "Hey Edith" wake word, and session history.

The brain is the **Claude API** with real tool use: Claude decides when to check
the weather, read your calendar, draft an email, and so on. A local **Ollama** mode
is available as an offline fallback (plain chat, no tools).

Two front-ends share this one backend:
- **Desktop** — the Tkinter app (`jarvis.py`), described below.
- **Web HUD** — an Iron Man-style browser command centre in [`web/`](web/):
  arc-reactor core, live chat, and panels for weather / calendar / inbox / tasks,
  served by a thin FastAPI bridge over the same modules. Run it with
  `python3 -m uvicorn web.api:app --port 8000` and open http://localhost:8000
  (see [web/README.md](web/README.md)).

---

## Architecture

| Layer | Component | What it does |
|-------|-----------|--------------|
| GUI | `jarvis.py` | Tkinter app — chat, sidebar history, voice, wake word, system panel |
| Brain (cloud) | `claude_client.py` | Claude API + manual tool-use loop |
| Brain (offline) | Ollama | Optional local LLM, plain chat, no tools |
| Identity | `memory_manager.py` | System prompt (voice/rules) built from this repo's `CLAUDE.md` |
| Tools | `agent_tools.py` | Claude tool schemas + dispatcher |
| Local tools | `tools.py`, `task_manager.py` | Weather, news, web search, reminders, system stats, tasks |
| Integrations | `google_integration.py`, `notion_integration.py` | Gmail, Calendar, Drive, Notion |
| Proactive | `briefing.py` | Morning briefing; inbox triage & draft flows in the GUI |

Side-effectful actions (send email, create/delete calendar event, write to Drive or
Notion) always pop a confirmation dialog first. If an integration isn't connected,
EDITH says so — she never fabricates data.

---

## Quick Start

```bash
cd ~/Desktop/coding\ projects/my-ai-chatbot
pip3 install -r requirements.txt          # optional integration/voice deps included
cp .env.example .env                       # then add your keys
python3 jarvis.py
```

At minimum, set `ANTHROPIC_API_KEY` in `.env` to use the Claude brain. Everything
else is optional and enables more tools as you add it.

---

## Built-in flows

| Trigger | What it does |
|---------|--------------|
| On launch | Morning briefing — weather, calendar, unread email, tasks, news |
| Daily timer | Auto morning briefing + end-of-day summary + calendar alerts (see below) |
| 📥 button | Inbox triage — sorts unread mail into URGENT / ACTION / FYI / SKIP |
| ✍️ button | Draft an email in Ahmed's voice (saved as a Gmail draft) |
| "good night Edith" | End-of-day summary, saved to `daily_log/YYYY-MM-DD.md` |
| 🎤 / "Hey Edith" | Voice input |

### Scheduled jobs

While the app is open, a daily scheduler (`scheduler.py`) fires three things,
each at most once per calendar day and all configurable in `config.py`:

| Job | Fires | Config |
|-----|-------|--------|
| Morning briefing | at `MORNING_BRIEFING_TIME` (default 08:00) | `AUTO_MORNING_BRIEFING` |
| End-of-day summary | at `END_OF_DAY_TIME` (default 22:00) | `AUTO_END_OF_DAY` |
| Calendar alerts | `CALENDAR_ALERT_MINUTES` before each event | `ENABLE_PROACTIVE_ALERTS` |

Set `ENABLE_SCHEDULED_JOBS = False` to turn the whole scheduler off. Calendar
alerts stay idle until Google Calendar is connected — nothing fabricated.

Triage and draft use Claude's Gmail tools, so they need Claude (cloud) mode and a
connected Gmail account; the briefing falls back to weather/tasks/news when Google
isn't connected.

---

## Configuration (`.env`)

| Key | Enables |
|-----|---------|
| `ANTHROPIC_API_KEY` | The Claude (cloud) brain + all tool use |
| `GOOGLE_CALENDAR_CREDENTIALS` | Gmail, Calendar, Drive (path to OAuth client-secrets JSON) |
| `NOTION_TOKEN` | Notion (internal integration token) |
| `TAVILY_API_KEY` | Better web search (else DuckDuckGo fallback) |
| `NEWS_API_KEY` | NewsAPI headlines (else BBC RSS fallback) |

### Google (Gmail / Calendar / Drive)

1. In [Google Cloud Console](https://console.cloud.google.com), create a project and
   enable the Gmail, Calendar, and Drive APIs.
2. Credentials → Create OAuth 2.0 Client ID → **Desktop app** → download the JSON.
3. Point `GOOGLE_CALENDAR_CREDENTIALS` at that file. First use opens a browser for
   consent once; a refresh token is then cached in `token.json`.

Google Tasks is intentionally **not** wired up — EDITH uses her own local task list
(`task_manager.py`) to avoid two competing to-do lists.

### Notion

1. Create an internal integration at [notion.so/my-integrations](https://www.notion.so/my-integrations).
2. Share the pages/databases you want EDITH to reach with the integration.
3. Put the token in `NOTION_TOKEN`.

---

## File structure

```
jarvis.py               Main Tkinter app
claude_client.py        Claude API backend + tool-use loop
agent_tools.py          Tool schemas + dispatcher (local + integrations)
tools.py                Weather, news, web search, reminders, system stats
task_manager.py         Local JSON task list
google_integration.py   Gmail / Calendar / Drive (local OAuth)
notion_integration.py   Notion (integration token)
briefing.py             Morning briefing
scheduler.py            Daily jobs — auto briefing, EOD, calendar alerts
memory_manager.py       Persistent memory + system prompt
voice_manager.py        TTS, speech-to-text, wake word
config.py               Feature flags & settings
CLAUDE.md               EDITH identity, voice, and rules
daily_log/              End-of-day markdown summaries
chat_history/           Saved sessions
chatbot.py              Deprecated original CLI prototype
```
