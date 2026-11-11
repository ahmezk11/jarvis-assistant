import { useState } from "react";
import HudFrame from "../HudFrame";
import { api, type Task } from "../../api";

const PRIORITY_COLOR: Record<string, string> = {
  high: "#ff3b5c",
  normal: "#38e1ff",
  low: "#2b7d94",
};

export default function TasksPanel({
  data,
  reload,
  delay,
}: {
  data: { tasks: Task[]; pending: number } | null;
  reload: () => void;
  delay?: number;
}) {
  const [text, setText] = useState("");
  const pending = (data?.tasks ?? []).filter((t) => !t.done);

  const add = async () => {
    const v = text.trim();
    if (!v) return;
    setText("");
    await api.addTask(v);
    reload();
  };

  return (
    <HudFrame
      label="Directives"
      delay={delay}
      right={<span className="mono text-[0.7rem] text-cyan">{pending.length} ACTIVE</span>}
    >
      <div className="flex min-h-0 flex-col gap-2">
        <ul className="min-h-0 flex-1 space-y-1.5 overflow-auto">
          {pending.length === 0 ? (
            <li className="text-sm text-ink-dim">No active directives.</li>
          ) : (
            pending.map((t) => (
              <li key={t.id} className="group flex items-center gap-2">
                <button
                  onClick={async () => {
                    await api.completeTask(t.id);
                    reload();
                  }}
                  title="Mark complete"
                  className="grid h-4 w-4 shrink-0 place-items-center rounded-full border transition"
                  style={{ borderColor: PRIORITY_COLOR[t.priority] }}
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full opacity-0 transition group-hover:opacity-100"
                    style={{ background: PRIORITY_COLOR[t.priority] }}
                  />
                </button>
                <span className="flex-1 truncate text-sm text-ink">{t.text}</span>
              </li>
            ))
          )}
        </ul>
        <div className="flex items-center gap-2 border-t border-[var(--edge)] pt-2">
          <input
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && add()}
            placeholder="add directive…"
            className="mono flex-1 bg-transparent text-sm text-ink placeholder:text-ink-mute focus:outline-none"
          />
          <button onClick={add} className="label text-cyan hover:glow-cyan">
            +ADD
          </button>
        </div>
      </div>
    </HudFrame>
  );
}
