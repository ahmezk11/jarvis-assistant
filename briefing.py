from datetime import datetime
import task_manager
import google_integration as google
from tools import (
    get_weather, format_weather,
    get_news,
    get_system_stats, format_system_stats,
)


def _fmt_event_time(iso: str) -> str:
    if "T" in iso:
        try:
            return datetime.fromisoformat(iso).strftime("%-I:%M %p")
        except ValueError:
            return iso
    return iso  # all-day event (date only)


def build_briefing(memory: dict, config) -> str:
    now  = datetime.now()
    hour = now.hour

    if hour < 12:
        greeting = "Good morning"
    elif hour < 17:
        greeting = "Good afternoon"
    else:
        greeting = "Good evening"

    name     = memory.get("preferred_name") or memory.get("user_name") or "Ahmed"
    day_str  = now.strftime("%A, %B %-d")
    time_str = now.strftime("%-I:%M %p")

    sections = [f"{greeting}, {name}. It is {day_str}. The time is {time_str}."]

    if config.ENABLE_WEATHER:
        city = memory.get("city")
        if city:
            w = get_weather(city)
            sections.append(f"Weather in {city}: {format_weather(w)}")
        else:
            sections.append("Tip: set your city in Settings for weather updates.")

    # System diagnostics are shown live in the HUD's System panel, so they're
    # intentionally left out of the spoken/briefed summary.

    # Real calendar + inbox when Google is connected; silently skipped otherwise
    # so the briefing never fabricates or crashes on an unavailable service.
    if google.is_available():
        try:
            n = google.unread_count()
            sections.append(f"Inbox: {n} unread email{'s' if n != 1 else ''}.")
        except Exception:
            pass
        try:
            start_iso = now.astimezone().isoformat()
            end_iso = now.replace(hour=23, minute=59, second=59).astimezone().isoformat()
            events = google.list_events(start_iso, end_iso)
            if events:
                lines = "\n".join(
                    f"  • {_fmt_event_time(e['start'])} — {e['summary']}"
                    + (f" @ {e['location']}" if e.get("location") else "")
                    for e in events
                )
                sections.append(f"Remaining events today:\n{lines}")
            else:
                sections.append("No more events on your calendar today.")
        except Exception:
            pass

    if config.ENABLE_NEWS:
        headlines = get_news(config.NEWS_CATEGORY, config.NEWS_COUNT)
        if headlines:
            lines = "\n".join(f"  • {h}" for h in headlines)
            sections.append(f"Today's headlines:\n{lines}")

    pending = task_manager.list_tasks()
    if pending:
        high = [t for t in pending if t.get("priority") == "high"]
        summary = f"You have {len(pending)} pending task{'s' if len(pending) != 1 else ''}"
        if high:
            summary += f", {len(high)} high priority"
        summary += ":\n" + task_manager.format_tasks(pending)
        sections.append(summary)

    sections.append("How may I assist you today?")
    return "\n\n".join(sections)
