import os
import re
import platform
import subprocess
import threading
import time
import requests
from datetime import datetime, timedelta

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False


# ── System stats ──────────────────────────────────────────────

def get_system_stats() -> dict:
    if not PSUTIL_AVAILABLE:
        return {"error": "psutil not installed"}
    cpu  = psutil.cpu_percent(interval=0.5)
    ram  = psutil.virtual_memory()
    result = {
        "cpu_pct":      cpu,
        "ram_pct":      ram.percent,
        "ram_used_gb":  round(ram.used  / 1024 ** 3, 1),
        "ram_total_gb": round(ram.total / 1024 ** 3, 1),
        "battery":      None,
        "uptime_str":   None,
    }
    if hasattr(psutil, "sensors_battery"):
        batt = psutil.sensors_battery()
        if batt:
            result["battery"] = {"pct": round(batt.percent), "charging": batt.power_plugged}
    secs = time.time() - psutil.boot_time()
    result["uptime_str"] = f"{int(secs // 3600)}h {int((secs % 3600) // 60)}m"
    return result


def format_system_stats(stats: dict) -> str:
    if "error" in stats:
        return stats["error"]
    batt = ""
    if stats["battery"]:
        b = stats["battery"]
        batt = f"  Battery: {b['pct']}% {'⚡' if b['charging'] else '🔋'}"
    return (
        f"CPU: {stats['cpu_pct']}%  "
        f"RAM: {stats['ram_used_gb']}/{stats['ram_total_gb']} GB ({stats['ram_pct']}%)"
        f"{batt}  Uptime: {stats['uptime_str']}"
    )


# ── Time ──────────────────────────────────────────────────────

def get_current_time() -> str:
    now = datetime.now()
    return now.strftime("%A, %B %-d, %Y at %-I:%M %p")


# ── Weather (wttr.in — no API key required) ───────────────────

def get_weather(city: str) -> dict | None:
    if not city:
        return None
    try:
        url  = f"https://wttr.in/{requests.utils.quote(city)}?format=j1"
        resp = requests.get(url, timeout=6)
        resp.raise_for_status()
        cur  = resp.json()["current_condition"][0]
        return {
            "desc":     cur["weatherDesc"][0]["value"],
            "temp_f":   cur["temp_F"],
            "temp_c":   cur["temp_C"],
            "feels_f":  cur["FeelsLikeF"],
            "feels_c":  cur["FeelsLikeC"],
            "humidity": cur["humidity"],
        }
    except Exception:
        return None


def format_weather(w: dict | None) -> str:
    if not w:
        return "Weather unavailable"
    return (
        f"{w['desc']}, {w['temp_c']}°C, "
        f"feels like {w['feels_c']}°C. Humidity: {w['humidity']}%."
    )


# ── News ──────────────────────────────────────────────────────

def get_news(category: str = "general", count: int = 3) -> list[str]:
    api_key = os.getenv("NEWS_API_KEY", "")
    if api_key:
        try:
            url  = (f"https://newsapi.org/v2/top-headlines"
                    f"?category={category}&language=en&pageSize={count}&apiKey={api_key}")
            data = requests.get(url, timeout=6).json()
            articles = data.get("articles", [])
            if articles:
                return [a["title"] for a in articles[:count]]
        except Exception:
            pass
    return _rss_headlines(count)


def _rss_headlines(count: int = 3) -> list[str]:
    try:
        import xml.etree.ElementTree as ET
        resp  = requests.get("https://feeds.bbcnews.com/news/rss.xml", timeout=6)
        root  = ET.fromstring(resp.content)
        items = root.findall(".//item")[:count]
        return [i.find("title").text for i in items if i.find("title") is not None]
    except Exception:
        return []


# ── Open app ──────────────────────────────────────────────────

def open_app(app_name: str) -> str:
    system = platform.system()
    try:
        if system == "Darwin":
            subprocess.Popen(["open", "-a", app_name])
        elif system == "Windows":
            subprocess.Popen(f'start "" "{app_name}"', shell=True)
        else:
            subprocess.Popen([app_name.lower()])
        return f"Opening {app_name}."
    except Exception as exc:
        return f"Could not open {app_name}: {exc}"


# ── Web search (Tavily, DuckDuckGo fallback) ──────────────────

def web_search(query: str, max_results: int = 5) -> list[dict]:
    """Returns list of {title, url, content} dicts. Empty list on failure."""
    api_key = os.getenv("TAVILY_API_KEY", "")
    if api_key:
        try:
            resp = requests.post(
                "https://api.tavily.com/search",
                json={
                    "api_key":      api_key,
                    "query":        query,
                    "max_results":  max_results,
                    "search_depth": "basic",
                },
                timeout=10,
            )
            resp.raise_for_status()
            results = resp.json().get("results", [])
            if results:
                return results
        except Exception:
            pass
    # Fallback: DuckDuckGo instant answers
    try:
        url  = (f"https://api.duckduckgo.com/?q={requests.utils.quote(query)}"
                f"&format=json&no_html=1&skip_disambig=1")
        data = requests.get(url, timeout=6).json()
        out  = []
        if data.get("AbstractText"):
            out.append({"title": query, "url": data.get("AbstractURL", ""),
                        "content": data["AbstractText"]})
        for r in data.get("RelatedTopics", [])[:4]:
            if isinstance(r, dict) and r.get("Text"):
                out.append({"title": r.get("Text", "")[:60], "url": r.get("FirstURL", ""),
                            "content": r["Text"]})
        return out[:max_results]
    except Exception:
        return []


def format_search_results(results: list[dict]) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        lines.append(f"[{i}] {r.get('title', 'Result')}")
        lines.append(f"    {r.get('content', '')[:400]}")
        if r.get("url"):
            lines.append(f"    Source: {r['url']}")
        lines.append("")
    return "\n".join(lines)


# ── Reminders ─────────────────────────────────────────────────

def set_reminder(message: str, minutes: int, on_fire) -> None:
    def _wait():
        time.sleep(minutes * 60)
        on_fire(f"Reminder: {message}")
    threading.Thread(target=_wait, daemon=True).start()


def parse_reminder_text(text: str) -> tuple[str | None, int | None]:
    m = re.search(r"remind me to (.+?) in (\d+) minutes?", text, re.IGNORECASE)
    if m:
        return m.group(1).strip(), int(m.group(2))
    return None, None


# ── Command detection ─────────────────────────────────────────

def detect_command(text: str) -> str | None:
    t = text.lower().strip()
    # ── Tasks ─────────────────────────────────────────────────
    if re.match(r"^(add (a )?(high|low|urgent|important|minor|priority)?\s*(priority\s+)?task[:\s]|add to (my )?list[:\s]|new task[:\s])", t):
        return "add_task"
    if any(p in t for p in ["my tasks", "show tasks", "list tasks", "to-do list",
                             "todo list", "what's on my list", "what do i need to do",
                             "my to do", "pending tasks"]):
        return "list_tasks"
    if re.search(r"\b(mark|complete|finish|done with)\b.{0,30}\btask\b", t) or \
       re.search(r"\btask\b.{0,30}\b(done|complete|finished)\b", t) or \
       re.match(r"^(complete|finish|done)\s+\d+", t):
        return "complete_task"
    if any(p in t for p in ["clear completed", "remove completed", "delete completed"]):
        return "clear_tasks"
    if any(p in t for p in ["what did i do today", "what have i done", "completed today",
                             "tasks done today"]):
        return "done_today"
    # ── Other ─────────────────────────────────────────────────
    if any(p in t for p in ["what's my day", "day looking", "my schedule", "my calendar"]):
        return "calendar"
    if any(p in t for p in ["any news", "headlines", "what's in the news", "news today"]):
        return "news"
    if any(p in t for p in ["how's the weather", "what's the weather", "weather today",
                             "weather like", "weather in", "how is the weather"]):
        return "weather"
    if re.search(r"remind me to .+ in \d+", t):
        return "reminder"
    if re.match(r"^open\s+.+", t):
        return "open_app"
    if any(p in t for p in ["how's the system", "system stats", "system status",
                             "how is the system", "check the system"]):
        return "system_stats"
    if any(p in t for p in ["good night edith", "good night jarvis", "good night", "shut down for the night"]):
        return "end_of_day"
    if any(p in t for p in ["what time", "current time", "what's the time",
                             "what day is", "what's today"]):
        return "time"
    if re.match(r"^(search (for|the web for|online for)?|look up|find out about|"
                r"research|what is the latest on|tell me about)\s+.+", t):
        return "web_search"
    return None
