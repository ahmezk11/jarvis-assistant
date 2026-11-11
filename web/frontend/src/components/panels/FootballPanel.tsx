import HudFrame from "../HudFrame";
import type { Competition, Football, Match } from "../../api";

function stateColor(s: string): string {
  if (s === "live") return "#ff3b5c";
  if (s === "finished") return "#7398aa";
  return "#38e1ff"; // upcoming
}

function Row({ m }: { m: Match }) {
  const c = stateColor(m.state);
  return (
    <li className="flex items-center gap-2 text-sm">
      <span
        className={`h-1.5 w-1.5 shrink-0 rounded-full ${m.state === "live" ? "animate-core" : ""}`}
        style={{ background: c, boxShadow: m.state === "live" ? `0 0 8px ${c}` : "none" }}
      />
      <span className="min-w-0 flex-1 truncate text-ink">
        {m.home} <span className="text-ink-mute">v</span> {m.away}
      </span>
      <span className="mono shrink-0 text-[0.72rem]" style={{ color: c }}>
        {m.state === "live" ? "LIVE" : m.detail}
      </span>
    </li>
  );
}

function Section({ title, comp }: { title: string; comp?: Competition }) {
  if (!comp) return null;
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between">
        <span className="label text-cyan-bright">{title}</span>
        <span className="mono text-[0.62rem] text-ink-dim">{comp.status}</span>
      </div>
      {comp.matches.length === 0 ? (
        <p className="text-sm text-ink-dim">No fixtures.</p>
      ) : (
        <ul className="space-y-1">
          {comp.matches.slice(0, 5).map((m, i) => (
            <Row key={i} m={m} />
          ))}
        </ul>
      )}
    </div>
  );
}

export default function FootballPanel({
  data,
  loading,
  error,
  delay,
}: {
  data: Football | null;
  loading: boolean;
  error?: string | null;
  delay?: number;
}) {
  const emptyMsg = error ? "feed unavailable" : loading ? "acquiring feed…" : "no data";
  return (
    <HudFrame label="Football" delay={delay} right={<span className="mono text-[0.62rem] text-ink-dim">GST</span>}>
      {!data ? (
        <p className="label text-ink-mute">{emptyMsg}</p>
      ) : (
        <Section title="Premier League" comp={data.premier_league} />
      )}
    </HudFrame>
  );
}
