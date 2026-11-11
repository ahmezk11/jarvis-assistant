import HudFrame from "../HudFrame";
import type { Prayer } from "../../api";

/** Minutes from now until an "HH:MM" time today (negative once it's passed). */
function minsUntil(hhmm: string): number {
  const [h, m] = hhmm.split(":").map(Number);
  const now = new Date();
  const t = new Date(now);
  t.setHours(h, m, 0, 0);
  return Math.round((t.getTime() - now.getTime()) / 60000);
}

function countdown(hhmm: string): string {
  const mins = minsUntil(hhmm);
  if (mins <= 0) return "now";
  const h = Math.floor(mins / 60);
  return h > 0 ? `in ${h}h ${mins % 60}m` : `in ${mins}m`;
}

export default function PrayerPanel({ data, delay }: { data: Prayer | null; delay?: number }) {
  const next = data?.times.find((t) => t.next);
  return (
    <HudFrame
      label="Prayer Times"
      delay={delay}
      live={!!data?.available}
      right={
        next ? (
          <span className="mono text-[0.62rem] text-gold glow-gold">
            {next.name.toUpperCase()} {countdown(next.time)}
          </span>
        ) : undefined
      }
    >
      {!data?.available ? (
        <p className="label text-ink-mute">unavailable</p>
      ) : (
        <ul className="grid grid-cols-3 gap-x-3 gap-y-2">
          {data.times.map((t) => (
            <li key={t.name} className="flex flex-col">
              <span
                className="label text-[0.55rem]"
                style={{ color: t.next ? "#ffb020" : undefined }}
              >
                {t.name}
              </span>
              <span
                className="mono text-sm"
                style={
                  t.next
                    ? { color: "#ffb020", textShadow: "0 0 8px rgba(255,176,32,.6)" }
                    : { color: minsUntil(t.time) < 0 ? "#3f5c6a" : "#cfeaf5" }
                }
              >
                {t.time}
              </span>
            </li>
          ))}
        </ul>
      )}
    </HudFrame>
  );
}
