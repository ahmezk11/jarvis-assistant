import HudFrame from "../HudFrame";
import type { CalEvent } from "../../api";

function fmtTime(iso: string): string {
  if (!iso.includes("T")) return "ALL DAY";
  try {
    return new Intl.DateTimeFormat("en-GB", {
      timeZone: "Asia/Dubai",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}

export default function CalendarPanel({
  data,
  delay,
}: {
  data: { connected: boolean; events: CalEvent[] } | null;
  delay?: number;
}) {
  const events = data?.events ?? [];
  return (
    <HudFrame
      label="Schedule"
      delay={delay}
      live={!!data?.connected}
      right={<span className="mono text-[0.7rem] text-cyan">{events.length} TODAY</span>}
    >
      {!data?.connected ? (
        <p className="label text-ink-mute">calendar offline</p>
      ) : events.length === 0 ? (
        <p className="text-sm text-ink-dim">No events remaining today.</p>
      ) : (
        <ul className="space-y-2">
          {events.map((e) => (
            <li key={e.id} className="flex gap-3 border-l-2 border-cyan/50 pl-2.5">
              <span className="mono shrink-0 text-[0.7rem] text-cyan">{fmtTime(e.start)}</span>
              <span className="truncate text-sm text-ink">{e.summary}</span>
            </li>
          ))}
        </ul>
      )}
    </HudFrame>
  );
}
