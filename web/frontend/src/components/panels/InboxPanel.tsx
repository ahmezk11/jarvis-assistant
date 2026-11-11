import HudFrame from "../HudFrame";
import type { Email } from "../../api";

function cleanSender(s: string): string {
  const m = s.match(/^"?([^"<]+?)"?\s*</);
  return (m ? m[1] : s).trim();
}

export default function InboxPanel({
  data,
  delay,
}: {
  data: { connected: boolean; unread: number; emails: Email[] } | null;
  delay?: number;
}) {
  return (
    <HudFrame
      label="Inbox"
      delay={delay}
      live={!!data?.connected}
      right={
        <span className="mono text-[0.7rem] text-gold glow-gold">
          {data?.unread ?? 0} UNREAD
        </span>
      }
    >
      {!data?.connected ? (
        <p className="label text-ink-mute">gmail offline</p>
      ) : data.emails.length === 0 ? (
        <p className="text-sm text-ink-dim">Inbox clear.</p>
      ) : (
        <ul className="space-y-2">
          {data.emails.slice(0, 6).map((m) => (
            <li key={m.id} className="min-w-0">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate text-sm font-semibold text-ink">
                  {cleanSender(m.sender)}
                </span>
              </div>
              <div className="truncate text-[0.8rem] text-ink-dim">{m.subject}</div>
            </li>
          ))}
        </ul>
      )}
    </HudFrame>
  );
}
