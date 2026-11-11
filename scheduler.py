"""Daily scheduler for Jarvis's automatic jobs.

Drives three time-based behaviours off the Tk event loop (``window.after``), so
every callback runs on the GUI thread:

  • Morning briefing — once a day at ``MORNING_BRIEFING_TIME``.
  • End-of-day summary — once a day at ``END_OF_DAY_TIME``.
  • Proactive calendar alerts — a toast a few minutes before each event.

The briefing and EOD callbacks are the same ones the launch flow and the
"good night jarvis" phrase already use; the scheduler just decides *when*. Each
day's briefing/EOD is guarded by a date stamp the callbacks write to memory
(``last_briefing_date`` / ``last_eod_date``), so a job runs at most once per
calendar day and never double-fires when the app is opened after its time.

Everything degrades quietly: if Google isn't connected, calendar alerts simply
don't fire; if a callback raises, the tick loop keeps going.
"""

import threading
from datetime import datetime, timedelta


def _parse_hhmm(value: str) -> tuple[int, int]:
    """Parse 'HH:MM' → (hour, minute); fall back to (0, 0) on garbage."""
    try:
        h, m = value.strip().split(":")
        h, m = int(h), int(m)
        if 0 <= h < 24 and 0 <= m < 60:
            return h, m
    except Exception:
        pass
    return 0, 0


class Scheduler:
    """Ticks on the Tk loop and fires daily jobs when their time arrives.

    The host wires in the callbacks so this module never imports the GUI:
      on_morning_briefing() — show the briefing (and stamp last_briefing_date)
      on_end_of_day()       — write the EOD summary (and stamp last_eod_date)
      on_calendar_alert(msg)— surface a short proactive toast
      get_upcoming_events(minutes) -> list[{id, summary, minutes_until}]
    """

    def __init__(self, window, config, memory, *,
                 on_morning_briefing=None,
                 on_end_of_day=None,
                 on_calendar_alert=None,
                 get_upcoming_events=None):
        self.window = window
        self.config = config
        self.memory = memory
        self.on_morning_briefing = on_morning_briefing
        self.on_end_of_day = on_end_of_day
        self.on_calendar_alert = on_calendar_alert
        self.get_upcoming_events = get_upcoming_events

        self._after_id = None
        self._alerted_event_ids: set[str] = set()
        self._alerted_day: str | None = None

    # ── Lifecycle ─────────────────────────────────────────────

    def start(self) -> None:
        self._tick()

    def stop(self) -> None:
        if self._after_id is not None:
            try:
                self.window.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _tick(self) -> None:
        try:
            self._check(datetime.now())
        except Exception:
            pass  # a bad tick must never kill the loop
        finally:
            interval_ms = max(15, int(getattr(self.config, "SCHEDULER_TICK_SECONDS", 60))) * 1000
            self._after_id = self.window.after(interval_ms, self._tick)

    # ── Core check ────────────────────────────────────────────

    def _check(self, now: datetime) -> None:
        if not getattr(self.config, "ENABLE_SCHEDULED_JOBS", True):
            return

        today = now.date().isoformat()

        # New day → forget which events we've already alerted on.
        if self._alerted_day != today:
            self._alerted_day = today
            self._alerted_event_ids.clear()

        # Morning briefing — fire once the configured time has passed today.
        if (getattr(self.config, "AUTO_MORNING_BRIEFING", True)
                and self.on_morning_briefing
                and self.memory.get("last_briefing_date") != today
                and self._time_reached(now, self.config.MORNING_BRIEFING_TIME)):
            self.on_morning_briefing()

        # End-of-day summary — fire once the configured time has passed today.
        if (getattr(self.config, "AUTO_END_OF_DAY", True)
                and self.on_end_of_day
                and self.memory.get("last_eod_date") != today
                and self._time_reached(now, self.config.END_OF_DAY_TIME)):
            self.on_end_of_day()

        # Proactive calendar alerts.
        if (getattr(self.config, "ENABLE_PROACTIVE_ALERTS", False)
                and self.on_calendar_alert and self.get_upcoming_events):
            self._check_calendar(now)

    def _time_reached(self, now: datetime, hhmm: str) -> bool:
        h, m = _parse_hhmm(hhmm)
        return (now.hour, now.minute) >= (h, m)

    def _check_calendar(self, now: datetime) -> None:
        window_min = int(getattr(self.config, "CALENDAR_ALERT_MINUTES", 10))
        try:
            events = self.get_upcoming_events(window_min) or []
        except Exception:
            return
        for ev in events:
            eid = ev.get("id")
            if not eid or eid in self._alerted_event_ids:
                continue
            self._alerted_event_ids.add(eid)
            mins = ev.get("minutes_until")
            summary = ev.get("summary", "an event")
            if mins is None or mins <= 0:
                when = "now"
            elif mins == 1:
                when = "in 1 minute"
            else:
                when = f"in {mins} minutes"
            self.on_calendar_alert(f"📅 {summary} — {when}.")


class BackgroundScheduler(Scheduler):
    """Thread-driven scheduler for the web API, which has no Tk event loop.

    Reuses Scheduler's decision logic (`_check`) verbatim — only the timing
    driver differs: a daemon thread instead of `window.after`. Callbacks run on
    that thread, so they must be thread-safe (the web callbacks just append to
    a queue the front-end polls).
    """

    def __init__(self, config, memory, **callbacks):
        super().__init__(None, config, memory, **callbacks)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="edith-scheduler")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def _loop(self) -> None:
        interval = max(15, int(getattr(self.config, "SCHEDULER_TICK_SECONDS", 60)))
        while not self._stop_event.is_set():
            try:
                self._check(datetime.now())
            except Exception as exc:  # a bad tick must never kill the loop
                print(f"[scheduler] tick failed: {exc}", flush=True)
            self._stop_event.wait(interval)


def upcoming_events_within(google, minutes: int) -> list[dict]:
    """Helper the host can pass as get_upcoming_events.

    Returns [{id, summary, minutes_until}] for events starting between now and
    ``minutes`` from now. Empty on any failure (Google not connected, etc.).
    """
    if not google.is_available():
        return []
    now = datetime.now().astimezone()
    horizon = now + timedelta(minutes=minutes)
    try:
        events = google.list_events(now.isoformat(), horizon.isoformat())
    except Exception:
        return []
    out = []
    for ev in events:
        start = ev.get("start", "")
        if "T" not in start:  # all-day event — no useful minute countdown
            continue
        try:
            start_dt = datetime.fromisoformat(start)
        except ValueError:
            continue
        if start_dt.tzinfo is None:
            start_dt = start_dt.astimezone()
        minutes_until = int((start_dt - now).total_seconds() // 60)
        if 0 <= minutes_until <= minutes:
            out.append({
                "id": ev.get("id"),
                "summary": ev.get("summary", "(no title)"),
                "minutes_until": minutes_until,
            })
    return out
